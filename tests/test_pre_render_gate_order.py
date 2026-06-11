"""Pre-render gate ordering: the blocking validation must judge the
normalized content actually rendered in the PDF (post mapper fallbacks),
not the raw LLM text. Raw-text validation stays diagnostic-only.

Regression context: DeepSeek-generated Highlights with prose-only
"Risk/Implications" bullets tripped the gate even though the mapper
replaces that text with the metric-substantiated deterministic fallback.
"""
import pytest

from backend.earnings_deep_dive.mapper import (
    build_earnings_deep_dive_report,
    effective_section_analysis,
)
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
from backend.earnings_deep_dive.pre_render_validator import (
    annotate_sections_with_warnings,
    validate_pre_render,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics


GENERIC_METRICS = FinancialMetrics(
    revenue_actual=10.5e9, revenue_estimate=10.0e9, revenue_yoy=0.12,
    eps_actual=2.10, eps_estimate=2.00, gross_margin=0.55, operating_margin=0.30,
    free_cash_flow=3.2e9, operating_cash_flow=4.0e9, pe_forward=18.0,
)

# DeepSeek-style raw output: prose-only risk bullets, no numbers, no sources.
UNSUBSTANTIATED_RAW = {
    "Highlights": (
        "## Highlights\n\n"
        "⚠️ Risk/Implications\n"
        "• Consumer demand softness could erode volumes and signal rising price sensitivity over coming quarters.\n"
        "• Reporting framework changes could muddy comparisons and obscure underlying trends until history rebuilds.\n"
    )
}

# Conforming concise structure (kept by the mapper) but still unsubstantiated.
KEPT_BUT_UNSUBSTANTIATED_RAW = {
    "Highlights": (
        "Highlights\n"
        "1. Demand narrative\n"
        "• Management tone was upbeat about demand momentum across regions.\n"
        "2. Mix shift\n"
        "• Mix shifted toward premium tiers with better unit economics ahead.\n"
        "3. Pipeline\n"
        "• Pipeline keeps expanding across territories and verticals.\n"
        "\n"
        "Lowlights\n"
        "1. Competition\n"
        "• Competitive intensity keeps rising in core markets.\n"
    )
}


def _has_error(result, check):
    return any(w.check == check and w.severity == "error" for w in result.warnings)


def _effective_validation(ticker, raw_sections, metrics, language="en"):
    """The new gate order: raw diagnostic → annotate → build → validate effective."""
    raw_val = validate_pre_render(ticker, "FY2026 Q2", metrics, raw_sections)
    sections = annotate_sections_with_warnings(raw_sections, raw_val)
    report = build_earnings_deep_dive_report(
        ticker=ticker, company=f"{ticker} Corp", quarter="FY2026 Q2",
        language=language, metrics=metrics, transcript_url="",
        section_analysis=sections,
    )
    effective = effective_section_analysis(report)
    return raw_val, validate_pre_render(ticker, "FY2026 Q2", metrics, effective), report


def test_unsubstantiated_raw_passes_once_normalized_generic_ticker():
    """Raw DeepSeek-style Highlights fail diagnostics, but the mapper's
    deterministic fallback is substantiated — the gate must PASS. Generic
    non-NVDA ticker proves nothing is hardcoded."""
    raw_val, eff_val, report = _effective_validation("ACME", UNSUBSTANTIATED_RAW, GENERIC_METRICS)
    assert _has_error(raw_val, "highlights_unsubstantiated"), "raw diagnostic must still flag"
    assert not _has_error(eff_val, "highlights_unsubstantiated")
    assert not eff_val.errors, [w.detail for w in eff_val.errors]
    # The offending raw text must not be in the rendered content.
    highlights = next(s for s in report.sections if s.key == "Highlights")
    assert "Risk/Implications" not in "\n".join(highlights.analysis)


def test_normalized_content_still_invalid_blocks():
    """When the mapper keeps the LLM text (conforming structure) and it is
    still unsubstantiated, the gate must keep blocking."""
    _, eff_val, report = _effective_validation("ACME", KEPT_BUT_UNSUBSTANTIATED_RAW,
                                               FinancialMetrics(revenue_actual=10.5e9, eps_actual=2.10,
                                                                free_cash_flow=3.2e9))
    highlights = next(s for s in report.sections if s.key == "Highlights")
    assert "Management tone was upbeat" in "\n".join(highlights.analysis), "precondition: text kept"
    assert _has_error(eff_val, "highlights_unsubstantiated")
    assert eff_val.errors


def test_effective_section_analysis_covers_all_sections():
    report = build_earnings_deep_dive_report(
        ticker="MSFT", company="Microsoft Corporation", quarter="FY2026 Q1",
        language="en", metrics=GENERIC_METRICS, transcript_url="",
        section_analysis=UNSUBSTANTIATED_RAW,
    )
    effective = effective_section_analysis(report)
    assert set(effective) == {s.key for s in report.sections}
    assert all(isinstance(v, str) for v in effective.values())


def test_non_regression_valid_fixture_renders_pdf(tmp_path):
    """End-to-end with the new order: a normal valid report must pass the
    effective gate and still render a PDF."""
    _, eff_val, report = _effective_validation("MSFT", UNSUBSTANTIATED_RAW, GENERIC_METRICS)
    assert not eff_val.errors
    pdf_path = tmp_path / "deep_dive.pdf"
    render_earnings_deep_dive_pdf(report, pdf_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 10_000
