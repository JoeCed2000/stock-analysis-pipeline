"""
V2.5 Peer Universe Configuration — curated competitive peers.

Provides `get_peers(ticker)` returning a structured dict with peer
information for competitive analysis. Peer groups are manually curated
in `peer_universe.json`.

Returns always include `status`, `source`, and `timestamp` following
the backend service convention.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Path to the curated JSON config ─────────────────────────────
_CONFIG_PATH = Path(__file__).resolve().parent / "peer_universe.json"

# ── Module-level cache ───────────────────────────────────────────
_peer_universe: Optional[Dict[str, Any]] = None
_load_errors: list[str] = []

# Common share-class aliases that should map to the same peer group logic.
_TICKER_ALIASES: Dict[str, set[str]] = {
    "GOOG": {"GOOGL"},
    "GOOGL": {"GOOG"},
}

_DYNAMIC_PEER_CACHE: Dict[str, List[str]] = {}
_VALID_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


def _equivalent_tickers(ticker: str) -> set[str]:
    """Return ticker + known aliases for matching/skip logic."""
    t = ticker.upper().strip()
    return {t, *_TICKER_ALIASES.get(t, set())}


def _normalize_dynamic_peers(raw_peers: Any, equivalent: set[str]) -> List[str]:
    """Normalize provider peer symbols and drop invalid/self/duplicates."""
    if not isinstance(raw_peers, list):
        return []

    out: List[str] = []
    for raw in raw_peers:
        if not isinstance(raw, str):
            continue
        sym = raw.upper().strip()
        if not sym or sym in equivalent:
            continue
        if not _VALID_TICKER.match(sym):
            continue
        if sym not in out:
            out.append(sym)

    # Keep a compact basket for stable UI/latency.
    return out[:8]


def _fetch_dynamic_peers_from_finnhub(ticker: str, equivalent: set[str]) -> List[str]:
    """Try Finnhub company_peers as runtime fallback for non-curated tickers."""
    ticker = ticker.upper().strip()

    if ticker in _DYNAMIC_PEER_CACHE:
        return _DYNAMIC_PEER_CACHE[ticker]

    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        from backend.http_client import http

        resp = http.get(
            "https://finnhub.io/api/v1/stock/peers",
            params={"symbol": ticker, "token": api_key},
            timeout=8,
        )
        if resp.status_code != 200:
            logger.debug(
                "dynamic peers: finnhub HTTP %s for %s",
                resp.status_code,
                ticker,
            )
            return []

        peers = _normalize_dynamic_peers(resp.json(), equivalent)
        _DYNAMIC_PEER_CACHE[ticker] = peers
        return peers
    except Exception as exc:
        logger.debug("dynamic peers: finnhub fetch failed for %s — %s", ticker, exc)
        return []


def _load_config() -> Dict[str, Any]:
    # pyright: ignore[reportReturnType] — _peer_universe is never None after first load
    """Load and validate peer_universe.json. Cached after first load."""
    global _peer_universe, _load_errors

    if _peer_universe is not None:
        return _peer_universe

    try:
        raw = _CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        _load_errors.append("peer_universe.json not found")
        _peer_universe = {}
        return _peer_universe
    except json.JSONDecodeError as exc:
        _load_errors.append(f"peer_universe.json is malformed: {exc}")
        _peer_universe = {}
        return _peer_universe

    return _validate_and_cache(data)


def _validate_and_cache(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate raw peer universe dict and cache it. Export for tests."""
    global _peer_universe, _load_errors
    _load_errors = []

    # ── Validate structure ────────────────────────────────────────
    if "_meta" not in data:
        _load_errors.append("missing _meta section")

    groups = {k: v for k, v in data.items() if not k.startswith("_")}
    if not groups:
        _load_errors.append("no peer groups defined")
        _peer_universe = {}
        return _peer_universe

    for key, group in groups.items():
        if not isinstance(group, dict):
            _load_errors.append(f"{key}: not a valid group object")
            continue

        ticker = group.get("ticker")
        group_id = group.get("group_id")
        peers = group.get("peers", [])

        if not ticker:
            _load_errors.append(f"{key}: missing ticker field")
        if not group_id:
            _load_errors.append(f"{key}: missing group_id field")
        if not isinstance(peers, list) or len(peers) == 0:
            _load_errors.append(f"{key}: peers must be a non-empty list")

        # ── Self-reference check ──────────────────────────────────
        if ticker and ticker.upper() in [p.upper() for p in peers]:
            _load_errors.append(
                f"{key}: ticker {ticker} references itself in peers"
            )

        # ── Duplicate check ───────────────────────────────────────
        seen = set()
        for p in peers:
            pu = p.upper()
            if pu in seen:
                _load_errors.append(
                    f"{key}: duplicate peer ticker '{p}' in peers list"
                )
            seen.add(pu)

    _peer_universe = data
    return _peer_universe


def get_peers(ticker: str) -> Dict[str, Any]:
    """Return peer information for *ticker*.

    Args:
        ticker: Stock ticker symbol (case-insensitive, e.g. "NVDA", "aapl")

    Returns:
        dict with keys:
          - status: "available" | "unavailable" | "error"
          - source: "curated" | "dynamic_finnhub" | "none"
          - timestamp: ISO-8601 UTC
          - ticker: resolved uppercase ticker
          - group_id: peer group identifier (only when available)
          - group_label: human-readable group name (only when available)
          - peers: list of peer ticker symbols (only when available)
          - errors: list of validation errors (only when present)
    """
    now = datetime.now(timezone.utc).isoformat()
    ticker = ticker.upper().strip()

    config = _load_config()

    # ── Load errors detected ──────────────────────────────────────
    if _load_errors:
        return {
            "status": "error",
            "source": "curated",
            "timestamp": now,
            "ticker": ticker,
            "errors": _load_errors.copy(),
        }

    # ── Search for ticker (case-insensitive match) ────────────────
    ticker_lower = ticker.lower()
    entry = config.get(ticker_lower)
    equivalent = _equivalent_tickers(ticker)

    derived_from_root: Optional[str] = None

    if entry is None:
        # Try case-insensitive lookup across all root groups.
        for key, group in config.items():
            if key.startswith("_"):
                continue
            group_ticker = str(group.get("ticker", "")).upper().strip() if isinstance(group, dict) else ""
            if group_ticker in equivalent:
                entry = group
                break

    if entry is None:
        # Fallback: if ticker appears as a peer inside a curated root group,
        # derive a group on the fly instead of returning unavailable.
        for key, group in config.items():
            if key.startswith("_") or not isinstance(group, dict):
                continue

            root_ticker = str(group.get("ticker", "")).upper().strip()
            raw_peers = group.get("peers", [])
            peers = [
                str(p).upper().strip()
                for p in raw_peers
                if isinstance(p, str) and str(p).strip()
            ]

            if not any(p in equivalent for p in peers):
                continue

            derived_peers = []
            if root_ticker and root_ticker not in equivalent:
                derived_peers.append(root_ticker)
            for p in peers:
                if p not in equivalent and p not in derived_peers:
                    derived_peers.append(p)

            entry = {
                "ticker": ticker,
                "group_id": group.get("group_id"),
                "group_label": group.get("group_label"),
                "peers": derived_peers,
            }
            derived_from_root = root_ticker or None
            break

    if entry is None:
        dynamic_peers = _fetch_dynamic_peers_from_finnhub(ticker, equivalent)
        if len(dynamic_peers) >= 2:
            return {
                "status": "available",
                "source": "dynamic_finnhub",
                "timestamp": now,
                "ticker": ticker,
                "group_id": f"dynamic_{ticker_lower}",
                "group_label": "Dynamic Peers (Finnhub)",
                "peers": dynamic_peers,
                "derived_from_provider": "finnhub",
            }

        return {
            "status": "unavailable",
            "source": "curated",
            "timestamp": now,
            "ticker": ticker,
        }

    result = {
        "status": "available",
        "source": "curated",
        "timestamp": now,
        "ticker": entry["ticker"].upper(),
        "group_id": entry["group_id"],
        "group_label": entry["group_label"],
        "peers": [p.upper() for p in entry["peers"]],
    }
    if derived_from_root:
        result["derived_from_root"] = derived_from_root

    return result


def reload() -> Dict[str, Any]:
    """Force reload of the peer universe config. Useful for tests."""
    global _peer_universe, _load_errors
    _peer_universe = None
    _load_errors = []
    _DYNAMIC_PEER_CACHE.clear()
    return _load_config()
