"""Quota-aware client for the openFDA Drug Adverse Event (FAERS) API.

Design goals:
- NEVER burn the anonymous 1000 req/day quota unnecessarily: every call goes
  through a parquet cache keyed by (query, count field, date range).
- Graceful handling of HTTP 404 (openFDA returns 404 for zero-match searches,
  which is an empty result, not an error).
- Polite rate limiting (240 req/min official ceiling; we default to ~2 req/s
  with API key, slower without).
- Optional API key via the OPENFDA_API_KEY environment variable
  (free registration at https://open.fda.gov/apis/authentication/ —
  raises the daily quota from 1,000 to 120,000).
"""

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.fda.gov/drug/event.json"
ENV_KEY_VAR = "OPENFDA_API_KEY"

# Polite defaults: official ceiling is 240 req/min; stay well under it.
MIN_INTERVAL_S_WITH_KEY = 0.25
MIN_INTERVAL_S_ANONYMOUS = 1.0


class QuotaExceededError(RuntimeError):
    """Raised when the client refuses to make another request to protect quota."""


class OpenFDAClient:
    def __init__(self, cache_dir="data/cache", api_key=None,
                 max_requests_per_run=None, dry_run=False):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get(ENV_KEY_VAR)
        self.max_requests_per_run = max_requests_per_run
        self.dry_run = dry_run
        self.requests_made = 0
        self.cache_hits = 0
        self._last_call = 0.0

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _key(params: dict) -> str:
        canon = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()[:16]

    def _cache_path(self, params: dict) -> Path:
        return self.cache_dir / f"{self._key(params)}.parquet"

    def _meta_path(self, params: dict) -> Path:
        return self.cache_dir / f"{self._key(params)}.json"

    # ----------------------------------------------------------------- request
    def _polite_sleep(self):
        interval = (MIN_INTERVAL_S_WITH_KEY if self.api_key
                    else MIN_INTERVAL_S_ANONYMOUS)
        wait = interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def _get(self, params: dict) -> dict:
        """Raw GET with 404-as-empty semantics and a hard per-run request cap."""
        if (self.max_requests_per_run is not None
                and self.requests_made >= self.max_requests_per_run):
            raise QuotaExceededError(
                f"Refusing request #{self.requests_made + 1}: "
                f"max_requests_per_run={self.max_requests_per_run} reached "
                f"(quota protection)."
            )
        if self.dry_run:
            raise QuotaExceededError("dry_run=True: no network calls allowed.")

        self._polite_sleep()
        q = dict(params)
        if self.api_key:
            q["api_key"] = self.api_key
        # IMPORTANT: build the query string manually. openFDA's search parser
        # requires literal `+` (as AND) and literal `[`/`]` for ranges;
        # urllib.parse.urlencode would encode them (%2B, %5B…) and openFDA
        # returns HTTP 500. Values are constructed by us, so no escaping needed.
        qs = "&".join(f"{k}={v}" for k, v in q.items())
        url = BASE_URL + "?" + qs
        self._last_call = time.time()
        resp = requests.get(url, timeout=60)
        self.requests_made += 1

        if resp.status_code == 404:
            # openFDA semantics: zero matches -> 404. Treat as empty result.
            return {"results": []}
        resp.raise_for_status()
        return resp.json()

    # --------------------------------------------------------------- count API
    def count(self, search: str, count_field: str,
              date_from: str = None, date_to: str = None,
              limit: int = 100) -> pd.DataFrame:
        """Aggregation query, e.g. count reactions for a drug.

        search: openFDA search string, e.g. 'patient.drug.medicinalproduct:aspirin'
        count_field: e.g. 'patient.reaction.reactionmeddrapt.exact'
        date_from/date_to: 'YYYYMMDD'; filters on receivedate.
        Returns DataFrame with columns [term, count].
        """
        q = dict(count=count_field, limit=min(limit, 1000))
        if date_from or date_to:
            daterange = f"receivedate:[{date_from or '*'}+TO+{date_to or '*'}]"
            # empty search = whole background in the window (no redundant AND)
            q["search"] = f"({search})+AND+{daterange}" if search else daterange
        else:
            q["search"] = search

        cache_path, meta_path = self._cache_path(q), self._meta_path(q)
        if cache_path.exists():
            self.cache_hits += 1
            return pd.read_parquet(cache_path)

        payload = self._get(q)
        rows = [
            {"term": r.get("term"), "count": r.get("count", 0)}
            for r in payload.get("results", [])
            if r.get("term")
        ]
        df = pd.DataFrame(rows, columns=["term", "count"])
        df.to_parquet(cache_path, index=False)
        meta_path.write_text(json.dumps(
            {"params": q, "requests_made_total": self.requests_made}, indent=2))
        return df

    def total_reports(self, search: str, date_from: str = None,
                      date_to: str = None) -> int:
        """Total report count for a search via limit=1 (cheap: 1 API call)."""
        q = dict(limit=1)
        if date_from or date_to:
            daterange = f"receivedate:[{date_from or '*'}+TO+{date_to or '*'}]"
            q["search"] = f"({search})+AND+{daterange}" if search else daterange
        else:
            q["search"] = search
        cache_path, meta_path = self._cache_path(q), self._meta_path(q)
        if cache_path.exists():
            self.cache_hits += 1
            return int(pd.read_parquet(cache_path)["total"][0])

        payload = self._get(q)
        total = int(payload.get("meta", {}).get("results", {}).get("total", 0))
        pd.DataFrame({"total": [total]}).to_parquet(cache_path, index=False)
        meta_path.write_text(json.dumps({"params": q}, indent=2))
        return total

    def stats(self) -> dict:
        return {
            "requests_made": self.requests_made,
            "cache_hits": self.cache_hits,
            "api_key_set": bool(self.api_key),
        }
