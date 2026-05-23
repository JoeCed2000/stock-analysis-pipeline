"""
Targeted tests for company_overview.py — 12 tests covering:

  Schema validation (4):     output structure, company_profile, key_financials, recent_developments
  Cache TTL (2):            fresh cache returned, expired cache returns None
  Thin ticker fallback (2):  minimal yf_info fallback, ticker always present
  JSON parsing (3):          escaped chars, partial JSON, non-JSON text
  End-to-end GOOGL (1):      full get_company_overview("GOOGL") integration

These complement the 21 existing tests in tests/test_company_overview.py
by covering validation, parsing edge cases, and integration gaps.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.company_overview import (
    OVERVIEW_CACHE_TTL,
    _overview_cache_get,
    _overview_cache_set,
    _overview_cache_path,
    _build_yahoo_info_dict,
    _parse_llm_response,
    _fallback_overview,
    _synthesize_overview_en,
    get_company_overview,
)

REQUIRED_TOP_KEYS = [
    "company_profile",
    "business_description",
    "key_financials",
    "recent_developments",
    "competitive_position",
]

REQUIRED_PROFILE_KEYS = [
    "name", "ticker", "sector", "industry",
    "country", "website", "employees", "founded", "headquarters",
]

REQUIRED_FINANCIAL_KEYS = [
    "market_cap", "market_cap_display", "revenue", "revenue_display",
    "pe_ratio", "pe_forward", "dividend_yield", "beta",
    "52w_high", "52w_low",
]

REQUIRED_DEV_KEYS = ["title", "summary", "sentiment"]


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION — 4 tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemaValidation:
    """Validate JSON output structure of company_overview functions."""

    def test_fallback_overview_has_all_top_level_keys(self, empty_yf_info):
        """_fallback_overview always returns the 5 required top-level keys."""
        result = _fallback_overview("ZZZZZ", empty_yf_info)

        for key in REQUIRED_TOP_KEYS:
            assert key in result, (
                f"Missing top-level key '{key}' in fallback_overview output. "
                f"Got keys: {list(result.keys())}"
            )

    def test_fallback_company_profile_has_required_subkeys(self, empty_yf_info):
        """company_profile dict in fallback has all 9 required subkeys."""
        result = _fallback_overview("ZZZZZ", empty_yf_info)
        profile = result["company_profile"]

        for key in REQUIRED_PROFILE_KEYS:
            assert key in profile, (
                f"Missing company_profile key '{key}'. Got: {list(profile.keys())}"
            )

    def test_fallback_key_financials_has_required_subkeys(self, empty_yf_info):
        """key_financials dict in fallback has all 10 required subkeys."""
        result = _fallback_overview("ZZZZZ", empty_yf_info)
        financials = result["key_financials"]

        for key in REQUIRED_FINANCIAL_KEYS:
            assert key in financials, (
                f"Missing key_financials key '{key}'. Got: {list(financials.keys())}"
            )

    def test_recent_developments_items_have_required_fields(self, sample_yf_info):
        """Each item in recent_developments has title, summary, and sentiment."""
        with patch("backend.codex_provider._codex_chat") as mock_llm:
            mock_llm.return_value = json.dumps({
                "company_profile": {"name": "TestCo", "ticker": "TEST"},
                "business_description": "A test company.",
                "key_financials": {"market_cap": 1000, "market_cap_display": "$1K", "revenue": 500, "revenue_display": "$500", "pe_ratio": None, "pe_forward": None, "dividend_yield": None, "beta": None, "52w_high": None, "52w_low": None},
                "recent_developments": [
                    {"title": "Dev 1", "summary": "Summary 1", "sentiment": "positive"},
                    {"title": "Dev 2", "summary": "Summary 2", "sentiment": "negative", "date": "2026-05-01"},
                ],
                "competitive_position": "Good.",
            })

            result = _synthesize_overview_en("TEST", sample_yf_info, [])

        devs = result["recent_developments"]
        assert len(devs) == 2

        for i, dev in enumerate(devs):
            for key in REQUIRED_DEV_KEYS:
                assert key in dev, (
                    f"development[{i}] missing key '{key}'. Got: {list(dev.keys())}"
                )
            assert dev["sentiment"] in ("positive", "neutral", "negative"), (
                f"development[{i}] sentiment must be positive|neutral|negative, got: {dev['sentiment']!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# CACHE TTL — 2 tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCacheTTL:
    """Verify cache freshness / expiry boundaries."""

    def test_cache_fresh_just_under_ttl_returns_data(self, tmp_cache_dir):
        """Data cached 1 second under TTL should still be returned."""
        data = {"fresh": True}
        _overview_cache_set("FRESH", "en", data)

        # Rewrite timestamp to be (TTL - 1) seconds ago
        path = _overview_cache_path("FRESH", "en")
        with open(path) as f:
            entry = json.load(f)
        entry["timestamp"] = datetime.now(timezone.utc).timestamp() - OVERVIEW_CACHE_TTL + 1
        with open(path, "w") as f:
            json.dump(entry, f)

        result = _overview_cache_get("FRESH", "en")
        assert result == data, "Cache should return data when 1s under TTL"

    def test_cache_exactly_expired_returns_none(self, tmp_cache_dir):
        """Data cached exactly at TTL age should return None (expired)."""
        data = {"expired": True}
        _overview_cache_set("EXP", "en", data)

        # Rewrite timestamp to be exactly TTL seconds ago
        path = _overview_cache_path("EXP", "en")
        with open(path) as f:
            entry = json.load(f)
        entry["timestamp"] = datetime.now(timezone.utc).timestamp() - OVERVIEW_CACHE_TTL
        with open(path, "w") as f:
            json.dump(entry, f)

        result = _overview_cache_get("EXP", "en")
        assert result is None, (
            f"Cache should return None when exactly at TTL ({OVERVIEW_CACHE_TTL}s). "
            "Expiry is strict: age > TTL means expired."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# THIN TICKER FALLBACK — 2 tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestThinTickerFallback:
    """Fallback behavior when yfinance returns minimal or empty data."""

    def test_fallback_for_near_empty_yf_info_produces_valid_structure(self, empty_yf_info):
        """Empty yf_info → fallback still returns the 5 top-level keys with sensible defaults."""
        result = _fallback_overview("ZZZZZ", empty_yf_info)

        # All required keys present
        for key in REQUIRED_TOP_KEYS:
            assert key in result

        # business_description uses ticker as fallback text
        assert "ZZZZZ" in result["business_description"], (
            f"Fallback description should mention ticker. Got: {result['business_description']!r}"
        )

        # recent_developments is an empty list
        assert result["recent_developments"] == []

        # key_financials has None values (not strings like "N/A" or 0)
        assert result["key_financials"]["market_cap"] is None
        assert result["key_financials"]["revenue"] is None

    def test_fallback_always_includes_ticker_in_company_profile(self, thin_yf_info):
        """Fallback company_profile.ticker always set, even when yf_info is nearly empty."""
        result = _fallback_overview("PENNY", thin_yf_info)
        profile = result["company_profile"]

        assert profile["ticker"] == "PENNY", (
            f"company_profile.ticker must always be the input ticker. Got: {profile['ticker']!r}"
        )
        # name may be None when yfinance returns null — that's upstream's signal
        # The ticker is the invariant guarantee
        assert "name" in profile, "company_profile must have a 'name' key"
        # Verify all other profile keys exist with correct types or None
        for key in ["sector", "industry", "country", "website", "founded", "headquarters"]:
            assert key in profile, f"Missing company_profile key: {key}"


# ═══════════════════════════════════════════════════════════════════════════════
# JSON PARSING — 3 tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestJsonParsing:
    """Test _parse_llm_response edge cases."""

    def test_parse_json_with_escaped_characters(self):
        """JSON with escaped quotes, newlines, unicode inside strings."""
        response = json.dumps({
            "company_profile": {"name": 'Company "Best" Inc.', "ticker": "BEST"},
            "business_description": "Line 1\\nLine 2 with \\\"quotes\\\" and \\u2605 star.",
            "key_financials": {"market_cap": 1e9, "market_cap_display": "$1.0B", "revenue": None, "revenue_display": None, "pe_ratio": None, "pe_forward": None, "dividend_yield": None, "beta": None, "52w_high": None, "52w_low": None},
            "recent_developments": [],
            "competitive_position": "Strong.",
        })

        result = _parse_llm_response(response, "BEST", {})
        assert result is not None, "Valid JSON with escaped chars should parse"
        assert result["company_profile"]["name"] == 'Company "Best" Inc.'

    def test_parse_partial_json_gets_defaults_for_missing_keys(self):
        """JSON missing some top-level keys → defaults filled in."""
        response = json.dumps({
            "company_profile": {"name": "PartialCo", "ticker": "PART"},
            # business_description intentionally omitted
            # key_financials intentionally omitted
            # recent_developments intentionally omitted
            # competitive_position intentionally omitted
        })

        result = _parse_llm_response(response, "PART", {})
        assert result is not None, "Partial JSON should still parse"
        assert result["business_description"] == "", "Missing field → empty string default"
        assert result["key_financials"] == {}, "Missing field → empty dict default"
        assert result["recent_developments"] == [], "Missing field → empty list default"
        assert result["competitive_position"] == "", "Missing field → empty string default"

    def test_parse_non_json_text_returns_none(self):
        """Plain text (not JSON) → _parse_llm_response returns None."""
        result = _parse_llm_response(
            "I'm sorry, I cannot generate that overview right now. Please try again later.",
            "FAIL",
            {},
        )
        assert result is None, "Non-JSON text should return None (caller uses fallback)"

    def test_parse_markdown_wrapped_json_with_trailing_text(self):
        """JSON wrapped in ```json``` fences with trailing commentary."""
        response = '```json\n{"company_profile":{"name":"FenceCo","ticker":"FENC"},"business_description":"Works.","key_financials":{"market_cap":100,"market_cap_display":"$100","revenue":null,"revenue_display":null,"pe_ratio":null,"pe_forward":null,"dividend_yield":null,"beta":null,"52w_high":null,"52w_low":null},"recent_developments":[],"competitive_position":"Good."}\n```\n\nLet me know if you need anything else!'

        result = _parse_llm_response(response, "FENC", {})
        assert result is not None, "Markdown-wrapped JSON should parse"
        assert result["company_profile"]["name"] == "FenceCo"
        assert result["company_profile"]["ticker"] == "FENC"


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END GOOGL INTEGRATION — 1 test
# ═══════════════════════════════════════════════════════════════════════════════


class TestGooglIntegration:
    """End-to-end: get_company_overview("GOOGL") with mocked external services."""

    @patch("backend.company_overview._fetch_yahoo_info")
    @patch("backend.company_overview._search_tavily_overview")
    @patch("backend.company_overview._synthesize_overview_en")
    @pytest.mark.asyncio
    async def test_googl_overview_end_to_end(
        self, mock_synth, mock_tavily, mock_yf, tmp_cache_dir,
    ):
        """Full pipeline for GOOGL: cache miss → fetch → synthesize → cache → return."""
        mock_yf.return_value = {
            "ticker": "GOOGL",
            "name": "Alphabet Inc.",
            "sector": "Communication Services",
            "industry": "Internet Content & Information",
            "country": "United States",
            "website": "https://abc.xyz",
            "employees": 182000,
            "description": "Alphabet is a collection of companies, including Google.",
            "market_cap": 2200000000000,
            "enterprise_value": 2100000000000,
            "current_price": 175.00,
            "previous_close": 174.00,
            "pe_trailing": 26.0,
            "pe_forward": 22.0,
            "dividend_yield": 0.004,
            "beta": 1.05,
            "52w_high": 190.00,
            "52w_low": 130.00,
            "revenue_growth": 0.12,
            "earnings_growth": 0.18,
            "total_revenue": 307000000000,
            "currency": "USD",
            "exchange": "NASDAQ",
            "headquarters": "Mountain View, CA, United States",
        }

        mock_tavily.return_value = [
            {
                "title": "Alphabet Q1 2026 Results Beat Estimates",
                "url": "https://example.com/googl-q1",
                "content": "Alphabet reported Q1 revenue of $85B.",
                "date": "2026-04-25",
            },
        ]

        mock_synth.return_value = {
            "company_profile": {
                "name": "Alphabet Inc.",
                "ticker": "GOOGL",
                "sector": "Communication Services",
                "industry": "Internet Content & Information",
                "country": "United States",
                "website": "https://abc.xyz",
                "employees": 182000,
                "founded": 2015,
                "headquarters": "Mountain View, CA, United States",
            },
            "business_description": "Alphabet is the parent company of Google, offering search, advertising, cloud, and AI services worldwide.",
            "key_financials": {
                "market_cap": 2200000000000,
                "market_cap_display": "$2.20T",
                "revenue": 307000000000,
                "revenue_display": "$307.0B",
                "pe_ratio": 26.0,
                "pe_forward": 22.0,
                "dividend_yield": 0.004,
                "beta": 1.05,
                "52w_high": 190.00,
                "52w_low": 130.00,
            },
            "recent_developments": [
                {
                    "title": "Alphabet Q1 2026 Results Beat Estimates",
                    "summary": "Alphabet reported Q1 revenue of $85B, beating estimates by 6%.",
                    "date": "2026-04-25",
                    "sentiment": "positive",
                },
            ],
            "competitive_position": "Alphabet dominates search advertising with >90% market share and is rapidly growing its cloud business.",
        }

        result = await get_company_overview("googl", language="en")

        # Verify output schema
        for key in REQUIRED_TOP_KEYS:
            assert key in result, f"GOOGL overview missing top-level key: {key}"

        # Verify ticker was normalized to uppercase
        assert result["company_profile"]["ticker"] == "GOOGL"

        # Verify company identity
        assert result["company_profile"]["name"] == "Alphabet Inc."
        assert result["key_financials"]["market_cap"] == 2200000000000

        # Verify developments
        assert len(result["recent_developments"]) == 1
        assert result["recent_developments"][0]["sentiment"] == "positive"

        # Verify data was cached
        cached = _overview_cache_get("GOOGL", "en")
        assert cached is not None, "GOOGL overview should be cached after first fetch"
        assert cached["company_profile"]["ticker"] == "GOOGL"

        # Verify external services were called
        mock_yf.assert_called_once_with("GOOGL")
        mock_tavily.assert_called_once()
        mock_synth.assert_called_once()
