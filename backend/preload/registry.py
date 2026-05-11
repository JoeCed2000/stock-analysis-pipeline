"""
Ticker registry — popularity scoring and tier assignment.

Phase 1 MVP: Mag 7 hardcoded.
Phase 2: dynamic scoring from search history + indices.
"""

import json
import os
from pathlib import Path
from typing import Dict, List

_REGISTRY_DIR = Path(__file__).parent.parent
_CACHE_DIR = _REGISTRY_DIR / ".cache"

# ── Phase 1: Mag 7 ──────────────────────────────────────────────────────
MAG7 = [
    {"ticker": "AAPL", "company": "Apple Inc."},
    {"ticker": "MSFT", "company": "Microsoft Corporation"},
    {"ticker": "GOOGL", "company": "Alphabet Inc."},
    {"ticker": "AMZN", "company": "Amazon.com Inc."},
    {"ticker": "NVDA", "company": "NVIDIA Corporation"},
    {"ticker": "META", "company": "Meta Platforms Inc."},
    {"ticker": "TSLA", "company": "Tesla Inc."},
]

# ── Popularity scoring model (Phase 2+) ─────────────────────────────────
def score_ticker(
    ticker: str,
    *,
    pinned: bool = False,
    in_nasdaq100: bool = False,
    in_sp500: bool = False,
    in_mag7: bool = False,
    search_count_7d: int = 0,
    search_count_30d: int = 0,
    earnings_within_7d: bool = False,
    earnings_released_3d: bool = False,
) -> int:
    """Deterministic popularity score (0-200)."""
    score = 0
    if pinned:           score += 50
    if in_nasdaq100:     score += 30
    if in_sp500:         score += 25
    if in_mag7:          score += 20
    score += search_count_7d * 10
    score += search_count_30d * 5
    if earnings_within_7d: score += 20
    if earnings_released_3d: score += 15
    return score


def get_tier(ticker: str) -> int:
    """0 = pinned, 1 = popular, 2 = searched, 3 = fallback."""
    # Phase 1: all Mag 7 are Tier 1
    if any(m["ticker"] == ticker.upper() for m in MAG7):
        return 1
    return 3


def get_universe() -> List[Dict]:
    """Return the current ticker universe with tiers."""
    # Phase 1: just Mag 7
    result = []
    for m in MAG7:
        entry = dict(m)
        entry["tier"] = 1
        entry["pinned"] = False
        result.append(entry)
    
    # Phase 2: load from ticker_universe.json, merge with search history
    universe_file = _REGISTRY_DIR / "preload" / "ticker_universe.json"
    if universe_file.exists():
        try:
            with open(universe_file) as f:
                extra = json.load(f)
            result.extend(extra)
        except (json.JSONDecodeError, OSError):
            pass
    
    return result
