"""TDD tests for F1 (EPS estimate source) and F2 (quarter in title).

F1: eps_estimate comes from Yahoo Finance consensus, NOT SEC filings.
F2: title should include the quarter label.
"""

import pytest
from backend.earnings_deep_dive.mapper import _rows_for_section, build_earnings_deep_dive_report
from backend.earnings_deep_dive.schemas import FinancialMetrics


# ── F1: EPS estimate source ────────────────────────────────────────────────

def _eps_metrics(eps_est=None, eps_act=None):
    """Helper to build minimal metrics for EPS row testing."""
    return FinancialMetrics(eps_estimate=eps_est, eps_actual=eps_act)


def test_eps_source_uses_yahoo_finance_consensus_when_estimate_present():
    """RED: EPS estimate sourced from Yahoo Finance consensus, not SEC."""
    metrics = _eps_metrics(eps_est=3.10, eps_act=3.46)
    rows = _rows_for_section("EPS & Revenue", ("EPS", "Revenue"), metrics)

    eps_row = rows[0]
    source_cell = eps_row[-1]  # Last column is Source

    assert "Yahoo Finance (consensus)" in source_cell, (
        f"Expected 'Yahoo Finance (consensus)' for EPS estimate, got: {source_cell}"
    )
    assert "SEC Filing" not in source_cell, (
        f"EPS estimate is NOT from SEC filings, but source says: {source_cell}"
    )


def test_eps_source_falls_back_to_sec_when_no_estimate():
    """When eps_estimate is missing, fall back to SEC source for eps_actual."""
    metrics = _eps_metrics(eps_est=None, eps_act=3.46)
    rows = _rows_for_section("EPS & Revenue", ("EPS", "Revenue"), metrics)

    eps_row = rows[0]
    source_cell = eps_row[-1]

    assert "SEC Filing" in source_cell or "SEC" in source_cell, (
        f"Without estimate, source should be SEC Filing, got: {source_cell}"
    )


# ── F2: Quarter label in title ──────────────────────────────────────────────

def _title_metrics():
    """Minimal metrics sufficient to build a valid report."""
    return FinancialMetrics(
        eps_estimate=3.10,
        eps_actual=3.46,
        eps_vs_estimate=0.116,
        eps_yoy=0.22,
        revenue_estimate=80_000_000_000,
        revenue_actual=82_900_000_000,
        revenue_yoy=0.183,
        gross_profit=56_000_000_000,
        gross_margin=0.676,
        opex=18_000_000_000,
        operating_income=38_400_000_000,
        operating_margin=0.463,
        net_income=27_200_000_000,
        free_cash_flow=71_600_000_000,
        operating_cash_flow=95_000_000_000,
        capex=23_400_000_000,
        roe=0.35,
        roic=0.28,
        buybacks=8_000_000_000,
        dividends=6_000_000_000,
        pe_forward=21.19,
    )


def test_title_includes_quarter_label():
    """RED: Title should include quarter like 'Q1 2026'."""
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=_title_metrics(),
    )

    assert "FY2026 Q1" in report.title, (
        f"Title should include quarter 'FY2026 Q1', got: {report.title}"
    )


def test_title_includes_quarter_when_explicit_format():
    """Quarter in '2026Q1' format should appear in title."""
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="2026Q1",
        language="en",
        metrics=_title_metrics(),
    )

    assert "2026Q1" in report.title, (
        f"Title should include quarter '2026Q1', got: {report.title}"
    )
