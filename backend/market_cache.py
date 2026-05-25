"""TTL market data cache — V2.3.

Caching states:
  fresh        < FRESH_TTL seconds (5 min)    — return immediately, no fetch needed
  cached       < CACHED_TTL seconds (30 min)  — return but mark as "cached"
  stale        >= CACHED_TTL seconds           — return with "stale" flag, trigger refresh
  unavailable  no file on disk                 — must fetch

Rule: 429 → stale.  If the provider rate-limits, serve stale cache
rather than returning nothing.  Never invent data.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# TTL thresholds (seconds)
FRESH_TTL: int = 300      # 5 minutes
CACHED_TTL: int = 1800    # 30 minutes

CACHE_DIR: Path = Path(__file__).resolve().parent / ".cache"


def _cache_path(ticker: str) -> Path:
    """Filesystem path for a ticker's market cache file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"market_{ticker.upper()}.json"


def get(ticker: str) -> Optional[Dict[str, Any]]:
    """Return cached market data dict, or None if unavailable."""
    data, _state = get_with_state(ticker)
    return data


def get_with_state(ticker: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (data_dict_or_None, state).

    States: 'fresh', 'cached', 'stale', 'unavailable'
    """
    path = _cache_path(ticker)
    if not path.exists():
        return None, "unavailable"

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("market_cache: cannot read %s — %s", path, exc)
        return None, "unavailable"

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("market_cache: corrupt JSON for %s — %s", ticker, exc)
        return None, "unavailable"

    data = payload.get("data")
    ts = payload.get("cached_at")
    if data is None or ts is None:
        return None, "unavailable"

    age = time.time() - ts
    if age < FRESH_TTL:
        return data, "fresh"
    if age < CACHED_TTL:
        return data, "cached"
    return data, "stale"


def set(ticker: str, data: Dict[str, Any]) -> None:
    """Write market data to cache with current timestamp."""
    path = _cache_path(ticker)
    payload: Dict[str, Any] = {
        "cached_at": time.time(),
        "cached_at_iso": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        logger.debug("market_cache: stored %s (%d keys)", ticker.upper(), len(data))
    except OSError as exc:
        logger.warning("market_cache: write failed for %s — %s", ticker, exc)


def get_state(ticker: str) -> str:
    """Return cache state string: fresh / cached / stale / unavailable."""
    _data, state = get_with_state(ticker)
    return state


def invalidate(ticker: str) -> bool:
    """Remove cache entry.  Returns True if a file was deleted."""
    path = _cache_path(ticker)
    if path.exists():
        try:
            path.unlink()
            logger.debug("market_cache: invalidated %s", ticker.upper())
            return True
        except OSError as exc:
            logger.warning("market_cache: could not invalidate %s — %s", ticker, exc)
    return False
