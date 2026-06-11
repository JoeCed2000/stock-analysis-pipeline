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
            {
                "Gross Profit": 560.0,
                "Total Revenue": 800.0,
                "Operating Expense": 180.0,
                "Operating Income": 380.0,
                "Net Income": 100.0,
            },
            {
                "Gross Profit": 480.0,
                "Total Revenue": 700.0,
                "Operating Expense": 160.0,
                "Operating Income": 320.0,
                "Net Income": 80.0,
            },
        )
        self.quarterly_balance_sheet = _quarterly_frame(
            {
                "Stockholders Equity": 400.0,
                "Total Assets": 1000.0,
                "Tangible Book Value": 250.0,
                "Invested Capital": 500.0,
                "Net Debt": 82.0,
            },
            {
                "Stockholders Equity": 320.0,
                "Total Assets": 800.0,
                "Tangible Book Value": 200.0,
                "Invested Capital": 400.0,
                "Net Debt": 141.0,
            },
        )
        self.quarterly_cashflow = _quarterly_frame(
            {
                "Operating Cash Flow": 467.0,
                "Capital Expenditure": -309.0,
                "Free Cash Flow": 158.0,
                "Repurchase Of Capital Stock": -30.0,
                "Cash Dividends Paid": -15.0,
            },
            {
                "Operating Cash Flow": 370.0,
                "Capital Expenditure": -167.0,
                "Free Cash Flow": 203.0,
                "Repurchase Of Capital Stock": -25.0,
                "Cash Dividends Paid": -10.0,
            },
        )
        self.info = {"forwardPE": 21.8}


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


def test_extract_quarterly_comparison_includes_operating_cash_flow_and_forward_pe(monkeypatch):
    fake_yfinance = types.SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    result = pipeline._extract_quarterly_comparison("MSFT")

    expected_keys = {
        "gross_profit",
        "gross_profit_prior_year",
        "gross_profit_yoy",
        "revenue_quarterly",
        "revenue_quarterly_prior_year",
        "opex",
        "opex_prior_year",
        "opex_yoy",
        "operating_income",
        "operating_income_prior_year",
        "operating_income_yoy",
        "net_income_quarterly",
        "net_income_quarterly_prior_year",
        "net_income_yoy",
        "gross_margin",
        "gross_margin_prior_year",
        "gross_margin_yoy",
        "operating_margin",
        "operating_margin_prior_year",
        "operating_margin_yoy",
        "operating_cash_flow",
        "operating_cash_flow_prior_year",
        "operating_cash_flow_yoy",
        "capex",
        "capex_prior_year",
        "capex_yoy",
        "free_cash_flow",
        "free_cash_flow_prior_year",
        "free_cash_flow_yoy",
        "net_debt",
        "net_debt_prior_year",
        "net_debt_yoy",
        "pe_forward",
    }

    assert expected_keys <= result.keys()
    assert result["gross_margin"] == pytest.approx(560.0 / 800.0 * 100)
    assert result["gross_margin_prior_year"] == pytest.approx(480.0 / 700.0 * 100)
    assert result["gross_margin_yoy"] == pytest.approx(70.0 - 480.0 / 700.0 * 100)
    assert result["operating_margin_yoy"] == pytest.approx(47.5 - 320.0 / 700.0 * 100)
    assert result["operating_margin"] == pytest.approx(380.0 / 800.0 * 100)
    assert result["capex"] == -309.0
    assert result["capex_yoy"] == pytest.approx((-309.0 / -167.0 - 1) * 100)
    assert result["net_debt_yoy"] == pytest.approx((82.0 / 141.0 - 1) * 100)
    assert result["pe_forward"] == 21.8


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

    assert rows[0] == ["ROE", "+25.0%", "+20.0%", "+25.0%", "improvement", "SEC Filing (10-Q/10-K) via EDGAR"]
    assert rows[1][4] == "decline"
    assert rows[3][4] == "flat"
    assert rows[4][2] == "$25"
    assert rows[4][3] == "+20.0%"
    assert rows[5][2] == "$10"
    assert MISSING not in rows[5]


def test_operating_metrics_rows_use_prior_year_and_yoy():
    metrics = FinancialMetrics(
        gross_profit=560_000_000_000,
        gross_profit_prior_year=480_000_000_000,
        gross_profit_yoy=16.7,
        gross_margin=70.0,
        gross_margin_prior_year=480.0 / 700.0 * 100,
        gross_margin_yoy=2.1,
        opex=180_000_000_000,
        opex_prior_year=160_000_000_000,
        opex_yoy=12.5,
        operating_income=380_000_000_000,
        operating_income_prior_year=320_000_000_000,
        operating_income_yoy=18.8,
        operating_margin=47.5,
        operating_margin_prior_year=320.0 / 700.0 * 100,
        operating_margin_yoy=3.9,
        net_income_quarterly=100_000_000_000,
        net_income_quarterly_prior_year=80_000_000_000,
        net_income_yoy=25.0,
    )

    rows = _rows_for_section(
        "Operating Metrics",
        ("粗利益", "粗利益率", "営業費用", "営業利益", "営業利益率", "純利益"),
        metrics,
    )

    assert rows[0] == ["粗利益", "$560.0B", "$480.0B", "+16.7%", "会社開示 / 計算ベース"]
    assert rows[1][1:4] == ["+70.0%", "+68.6%", "+2.1 pts"]
    assert rows[2][1:4] == ["$180.0B", "$160.0B", "+12.5%"]
    assert rows[5][1:4] == ["$100.0B", "$80.0B", "+25.0%"]
    assert MISSING not in rows[5]


def test_cash_flow_rows_use_prior_year_yoy_and_quality():
    metrics = FinancialMetrics(
        operating_cash_flow=467_000_000_000,
        operating_cash_flow_prior_year=370_000_000_000,
        operating_cash_flow_yoy=26.2,
        capex=-309_000_000_000,
        capex_prior_year=-167_000_000_000,
        capex_yoy=85.0,
        free_cash_flow=158_000_000_000,
        free_cash_flow_prior_year=203_000_000_000,
        free_cash_flow_yoy=-22.2,
        net_debt=82_000_000_000,
        net_debt_prior_year=141_000_000_000,
        net_debt_yoy=-41.8,
    )

    rows = _rows_for_section(
        "Cash Flow",
        ("営業キャッシュフロー", "設備投資", "フリーキャッシュフロー", "純負債"),
        metrics,
    )

    # Client PDF revision contract: 5 columns (no Quality), FCF margin row,
    # net cash/(debt) row displays the negated net_debt sign convention.
    assert rows[0] == ["営業キャッシュフロー", "$467.0B", "$370.0B", "+26.2%", "SEC Filing (10-Q/10-K) via EDGAR"]
    assert rows[1][1:4] == ["-$309.0B", "-$167.0B", "+85.0%"]
    assert rows[2][1:4] == ["$158.0B", "$203.0B", "-22.2%"]

    assert rows[3][0] == "FCFマージン"

    assert rows[4][0] == "現金・短期投資"
    assert rows[4][1] == MISSING

    assert rows[5][0] == "ネットキャッシュ /（純負債）"
    assert rows[5][1:4] == ["-$82.0B", "-$141.0B", "-41.8%"]


def test_forward_pe_row_uses_forward_pe_and_trailing_reference():
    metrics = FinancialMetrics(pe_forward=21.8, pe_trailing=33.4)

    rows = _rows_for_section("Forward P/E", ("予想PER", "バリュエーションシグナル"), metrics)

    assert rows[0] == ["予想PER", "21.80x", "33.40x", MISSING, "会社開示 / 計算ベース"]


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
            "gross_profit": 560.0,
            "gross_profit_prior_year": 480.0,
            "gross_profit_yoy": 16.7,
            "revenue_quarterly": 800.0,
            "revenue_quarterly_prior_year": 700.0,
            "gross_margin": 70.0,
            "gross_margin_prior_year": 480.0 / 700.0 * 100,
            "gross_margin_yoy": 2.1,
            "opex": 180.0,
            "opex_prior_year": 160.0,
            "opex_yoy": 12.5,
            "operating_income": 380.0,
            "operating_income_prior_year": 320.0,
            "operating_income_yoy": 18.8,
            "operating_margin": 47.5,
            "operating_margin_prior_year": 320.0 / 700.0 * 100,
            "operating_margin_yoy": 3.9,
            "net_income_quarterly": 100.0,
            "net_income_quarterly_prior_year": 80.0,
            "net_income_yoy": 25.0,
            "operating_cash_flow": 467.0,
            "operating_cash_flow_prior_year": 370.0,
            "operating_cash_flow_yoy": 26.2,
            "capex": -309.0,
            "capex_prior_year": -167.0,
            "capex_yoy": 85.0,
            "free_cash_flow": 158.0,
            "free_cash_flow_prior_year": 203.0,
            "free_cash_flow_yoy": -22.2,
            "net_debt": 82.0,
            "net_debt_prior_year": 141.0,
            "net_debt_yoy": -41.8,
            "pe_forward": 21.8,
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
    assert metrics.gross_profit == 560.0
    assert metrics.gross_profit_prior_year == 480.0
    assert metrics.gross_margin == 70.0
    assert metrics.gross_margin_prior_year == pytest.approx(480.0 / 700.0 * 100)
    assert metrics.operating_cash_flow_prior_year == 370.0
    assert metrics.capex == -309.0
    assert metrics.free_cash_flow_yoy == -22.2
    assert metrics.net_debt_prior_year == 141.0
    assert metrics.pe_forward == 21.8
