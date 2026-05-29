"""Tests for /api/valuation/{ticker} V2.3 endpoint.

Covers: schema validation, successful response, ev_source tracking,
error handling, and yfinance enrichment. EUR disabled in V2.3.
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

# -- V2.3 contract: 27 required fields --------------------------------
REQUIRED_FIELDS = [
    "ticker", "exchange", "quote_currency", "display_currency",
    "price", "price_eur", "market_cap", "market_cap_eur",
    "enterprise_value", "enterprise_value_eur", "ev_source",
    "shares_outstanding",
    "cash_and_equivalents", "total_debt",
    "pe_current", "pe_forward", "peg_ratio",
    "eps_growth", "revenue_growth",
    "quote_timestamp", "fundamentals_timestamp",
    "fx_rate_eur", "fx_timestamp", "fx_status",
    "source", "served_from", "status",
]


# -- Sample data fixtures -----------------------------------------------

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
            "revenue_yoy_growth": 0.08,
            "revenue_annual_growth": 0.06,
            "eps_yoy": 0.10,
        },
        "pe_current": 30.5,
        "pe_forward": 28.0,
        "peg_ratio": 1.9,
        "expected_growth": 0.12,
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


# =====================================================================
# SCHEMA VALIDATION — 2 tests
# =====================================================================


class TestSchemaValidation:

    def test_model_has_all_27_fields(self):
        """ValuationV2Response must expose the full V2.3+ contract."""
        fields = list(ValuationV2Response.model_fields.keys())
        assert len(fields) == 27, f"Expected 27 fields, got {len(fields)}: {fields}"
        for field in REQUIRED_FIELDS:
            assert field in fields, f"Missing required field: {field}"

    def test_default_values(self):
        """Default values for non-optional fields should be sensible."""
        resp = ValuationV2Response(ticker="TEST")
        assert resp.ticker == "TEST"
        assert resp.quote_currency == "USD"
        assert resp.display_currency == "EUR"
        assert resp.source == "unknown"
        assert resp.status == "unavailable"   # V2.3 default: explicit unavailable
        assert resp.fx_status == "unavailable"  # V2.3: no live FX
        assert resp.price is None
        assert resp.exchange is None


# =====================================================================
# VALUATION LAYER — 4 tests
# =====================================================================


class TestValuationLayer:

    def test_successful_fetch_all_fields(self, mock_stock_data, mock_yf_info):
        """Full fetch returns all fields with ev_source=reported, EUR disabled."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", return_value=mock_stock_data):
            with patch("backend.valuation._yf_ticker_safe") as mock_yt:
                mock_ticker = MagicMock()
                mock_ticker.info = mock_yf_info
                mock_yt.return_value = mock_ticker

                resp = get_valuation("AAPL")

        assert resp.ticker == "AAPL"
        assert resp.exchange == "NMS"
        assert resp.quote_currency == "USD"
        assert resp.display_currency == "EUR"
        assert resp.price == 185.50
        assert resp.market_cap == 3000000000000.0
        assert resp.enterprise_value == 3100000000000.0  # reported from mock yfinance
        assert resp.ev_source == "reported"
        assert resp.shares_outstanding == 15500000000
        assert resp.cash_and_equivalents == 65000000000
        assert resp.total_debt == 110000000000
        assert resp.pe_current == 30.5
        assert resp.pe_forward == 28.0
        assert resp.peg_ratio == 1.9
        assert resp.eps_growth == 0.12
        assert resp.revenue_growth == 0.08
        assert resp.source == "finnhub"
        assert resp.served_from == "live"   # live fetch from provider
        assert resp.status in ("fresh", "cached")

        # EUR disabled in V2.3
        assert resp.price_eur is None
        assert resp.market_cap_eur is None
        assert resp.enterprise_value_eur is None
        assert resp.fx_rate_eur is None
        assert resp.fx_status == "unavailable"

        # Timestamps
        assert resp.quote_timestamp is not None
        assert resp.fundamentals_timestamp is not None
        assert resp.fx_timestamp is None  # no FX source

    def test_empty_stock_data_returns_error(self):
        """When get_stock_data returns None, status=unavailable."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", return_value=None):
            resp = get_valuation("ZZZZZ")

        assert resp.ticker == "ZZZZZ"
        assert resp.status == "unavailable"
        assert resp.price is None
        assert resp.market_cap is None

    def test_stock_data_exception_returns_error(self):
        """When get_stock_data raises, status=unavailable."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", side_effect=RuntimeError("API down")):
            resp = get_valuation("AAPL")

        assert resp.status == "unavailable"

    def test_missing_fx_rate_still_returns_data(self, mock_stock_data):
        """EUR fields are None (disabled) but USD data present."""
        from backend.valuation import get_valuation

        with patch("backend.valuation.get_stock_data", return_value=mock_stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=TimeoutError):
                resp = get_valuation("AAPL")

        assert resp.status in ("fresh", "cached")  # price + market_cap present
        assert resp.price == 185.50
        assert resp.market_cap == 3000000000000.0
        assert resp.price_eur is None           # EUR disabled in V2.3
        assert resp.market_cap_eur is None      # EUR disabled in V2.3
        assert resp.enterprise_value_eur is None  # EUR disabled in V2.3
        assert resp.fx_rate_eur is None         # EUR disabled in V2.3
        assert resp.fx_status == "unavailable"  # V2.3: no live FX

    def test_cached_na_strings_normalized(self):
        """Cache entries with string 'NA' values are converted to None."""
        from backend.valuation import get_valuation

        stock_data = {
            "ticker": "TEST", "price": "NA", "market_cap": "NA",
            "currency": "USD", "_source": "cache"
        }
        with patch("backend.valuation.get_stock_data", return_value=stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=RuntimeError):
                resp = get_valuation("TEST")
        assert resp.price is None
        assert resp.market_cap is None
        assert resp.status != "error"  # must not crash Pydantic


# =====================================================================
# ALTERNATIVE PROVIDER BACKFILL — 2 tests
# =====================================================================


class TestAlternativeProviderBackfill:

    def test_backfill_from_alpha_vantage_overview_and_balance_sheet(self):
        """Alpha Vantage payload fills missing valuation fields with normalized decimals."""
        from backend.valuation import _backfill_from_alpha_vantage

        def _fake_request(function, _ticker):
            if function == "OVERVIEW":
                return {
                    "PERatio": "24.1",
                    "ForwardPE": "21.3",
                    "PEGRatio": "1.45",
                    "QuarterlyEarningsGrowthYOY": "12.5",
                    "QuarterlyRevenueGrowthYOY": "8.2",
                }
            if function == "BALANCE_SHEET":
                return {
                    "quarterlyReports": [
                        {"shortLongTermDebtTotal": "1234567890"}
                    ]
                }
            return None

        with patch("backend.valuation._alpha_vantage_request", side_effect=_fake_request):
            out = _backfill_from_alpha_vantage(
                ticker="INTC",
                pe_current=None,
                pe_forward=None,
                peg_ratio=None,
                eps_growth=None,
                revenue_growth=None,
                total_debt=None,
            )

        assert out["pe_current"] == 24.1
        assert out["pe_forward"] == 21.3
        assert out["peg_ratio"] == 1.45
        assert out["eps_growth"] == 0.125
        assert out["revenue_growth"] == pytest.approx(0.082, rel=1e-9)
        assert out["total_debt"] == 1234567890.0

    def test_get_valuation_promotes_source_when_backfill_used(self):
        """When yfinance misses fields and fallback fills them, source becomes alpha_vantage."""
        from backend.valuation import get_valuation

        stock_data = {
            "ticker": "INTC",
            "price": 42.0,
            "market_cap": 170000000000.0,
            "currency": "USD",
            "financials": {},
            "_source": "cache",
        }

        with patch("backend.valuation.get_stock_data", return_value=stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=RuntimeError("no yfinance")):
                with patch(
                    "backend.valuation._backfill_from_alpha_vantage",
                    return_value={
                        "pe_current": 19.2,
                        "pe_forward": 16.8,
                        "peg_ratio": 1.1,
                        "eps_growth": 0.11,
                        "revenue_growth": 0.07,
                        "total_debt": 35000000000.0,
                    },
                ):
                    resp = get_valuation("INTC")

        assert resp.source == "alpha_vantage"
        assert resp.served_from == "fallback"
        assert resp.pe_current == 19.2
        assert resp.pe_forward == 16.8
        assert resp.peg_ratio == 1.1
        assert resp.eps_growth == 0.11
        assert resp.revenue_growth == 0.07
        assert resp.total_debt == 35000000000.0

    def test_get_valuation_promotes_source_when_fmp_backfill_used(self):
        """When external chain reports FMP fills, source should be fmp/fallback."""
        from backend.valuation import get_valuation

        stock_data = {
            "ticker": "INTC",
            "price": 42.0,
            "market_cap": 170000000000.0,
            "currency": "USD",
            "financials": {},
            "_source": "cache",
        }

        with patch("backend.valuation.get_stock_data", return_value=stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=RuntimeError("no yfinance")):
                with patch(
                    "backend.valuation._backfill_from_external_providers",
                    return_value=(
                        {
                            "pe_current": 18.7,
                            "pe_forward": 15.9,
                            "peg_ratio": 1.0,
                            "eps_growth": 0.09,
                            "revenue_growth": 0.04,
                            "total_debt": 12000000000.0,
                        },
                        "fmp",
                    ),
                ):
                    resp = get_valuation("INTC")

        assert resp.source == "fmp"
        assert resp.served_from == "fallback"
        assert resp.pe_current == 18.7
        assert resp.pe_forward == 15.9
        assert resp.peg_ratio == 1.0
        assert resp.eps_growth == 0.09
        assert resp.revenue_growth == 0.04
        assert resp.total_debt == 12000000000.0

    def test_backfill_from_fmp_fills_missing_without_overwrite(self):
        """FMP fallback fills null fields but never overwrites existing values."""
        from backend.valuation import _backfill_from_fmp

        def _fake_fmp_request(endpoint, _ticker, params=None):
            _ = params
            if endpoint == "ratios-ttm":
                return [{
                    "peRatioTTM": "31.2",
                    "forwardPERatio": "25.4",
                    "pegRatioTTM": "1.6",
                }]
            if endpoint == "income-statement-growth":
                return [{
                    "growthEPS": "15.5",
                    "growthRevenue": "9.0",
                }]
            if endpoint == "balance-sheet-statement":
                return [{"totalDebt": "42000000000"}]
            return None

        current = {
            "pe_current": 22.0,
            "pe_forward": None,
            "peg_ratio": None,
            "eps_growth": None,
            "revenue_growth": None,
            "total_debt": None,
        }

        with patch("backend.valuation._fmp_request", side_effect=_fake_fmp_request):
            out = _backfill_from_fmp("INTC", current)

        assert out["pe_current"] == 22.0  # no overwrite
        assert out["pe_forward"] == 25.4
        assert out["peg_ratio"] == 1.6
        assert out["eps_growth"] == pytest.approx(0.155, rel=1e-9)
        assert out["revenue_growth"] == pytest.approx(0.09, rel=1e-9)
        assert out["total_debt"] == 42000000000.0

    def test_external_backfill_keeps_first_provider_provenance(self):
        """Provider provenance stays on the first fallback that filled missing data."""
        from backend.valuation import _backfill_from_external_providers

        alpha_out = {
            "pe_current": None,
            "pe_forward": None,
            "peg_ratio": None,
            "eps_growth": None,
            "revenue_growth": None,
            "total_debt": None,
        }
        fmp_out = {
            "pe_current": 19.3,
            "pe_forward": None,
            "peg_ratio": None,
            "eps_growth": None,
            "revenue_growth": None,
            "total_debt": None,
        }
        eodhd_out = {
            "pe_current": 19.3,
            "pe_forward": 17.9,
            "peg_ratio": 1.2,
            "eps_growth": 0.08,
            "revenue_growth": 0.05,
            "total_debt": 15000000000.0,
        }

        with patch("backend.valuation._backfill_from_alpha_vantage", return_value=alpha_out):
            with patch("backend.valuation._backfill_from_fmp", return_value=fmp_out):
                with patch("backend.valuation._backfill_from_eodhd", return_value=eodhd_out):
                    out, provider = _backfill_from_external_providers(
                        ticker="INTC",
                        pe_current=None,
                        pe_forward=None,
                        peg_ratio=None,
                        eps_growth=None,
                        revenue_growth=None,
                        total_debt=None,
                    )

        assert provider == "fmp"
        assert out["pe_current"] == 19.3
        assert out["pe_forward"] == 17.9
        assert out["peg_ratio"] == 1.2
        assert out["eps_growth"] == 0.08
        assert out["revenue_growth"] == 0.05
        assert out["total_debt"] == 15000000000.0

    def test_external_backfill_uses_eodhd_when_alpha_and_fmp_empty(self):
        """Chain falls through to EODHD when prior fallbacks provide no values."""
        from backend.valuation import _backfill_from_external_providers

        empty = {
            "pe_current": None,
            "pe_forward": None,
            "peg_ratio": None,
            "eps_growth": None,
            "revenue_growth": None,
            "total_debt": None,
        }
        eodhd_out = {
            "pe_current": 14.2,
            "pe_forward": 12.8,
            "peg_ratio": 0.9,
            "eps_growth": 0.06,
            "revenue_growth": 0.04,
            "total_debt": 9000000000.0,
        }

        with patch("backend.valuation._backfill_from_alpha_vantage", return_value=empty):
            with patch("backend.valuation._backfill_from_fmp", return_value=empty):
                with patch("backend.valuation._backfill_from_eodhd", return_value=eodhd_out):
                    out, provider = _backfill_from_external_providers(
                        ticker="INTC",
                        pe_current=None,
                        pe_forward=None,
                        peg_ratio=None,
                        eps_growth=None,
                        revenue_growth=None,
                        total_debt=None,
                    )

        assert provider == "eodhd"
        assert out["pe_current"] == 14.2
        assert out["pe_forward"] == 12.8
        assert out["peg_ratio"] == 0.9
        assert out["eps_growth"] == 0.06
        assert out["revenue_growth"] == 0.04
        assert out["total_debt"] == 9000000000.0


# =====================================================================
# ENDPOINT INTEGRATION — 2 tests
# =====================================================================


class TestValuationEndpoint:

    def test_valid_ticker_returns_200(self, mock_stock_data, mock_yf_info):
        """GET /api/valuation/AAPL returns 200 with V2.3 data."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.valuation.get_stock_data", return_value=mock_stock_data):
            with patch("backend.valuation._yf_ticker_safe") as mock_yt:
                mock_ticker = MagicMock()
                mock_ticker.info = mock_yf_info
                mock_yt.return_value = mock_ticker

                response = client.get("/api/valuation/AAPL")

        assert response.status_code == 200
        data = response.json()
        for field in REQUIRED_FIELDS:
            assert field in data, f"Missing field in response: {field}"
        assert data["ticker"] == "AAPL"
        assert data["status"] in ("fresh", "cached")   # V2.3 status contract
        assert data["ev_source"] == "reported"          # from mock yfinance
        assert data["fx_status"] == "unavailable"       # V2.3: no live FX

    def test_error_ticker_returns_200_with_error_status(self):
        """GET /api/valuation/ERROR returns 200 with status=unavailable, not 500."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.valuation.get_stock_data", return_value=None):
            response = client.get("/api/valuation/ERROR")

        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "ERROR"
        assert data["status"] == "unavailable"


# =====================================================================
# EDGE CASES — 2 tests
# =====================================================================


class TestEdgeCases:

    def test_ticker_lowercase_normalized(self):
        """Ticker 'aapl' is normalized to 'AAPL'."""
        from backend.valuation import get_valuation

        stock_data = {"ticker": "AAPL", "price": 100, "market_cap": 1e9,
                      "currency": "USD", "_source": "test"}
        with patch("backend.valuation.get_stock_data", return_value=stock_data):
            with patch("backend.valuation._yf_ticker_safe", side_effect=RuntimeError):
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
