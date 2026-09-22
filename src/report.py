"""Static HTML report builder: top signals, emergence timeline, method notes.

Usage:
    from src.report import build_report
    build_report(scored, emergence, drug, out_path="report.html",
                 stats=client.stats())
"""

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def timeline_png(scored: dict, terms: list, title: str) -> str:
    """Matplotlib line chart of PRR lower-95%-CI over windows -> base64 PNG."""
    labels = list(scored.keys())
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(10, 4))
    for term in terms:
        ys = []
        for lab in labels:
            df = scored[lab]
            hit = df[df["term"] == term]
            ys.append(hit.iloc[0]["prr_lo"] if len(hit) else float("nan"))
        ax.plot(list(x), ys, marker="o", linewidth=1.5, label=term)
    ax.axhline(1.0, color="red", linestyle="--", linewidth=1,
               label="signal threshold (PRR lower CI = 1)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("PRR lower 95% CI bound")
    ax.set_title(title)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _df_table(df: pd.DataFrame, cols: list, max_rows: int = 25) -> str:
    sub = df[cols].head(max_rows).copy()
    return sub.to_html(index=False, classes="tbl", float_format="%.3f",
                       border=0)


def build_report(scored: dict, emergence: pd.DataFrame, drug: str,
                 out_path: str, stats: dict = None,
                 notes: str = "") -> str:
    labels = list(scored.keys())
    latest = scored[labels[-1]]
    top_chart_terms = latest.head(6)["term"].tolist()
    chart_b64 = timeline_png(
        scored, top_chart_terms,
        f"PRR lower 95% CI over time — {drug} (top 6 by latest PRR)")

    top_cols = ["term", "a_raw", "prr", "prr_lo", "prr_hi",
                "ror", "chi2", "is_signal"]
    emerg_cols = ["term", "emergence_window", "windows_since_first_seen",
                  "consecutive_hot_windows", "prr_at_emergence",
                  "prr_latest", "prr_growth", "reports_latest_window"]

    stats_html = ""
    if stats:
        stats_html = ("<ul>" + "".join(
            f"<li><b>{k}</b>: {v}</li>" for k, v in stats.items()) + "</ul>")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>FDA Signal Watch — {drug}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 1080px; margin: 2em auto;
       padding: 0 1em; color: #1a1a1a; }}
h1, h2 {{ color: #0b3d62; }}
.tbl {{ border-collapse: collapse; width: 100%; font-size: 0.85em; }}
.tbl th, .tbl td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: right; }}
.tbl th {{ background: #eef4fa; }} .tbl td:first-child {{ text-align: left; }}
.note {{ background: #fff8e1; border-left: 4px solid #f5b301; padding: 0.6em 1em; }}
code {{ background: #f4f4f4; padding: 1px 5px; border-radius: 3px; }}
img {{ max-width: 100%; }}
</style></head><body>
<h1>FDA Signal Watch — {drug}</h1>
<p>Streaming pharmacovigilance: disproportionality statistics (PRR/ROR with 95%
CIs) computed per time window, with <b>signal-emergence tracking</b> — detection
of the window in which a drug↔reaction pair first crosses the significance
threshold and holds it. Latest window: <b>{labels[-1]}</b>;
{len(labels)} windows analysed.</p>

<h2>Emergence timeline (PRR lower 95% CI)</h2>
<img src="data:image/png;base64,{chart_b64}" alt="emergence timeline chart">
<div class="note">A pair is "hot" when its PRR lower-95%-CI bound &gt; 1
(elevated vs background). Emergence = first window of a run of ≥2 consecutive
hot windows. This is a statistical flag, <b>not</b> proof of causation.</div>

<h2>Emerging signals (ordered by latest PRR)</h2>
{_df_table(emergence, emerg_cols) if len(emergence) else "<p>No emergent signals under current rule.</p>"}

<h2>Top disproportionality scores — {labels[-1]}</h2>
{_df_table(latest, top_cols)}

<h2>Method notes</h2>
<ul>
<li>Contingency tables per window: a = drug+reaction+ reports, b = drug+reaction−,
c = drug−reaction+, d = drug−reaction−. Background = all FAERS reports in window.</li>
<li>PRR with 95% CI on the log scale; ROR with 95% CI; χ² with Yates correction;
Haldane 0.5 correction for zero cells.</li>
<li>Classical signal rule (Evans 2001): PRR ≥ 2, χ² ≥ 4, ≥ 3 reports.</li>
<li>Emergence rule: PRR lower CI &gt; 1 for ≥ 2 consecutive windows.</li>
<li>All API results cached as parquet in <code>data/cache/</code> keyed by
query+date range; re-runs hit cache first (quota-safe).</li>
{("<li>" + notes + "</li>") if notes else ""}
</ul>

<h2>Run stats</h2>
{stats_html or "<p>n/a</p>"}
<p><small>Data source: FDA Adverse Event Reporting System (FAERS) via the
<a href="https://open.fda.gov/apis/drug/event/">openFDA Drug Adverse Event API</a>.
openFDA data are public and do not include patient identifiers.
<a href="https://www.fda.gov/drugs/fdas-adverse-event-reporting-system-faers">
FAERS</a> is a spontaneous-report system: reporting biases apply.</small></p>
</body></html>"""
    Path = __import__("pathlib").Path
    Path(out_path).write_text(html)
    return out_path
