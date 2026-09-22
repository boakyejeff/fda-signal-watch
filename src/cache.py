"""Thin convenience layer over OpenFDAClient cache files.

cache.list_cache() lets you see what was already pulled; cache.clear_stale()
removes entries older than N days so numbers can be refreshed deliberately.
"""

import json
import time
from pathlib import Path


def list_cache(cache_dir="data/cache"):
    rows = []
    for meta in sorted(Path(cache_dir).glob("*.json")):
        try:
            info = json.loads(meta.read_text())
            rows.append({
                "key": meta.stem,
                "params": info.get("params", {}),
                "age_days": round(
                    (time.time() - meta.stat().st_mtime) / 86400, 2),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return rows


def clear_stale(cache_dir="data/cache", older_than_days=30) -> int:
    removed = 0
    cutoff = time.time() - older_than_days * 86400
    for path in Path(cache_dir).glob("*"):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed
