"""Regression tests for the 2026-06-11 client PDF revision (NVDA FY2027 Q1).

Acceptance anchors from the client's annotated PDF + Investing.com screenshot:
EPS 1.87 / est 1.77 (+5.65%), Revenue 81.6B / est 79.19B (+3.04%),
Net Cash ≈ $72.1B, FCF Margin ≈ 59.6%, fiscal label FY2027 Q1 (not 2026Q2).
"""
from datetime import date

from backend.sources_collector import _fiscal_period_label, _net_position
from backend.consensus_overrides import get_consensus_override
from backend.earnings_deep_dive.mapper import (
    _variance,
    _quarter_labels_from_resolved,
    _resolved_quarter_label,
    _rows_for_section,
    _consensus_label,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics


# ── Fiscal period derivation ──────────────────────────────────────────────

class TestFiscalPeriodLabel:
    def test_nvda_offset_fiscal_year(self):
        # NVDA fiscal year ends late January → Apr 2026 quarter is FY2027 Q1
        info = {"lastFiscalYearEnd": int(date(2026, 1, 25).strftime("%s"))}
        assert _fiscal_period_label(date(2026, 4, 26), info) == "FY2027 Q1"

    def test_aapl_september_fiscal_year(self):
        info = {"lastFiscalYearEnd": int(date(2025, 9, 27).strftime("%s"))}
        assert _fiscal_period_label(date(2026, 3, 28), info) == "FY2026 Q2"

    def test_msft_june_fiscal_year(self):
        info = {"lastFiscalYearEnd": int(date(2025, 6, 30).strftime("%s"))}
        assert _fiscal_period_label(date(2026, 3, 31), info) == "FY2026 Q3"

    def test_calendar_fiscal_year_default(self):
        # No fiscal-year-end info → calendar quarters
        assert _fiscal_period_label(date(2026, 3, 31), {}) == "FY2026 Q1"

    def test_bad_input_returns_none(self):
        assert _fiscal_period_label(None, {}) is None


# ── Net Cash / Net Debt methodology ──────────────────────────────────────

class TestNetPosition:
    def test_nvda_acceptance_case(self):
        # Client-provided FY2027 Q1 balance sheet ($M):
        # cash 13,237 + marketable 67,335 = 80,572; debt 8,470 → net cash 72,102
        net_debt, cash_total = _net_position(8470.0, 13237.0, 37098.0 + 30237.0)
        assert cash_total == 80572.0
        assert net_debt == 8470.0 - 80572.0  # negative = net cash
        assert round(-net_debt) == 72102

    def test_combined_row_preferred(self):
        net_debt, cash_total = _net_position(100.0, 10.0, 5.0, combined=50.0)
        assert cash_total == 50.0 and net_debt == 50.0

    def test_missing_inputs(self):
        assert _net_position(None, 10.0, 5.0) == (None, 15.0)
        assert _net_position(10.0, None, None) == (None, None)


# ── Surprise % rounding ──────────────────────────────────────────────────

class TestSurpriseRounding:
    def test_eps_surprise_2dp(self):
        assert _variance(1.87, 1.77, precision=2) == "+5.65%"

    def test_revenue_surprise_2dp(self):
        assert _variance(81.6e9, 79.19e9, precision=2) == "+3.04%"

    def test_computed_wins_over_explicit_when_both_cells_present(self):
        # Surprise must reconcile with the displayed actual/estimate cells
        assert _variance(1.87, 1.77, explicit=0.055, precision=2) == "+5.65%"

    def test_explicit_fallback_when_estimate_missing(self):
        assert _variance(1.87, None, explicit=0.0565) == "+5.7%"


# ── EPS & Revenue source labeling ────────────────────────────────────────

class TestConsensusLabeling:
    def test_investing_provider_label(self):
        m = FinancialMetrics(consensus_provider="Investing.com (analyst consensus)")
        assert _consensus_label(m, 1.77) == "Investing.com (consensus)"

    def test_consensus_never_labeled_sec(self):
        m = FinancialMetrics(consensus_provider="yfinance earnings_history")
        assert "SEC" not in _consensus_label(m, 1.77)

    def test_nvda_override_entry(self):
        ov = get_consensus_override("NVDA", "FY2027 Q1")
        assert ov and ov["eps_estimate"] == 1.77 and ov["revenue_estimate"] == 79.19e9
        assert "investing" in ov["source"].lower()


# ── Cash Flow table: no Quality column, FCF Margin present ──────────────

class TestCashFlowTable:
    ROW_LABELS = ("Operating cash flow", "CapEx", "Free cash flow", "Net debt")

    def _metrics(self):
        return FinancialMetrics(
            operating_cash_flow=50.3e9, capex=1.8e9, free_cash_flow=48.6e9,
            revenue_actual=81.6e9, net_debt=-72.102e9,
            cash_and_marketable_securities=80.572e9,
        )

    def test_no_quality_column(self):
        rows = _rows_for_section("Cash Flow", self.ROW_LABELS, self._metrics())
        assert all(len(r) == 5 for r in rows), "Cash Flow rows must be 5 columns (Quality removed)"
        flat = " ".join(str(c) for r in rows for c in r)
        assert "Liquidity buffer" not in flat and "Net debt (leverage)" not in flat

    def test_fcf_margin_row(self):
        rows = _rows_for_section("Cash Flow", self.ROW_LABELS, self._metrics())
        margin_rows = [r for r in rows if "FCF Margin" in r[0]]
        assert len(margin_rows) == 1
        assert margin_rows[0][1] == "+59.6%"  # 48.6 / 81.6

    def test_net_cash_displayed_positive(self):
        rows = _rows_for_section("Cash Flow", self.ROW_LABELS, self._metrics())
        net_row = next(r for r in rows if "Net Cash" in r[0])
        assert "$72.1B" in net_row[1].replace(",", "")


# ── Period labels ────────────────────────────────────────────────────────

class TestPeriodLabels:
    def test_fy_prefixed_labels(self):
        cur, prior, ttm_cur, ttm_prior = _quarter_labels_from_resolved("FY2027 Q1")
        assert (cur, prior) == ("FY2027 Q1", "FY2026 Q1")
        assert ttm_cur == "TTM Ending FY2027 Q1"

    def test_fiscal_label_overrides_calendar_request(self):
        m = FinancialMetrics(fiscal_period_label="FY2027 Q1")
        assert _resolved_quarter_label("2026Q2", m) == "FY2027 Q1"

    def test_requested_kept_without_fiscal_data(self):
        assert _resolved_quarter_label("FY2026 Q3", FinancialMetrics()) == "FY2026 Q3"


class TestLatestQuarterLabelResolution:
    """quarter='latest' (the GET endpoint default) must never leak literally
    into the client title, and derived fallbacks must never fabricate a
    confident calendar-based 'FY...' label (NVDA regression 2026-06-12:
    a 'latest' generation shipped a wrong fiscal title)."""

    def test_latest_uses_fiscal_label_when_available(self):
        m = FinancialMetrics(fiscal_period_label="FY2027 Q1")
        assert _resolved_quarter_label("latest", m) == "FY2027 Q1"

    def test_latest_never_returned_literally(self):
        label = _resolved_quarter_label("latest", FinancialMetrics())
        assert label.lower() not in ("latest", "latest quarter")

    def test_period_end_fallback_is_calendar_tag_not_fake_fiscal(self):
        m = FinancialMetrics(period_end_date="2026-04-27")
        label = _resolved_quarter_label("latest", m)
        assert label == "2026Q2", label
        assert not label.startswith("FY"), \
            "calendar-derived fallback must not impersonate a fiscal label"

    def test_last_resort_is_estimated_calendar_tag(self):
        label = _resolved_quarter_label("latest", FinancialMetrics())
        assert label.endswith("(est.)")
        assert not label.startswith("FY")
