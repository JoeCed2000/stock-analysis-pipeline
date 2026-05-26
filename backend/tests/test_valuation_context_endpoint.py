"""
Tests for GET /api/valuation-context/{ticker} — V2.4 valuation context endpoint.

Covers: contract validation, successful response, unknown ticker,
historical context unavailability, and metadata preservation.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ── Expected response contract fields ──────────────────────────────────
REQUIRED_TOP_FIELDS = [
    "ticker", "currency", "valuation", "context",
    "historical_context", "source", "status", "quote_timestamp",
]

REQUIRED_VALUATION_FIELDS = [
    "pe_ttm", "ps_ttm", "ev_ebitda", "p_fcf", "fcf_yield",
    "eps_growth", "revenue_growth", "ebitda_growth", "fcf_growth",
]

REQUIRED_CONTEXT_FIELDS = [
    "peg_ttm", "ps_vs_growth", "ev_ebitda_vs_growth",
    "p_fcf_vs_growth", "fcf_yield_context",
    "valuation_support", "context_summary",
]


# ── Mock fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_yf_info_nvda():
    """Rich yfinance info for NVDA — growth + multiples available."""
    return {
        "trailingPE": 42.5,
        "forwardPE": 32.0,
        "priceToSalesTrailing12Months": 22.1,
        "enterpriseToEbitda": 35.0,
        "freeCashflow": 15600000000.0,
        "operatingCashflow": 18000000000.0,
        "marketCap": 2800000000000.0,
        "enterpriseValue": 2900000000000.0,
        "sharesOutstanding": 24600000000,
        "totalCash": 30000000000.0,
        "totalDebt": 12000000000.0,
        "revenueGrowth": 0.12,
        "earningsGrowth": 0.15,
        "ebitdaGrowth": 0.18,
        "pegRatio": 2.83,
        "currency": "USD",
        "exchange": "NASDAQ",
        "longName": "NVIDIA Corporation",
    }


@pytest.fixture
def mock_yf_info_thin():
    """Thin yfinance info — limited data, no growth."""
    return {
        "trailingPE": None,
        "priceToSalesTrailing12Months": 0.5,
        "enterpriseToEbitda": None,
        "freeCashflow": None,
        "marketCap": 50000000.0,
        "enterpriseValue": None,
        "sharesOutstanding": 100000000,
        "revenueGrowth": None,
        "earningsGrowth": None,
        "ebitdaGrowth": None,
        "pegRatio": None,
        "currency": "USD",
        "exchange": None,
        "longName": None,
    }


@pytest.fixture
def mock_yf_info_empty():
    """Empty yfinance info — ticker not found."""
    return {
        "trailingPE": None,
        "priceToSalesTrailing12Months": None,
        "enterpriseToEbitda": None,
        "freeCashflow": None,
        "marketCap": None,
        "enterpriseValue": None,
        "sharesOutstanding": None,
        "revenueGrowth": None,
        "earningsGrowth": None,
        "ebitdaGrowth": None,
        "pegRatio": None,
        "currency": None,
        "exchange": None,
        "longName": None,
    }


# =====================================================================
# CONTRACT VALIDATION — 2 tests
# =====================================================================


class TestContractValidation:

    def test_response_contract_matches_spec(self, mock_yf_info_nvda):
        """All required top-level, valuation, and context fields present."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.valuation_context._yf_ticker_safe") as mock_yt:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_yf_info_nvda
            mock_yt.return_value = mock_ticker

            response = client.get("/api/valuation-context/NVDA")

        assert response.status_code == 200
        data = response.json()

        # Top-level fields
        for field in REQUIRED_TOP_FIELDS:
            assert field in data, f"Missing top-level field: {field}"

        # Valuation sub-object
        val = data["valuation"]
        for field in REQUIRED_VALUATION_FIELDS:
            assert field in val, f"Missing valuation field: {field}"

        # Context sub-object
        ctx = data["context"]
        for field in REQUIRED_CONTEXT_FIELDS:
            assert field in ctx, f"Missing context field: {field}"

        # Currency must be explicit USD
        assert data["currency"] == "USD"

    def test_source_status_timestamp_preserved(self, mock_yf_info_nvda):
        """source, status, and quote_timestamp are present and non-empty."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.valuation_context._yf_ticker_safe") as mock_yt:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_yf_info_nvda
            mock_yt.return_value = mock_ticker

            response = client.get("/api/valuation-context/NVDA")

        assert response.status_code == 200
        data = response.json()

        assert data["source"] is not None and data["source"] != ""
        assert data["status"] is not None and data["status"] != ""
        assert data["quote_timestamp"] is not None and data["quote_timestamp"] != ""


# =====================================================================
# SUCCESSFUL RESPONSE — 2 tests
# =====================================================================


class TestSuccessfulResponse:

    def test_valuation_context_endpoint_nvda_returns_200(self, mock_yf_info_nvda):
        """GET /api/valuation-context/NVDA returns 200 with computed context."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.valuation_context._yf_ticker_safe") as mock_yt:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_yf_info_nvda
            mock_yt.return_value = mock_ticker

            response = client.get("/api/valuation-context/NVDA")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "NVDA"
        assert data["currency"] == "USD"
        assert data["status"] in ("fresh", "available")

        # Context should have computed signals (not all n/a)
        ctx = data["context"]
        peg = ctx["peg_ttm"]
        assert peg["level"] != "n/a", f"Expected PEG to be computed, got {peg}"
        assert peg["peg_ratio"] is not None

        ps = ctx["ps_vs_growth"]
        assert ps["level"] != "n/a", f"Expected P/S vs Growth computed, got {ps}"

    def test_valuation_context_thin_ticker_returns_200(self, mock_yf_info_thin):
        """Even with limited data, endpoint returns 200 (graceful degradation)."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.valuation_context._yf_ticker_safe") as mock_yt:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_yf_info_thin
            mock_yt.return_value = mock_ticker

            response = client.get("/api/valuation-context/PENNY")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "PENNY"

        # Context should show n/a for unavailable signals
        val = data["valuation"]
        assert val["pe_ttm"] is None
        assert val["ps_ttm"] == 0.5

        # Historical context should be false
        hist = data["historical_context"]
        assert hist["available"] is False


# =====================================================================
# ERROR / EDGE CASE — 3 tests
# =====================================================================


class TestErrorHandling:

    def test_valuation_context_endpoint_unknown_ticker_returns_404(
        self, mock_yf_info_empty
    ):
        """Unknown ticker (no price, no market cap) returns 404."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.valuation_context._yf_ticker_safe") as mock_yt:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_yf_info_empty
            mock_yt.return_value = mock_ticker

            response = client.get("/api/valuation-context/ZZZZZ")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_valuation_context_historical_unavailable_returns_gracefully(
        self, mock_yf_info_nvda
    ):
        """When historical context is unavailable, endpoint still returns 200
        with historical_context.available=False and a reason string."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.valuation_context._yf_ticker_safe") as mock_yt:
            mock_ticker = MagicMock()
            mock_ticker.info = mock_yf_info_nvda
            mock_yt.return_value = mock_ticker

            response = client.get("/api/valuation-context/NVDA")

        assert response.status_code == 200
        data = response.json()
        hist = data["historical_context"]
        assert "available" in hist
        assert hist["available"] is False
        assert "reason" in hist
        assert len(hist["reason"]) > 0

    def test_yfinance_exception_returns_404(self):
        """When yfinance raises, endpoint returns 404 gracefully (no 500)."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch(
            "backend.routes.valuation_context._yf_ticker_safe",
            side_effect=RuntimeError("API down"),
        ):
            response = client.get("/api/valuation-context/CRASH")

        assert response.status_code == 404
