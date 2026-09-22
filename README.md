# fda-signal-watch

Streaming pharmacovigilance early-warning on FDA FAERS data via the openFDA API.

## What it does

Instead of producing one static disproportionality table, `fda-signal-watch`
scores every (drug, adverse-reaction) pair **per time window** (quarterly) and
tracks **signal emergence**: the moment a pair's statistic crosses a
significance threshold and stays elevated. That turns PRR/ROR from a static
snapshot into a time series of early-warning flags.

Pipeline:

1. **Quota-aware client** (`src/client.py`) — every API call goes through a
   parquet cache keyed by query + date range (`data/cache/`, gitignored).
   Re-runs hit cache first. Polite rate limiting, HTTP 404 treated as "zero
   matches" (not an error), and a hard per-run request cap.
2. **Windowing** (`src/signals.py`) — count aggregations per quarter for the
   target drug plus a background comparator (all FAERS reports in the window).
3. **Disproportionality** (`src/disproportionality.py`) — PRR and ROR with 95%
   CIs (log scale), Yates-corrected χ², Haldane correction, classic Evans rule
   (PRR ≥ 2, χ² ≥ 4, ≥ 3 reports).
4. **Emergence tracking** — a pair is "hot" when its PRR lower-95%-CI bound > 1;
   emergence = first window of ≥ 2 consecutive hot windows. Records emergence
   window, latency since first seen, and PRR growth.
5. **Report** (`src/report.py`) — static `report.html` with top signals,
   an emergence-timeline chart (matplotlib PNG embedded), and method notes.

## Quickstart

```bash
pip install -r requirements.txt

# Smoke run: aspirin, 6 quarterly windows (~24 API calls, then cached)
python run_smoke.py
# open report.html

# More windows (watch your quota!)
SMOKE_WINDOWS=12 python run_smoke.py
SMOKE_DRUG=ibuprofen python run_smoke.py

# Stretch: interactive dashboard
streamlit run streamlit/app.py   # streamlit optional, not in requirements
```

## Quota notes (important)

- Anonymous openFDA quota: **1,000 requests/day**, 240/min. With a free key
  (`OPENFDA_API_KEY` env var, register at https://open.fda.gov/apis/authentication/)
  the daily quota rises to **120,000**.
- This repo is designed to sip quota: it uses **count aggregations** (a handful
  of calls per window) instead of paginating raw reports, and **caches
  everything** to `data/cache/`. Re-runs make zero API calls.
- `max_requests_per_run` caps each run (default 60 in the smoke script);
  `SMOKE_MAX_REQ` overrides it.

## Data source

FDA Adverse Event Reporting System (FAERS) via the
[openFDA Drug Adverse Event API](https://open.fda.gov/apis/drug/event/).
FAERS is a spontaneous-reporting system — reports reflect reporting behavior,
not proven causation. Disproportionality flags are statistical hypotheses, not
safety conclusions.

## Layout

```
src/client.py            quota-aware openFDA client (parquet cache)
src/cache.py             cache listing / stale-entry cleanup
src/disproportionality.py  PRR/ROR/χ² with 95% CIs, 2x2 tables
src/signals.py           windowing, per-window scoring, emergence tracking
src/report.py            static HTML report + timeline chart
run_smoke.py             end-to-end smoke run (aspirin)
streamlit/app.py         stretch: interactive dashboard
report.html              demo output (aspirin smoke run)
BUILD-NOTES.md           build/observed numbers/quota/pending items
```

## Disclaimer

Research/educational demo only. Not medical advice; not a validated safety
surveillance tool.
