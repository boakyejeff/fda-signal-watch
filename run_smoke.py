"""Smoke run: aspirin, a small window set, count aggregations only.

Quota budget: per window -> 2 count calls (drug reactions + background
reactions) + 2 total-report calls (limit=1). With N windows that's 4N calls.
Default N=6 -> 24 API calls, then everything is cached in data/cache/.

Set env SMOKE_WINDOWS=N for more windows, or run twice to demo cache reuse.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.client import OpenFDAClient
from src.report import build_report
from src.signals import collect_window, quarterly_windows, score_windows, track_emergence

DRUG = os.environ.get("SMOKE_DRUG", "aspirin")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    n_windows = int(os.environ.get("SMOKE_WINDOWS", "6"))
    max_req = int(os.environ.get("SMOKE_MAX_REQ", "60"))
    windows = quarterly_windows(2024, 2026)[:n_windows]
    print(f"drug={DRUG} windows={[w[0] for w in windows]} "
          f"max_requests_per_run={max_req}")

    client = OpenFDAClient(max_requests_per_run=max_req)
    data = collect_window(client, DRUG, windows, reaction_limit=100)
    for w in data:
        top = w["drug_rx"].head(5)
        print(f"  [{w['label']}] drug_reports={w['n_drug']:,} "
              f"bg_reports={w['n_bg']:,} "
              f"top_reactions={list(top['term'])[:3]}")

    scored = score_windows(data)
    latest = scored[windows[-1][0]]
    print(f"\nLatest window {windows[-1][0]}: top-5 rows")
    print(latest[["term", "a_raw", "prr", "prr_lo", "ror", "chi2",
                  "is_signal"]].head(5).to_string(index=False))

    emergence = track_emergence(scored, min_consecutive=2)
    print(f"\nEmerging signals: {len(emergence)}")
    if len(emergence):
        print(emergence.to_string(index=False))

    out = build_report(
        scored, emergence, DRUG,
        out_path=os.path.join(REPO_DIR, "report.html"),
        stats=client.stats(),
        notes="Smoke run: quarterly windows, top-100 reactions per window "
              "via count aggregations (no raw-report pagination).")
    print(f"\nreport -> {out}")
    print(f"client stats: {client.stats()}")


if __name__ == "__main__":
    main()
