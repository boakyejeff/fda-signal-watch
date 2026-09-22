# BUILD NOTES — fda-signal-watch (repo 2 of 4)

Built 2026-09-22. Original code; no dataset download (live openFDA API).

## What was built
- `src/client.py` — quota-aware openFDA client: parquet cache keyed by
  query+date range, cache-first, polite rate limiting (1s anon / 0.25s w/ key),
  HTTP 404 → empty result, `max_requests_per_run` hard cap, `OPENFDA_API_KEY`
  env var. **Key quirk found:** the search string must contain literal `+AND+`
  and literal `[`/`]`; `urllib.parse.urlencode` encodes them and openFDA
  returns HTTP 500. The client now builds the query string manually.
- `src/cache.py` — cache listing / stale-entry cleanup.
- `src/disproportionality.py` — PRR/ROR with 95% CIs (log scale), Yates χ²,
  Haldane 0.5 correction, Evans rule (PRR≥2, χ²≥4, ≥3 reports).
- `src/signals.py` — quarterly windowing, per-window scoring, emergence
  tracking (hot = PRR lower CI > 1; emergence = first of ≥2 consecutive hot
  windows; records emergence window, latency, PRR growth).
- `src/report.py` — static HTML report with embedded matplotlib timeline PNG.
- `run_smoke.py` — end-to-end smoke run. `streamlit/app.py` — stretch dashboard.

## Smoke run — real observed numbers (aspirin, 2024-Q1 → 2025-Q2, 6 windows)
- Per-window report volumes: drug ~7,358–7,951 reports; background
  ~318,431–327,800 reports per quarter.
- Top drug reactions per window (live): FATIGUE, OFF LABEL USE, DIARRHOEA,
  DYSPNOEA, NAUSEA — consistent with staging report (FATIGUE ~38k all-time).
- Latest window (2025-Q2) top disproportionality rows:
  - HOT FLUSH: n=265, PRR 5.29 (95% CI 4.66–6.00), ROR 5.44, χ² 817
  - GASTROINTESTINAL HAEMORRHAGE: n=81, PRR 5.04 (4.01–6.35), χ² 230
  - OEDEMA PERIPHERAL: n=136, PRR 4.90, χ² 375
- Emergence tracking: **70 pairs** emergent under the rule; e.g. HOT FLUSH
  emerged 2024-Q3 (PRR 2.77 → 5.29, growth ×1.91, 4 consecutive hot windows);
  GASTROINTESTINAL HAEMORRHAGE emerged 2024-Q4.
- **Methodology lesson learned:** background aggregation must use a large
  limit (500) or missing background cells inflate PRR into the thousands.
  Drug reactions absent from the background top-N are dropped from scoring
  rather than zero-filled.

## Quota consumed
- Run 1 (buggy bg limit=100, then fixed): 12 requests, then 12 more for the
  limit=500 background aggregations (old orphans cleaned from cache).
- Total this session: **~30 requests** (incl. ~6 manual URL-form probes during
  debugging), all anonymous. Cache now holds 24 entries; re-runs make **0
  API calls**. Well under the 1,000/day anonymous quota.
- Note: openFDA returns **403 API_KEY_MISSING for count limit=1000** on
  aggregations — anonymous max is effectively 500 per aggregation call.
  Documented in README.

## Outputs
- `report.html` (119 KB, committed as demo artifact) — top signals,
  emergence timeline chart, method notes.
- `data/cache/` — 24 parquet+meta pairs (gitignored).

## Pending / stretch
- `streamlit/app.py` written but not run (streamlit not installed; optional).
- Larger window sets (e.g. quarterly 2015→2026 = 48 windows ≈ 192 calls) —
  fits in one anonymous day but should be done with a key for headroom.
- Longer histories + more drugs would let the emergence rule be validated
  against known label changes (e.g. /drug/label.json comparison) — flagged
  as future work, not implemented.
- No push performed (no auth) — local git repo initialized; initial commit
  recorded below.
