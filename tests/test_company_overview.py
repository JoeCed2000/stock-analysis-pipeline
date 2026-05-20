"""Tests for company_overview.py — yfinance + Tavily + LLM synthesis + 7d cache."""

import json
import os
import sys
import pytest
from unittest.mock import patch
from datetime import datetime, timezone

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.company_overview import (
    OVERVIEW_CACHE_TTL,
    _overview_cache_path,
    _overview_cache_get,
    _overview_cache_set,
    _build_yahoo_info_dict,
    _synthesize_overview,
    get_company_overview,
)


# ── CACHE TESTS ──────────────────────────────────────────────────────────

class TestCacheLayer:
    """File-based JSON cache with 7-day TTL."""

    def test_cache_path_uppercase(self):
        path = _overview_cache_path("aapl", "en")
        assert path.name == "overview_AAPL_en.json"

    def test_cache_path_lowercase_input(self):
        path = _overview_cache_path("nvdA", "jp")
        assert path.name == "overview_NVDA_jp.json"

    def test_cache_set_and_get(self, tmp_path, monkeypatch):
        """Write cache entry, read it back."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        data = {"company_profile": {"name": "TestCo"}}
        _overview_cache_set("TEST", "en", data)

        result = _overview_cache_get("TEST", "en")
        assert result == data

    def test_cache_miss_nonexistent(self, tmp_path, monkeypatch):
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)

        result = _overview_cache_get("NOPE", "en")
        assert result is None

    def test_cache_expired(self, tmp_path, monkeypatch):
        """Cache entry older than 7 days should be missed."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        data = {"test": True}
        _overview_cache_set("OLD", "en", data)

        # Manually age the cache file
        cache_path = _overview_cache_path("OLD", "en")
        with open(cache_path) as f:
            entry = json.load(f)
        entry["timestamp"] = datetime.now(timezone.utc).timestamp() - OVERVIEW_CACHE_TTL - 3600
        with open(cache_path, "w") as f:
            json.dump(entry, f)

        result = _overview_cache_get("OLD", "en")
        assert result is None

    def test_cache_version_mismatch(self, tmp_path, monkeypatch):
        """Different version → cache miss."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        data = {"test": True}
        _overview_cache_set("VER", "en", data)

        # Change version
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 100)

        result = _overview_cache_get("VER", "en")
        assert result is None

    def test_cache_language_isolation(self, tmp_path, monkeypatch):
        """EN and JP caches are independent."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        _overview_cache_set("AAPL", "en", {"lang": "en"})
        _overview_cache_set("AAPL", "jp", {"lang": "jp"})

        en = _overview_cache_get("AAPL", "en")
        jp = _overview_cache_get("AAPL", "jp")
        assert en == {"lang": "en"}
        assert jp == {"lang": "jp"}


# ── YAHOO INFO EXTRACTION ────────────────────────────────────────────────

class TestBuildYahooInfoDict:
    """Extract structured dict from yfinance Ticker.info."""

    def test_full_info(self):
        info = {
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "United States",
            "website": "https://www.apple.com",
            "fullTimeEmployees": 164000,
            "longBusinessSummary": "Apple designs and sells consumer electronics.",
            "marketCap": 3000000000000,
            "currentPrice": 185.50,
            "previousClose": 184.00,
            "trailingPE": 30.5,
            "forwardPE": 28.0,
            "dividendYield": 0.0052,
            "beta": 1.25,
            "fiftyTwoWeekHigh": 199.62,
            "fiftyTwoWeekLow": 124.17,
            "revenueGrowth": 0.05,
            "earningsGrowth": 0.08,
            "totalRevenue": 383285000000,
            "currency": "USD",
            "address1": "One Apple Park Way",
            "city": "Cupertino",
            "state": "CA",
            "zip": "95014",
        }
        result = _build_yahoo_info_dict("AAPL", info)
        assert result["ticker"] == "AAPL"
        assert result["name"] == "Apple Inc."
        assert result["sector"] == "Technology"
        assert result["industry"] == "Consumer Electronics"
        assert result["country"] == "United States"
        assert result["website"] == "https://www.apple.com"
        assert result["employees"] == 164000
        assert result["description"][:6] == "Apple "
        assert result["market_cap"] == 3000000000000
        assert result["current_price"] == 185.50
        assert result["pe_trailing"] == 30.5
        assert result["pe_forward"] == 28.0
        assert result["dividend_yield"] == 0.0052
        assert result["beta"] == 1.25
        assert result["52w_high"] == 199.62
        assert result["52w_low"] == 124.17
        assert result["revenue_growth"] == 0.05
        assert result["total_revenue"] == 383285000000

    def test_minimal_info(self):
        """Handle tickers with minimal info."""
        info = {"longName": "SmallCo", "marketCap": 50000000}
        result = _build_yahoo_info_dict("SML", info)
        assert result["ticker"] == "SML"
        assert result["name"] == "SmallCo"
        assert result["market_cap"] == 50000000
        assert result["sector"] is None
        assert result["employees"] is None
        assert result["description"] is None

    def test_missing_keys_default_none(self):
        info = {}
        result = _build_yahoo_info_dict("TST", info)
        assert result["ticker"] == "TST"
        assert result["name"] is None
        for key in ["sector", "industry", "country", "market_cap"]:
            assert result[key] is None


# ── LLM SYNTHESIS ────────────────────────────────────────────────────────

class TestSynthesizeOverview:
    """LLM synthesis produces valid JSON output."""

    @patch("backend.codex_provider._codex_chat")
    def test_returns_structured_json(self, mock_codex):
        """LLM returns valid JSON → parsed into expected structure."""
        mock_codex.return_value = json.dumps({
            "company_profile": {
                "name": "Apple Inc.",
                "ticker": "AAPL",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "country": "United States",
                "website": "https://www.apple.com",
                "employees": 164000,
                "founded": 1976,
                "headquarters": "Cupertino, CA",
            },
            "business_description": "Apple designs, manufactures and markets smartphones, personal computers, tablets, wearables, and accessories.",
            "key_financials": {
                "market_cap": 3000000000000,
                "market_cap_display": "$3.00T",
                "revenue": 383285000000,
                "revenue_display": "$383.3B",
                "pe_ratio": 30.5,
                "pe_forward": 28.0,
                "dividend_yield": 0.0052,
                "beta": 1.25,
                "52w_high": 199.62,
                "52w_low": 124.17,
            },
            "recent_developments": [
                {"title": "Apple launches new iPhone", "summary": "Summary here.", "date": "2026-05-15", "sentiment": "positive"},
            ],
            "competitive_position": "Apple is the dominant player in premium smartphones with strong ecosystem lock-in.",
        })

        yf_info = {"ticker": "AAPL", "name": "Apple Inc."}
        tavily = [{"title": "Apple news", "url": "https://example.com", "content": "Apple launches iPhone."}]

        result = _synthesize_overview("AAPL", yf_info, tavily, "en")
        assert result["company_profile"]["name"] == "Apple Inc."
        assert result["company_profile"]["employees"] == 164000
        assert result["key_financials"]["market_cap"] == 3000000000000
        assert len(result["recent_developments"]) == 1
        assert "competitive_position" in result

    @patch("backend.codex_provider._codex_chat")
    def test_llm_returns_markdown_wrapped_json(self, mock_codex):
        """LLM wraps JSON in ```json fence → still parsed correctly."""
        mock_codex.return_value = '```json\n{"company_profile":{"name":"TestCo"},"business_description":"...","key_financials":{"market_cap":1000},"recent_developments":[],"competitive_position":"..."}\n```'

        result = _synthesize_overview("TST", {}, [], "en")
        assert result["company_profile"]["name"] == "TestCo"

    @patch("backend.codex_provider._codex_chat")
    def test_llm_failure_fallback(self, mock_codex):
        """LLM unavailable → graceful fallback with raw data."""
        mock_codex.return_value = None

        yf_info = {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"}
        result = _synthesize_overview("AAPL", yf_info, [], "en")

        # Should have fallback structure with available data
        assert result["company_profile"]["name"] == "Apple Inc."
        assert result["company_profile"]["sector"] == "Technology"
        assert "business_description" in result
        assert "key_financials" in result

    @patch("backend.codex_provider._codex_chat")
    def test_llm_invalid_json_fallback(self, mock_codex):
        """LLM returns garbage → graceful fallback."""
        mock_codex.return_value = "Sorry, I cannot do that right now."

        yf_info = {"ticker": "MSFT", "name": "Microsoft Corp."}
        result = _synthesize_overview("MSFT", yf_info, [], "en")
        assert result["company_profile"]["name"] == "Microsoft Corp."


# ── INTEGRATION: get_company_overview ────────────────────────────────────

class TestGetCompanyOverview:
    """End-to-end: cache → fetch → synthesize."""

    @patch("backend.company_overview._fetch_yahoo_info")
    @patch("backend.company_overview._search_tavily_overview")
    @patch("backend.company_overview._synthesize_overview")
    @pytest.mark.asyncio
    async def test_happy_path(self, mock_synth, mock_tavily, mock_yf, tmp_path, monkeypatch):
        """Full flow: cache miss → fetch → synthesize → cache → return."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        mock_yf.return_value = {"ticker": "AAPL", "name": "Apple Inc."}
        mock_tavily.return_value = [{"title": "News", "url": "https://x.com"}]
        mock_synth.return_value = {"company_profile": {"name": "Apple Inc."}, "business_description": "..."}

        result = await get_company_overview("AAPL")

        assert result["company_profile"]["name"] == "Apple Inc."
        mock_yf.assert_called_once_with("AAPL")
        mock_tavily.assert_called_once()
        mock_synth.assert_called_once()

    @patch("backend.company_overview._fetch_yahoo_info")
    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self, mock_yf, tmp_path, monkeypatch):
        """Second call uses cache, skips API calls."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        # Pre-populate cache
        _overview_cache_set("AAPL", "en", {"cached": True})

        result = await get_company_overview("AAPL")
        assert result == {"cached": True}
        mock_yf.assert_not_called()

    @patch("backend.company_overview._fetch_yahoo_info")
    @patch("backend.company_overview._search_tavily_overview")
    @patch("backend.company_overview._synthesize_overview")
    @pytest.mark.asyncio
    async def test_language_jp(self, mock_synth, mock_tavily, mock_yf, tmp_path, monkeypatch):
        """JP language parameter flows through to LLM synthesis."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        mock_yf.return_value = {"ticker": "AAPL"}
        mock_tavily.return_value = []
        mock_synth.return_value = {"company_profile": {"name": "Apple"}}

        result = await get_company_overview("AAPL", language="jp")
        # Verify language was passed to synthesis
        call_args = mock_synth.call_args
        assert call_args[0][3] == "jp"  # 4th positional arg is language
        assert result["company_profile"]["name"] == "Apple"
