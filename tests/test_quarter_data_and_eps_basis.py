"""R20: mocked tests for get_yahoo_data_for_quarter · B14: EPS YoY basis rules."""
import pandas as pd
import pytest

import backend.sources_collector as sc
import backend.pipeline as pl
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.mapper import _rows_for_section, MISSING


Q_END = pd.Timestamp("2026-04-26")
PRIOR_END = pd.Timestamp("2025-04-27")


class FakeTicker:
    def __init__(self, qf=None, cf=None, bs=None, info=None, eh=None):
        self.quarterly_financials = qf if qf is not None else pd.DataFrame()
        self.quarterly_cashflow = cf if cf is not None else pd.DataFrame()
        self.quarterly_balance_sheet = bs if bs is not None else pd.DataFrame()
        self.info = info or {}
        self.earnings_history = eh


def _fake_statements():
    cols = [Q_END, pd.Timestamp("2026-01-25"), pd.Timestamp("2025-10-26"),
            pd.Timestamp("2025-07-27"), PRIOR_END]
    qf = pd.DataFrame(
        {c: [81.6e9 if c == Q_END else 44.0e9, 1.76 if c == Q_END else 1.05]
         for c in cols},
        index=["Total Revenue", "Diluted EPS"])
    bs = pd.DataFrame(
        {Q_END: [8470e6, 13237e6, 67335e6, 80572e6]},
        index=["Total Debt", "Cash And Cash Equivalents",
               "Other Short Term Investments",
               "Cash Cash Equivalents And Short Term Investments"])
    info = {"currentPrice": 200.0, "lastFiscalYearEnd": int(pd.Timestamp("2026-01-25").timestamp())}
    return qf, pd.DataFrame(), bs, info


class TestGetYahooDataForQuarter:
    def _patch(self, monkeypatch, ticker):
        monkeypatch.setattr(sc, "_yf_ticker_safe", lambda *a, **k: ticker)
        monkeypatch.setattr(sc, "_load_yfinance", lambda: None)

    def test_successful_quarter_extraction(self, monkeypatch):
        qf, cf, bs, info = _fake_statements()
        self._patch(monkeypatch, FakeTicker(qf, cf, bs, info))
        data = sc.get_yahoo_data_for_quarter("NVDA", "2026Q2")
        fin = data["financials"]
        assert fin["revenue_quarterly"] == 81.6e9
        assert fin["revenue_yoy_growth"] == round((81.6e9 - 44.0e9) / 44.0e9, 4)
        # Net Cash = combined cash row - total debt (marketable securities included)
        assert fin["cash_and_marketable_securities"] == 80572e6
        assert fin["net_debt"] == 8470e6 - 80572e6
        # Fiscal label derived from offset fiscal year end (late January)
        assert fin["fiscal_period_label"] == "FY2027 Q1"
        assert fin["period_end_date"] == "2026-04-26"

    def test_quarter_not_found_falls_back_to_latest(self, monkeypatch):
        qf, cf, bs, info = _fake_statements()
        self._patch(monkeypatch, FakeTicker(qf, cf, bs, info))
        sentinel = {"ticker": "NVDA", "financials": {}}
        monkeypatch.setattr(sc, "get_yahoo_data", lambda t: sentinel)
        assert sc.get_yahoo_data_for_quarter("NVDA", "2019Q1") is sentinel

    def test_empty_statements_return_none(self, monkeypatch):
        self._patch(monkeypatch, FakeTicker())
        assert sc.get_yahoo_data_for_quarter("NVDA", "2026Q2") is None

    def test_invalid_quarter_string(self, monkeypatch):
        qf, cf, bs, info = _fake_statements()
        self._patch(monkeypatch, FakeTicker(qf, cf, bs, info))
        assert sc.get_yahoo_data_for_quarter("NVDA", "garbage") is None


class TestEpsYoyBasis:
    """B14: never mix adjusted EPS actual with GAAP-based YoY."""

    def _metrics(self, monkeypatch, comparison, fin_data):
        monkeypatch.setattr(pl, "_extract_quarterly_comparison", lambda t: comparison)
        result = type("R", (), {"ticker": "NVDA", "financials": None, "valuation": None})()
        return pl._deep_dive_metrics(result, {"ticker": "NVDA", "financials": fin_data})

    def test_adjusted_actual_without_comparison_yoy_uses_snapshot_fallback(self, monkeypatch):
        # B14 refined (a813f33): the snapshot eps_yoy is computed from
        # earnings_history — same adjusted basis as the displayed actual —
        # so it is a valid fallback when the comparison provides no YoY.
        m = self._metrics(monkeypatch,
                          {"eps_actual": 1.87},               # adjusted, no comparison YoY
                          {"eps_actual": 1.76, "eps_yoy": 0.021})  # snapshot, adjusted basis
        assert m.eps_actual == 1.87
        assert m.eps_yoy == 0.021

    def test_adjusted_actual_with_same_basis_yoy_kept(self, monkeypatch):
        m = self._metrics(monkeypatch,
                          {"eps_actual": 1.87, "eps_yoy": 0.64},
                          {"eps_actual": 1.76, "eps_yoy": 0.021})
        assert m.eps_yoy == 0.64

    def test_gaap_path_keeps_gaap_yoy(self, monkeypatch):
        m = self._metrics(monkeypatch, {}, {"eps_actual": 1.76, "eps_yoy": 0.021})
        assert m.eps_actual == 1.76 and m.eps_yoy == 0.021

    def test_pdf_row_shows_not_disclosed_when_yoy_hidden(self):
        rows = _rows_for_section(
            "EPS & Revenue", ("EPS", "Revenue"),
            FinancialMetrics(eps_actual=1.87, eps_estimate=1.77, eps_yoy=None))
        eps_row = rows[0]
        assert eps_row[4] == MISSING  # YoY Change cell
