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
        import requests
        from backend.sources_collector import _get_stock_data_finnhub
        
        call_count = [0]
        
        def mock_get(url, timeout=10):
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
        
        with patch("requests.get", side_effect=mock_get):
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
        
        with patch("requests.get", side_effect=mock_get):
            result = _get_stock_data_finnhub("AAPL")
        
        # Should return None gracefully after exhausting retries
        assert result is None

    def test_finnhub_handles_timeout(self):
        """RED: Finnhub timeout should not crash, return None after retries."""
        import requests
        from backend.sources_collector import _get_stock_data_finnhub
        
        def mock_get(url, timeout=10):
            raise requests.Timeout("Connection timed out")
        
        with patch("requests.get", side_effect=mock_get):
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
