"""Phase 6 (B13/B17): URL-validation memoization and yfinance Ticker reuse.

All tests are mock-based — no live network.
"""
import asyncio

import pytest

import backend.url_validator as uv
import backend.sources_collector as sc


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    monkeypatch.setattr(uv, "_RESULT_CACHE", {})
    monkeypatch.setattr(sc, "_TICKER_CACHE", {})
    yield


class TestUrlValidationMemoization:
    def _patch_checker(self, monkeypatch, calls):
        async def fake_check(url, label, **kwargs):
            calls.append(url)
            return uv.UrlCheck(url=url, label=label, status_code=200, alive=True)
        monkeypatch.setattr(uv, "_check_one_url", fake_check)

    def test_second_validation_uses_cache(self, monkeypatch):
        monkeypatch.setattr(uv, "_RESULT_CACHE_TTL", 900.0)
        calls: list[str] = []
        self._patch_checker(monkeypatch, calls)
        pairs = [("https://a.example/x", "A"), ("https://b.example/y", "B")]
        r1 = asyncio.run(uv._validate_url_pairs(list(pairs), ticker="T"))
        r2 = asyncio.run(uv._validate_url_pairs(list(pairs), ticker="T"))
        assert len(calls) == 2, "second run must not re-check cached URLs"
        # Validation output unchanged: both reports carry both URLs as alive
        for r in (r1, r2):
            assert len(r.checks) == 2 and all(c.alive for c in r.checks)

    def test_cached_result_keeps_current_label(self, monkeypatch):
        monkeypatch.setattr(uv, "_RESULT_CACHE_TTL", 900.0)
        calls: list[str] = []
        self._patch_checker(monkeypatch, calls)
        asyncio.run(uv._validate_url_pairs([("https://a.example/x", "old")], ticker="T"))
        r2 = asyncio.run(uv._validate_url_pairs([("https://a.example/x", "new")], ticker="T"))
        assert r2.checks[0].label == "new"

    def test_ttl_zero_disables_cache(self, monkeypatch):
        monkeypatch.setattr(uv, "_RESULT_CACHE_TTL", 0.0)
        calls: list[str] = []
        self._patch_checker(monkeypatch, calls)
        pairs = [("https://a.example/x", "A")]
        asyncio.run(uv._validate_url_pairs(list(pairs), ticker="T"))
        asyncio.run(uv._validate_url_pairs(list(pairs), ticker="T"))
        assert len(calls) == 2

    def test_dead_result_also_memoized(self, monkeypatch):
        monkeypatch.setattr(uv, "_RESULT_CACHE_TTL", 900.0)
        calls: list[str] = []

        async def fake_check(url, label, **kwargs):
            calls.append(url)
            return uv.UrlCheck(url=url, label=label, status_code=404, alive=False, error="404")
        monkeypatch.setattr(uv, "_check_one_url", fake_check)
        pairs = [("https://dead.example/x", "D")]
        asyncio.run(uv._validate_url_pairs(list(pairs), ticker="T"))
        r2 = asyncio.run(uv._validate_url_pairs(list(pairs), ticker="T"))
        assert len(calls) == 1
        assert r2.checks[0].alive is False and r2.checks[0].status_code == 404


class TestTickerReuse:
    def _fake_yf(self, created):
        class FakeTicker:
            def __init__(self, symbol):
                created.append(symbol)
                self.symbol = symbol

        class FakeYf:
            Ticker = FakeTicker
        return FakeYf()

    def test_same_ticker_object_reused_within_ttl(self, monkeypatch):
        created: list[str] = []
        monkeypatch.setattr(sc, "_load_yfinance", lambda: self._fake_yf(created))
        monkeypatch.setattr(sc, "_ticker_cache_ttl", lambda: 300.0)
        t1 = sc._yf_ticker_safe("NVDA")
        t2 = sc._yf_ticker_safe("NVDA")
        assert t1 is t2 and created == ["NVDA"]

    def test_different_tickers_not_shared(self, monkeypatch):
        created: list[str] = []
        monkeypatch.setattr(sc, "_load_yfinance", lambda: self._fake_yf(created))
        monkeypatch.setattr(sc, "_ticker_cache_ttl", lambda: 300.0)
        assert sc._yf_ticker_safe("NVDA") is not sc._yf_ticker_safe("AAPL")
        assert created == ["NVDA", "AAPL"]

    def test_ttl_zero_disables_reuse(self, monkeypatch):
        created: list[str] = []
        monkeypatch.setattr(sc, "_load_yfinance", lambda: self._fake_yf(created))
        monkeypatch.setattr(sc, "_ticker_cache_ttl", lambda: 0.0)
        sc._yf_ticker_safe("NVDA")
        sc._yf_ticker_safe("NVDA")
        assert created == ["NVDA", "NVDA"]

    def test_expired_entry_recreated(self, monkeypatch):
        created: list[str] = []
        monkeypatch.setattr(sc, "_load_yfinance", lambda: self._fake_yf(created))
        monkeypatch.setattr(sc, "_ticker_cache_ttl", lambda: 300.0)
        sc._yf_ticker_safe("NVDA")
        # Force expiry
        key, (ts, obj) = next(iter(sc._TICKER_CACHE.items()))
        sc._TICKER_CACHE[key] = (ts - 301.0, obj)
        sc._yf_ticker_safe("NVDA")
        assert created == ["NVDA", "NVDA"]
