"""Tests for market_cache.py + market_data.py — V2.3.

Covers:
  - market_cache: TTL states, read/write, invalidation
  - market_data:  get_market_snapshot, normalize_market_data
  - 429 → stale fallback
  - Never-invent-data: missing fields stay None

Run:
  cd /home/ced/codex-projects/stock-analysis-pipeline
  python3 -B -m pytest tests/test_market_data.py -v
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend import market_cache
from backend.market_data import (
    _empty_snapshot,
    _fetch_from_yfinance,
    _float_or_none,
    _int_or_none,
    get_market_snapshot,
    normalize_market_data,
)
from backend.models import MarketSnapshot

# ─────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch, tmp_path):
    """Point market_cache to a tmp dir so tests don't touch real cache."""
    monkeypatch.setattr(market_cache, "CACHE_DIR", tmp_path / ".cache")
    yield
    # Cleanup
    import glob
    for f in glob.glob(str(tmp_path / ".cache" / "market_*.json")):
        os.remove(f)


# ═════════════════════════════════════════════════════════════
#  market_cache Tests
# ═════════════════════════════════════════════════════════════


class TestMarketCache:
    """TTL cache layer — no network."""

    def test_get_returns_none_when_empty(self):
        assert market_cache.get("MSFT") is None

    def test_get_state_unavailable_when_empty(self):
        assert market_cache.get_state("MSFT") == "unavailable"

    def test_set_and_get_roundtrip(self):
        data = {"price": 150.0, "market_cap": 2e12}
        market_cache.set("AAPL", data)
        cached = market_cache.get("AAPL")
        assert cached == data

    def test_set_and_get_state_fresh(self):
        market_cache.set("AAPL", {"price": 150.0})
        assert market_cache.get_state("AAPL") == "fresh"

    def test_get_with_state_returns_data_and_state(self):
        market_cache.set("GOOGL", {"price": 140.0})
        data, state = market_cache.get_with_state("GOOGL")
        assert data == {"price": 140.0}
        assert state == "fresh"

    def test_state_transitions_to_stale(self, monkeypatch):
        """Simulate old cache by patching the timestamp."""
        market_cache.set("TSLA", {"price": 250.0})
        # Manually rewrite the file with an old timestamp
        path = market_cache._cache_path("TSLA")
        raw = json.loads(path.read_text())
        raw["cached_at"] = time.time() - 2000  # 33 minutes ago → stale
        path.write_text(json.dumps(raw))
        assert market_cache.get_state("TSLA") == "stale"

    def test_state_transitions_to_cached(self, monkeypatch):
        """Simulate cache 10 min old."""
        market_cache.set("AMZN", {"price": 120.0})
        path = market_cache._cache_path("AMZN")
        raw = json.loads(path.read_text())
        raw["cached_at"] = time.time() - 600  # 10 minutes ago → cached
        path.write_text(json.dumps(raw))
        assert market_cache.get_state("AMZN") == "cached"

    def test_invalidate_removes_entry(self):
        market_cache.set("META", {"price": 500.0})
        assert market_cache.get("META") is not None
        market_cache.invalidate("META")
        assert market_cache.get("META") is None
        assert market_cache.get_state("META") == "unavailable"

    def test_invalidate_nonexistent_returns_false(self):
        assert market_cache.invalidate("NONEXISTENT") is False

    def test_corrupt_json_returns_none(self, tmp_path):
        path = market_cache._cache_path("CORRUPT")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json {{{", encoding="utf-8")
        assert market_cache.get("CORRUPT") is None
        assert market_cache.get_state("CORRUPT") == "unavailable"

    def test_empty_payload_returns_none(self, tmp_path):
        path = market_cache._cache_path("EMPTY")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        assert market_cache.get("EMPTY") is None


# ═════════════════════════════════════════════════════════════
#  market_data — normalize_market_data
# ═════════════════════════════════════════════════════════════


class TestNormalizeMarketData:
    """Normalize raw provider dicts into MarketSnapshot."""

    def test_full_data(self):
        raw = {
            "symbol": "NVDA",
            "current_price": 850.0,
            "previous_close": 840.0,
            "day_change": 10.0,
            "day_change_pct": 0.0119,
            "volume": 45000000,
            "avg_volume": 42000000,
            "market_cap": 2.1e12,
            "beta": 1.7,
            "high_52w": 1000.0,
            "low_52w": 450.0,
            "shares_outstanding": 2.47e9,
            "pe_ttm": 55.0,
            "ps_ttm": 25.0,
            "pb_ratio": 30.0,
            "dividend_yield": 0.0001,
        }
        snap = normalize_market_data(raw)
        assert snap.ticker == "NVDA"
        assert snap.current_price == 850.0
        assert snap.market_cap == 2.1e12
        assert snap.beta == 1.7
        assert snap.pe_ttm == 55.0
        assert snap.volume == 45000000
        assert snap.cache_state == "unavailable"  # caller overrides

    def test_partial_data(self):
        raw = {"symbol": "PENNY", "current_price": 0.05}
        snap = normalize_market_data(raw)
        assert snap.ticker == "PENNY"
        assert snap.current_price == 0.05
        assert snap.market_cap is None
        assert snap.beta is None
        assert snap.pe_ttm is None

    def test_empty_dict(self):
        snap = normalize_market_data({})
        assert snap.ticker == "???"
        assert snap.current_price is None

    def test_ticker_fallback(self):
        raw = {"ticker": "IBM"}
        snap = normalize_market_data(raw)
        assert snap.ticker == "IBM"

    def test_day_change_calculated_on_the_fly_by_caller(self):
        """normalize_market_data trusts the raw dict values. Day change
        calculation happens in _fetch_from_yfinance."""
        raw = {
            "symbol": "TEST",
            "current_price": 100.0,
            "previous_close": 98.0,
            "day_change": 2.0,
            "day_change_pct": 0.0204,
        }
        snap = normalize_market_data(raw)
        assert snap.day_change == 2.0
        assert snap.day_change_pct == pytest.approx(0.0204)


# ═════════════════════════════════════════════════════════════
#  market_data — get_market_snapshot
# ═════════════════════════════════════════════════════════════


SAMPLE_YFINANCE_INFO = {
    "symbol": "AAPL",
    "currentPrice": 175.0,
    "previousClose": 173.5,
    "volume": 55000000,
    "averageVolume": 52000000,
    "marketCap": 2.7e12,
    "beta": 1.2,
    "fiftyTwoWeekHigh": 200.0,
    "fiftyTwoWeekLow": 160.0,
    "sharesOutstanding": 15.5e9,
    "trailingPE": 28.0,
    "priceToSalesTrailing12Months": 7.0,
    "priceToBook": 45.0,
    "dividendYield": 0.005,
}


class TestGetMarketSnapshot:
    """Cache-first snapshot with yfinance fallback."""

    def test_returns_fresh_from_cache(self, monkeypatch):
        """When cache is fresh, no network call should happen."""
        market_cache.set("AAPL", SAMPLE_YFINANCE_INFO)
        fetch_called = [False]

        def fake_fetch(ticker):
            fetch_called[0] = True
            return None

        monkeypatch.setattr(
            "backend.market_data._fetch_from_yfinance", fake_fetch
        )

        snap = get_market_snapshot("AAPL")
        assert snap.cache_state == "fresh"
        assert snap.current_price == 175.0
        assert snap.ticker == "AAPL"
        assert fetch_called[0] is False, "Should NOT have called yfinance"

    def test_fetches_on_cache_miss(self, monkeypatch):
        """When no cache exists, fetch from provider."""
        monkeypatch.setattr(
            "backend.market_data._fetch_from_yfinance",
            lambda t: SAMPLE_YFINANCE_INFO,
        )

        snap = get_market_snapshot("MSFT")
        assert snap.cache_state == "fresh"
        assert snap.current_price == 175.0
        assert snap.ticker == "MSFT"

    def test_serves_stale_on_fetch_failure(self, monkeypatch):
        """When fetch fails but stale cache exists → serve stale."""
        market_cache.set("GOOGL", SAMPLE_YFINANCE_INFO)
        # Age the cache
        path = market_cache._cache_path("GOOGL")
        raw = json.loads(path.read_text())
        raw["cached_at"] = time.time() - 3600  # 1 hour old
        path.write_text(json.dumps(raw))

        monkeypatch.setattr(
            "backend.market_data._fetch_from_yfinance",
            lambda t: None,  # fetch fails
        )

        snap = get_market_snapshot("GOOGL")
        assert snap.cache_state == "stale"
        assert snap.current_price == 175.0

    def test_returns_unavailable_on_total_failure(self, monkeypatch):
        """No cache + fetch failure → empty snapshot."""
        monkeypatch.setattr(
            "backend.market_data._fetch_from_yfinance",
            lambda t: None,
        )

        snap = get_market_snapshot("DEAD")
        assert snap.cache_state == "unavailable"
        assert snap.current_price is None
        assert snap.ticker == "DEAD"

    def test_ticker_case_insensitive(self, monkeypatch):
        """Lowercase ticker should be normalized."""
        market_cache.set("NVDA", SAMPLE_YFINANCE_INFO)
        monkeypatch.setattr("backend.market_data._fetch_from_yfinance", lambda t: None)
        snap = get_market_snapshot("nvda")
        assert snap.ticker == "NVDA"

    def test_strips_whitespace(self, monkeypatch):
        market_cache.set("IBM", SAMPLE_YFINANCE_INFO)
        monkeypatch.setattr("backend.market_data._fetch_from_yfinance", lambda t: None)
        snap = get_market_snapshot("  ibm  ")
        assert snap.ticker == "IBM"


# ═════════════════════════════════════════════════════════════
#  Helper coercions
# ═════════════════════════════════════════════════════════════


class TestCoercions:
    def test_float_or_none_valid(self):
        assert _float_or_none(42.0) == 42.0
        assert _float_or_none("3.14") == 3.14
        assert _float_or_none(0) == 0.0

    def test_float_or_none_invalid(self):
        assert _float_or_none(None) is None
        assert _float_or_none("n/a") is None
        assert _float_or_none([1, 2]) is None

    def test_int_or_none_valid(self):
        assert _int_or_none(42) == 42
        assert _int_or_none("1000000") == 1000000

    def test_int_or_none_invalid(self):
        assert _int_or_none(None) is None
        assert _int_or_none("lots") is None
