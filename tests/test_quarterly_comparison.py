import sys
import types

import pandas as pd
import pytest

from backend import pipeline
from backend.earnings_deep_dive.mapper import MISSING, _rows_for_section
from backend.earnings_deep_dive.schemas import FinancialMetrics


def _quarterly_frame(current, prior):
    columns = pd.date_range("2026-03-31", periods=5, freq="-3ME")
    return pd.DataFrame({columns[0]: current, columns[4]: prior}).reindex(columns=columns)


class _FakeTicker:
    def __init__(self, ticker):
        assert ticker == "MSFT"
        self.quarterly_financials = _quarterly_frame(
            {"Net Income": 100.0},
            {"Net Income": 80.0},
        )
        self.quarterly_balance_sheet = _quarterly_frame(
            {
                "Stockholders Equity": 400.0,
                "Total Assets": 1000.0,
                "Tangible Book Value": 250.0,
                "Invested Capital": 500.0,
            },
            {
                "Stockholders Equity": 320.0,
                "Total Assets": 800.0,
                "Tangible Book Value": 200.0,
                "Invested Capital": 400.0,
            },
        )
        self.quarterly_cashflow = _quarterly_frame(
            {
                "Repurchase Of Capital Stock": -30.0,
                "Cash Dividends Paid": -15.0,
            },
            {
                "Repurchase Of Capital Stock": -25.0,
                "Cash Dividends Paid": -10.0,
            },
        )


def test_extract_quarterly_comparison_with_msft_yfinance_shape(monkeypatch):
    fake_yfinance = types.SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    result = pipeline._extract_quarterly_comparison("MSFT")

    assert result["roe"] > 0
    assert result["roe_prior_year"] > 0
    assert result["roe_yoy"] == 0.0
    assert result["rotce"] == 0.4
    assert result["roa"] == 0.1
    assert result["roic"] == 0.2
    assert result["buybacks"] == 30.0
    assert result["buybacks_prior_year"] == 25.0
    assert result["buybacks_yoy"] == pytest.approx(20.0)
    assert result["dividends_yoy"] == pytest.approx(50.0)


def test_extract_quarterly_comparison_gracefully_handles_missing_prior_year(monkeypatch):
    class ShortHistoryTicker(_FakeTicker):
        def __init__(self, ticker):
            super().__init__(ticker)
            self.quarterly_financials = self.quarterly_financials.iloc[:, :4]
            self.quarterly_balance_sheet = self.quarterly_balance_sheet.iloc[:, :4]
            self.quarterly_cashflow = self.quarterly_cashflow.iloc[:, :4]

    fake_yfinance = types.SimpleNamespace(Ticker=ShortHistoryTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    result = pipeline._extract_quarterly_comparison("MSFT")

    assert result["roe"] > 0
    assert result["roe_prior_year"] is None
    assert result["roe_yoy"] is None
    assert result["buybacks_prior_year"] is None
    assert result["dividends_yoy"] is None


def test_capital_efficiency_rows_use_prior_year_yoy_and_comments():
    metrics = FinancialMetrics(
        roe=0.25,
        rotce=0.4,
        roa=0.1,
        roic=0.2,
        buybacks=30.0,
        dividends=15.0,
        roe_prior_year=0.20,
        rotce_prior_year=0.50,
        roa_prior_year=0.08,
        roic_prior_year=0.20,
        buybacks_prior_year=25.0,
        dividends_prior_year=10.0,
        roe_yoy=25.0,
        rotce_yoy=-20.0,
        roa_yoy=25.0,
        roic_yoy=0.0,
        buybacks_yoy=20.0,
        dividends_yoy=50.0,
    )

    rows = _rows_for_section(
        "Capital Efficiency",
        ("ROE", "ROTCE", "ROA", "ROIC", "Buybacks", "Dividends"),
        metrics,
    )

    assert rows[0] == ["ROE", "+25.0%", "+20.0%", "+25.0%", "improvement", "会社開示 / 計算ベース"]
    assert rows[1][4] == "decline"
    assert rows[3][4] == "flat"
    assert rows[4][2] == "$25"
    assert rows[4][3] == "+20.0%"
    assert rows[5][2] == "$10"
    assert MISSING not in rows[5]


def test_deep_dive_metrics_passes_quarterly_comparison_fields(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_extract_quarterly_comparison",
        lambda ticker: {
            "roe": 0.25,
            "roe_prior_year": 0.20,
            "roe_yoy": 25.0,
            "rotce": 0.40,
            "rotce_prior_year": 0.50,
            "rotce_yoy": -20.0,
            "roa": 0.10,
            "roa_prior_year": 0.08,
            "roa_yoy": 25.0,
            "roic": 0.20,
            "roic_prior_year": 0.20,
            "roic_yoy": 0.0,
            "buybacks": 30.0,
            "buybacks_prior_year": 25.0,
            "buybacks_yoy": 20.0,
            "dividends": 15.0,
            "dividends_prior_year": 10.0,
            "dividends_yoy": 50.0,
        },
    )

    metrics = pipeline._deep_dive_metrics(
        types.SimpleNamespace(ticker="MSFT", financials=types.SimpleNamespace(), valuation=types.SimpleNamespace()),
        {},
    )

    assert metrics.roe == 0.25
    assert metrics.roe_prior_year == 0.20
    assert metrics.roe_yoy == 25.0
    assert metrics.buybacks == 30.0
    assert metrics.buybacks_prior_year == 25.0
    assert metrics.dividends_yoy == 50.0
