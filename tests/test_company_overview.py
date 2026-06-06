"""Tests for company_overview.py — yfinance + Tavily + LLM synthesis + 7d cache.

⚠️ Tests the 2-step language separation:
  Step 1 — EN: _synthesize_overview_en() → English content
  Step 2 — JP: _translate_overview_to_jp() → separate LLM translation call
"""

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
    _resolve_key_financials,
    _apply_key_financials_provenance,
    _parse_llm_response,
    _synthesize_overview_en,
    _translate_overview_to_jp,
    get_company_overview,
)


def _cacheable(data=None):
    payload = dict(data or {})
    payload.setdefault("key_financials_provenance", {
        "schema_version": 1,
        "fields": {},
    })
    return payload


# ── CACHE TESTS ──────────────────────────────────────────────────────────

class TestCacheLayer:
    """File-based JSON cache with 7-day TTL, format: company_overview:{ticker}:{lang}:v{N}"""

    def test_cache_path_uppercase(self):
        path = _overview_cache_path("aapl", "en")
        assert path.name == "company_overview_AAPL_en_v2.json"

    def test_cache_path_lowercase_input(self):
        path = _overview_cache_path("nvdA", "jp")
        assert path.name == "company_overview_NVDA_jp_v2.json"

    def test_cache_set_and_get(self, tmp_path, monkeypatch):
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        data = _cacheable({"company_profile": {"name": "TestCo"}})
        _overview_cache_set("TEST", "en", data)

        result = _overview_cache_get("TEST", "en")
        assert result == data

    def test_cache_miss_nonexistent(self, tmp_path, monkeypatch):
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)

        result = _overview_cache_get("NOPE", "en")
        assert result is None

    def test_cache_expired(self, tmp_path, monkeypatch):
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        data = _cacheable({"test": True})
        _overview_cache_set("OLD", "en", data)

        cache_path = _overview_cache_path("OLD", "en")
        with open(cache_path) as f:
            entry = json.load(f)
        entry["timestamp"] = datetime.now(timezone.utc).timestamp() - OVERVIEW_CACHE_TTL - 3600
        with open(cache_path, "w") as f:
            json.dump(entry, f)

        result = _overview_cache_get("OLD", "en")
        assert result is None

    def test_cache_version_mismatch(self, tmp_path, monkeypatch):
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        data = _cacheable({"test": True})
        _overview_cache_set("VER", "en", data)

        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 100)

        result = _overview_cache_get("VER", "en")
        assert result is None

    def test_cache_language_isolation(self, tmp_path, monkeypatch):
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        _overview_cache_set("AAPL", "en", _cacheable({"lang": "en"}))
        _overview_cache_set("AAPL", "jp", _cacheable({"lang": "jp"}))

        en = _overview_cache_get("AAPL", "en")
        jp = _overview_cache_get("AAPL", "jp")
        assert en is not None
        assert jp is not None
        assert en["lang"] == "en"
        assert jp["lang"] == "jp"


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
        assert result["employees"] == 164000
        assert result["market_cap"] == 3000000000000
        assert result["pe_trailing"] == 30.5
        assert result["pe_forward"] == 28.0
        assert result["52w_high"] == 199.62
        assert result["total_revenue"] == 383285000000

    def test_minimal_info(self):
        info = {"longName": "SmallCo", "marketCap": 50000000}
        result = _build_yahoo_info_dict("SML", info)
        assert result["ticker"] == "SML"
        assert result["name"] == "SmallCo"
        assert result["market_cap"] == 50000000
        assert result["sector"] is None

    def test_missing_keys_default_none(self):
        info = {}
        result = _build_yahoo_info_dict("TST", info)
        assert result["ticker"] == "TST"
        assert result["name"] is None


# ── EN SYNTHESIS (Step 1) ────────────────────────────────────────────────

class TestSynthesizeOverviewEn:
    """Step 1 — English: LLM generates structured company overview in English."""

    @patch("backend.codex_provider._codex_chat")
    def test_returns_structured_json(self, mock_codex):
        mock_codex.return_value = json.dumps({
            "company_profile": {
                "name": "Apple Inc.", "ticker": "AAPL",
                "sector": "Technology", "industry": "Consumer Electronics",
                "country": "United States", "website": "https://www.apple.com",
                "employees": 164000, "founded": 1976, "headquarters": "Cupertino, CA",
            },
            "business_description": "Apple designs smartphones and computers.",
            "key_financials": {
                "market_cap": 3000000000000, "market_cap_display": "$3.00T",
                "revenue": 383285000000, "revenue_display": "$383.3B",
                "pe_ratio": 30.5, "pe_forward": 28.0,
                "dividend_yield": 0.0052, "beta": 1.25,
                "52w_high": 199.62, "52w_low": 124.17,
            },
            "recent_developments": [
                {"title": "Apple launches new iPhone", "summary": "Summary.", "date": "2026-05-15", "sentiment": "positive"},
            ],
            "competitive_position": "Dominant player in premium smartphones.",
        })

        yf_info = {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "market_cap": 3000000000000,
            "total_revenue": 383285000000,
            "pe_trailing": 30.5,
            "pe_forward": 28.0,
            "dividend_yield": 0.0052,
            "beta": 1.25,
            "52w_high": 199.62,
            "52w_low": 124.17,
        }
        tavily = [{"title": "Apple news", "url": "https://example.com", "content": "Apple launches iPhone."}]

        result = _synthesize_overview_en("AAPL", yf_info, tavily)
        assert result["company_profile"]["name"] == "Apple Inc."
        assert result["company_profile"]["employees"] == 164000
        assert result["key_financials"]["market_cap"] == 3000000000000
        assert result["key_financials_provenance"]["fields"]["market_cap"]["selected_source"] == "yahoo_snapshot"
        assert result["key_financials_provenance"]["fields"]["market_cap"]["candidates"][-1]["source"] == "llm_output"
        assert len(result["recent_developments"]) == 1
        assert "competitive_position" in result

    @patch("backend.codex_provider._codex_chat")
    def test_llm_returns_markdown_wrapped_json(self, mock_codex):
        mock_codex.return_value = '```json\n{"company_profile":{"name":"TestCo"},"business_description":"...","key_financials":{"market_cap":1000},"recent_developments":[],"competitive_position":"..."}\n```'
        result = _synthesize_overview_en("TST", {}, [])
        assert result["company_profile"]["name"] == "TestCo"

    @patch("backend.codex_provider._codex_chat")
    def test_company_overview_uses_codex_spark_medium_by_default(self, mock_codex):
        mock_codex.return_value = json.dumps({
            "company_profile": {"name": "SparkCo"},
            "business_description": "Detailed investor overview.",
            "key_financials": {"market_cap": 1000},
            "recent_developments": [],
            "competitive_position": "Strong niche position.",
        })
        result = _synthesize_overview_en("SPRK", {}, [])
        assert result["company_profile"]["name"] == "SparkCo"
        _, kwargs = mock_codex.call_args
        assert kwargs["model"] == "gpt-5.3-codex-spark"
        assert kwargs["reasoning_effort"] == "medium"

    def test_parse_llm_response_accepts_first_json_with_trailing_object(self):
        first = json.dumps({
            "company_profile": {"name": "SparkCo"},
            "business_description": "Detailed investor overview.",
            "key_financials": {"market_cap": 1000},
            "recent_developments": [],
            "competitive_position": "Strong niche position.",
        })
        second = json.dumps({"debug": "duplicate object that Spark may append"})
        result = _parse_llm_response(first + "\n" + second, "SPRK", {})
        assert result is not None
        assert result["company_profile"]["name"] == "SparkCo"
        assert "debug" not in result

    @patch("backend.kimi_provider._deepseek_chat")
    @patch("backend.codex_provider._codex_chat")
    def test_llm_failure_fallback(self, mock_codex, mock_deepseek):
        mock_codex.return_value = None
        mock_deepseek.return_value = None
        yf_info = {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology"}
        result = _synthesize_overview_en("AAPL", yf_info, [])
        assert result["company_profile"]["name"] == "Apple Inc."
        assert result["company_profile"]["sector"] == "Technology"

    @patch("backend.kimi_provider._deepseek_chat")
    @patch("backend.codex_provider._codex_chat")
    def test_llm_invalid_json_fallback(self, mock_codex, mock_deepseek):
        mock_codex.return_value = "Sorry, I cannot do that right now."
        mock_deepseek.return_value = None
        yf_info = {"ticker": "MSFT", "name": "Microsoft Corp."}
        result = _synthesize_overview_en("MSFT", yf_info, [])
        assert result["company_profile"]["name"] == "Microsoft Corp."

    @patch("backend.codex_provider._codex_chat")
    def test_no_language_param(self, mock_codex):
        """_synthesize_overview_en takes only 3 args: ticker, yf_info, tavily_results."""
        mock_codex.return_value = json.dumps({
            "company_profile": {"name": "Test"}, "business_description": "desc",
            "key_financials": {"market_cap": 100}, "recent_developments": [],
            "competitive_position": "pos",
        })
        result = _synthesize_overview_en("TST", {}, [])
        assert result["company_profile"]["name"] == "Test"


# ── CANONICAL KEY FINANCIALS RESOLVER ─────────────────────────────────────

class TestCanonicalKeyFinancialsResolver:
    """Backend resolver owns numeric key_financials and provenance once."""

    @pytest.mark.parametrize(
        "ticker,market_cap,revenue,pe,beta",
        [
            ("NVDA", 3_200_000_000_000, 130_000_000_000, 45.5, 1.75),
            ("AAPL", 3_000_000_000_000, 383_285_000_000, 30.5, 1.25),
            ("GOOGL", 2_100_000_000_000, 350_018_000_000, 24.0, 1.05),
        ],
    )
    def test_selects_authoritative_yahoo_values_with_provenance(self, ticker, market_cap, revenue, pe, beta):
        selected, provenance = _resolve_key_financials(
            ticker,
            yahoo_snapshot={
                "market_cap": market_cap,
                "total_revenue": revenue,
                "pe_trailing": pe,
                "beta": beta,
                "52w_low": 100.0,
                "52w_high": 200.0,
            },
            llm_financials={
                "market_cap": market_cap * 10,
                "revenue": revenue * 10,
                "pe_ratio": 999,
                "beta": 9,
            },
        )

        assert selected["market_cap"] == market_cap
        assert selected["revenue"] == revenue
        assert selected["pe_ratio"] == pe
        assert selected["beta"] == beta
        assert provenance["schema_version"] == 1
        assert provenance["ticker"] == ticker
        assert provenance["fields"]["market_cap"]["selected_source"] == "yahoo_snapshot"
        assert provenance["fields"]["market_cap"]["candidates"][-1]["source"] == "llm_output"
        assert provenance["fields"]["market_cap"]["candidates"][-1]["non_authoritative"] is True

    def test_blocks_mismatched_ledger_and_yahoo_market_cap(self):
        selected, provenance = _resolve_key_financials(
            "NVDA",
            ledger={"market_cap": 3_200_000_000_000},
            yahoo_snapshot={"market_cap": 2_000_000_000_000},
        )

        assert selected["market_cap"] is None
        field = provenance["fields"]["market_cap"]
        assert field["status"] == "blocked"
        assert field["reason_code"] == "mismatch_blocked"
        assert field["display_value"] == "Not available"
        assert field["comparison"]["accepted"] is False

    def test_apply_overlays_llm_numbers_with_canonical_backend_values(self):
        overview = {"key_financials": {"market_cap": 1, "revenue": 2}}
        result = _apply_key_financials_provenance(
            overview,
            "AAPL",
            yahoo_snapshot={"market_cap": 3_000_000_000_000, "total_revenue": 383_285_000_000},
        )

        assert result["key_financials"]["market_cap"] == 3_000_000_000_000
        assert result["key_financials"]["revenue"] == 383_285_000_000
        assert result["key_financials_provenance"]["fields"]["market_cap"]["selected_source"] == "yahoo_snapshot"
        assert result["source_snapshot_metadata"]["schema_version"] == 1


# ── JP TRANSLATION (Step 2) ──────────────────────────────────────────────

class TestTranslateOverviewToJp:
    """Step 2 — Japanese: translate EN overview text fields via separate LLM call."""

    @patch("backend.codex_provider._codex_chat")
    def test_translates_text_fields(self, mock_codex):
        """EN overview → JP translation via separate LLM call."""
        en_overview = {
            "company_profile": {"name": "Apple Inc.", "ticker": "AAPL"},
            "business_description": "Apple designs smartphones and computers.",
            "key_financials": {"market_cap": 3000000000000},
            "recent_developments": [
                {"title": "New iPhone Launch", "summary": "Apple launched iPhone 18.", "sentiment": "positive"},
            ],
            "competitive_position": "Apple dominates the premium smartphone market.",
        }

        mock_codex.return_value = json.dumps({
            "business_description": "Appleはスマートフォンとコンピュータを設計・製造しています。",
            "competitive_position": "Appleはプレミアムスマートフォン市場を支配しています。",
            "dev_0_title": "新型iPhone発表",
            "dev_0_summary": "AppleがiPhone 18を発売しました。",
        })

        result = _translate_overview_to_jp(en_overview, "AAPL")
        assert result["business_description"] == "Appleはスマートフォンとコンピュータを設計・製造しています。"
        assert result["competitive_position"] == "Appleはプレミアムスマートフォン市場を支配しています。"
        assert result["recent_developments"][0]["title"] == "新型iPhone発表"
        assert result["recent_developments"][0]["summary"] == "AppleがiPhone 18を発売しました。"
        # Non-text fields preserved
        assert result["company_profile"]["name"] == "Apple Inc."
        assert result["key_financials"]["market_cap"] == 3000000000000

    @patch("backend.codex_provider._codex_chat")
    def test_translation_failure_fallback(self, mock_codex):
        """LLM unavailable → fallback returns EN content with marker."""
        mock_codex.return_value = None
        en_overview = {
            "company_profile": {"name": "Apple Inc."},
            "business_description": "Designs smartphones.",
            "key_financials": {},
            "recent_developments": [],
            "competitive_position": "Market leader.",
        }

        result = _translate_overview_to_jp(en_overview, "AAPL")
        assert result["company_profile"]["name"] == "Apple Inc."
        assert result["business_description"] == "Designs smartphones."  # EN fallback
        assert "_translation_note" in result


# ── INTEGRATION: get_company_overview ────────────────────────────────────

class TestGetCompanyOverview:
    """End-to-end: cache → fetch → synthesize (2-step for JP)."""

    @patch("backend.company_overview._fetch_yahoo_info")
    @patch("backend.company_overview._search_tavily_overview")
    @patch("backend.company_overview._synthesize_overview_en")
    @pytest.mark.asyncio
    async def test_en_happy_path(self, mock_synth, mock_tavily, mock_yf, tmp_path, monkeypatch):
        """EN: cache miss → fetch → synthesize_en → cache → return."""
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
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        _overview_cache_set("AAPL", "en", _cacheable({"cached": True}))

        result = await get_company_overview("AAPL")
        assert result is not None
        assert result["cached"] is True
        mock_yf.assert_not_called()

    @patch("backend.company_overview._fetch_yahoo_info")
    @patch("backend.company_overview._search_tavily_overview")
    @patch("backend.company_overview._synthesize_overview_en")
    @patch("backend.company_overview._translate_overview_to_jp")
    @pytest.mark.asyncio
    async def test_jp_two_step(self, mock_translate, mock_synth, mock_tavily, mock_yf, tmp_path, monkeypatch):
        """JP: Step 1 → EN synthesis, Step 2 → JP translation (two separate LLM calls)."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        mock_yf.return_value = {"ticker": "AAPL"}
        mock_tavily.return_value = []

        en_data = {"company_profile": {"name": "Apple"}, "business_description": "EN desc"}
        jp_data = {"company_profile": {"name": "Apple"}, "business_description": "JPの説明"}

        mock_synth.return_value = en_data
        mock_translate.return_value = jp_data

        result = await get_company_overview("AAPL", language="jp")

        # Verify two-step: EN synthesis called, then JP translation called
        mock_synth.assert_called_once()  # Step 1: EN
        mock_translate.assert_called_once()  # Step 2: JP translate

        # Returned data is JP translation, not raw EN
        assert result["business_description"] == "JPの説明"

    @patch("backend.company_overview._fetch_yahoo_info")
    @patch("backend.company_overview._search_tavily_overview")
    @patch("backend.company_overview._synthesize_overview_en")
    @patch("backend.company_overview._translate_overview_to_jp")
    @pytest.mark.asyncio
    async def test_jp_caches_en_first(self, mock_translate, mock_synth, mock_tavily, mock_yf, tmp_path, monkeypatch):
        """JP request: EN synthesis result is cached separately before translation."""
        import backend.company_overview as cov
        monkeypatch.setattr(cov, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 99)

        mock_yf.return_value = {"ticker": "AAPL"}
        mock_tavily.return_value = []

        en_data = {"company_profile": {"name": "Apple"}, "business_description": "EN desc"}
        jp_data = {"company_profile": {"name": "Apple"}, "business_description": "JPの説明"}

        mock_synth.return_value = en_data
        mock_translate.return_value = jp_data

        await get_company_overview("AAPL", language="jp")

        # EN cache should exist
        en_cached = _overview_cache_get("AAPL", "en")
        assert en_cached is not None
        assert en_cached["company_profile"] == en_data["company_profile"]

        # JP cache should exist
        jp_cached = _overview_cache_get("AAPL", "jp")
        assert jp_cached is not None
        assert jp_cached["company_profile"] == jp_data["company_profile"]
