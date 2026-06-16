"""Focused test: NVDA FY2027 Q1 title renders earnings date (2026-05-20).

Verifies the data chain: consensus_override → FinancialMetrics → ReportPeriodContext → PDF title.
Uses PyMuPDF (fitz) for reliable PDF text extraction.
"""

import tempfile
from pathlib import Path

import fitz

from backend.consensus_overrides import get_consensus_override
from backend.earnings_deep_dive.schemas import FinancialMetrics


def test_earnings_release_date_in_consensus_override():
    """NVDA FY2027 Q1 override contains 'earnings_release_date': '2026-05-20'."""
    override = get_consensus_override("NVDA", "FY2027 Q1")
    assert override is not None, "NVDA FY2027 Q1 override must exist"
    assert override.get("earnings_release_date") == "2026-05-20", \
        f"Expected '2026-05-20', got {override.get('earnings_release_date')}"


def test_earnings_release_date_flows_to_period_context():
    """_build_report_period_context picks up earnings_release_date from FinancialMetrics via _metric_text."""
    from backend.earnings_deep_dive.mapper import _build_report_period_context

    fm = FinancialMetrics(
        eps_estimate=1.77,
        earnings_release_date="2026-05-20",
        fiscal_period_label="FY2027 Q1",
    )
    ctx = _build_report_period_context(
        ticker="NVDA", company_name="NVIDIA Corp",
        resolved_quarter="FY2027 Q1", metrics=fm,
    )
    assert ctx.earnings_release_date == "2026-05-20", \
        f"Expected '2026-05-20', got {ctx.earnings_release_date}"


def _extract_pdf_text(report) -> str:
    """Render a report to PDF and extract text using PyMuPDF."""
    from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        out_path = f.name
    try:
        render_earnings_deep_dive_pdf(report, out_path)
        doc = fitz.open(out_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    finally:
        Path(out_path).unlink(missing_ok=True)


def test_title_renders_date_in_pdf():
    """PDF title heading contains 'FY2027 Q1 Earnings Summary (2026-05-20)'."""
    from backend.earnings_deep_dive.report_model import (
        EarningsDeepDiveReport, ReportPeriodContext,
        ExecutiveSnapshot,
    )

    report = EarningsDeepDiveReport(
        company="NVIDIA Corp",
        ticker="NVDA",
        quarter="FY2027 Q1",
        language="en",
        sections=[],
        generated_at="2026-06-16T20:00:00Z",
        title="NVIDIA Corp (NVDA) - Earnings Deep-Dive (FY2027 Q1)",
        period_context=ReportPeriodContext(
            ticker="NVDA",
            company_name="NVIDIA Corp",
            fiscal_year=2027,
            fiscal_quarter=1,
            earnings_release_date="2026-05-20",
            report_title_period_label="FY2027 Q1",
        ),
        executive_snapshot=ExecutiveSnapshot(
            ticker="NVDA", company_name="NVIDIA Corp", quarter="FY2027 Q1"
        ),
    )

    text = _extract_pdf_text(report)

    assert "NVIDIA Corp (NVDA)" in text, "Company title missing in PDF"
    assert "FY2027 Q1" in text, "Fiscal period missing in PDF"
    assert "Earnings Summary" in text, "'Earnings Summary' missing in PDF"
    assert "(2026-05-20)" in text, \
        f"Earnings date '(2026-05-20)' not found in PDF text.\nPDF text excerpt:\n{text[:500]}"


def test_title_no_date_when_release_date_absent():
    """PDF title has NO date suffix when earnings_release_date is not set (regression guard)."""
    from backend.earnings_deep_dive.report_model import (
        EarningsDeepDiveReport, ReportPeriodContext,
        ExecutiveSnapshot,
    )

    report = EarningsDeepDiveReport(
        company="Test Corp",
        ticker="TEST",
        quarter="FY2026 Q1",
        language="en",
        sections=[],
        generated_at="2026-06-16T20:00:00Z",
        title="Test Corp (TEST) - Earnings Deep-Dive (FY2026 Q1)",
        period_context=ReportPeriodContext(
            ticker="TEST",
            company_name="Test Corp",
            fiscal_year=2026,
            fiscal_quarter=1,
            # No earnings_release_date → no date suffix expected
            report_title_period_label="FY2026 Q1",
        ),
        executive_snapshot=ExecutiveSnapshot(
            ticker="TEST", company_name="Test Corp", quarter="FY2026 Q1"
        ),
    )

    text = _extract_pdf_text(report)

    assert "Test Corp (TEST)" in text, "Company title missing"
    assert "FY2026 Q1" in text, "Fiscal period missing"
    assert "Earnings Summary" in text, "'Earnings Summary' should still appear"
    # Date suffix should not appear without earnings_release_date
    assert "(2026-05-20)" not in text, \
        f"Date suffix should NOT appear without earnings_release_date.\nPDF text excerpt:\n{text[:500]}"
