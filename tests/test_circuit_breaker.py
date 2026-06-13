"""
Circuit breaker tests — TDD RED phase.
Tests that will FAIL until retry/backoff logic is implemented.
"""

import pytest
from unittest.mock import patch, MagicMock

# ═══════════════════════════════════════════════════════════════════
# PHASE 1 — RED: These tests WILL FAIL
# ═══════════════════════════════════════════════════════════════════


class TestCircuitBreakerFinnhub:
    """Finnhub should retry on 429 with exponential backoff."""

    def test_finnhub_retries_on_429(self):
        """RED: Finnhub 429 should trigger retry, not immediate failure."""
        import httpx
        from backend.sources_collector import _get_stock_data_finnhub
        
        call_count = [0]
        
        def mock_get(url, timeout=10, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] <= 2:
                resp.status_code = 429
                resp.headers = {"Retry-After": "1"}
            else:
                resp.status_code = 200
                resp.json.return_value = {
                    "name": "Apple Inc",
                    "finnhubIndustry": "Technology",
                    "marketCapitalization": 2800000,
                    "currency": "USD",
                }
            return resp
        
        with patch("backend.http_client.http.get", side_effect=mock_get):
            result = _get_stock_data_finnhub("AAPL")
        
        # Should succeed after retries
        assert result is not None
        assert result["company_name"] == "Apple Inc"
        assert call_count[0] >= 3, f"Expected 3+ calls (2 failures + 1 success), got {call_count[0]}"

    def test_finnhub_gives_up_after_max_retries(self):
        """RED: After max retries, Finnhub should return None, not crash."""
        from backend.sources_collector import _get_stock_data_finnhub
        
        def mock_get(url, timeout=10):
            resp = MagicMock()
            resp.status_code = 429
            resp.headers = {"Retry-After": "0"}
            return resp
        
        with patch("backend.http_client.http.get", side_effect=mock_get):
            result = _get_stock_data_finnhub("AAPL")
        
        # Should return None gracefully after exhausting retries
        assert result is None

    def test_finnhub_handles_timeout(self):
        """RED: Finnhub timeout should not crash, return None after retries."""
        import httpx
        from backend.sources_collector import _get_stock_data_finnhub
        
        def mock_get(url, timeout=10, **kwargs):
            raise httpx.TimeoutException("Connection timed out")
        
        with patch("backend.http_client.http.get", side_effect=mock_get):
            result = _get_stock_data_finnhub("AAPL")
        
        assert result is None


class TestSourcesManifestAccuracy:
    """sources_manifest should reflect actual data source."""

    def test_get_stock_data_returns_source_info(self):
        """RED: get_stock_data should include _source field."""
        from backend.sources_collector import get_stock_data
        
        # This will hit cache → None, then try live APIs
        # We just check the structure exists
        with patch("backend.sources_collector._cache_get", return_value={
            "ticker": "AAPL",
            "company_name": "Apple",
            "price": 185.0,
            "currency": "USD",
            "sector": "Technology",
            "market_cap": 2.8e12,
            "financials": {},
            "_source": "cache",
        }):
            result = get_stock_data("AAPL")
            assert "_source" in result, f"Expected _source in result, got keys: {list(result.keys())}"
            assert result["_source"] in ("cache", "yfinance", "finnhub", "twelvedata")

    def test_finnhub_result_enriched_with_yfinance_profile_even_when_financials_complete(self):
        """Company Overview needs rich identity fields, not just financials."""
        from backend.sources_collector import get_stock_data

        finnhub_result = {
            "ticker": "NVDA",
            "company_name": "NVIDIA Corp",
            "price": 180.0,
            "currency": "USD",
            "sector": "Technology",
            "market_cap": 4.4e12,
            "financials": {
                "revenue_quarterly": 81_615_000_000,
                "revenue_annual": 130_497_000_000,
                "net_income": 72_880_000_000,
                "free_cash_flow": 60_853_000_000,
            },
            "pe_current": 50.0,
            "pe_forward": 30.0,
            "peg_ratio": 0.7,
        }
        yfinance_profile = {
            "website": "https://www.nvidia.com",
            "employees": 36_000,
            "headquarters": "Santa Clara, CA, United States",
            "company_officers": [{"title": "President and CEO", "name": "Mr. Jen-Hsun Huang"}],
        }

        with patch("backend.sources_collector._cache_get", return_value=None), \
             patch("backend.sources_collector._get_stock_data_finnhub", return_value=finnhub_result), \
             patch("backend.sources_collector._cache_get_yf", return_value=yfinance_profile), \
             patch("backend.sources_collector._cache_set"):
            result = get_stock_data("NVDA")

        assert result["website"] == "https://www.nvidia.com"
        assert result["company_officers"][0]["name"] == "Mr. Jen-Hsun Huang"
        assert result["financials"]["revenue_quarterly"] == 81_615_000_000
