"""Tests for /api/valuation/{ticker} V2.3 endpoint.

Covers: schema validation, successful response, EUR conversion,
error handling, and yfinance enrichment.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.models import ValuationV2Response

# ── V2.3 contract: 18 required fields ──────────────────────────────
REQUIRED_FIELDS = [
    "ticker", "exchange", "quote_currency", "display_currency",
    "price", "price_eur", "market_cap", "market_cap_eur",
    "enterprise_value", "shares_outstanding",
    "cash_and_equivalents", "total_debt",
    "quote_timestamp", "fundamentals_timestamp",
    "fx_rate_eur", "fx_timestamp",
    "source", "status",
]


# ── Sample data fixtures ───────────────────────────────────────────

@pytest.fixture
def mock_stock_data():
    """Standard stock data matching the Finnhub cache format."""
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3000000000000.0,
        "price": 185.50,
        "prev_close": 184.00,
        "currency": "USD",
        "financials": {
            "revenue_quarterly": 95000000000.0,
            "net_income": 22000000000.0,
            "net_debt": None,
        },
        "pe_current": 30.5,
        "pe_forward": 28.0,
        "_source": "finnhub",
    }


@pytest.fixture
def mock_yf_info():
    """yfinance .info dict with enrichment fields."""
    return {
        "exchange": "NMS",
        "exchangeName": "NASDAQ",
        "enterpriseValue": 3100000000000.0,
        "sharesOutstanding": 15500000000,
        "totalCash": 65000000000,
        "totalDebt": 110000000000,
    }


@pytest.fixture
def mock_fx_info():
    """EUR/USD FX rate from yfinance."""
    return {
        "regularMarketPrice": 1.08,
        "currentPrice": 1.08,
    }


# ═══════════════════════════════════════════════════════════════════
# SCHEMA VALIDATION — 2 tests
# ═══════════════════════════════════════════════════════════════════


class TestSchemaValidation:

    def test_model_has_all_18_fields(self):
        """ValuationV2Response must have exactly 18 fields matching V2.3 contract."""
        fields = list(ValuationV2Response.model_fields.keys())
        assert len(fields) == 18, f"Expected 18 fields, got {len(fields)}: {fields}"
        for field in REQUIRED_FIELDS:
            assert field in fields, f"Missing required field: {field}"

    def test_default_values(self):
        """Default values for non-optional fields should be sensible."""
        resp = ValuationV2Response(ticker="TEST")
        assert resp.ticker == "TEST"
        assert resp.quote_currency == "USD"
        assert resp.display_currency == "EUR"
        assert resp.source == "unknown"
        assert resp.status == "ok"
        assert resp.price is None
        assert resp.exchange is None


# ═══════════════════════════════════════════════════════════════════
# VALUATION LAYER — 4 tests
# ═══════════════════════════════════════════════════════════════════


class TestValuationLayer:

    def test_successful_fetch_all_fields(self, mock_stock_data, mock_yf_info, mock_fx_info):
        """Full fetch returns all 18 fields with computed EUR equivalents."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", return_value=mock_stock_data):
            with patch("backend.valuation._yf_ticker_safe") as mock_yt:
                with patch("backend.valuation._load_yfinance") as mock_yf:
                    # yfinance ticker for the stock (exchange, EV, shares, cash, debt)
                    mock_ticker = MagicMock()
                    mock_ticker.info = mock_yf_info
                    mock_yt.return_value = mock_ticker

                    # yfinance ticker for EUR/USD FX
                    mock_fx = MagicMock()
                    mock_fx.info = mock_fx_info
                    mock_yf.return_value.Ticker.return_value = mock_fx

                    resp = get_valuation("AAPL")

        assert resp.ticker == "AAPL"
        assert resp.exchange == "NMS"
        assert resp.quote_currency == "USD"
        assert resp.display_currency == "EUR"
        assert resp.price == 185.50
        assert resp.market_cap == 3000000000000.0
        assert resp.enterprise_value == 3100000000000.0
        assert resp.shares_outstanding == 15500000000
        assert resp.cash_and_equivalents == 65000000000
        assert resp.total_debt == 110000000000
        assert resp.source == "finnhub"
        assert resp.status == "ok"

        # EUR conversion
        assert resp.fx_rate_eur == 1.08
        assert resp.price_eur == round(185.50 * 1.08, 2)
        assert resp.market_cap_eur == round(3000000000000.0 * 1.08, 2)

        # Timestamps
        assert resp.quote_timestamp is not None
        assert resp.fundamentals_timestamp is not None
        assert resp.fx_timestamp is not None

    def test_empty_stock_data_returns_error(self):
        """When get_stock_data returns None, status=error."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", return_value=None):
            resp = get_valuation("ZZZZZ")

        assert resp.ticker == "ZZZZZ"
        assert resp.status == "error"
        assert resp.price is None
        assert resp.market_cap is None

    def test_stock_data_exception_returns_error(self):
        """When get_stock_data raises, status=error."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", side_effect=RuntimeError("API down")):
            resp = get_valuation("AAPL")

        assert resp.status == "error"

    def test_missing_fx_rate_still_returns_data(self, mock_stock_data):
        """When FX rate is unavailable, EUR fields are None but USD data present."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", return_value=mock_stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=TimeoutError):
                resp = get_valuation("AAPL")

        assert resp.status == "ok"  # price + market_cap present
        assert resp.price == 185.50
        assert resp.market_cap == 3000000000000.0
        assert resp.price_eur is None
        assert resp.market_cap_eur is None
        assert resp.fx_rate_eur is None


# ═══════════════════════════════════════════════════════════════════
# ENDPOINT INTEGRATION — 2 tests
# ═══════════════════════════════════════════════════════════════════


class TestValuationEndpoint:

    def test_valid_ticker_returns_200(self, mock_stock_data, mock_yf_info, mock_fx_info):
        """GET /api/valuation/AAPL returns 200 with V2.3 data."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.valuation.get_stock_data", return_value=mock_stock_data):
            with patch("backend.valuation._yf_ticker_safe") as mock_yt:
                with patch("backend.valuation._load_yfinance") as mock_yf:
                    mock_ticker = MagicMock()
                    mock_ticker.info = mock_yf_info
                    mock_yt.return_value = mock_ticker

                    mock_fx = MagicMock()
                    mock_fx.info = mock_fx_info
                    mock_yf.return_value.Ticker.return_value = mock_fx

                    response = client.get("/api/valuation/AAPL")

        assert response.status_code == 200
        data = response.json()
        for field in REQUIRED_FIELDS:
            assert field in data, f"Missing field in response: {field}"
        assert data["ticker"] == "AAPL"
        assert data["status"] == "ok"

    def test_error_ticker_returns_200_with_error_status(self):
        """GET /api/valuation/ERROR returns 200 with status=error, not 500."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.valuation.get_stock_data", return_value=None):
            response = client.get("/api/valuation/ERROR")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "ERROR"
        assert data["status"] == "error"


# ═══════════════════════════════════════════════════════════════════
# EDGE CASES — 2 tests
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_ticker_lowercase_normalized(self):
        """Ticker 'aapl' is normalized to 'AAPL'."""
        from backend.valuation import get_valuation

        stock_data = {"ticker": "AAPL", "price": 100, "market_cap": 1e9,
                      "currency": "USD", "_source": "test"}
        with patch("backend.valuation.get_stock_data", return_value=stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=RuntimeError):
                with patch("backend.valuation._load_yfinance") as mock_yf:
                    mock_yf.return_value.Ticker.side_effect = RuntimeError
                    resp = get_valuation("aapl")

        assert resp.ticker == "AAPL"

    def test_nan_values_filtered(self):
        """NaN/inf values from yfinance are converted to None."""
        from backend.valuation import _safe_float
        import math

        assert _safe_float(None) is None
        assert _safe_float(float("nan")) is None
        assert _safe_float(float("inf")) is None
        assert _safe_float(float("-inf")) is None
        assert _safe_float("not_a_number") is None
        assert _safe_float(42.5) == 42.5
        assert _safe_float(0) == 0
