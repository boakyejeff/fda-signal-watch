"""Disproportionality statistics for (drug, reaction) signal detection.

For each 2x2 contingency table

               Reaction+   Reaction-
    Drug+         a           b
    Drug-         c           d

we compute:
  PRR = [a/(a+b)] / [c/(c+d)]
  ROR = (a*d) / (b*c)
  chi-square (with Yates continuity correction)
  95% confidence intervals on the log scale (Evans et al. style):
      SE(log PRR) = sqrt(1/a - 1/(a+b) + 1/c - 1/(c+d))
      SE(log ROR) = sqrt(1/a + 1/b + 1/c + 1/d)

Standard signal-of-interest criteria (Evans 2001 / EMA): PRR >= 2,
chi2 >= 4, and at least 3 reports (a >= 3).
"""

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency


def contingency_stats(a, b, c, d):
    """All statistics for one 2x2 table. Returns a dict."""
    a, b, c, d = (max(float(x), 0.5) for x in (a, b, c, d))  # Haldane correction
    prr = (a / (a + b)) / (c / (c + d))
    ror = (a * d) / (b * c)
    se_prr = np.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    se_ror = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    prr_lo, prr_hi = np.exp(np.log(prr) + np.array([-1.96, 1.96]) * se_prr)
    ror_lo, ror_hi = np.exp(np.log(ror) + np.array([-1.96, 1.96]) * se_ror)
    table = np.array([[a, b], [c, d]])
    try:
        chi2, p, _, _ = chi2_contingency(table, correction=True)
    except ValueError:
        chi2, p = np.nan, np.nan
    return {
        "prr": prr, "prr_lo": prr_lo, "prr_hi": prr_hi,
        "ror": ror, "ror_lo": ror_lo, "ror_hi": ror_hi,
        "chi2": chi2, "p_value": p,
    }


def build_contingency(drug_reactions: pd.DataFrame,
                      background_reactions: pd.DataFrame,
                      n_drug: int, n_background: int) -> pd.DataFrame:
    """Merge drug-specific and background reaction counts into one table.

    drug_reactions / background_reactions: DataFrames with [term, count].
    n_drug / n_background: total report counts in each stratum.
    """
    d = drug_reactions.rename(columns={"count": "a"})
    bg = background_reactions.rename(columns={"count": "c"})
    m = d.merge(bg, on="term", how="outer")
    # Drug reactions absent from the background aggregation (truncated below
    # its limit) cannot be scored honestly — drop them instead of letting
    # a zero-background cell inflate PRR into the thousands.
    m = m.dropna(subset=["a", "c"])
    m["a_raw"] = m["a"].astype(int)
    m["b"] = n_drug - m["a"]
    m["d"] = n_background - m["c"]
    return m


def score_window(contingency: pd.DataFrame) -> pd.DataFrame:
    """Add PRR/ROR/chi2 columns to a contingency table DataFrame."""
    stats = [contingency_stats(r.a, r.b, r.c, r.d)
             for r in contingency.itertuples()]
    s = pd.DataFrame(stats)
    out = pd.concat([contingency.reset_index(drop=True), s], axis=1)
    out["is_signal"] = (
        (out["prr"] >= 2.0) & (out["chi2"] >= 4.0) & (out["a_raw"] >= 3)
    )
    return out.sort_values("prr", ascending=False).reset_index(drop=True)
