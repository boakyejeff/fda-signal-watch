"""Signal-emergence tracking: the novel angle of this project.

Instead of one static PRR table, we score each (drug, reaction) pair in a
sequence of time windows and watch for *emergence*: the moment a pair's
statistic crosses a significance threshold and stays there.

Emergence rule (configurable):
  - lower CI bound of PRR > 1 (statistically elevated), OR prr >= 2 & chi2 >= 4
  - held for >= min_consecutive windows
We then record: emergence window (date), latency (windows since first seen),
and growth (PRR slope since emergence).
"""

import numpy as np
import pandas as pd

from .disproportionality import build_contingency, score_window


def collect_window(client, drug: str, windows: list,
                   reaction_limit: int = 100, bg_limit: int = 500,
                   count_field: str = "patient.reaction.reactionmeddrapt.exact"):
    """Pull reaction counts for target drug and background per time window.

    Quota budget per window: 2 count calls + 2 total-report calls.
    The background aggregation uses bg_limit=500 (openFDA requires an API key
    for limit=1000 on aggregations) so that the drug's top-N reactions are
    (almost) always present in the background table — otherwise missing
    background counts would inflate PRR. Drug reactions with no background
    entry get NaN stats (dropped from scoring).
    windows: list of (label, date_from, date_to) tuples, dates 'YYYYMMDD'.
    """
    drug_search = f"patient.drug.medicinalproduct:{drug}"
    out = []
    for label, dfrom, dto in windows:
        drug_rx = client.count(drug_search, count_field,
                               date_from=dfrom, date_to=dto,
                               limit=reaction_limit)
        bg_rx = client.count("", count_field,  # "" = all reports in window
                             date_from=dfrom, date_to=dto,
                             limit=bg_limit)
        n_drug = client.total_reports(drug_search, date_from=dfrom, date_to=dto)
        n_bg = client.total_reports("", date_from=dfrom, date_to=dto)
        out.append({
            "label": label, "drug_rx": drug_rx, "bg_rx": bg_rx,
            "n_drug": n_drug, "n_bg": n_bg,
        })
    return out


def score_windows(window_data: list) -> dict:
    """Score every window -> {label: scored DataFrame}."""
    scored = {}
    for w in window_data:
        cont = build_contingency(w["drug_rx"], w["bg_rx"],
                                 w["n_drug"], w["n_bg"])
        scored[w["label"]] = score_window(cont)
    return scored


def track_emergence(scored: dict, min_consecutive: int = 2,
                    use_ci: bool = True) -> pd.DataFrame:
    """Detect emergence across ordered windows.

    scored: ordered {label: scored DataFrame}.
    Returns rows: term, emergence_label, windows_since_first_seen, prr_at_emergence,
    prr_latest, prr_growth (latest/emergence), consecutive_windows.
    """
    labels = list(scored.keys())
    terms = set()
    for df in scored.values():
        terms.update(df["term"])

    def hot(df_row):
        if use_ci:
            return df_row["prr_lo"] > 1.0
        return bool(df_row["is_signal"])

    records = []
    for term in sorted(terms):
        series = []
        for lab in labels:
            df = scored[lab]
            hit = df[df["term"] == term]
            series.append(hot(hit.iloc[0]) if len(hit) else False)
        # first-seen window (any reports at all)
        first_seen = next(
            (i for i, lab in enumerate(labels)
             if term in set(scored[lab]["term"])), None)
        # longest trailing run of hot windows ending at the last window
        run = 0
        for s in reversed(series):
            if s:
                run += 1
            else:
                break
        if run >= min_consecutive and first_seen is not None:
            emerg_idx = len(labels) - run
            emerg_lab = labels[emerg_idx]
            e_row = scored[emerg_lab].query("term == @term").iloc[0]
            l_row = scored[labels[-1]].query("term == @term").iloc[0]
            records.append({
                "term": term,
                "emergence_window": emerg_lab,
                "windows_since_first_seen": emerg_idx - first_seen,
                "consecutive_hot_windows": run,
                "prr_at_emergence": round(e_row["prr"], 3),
                "prr_latest": round(l_row["prr"], 3),
                "prr_growth": round(l_row["prr"] / max(e_row["prr"], 1e-9), 3),
                "reports_latest_window": int(l_row["a_raw"]),
            })
    out = pd.DataFrame(records)
    if len(out):
        out = out.sort_values("prr_latest", ascending=False).reset_index(drop=True)
    return out


def quarterly_windows(start_year=2015, end_year=2026):
    """[(label, yyyymmdd_from, yyyymmdd_to)] quarterly windows."""
    wins = []
    for y in range(start_year, end_year + 1):
        for q, (m1, m2) in enumerate(
                [(1, 3), (4, 6), (7, 9), (10, 12)], start=1):
            wins.append((f"{y}-Q{q}", f"{y}{m1:02d}01", f"{y}{m2:02d}28"))
    return wins
