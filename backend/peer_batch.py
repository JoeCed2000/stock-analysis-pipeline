"""
V2.5 Peer Batch Layer — competitive benchmark snapshots.

Provides `get_peer_benchmark_snapshot(ticker)` that fetches V2.3/V2.4
metrics (market snapshot + valuation) for all configured peers of a
given ticker.

Partial success is supported — if some peers fail, the result includes
successful peers plus error details for failed ones. An in-memory cache
with 5-min TTL avoids redundant network calls when the same peer group
is queried repeatedly.

Acceptance criteria (SA-V25-T2):
  - Batch fetch works for NVDA/AAPL/TSLA
  - Partial success when a peer is unavailable
  - Cache reused within TTL
  - No crash on any individual peer failure
  - sample_size tracked in the result
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.peer_universe import get_peers
from backend.market_data import get_market_snapshot
from backend.valuation import get_valuation

logger = logging.getLogger(__name__)

# ── In-memory cache ─────────────────────────────────────────────
# Key: ticker (upper) →  Value: {"data": ..., "cached_at": epoch_s}
_BENCHMARK_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes


def get_peer_benchmark_snapshot(
    ticker: str,
    *,
    bypass_cache: bool = False,
) -> Dict[str, Any]:
    """Return a benchmark snapshot for *ticker* covering all peers.

    For each configured peer, fetches:
      - MarketSnapshot  (V2.3 — price, volume, market cap, ratios)
      - ValuationV2Response (V2.3 — multiples, EV, fundamentals)

    Args:
        ticker:   Stock ticker symbol (case-insensitive, e.g. "NVDA").
        bypass_cache: If True, skip the in-memory cache and re-fetch.

    Returns:
        dict with keys:
          - status:      "complete" | "partial" | "unavailable" | "error"
          - source:      "curated" | "none"
          - timestamp:   ISO-8601 UTC
          - ticker:      resolved uppercase ticker
          - group_id:    peer group identifier (when available)
          - group_label: human-readable group name (when available)
          - sample_size: number of peers successfully fetched
          - total_peers: total peers in the group
          - peers:       dict of {TICKER: {market: ..., valuation: ...}}
          - errors:      list of {"ticker": str, "error": str}
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = ticker.upper().strip()

    # ── Cache hit (unless bypassed) ──────────────────────────────
    if not bypass_cache:
        cached = _BENCHMARK_CACHE.get(ticker)
        if cached and (time.monotonic() - cached["cached_at"]) < _CACHE_TTL_SECONDS:
            logger.debug("peer_batch: %s — cache hit (age=%.0fs)", ticker, time.monotonic() - cached["cached_at"])
            data = dict(cached["data"])
            data["timestamp"] = now_iso  # Refresh timestamp
            return data

    # ── Get peer list ────────────────────────────────────────────
    peer_info = get_peers(ticker)

    if peer_info["status"] == "error":
        return {
            "status": "error",
            "source": "curated",
            "timestamp": now_iso,
            "ticker": ticker,
            "sample_size": 0,
            "total_peers": 0,
            "peers": {},
            "errors": peer_info.get("errors", []),
        }

    if peer_info["status"] == "unavailable":
        return {
            "status": "unavailable",
            "source": peer_info.get("source", "none"),
            "timestamp": now_iso,
            "ticker": ticker,
            "sample_size": 0,
            "total_peers": 0,
            "peers": {},
            "errors": [{"ticker": ticker, "error": "no peer group configured"}],
        }

    peer_list: List[str] = peer_info.get("peers", [])

    # ── Fetch each peer (sequential, graceful on failure) ───────
    peers_data: Dict[str, Dict[str, Any]] = {}
    errors: List[Dict[str, str]] = []

    for peer in peer_list:
        peer_upper = peer.upper().strip()
        try:
            market = None
            valuation = None
            market_error = None
            valuation_error = None

            # Market snapshot
            try:
                market_snapshot = get_market_snapshot(peer_upper)
                market = _pydantic_to_dict(market_snapshot)
            except Exception as exc:
                market_error = f"market_data: {_short_error(exc)}"
                logger.warning("peer_batch: %s market data failed — %s", peer_upper, market_error)

            # Valuation
            try:
                valuation_response = get_valuation(peer_upper)
                valuation = _pydantic_to_dict(valuation_response)
            except Exception as exc:
                valuation_error = f"valuation: {_short_error(exc)}"
                logger.warning("peer_batch: %s valuation failed — %s", peer_upper, valuation_error)

            # ── If both failed, this peer is a total miss ─────────
            if market is None and valuation is None:
                combined = f"{market_error}; {valuation_error}" if market_error and valuation_error else (market_error or valuation_error or "unknown error")
                errors.append({"ticker": peer_upper, "error": combined})
                continue

            # ── Partial data is ok — store what we got ────────────
            entry: Dict[str, Any] = {}
            if market is not None:
                entry["market"] = market
            if valuation is not None:
                entry["valuation"] = valuation
            if market_error:
                entry["market_error"] = market_error
            if valuation_error:
                entry["valuation_error"] = valuation_error

            peers_data[peer_upper] = entry

        except Exception as exc:
            # This should not happen — individual fetch errors are already
            # caught above — but guard against unexpected crashes.
            logger.exception("peer_batch: unexpected error for peer %s", peer_upper)
            errors.append({"ticker": peer_upper, "error": _short_error(exc)})

    # ── Determine overall status ─────────────────────────────────
    total_peers = len(peer_list)
    sample_size = len(peers_data)

    if sample_size == 0 and total_peers > 0:
        status = "error"  # All peers failed
    elif sample_size < total_peers:
        status = "partial"
    elif sample_size == 0 and total_peers == 0:
        status = "unavailable"
    else:
        status = "complete"

    result: Dict[str, Any] = {
        "status": status,
        "source": "curated",
        "timestamp": now_iso,
        "ticker": ticker,
        "group_id": peer_info.get("group_id"),
        "group_label": peer_info.get("group_label"),
        "sample_size": sample_size,
        "total_peers": total_peers,
        "peers": peers_data,
        "errors": errors,
    }

    # ── Cache ────────────────────────────────────────────────────
    _BENCHMARK_CACHE[ticker] = {"data": result, "cached_at": time.monotonic()}

    return result


def get_cache_size() -> int:
    """Return the number of tickers currently in the benchmark cache."""
    return len(_BENCHMARK_CACHE)


def clear_benchmark_cache(ticker: Optional[str] = None) -> None:
    """Clear the in-memory benchmark cache.

    Args:
        ticker: If provided, clear only that ticker. If None, clear all.
    """
    if ticker:
        _BENCHMARK_CACHE.pop(ticker.upper().strip(), None)
    else:
        _BENCHMARK_CACHE.clear()


def reload_cache() -> None:
    """Alias for clear_benchmark_cache() — match peer_universe convention."""
    clear_benchmark_cache()


# ── Internal helpers ─────────────────────────────────────────────


def _pydantic_to_dict(obj: Any) -> Optional[Dict[str, Any]]:
    """Safely convert a Pydantic model to a plain dict. Returns None on failure."""
    try:
        return obj.model_dump()
    except AttributeError:
        try:
            return dict(obj)
        except (TypeError, ValueError):
            logger.debug("peer_batch: could not convert %r to dict", type(obj).__name__)
            return None
    except Exception:
        logger.debug("peer_batch: model_dump failed for %r", type(obj).__name__)
        return None


def _short_error(exc: BaseException) -> str:
    """Return a concise error string (no traceback)."""
    return f"{type(exc).__name__}: {exc}"
