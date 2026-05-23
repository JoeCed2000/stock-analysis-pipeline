"""
TDD tests for pre-render validator — inserted between deep-dive generation and PDF build.

Validates:
- No "Not available" in section text
- Quarter consistency (quarter=None → flagged)
- Number consistency vs source metrics (±5%)
- Score-commentary alignment in Verdict
- Non-blocking: always returns, never raises on bad input
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.earnings_deep_dive.schemas import FinancialMetrics


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Detects "Not available" markers in section analysis
# ═══════════════════════════════════════════════════════════════════════════════

def test_detects_not_available_in_sections():
    """Validator flags sections containing 'Not available' or equivalent."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics(
        eps_estimate=3.10,
        eps_actual=3.46,
        revenue_actual=82_900_000_000,
    )
    section_analysis = {
        "EPS & Revenue": "EPS came in at $3.46, beating estimates of $3.10.\n\nRevenue: Not available",
        "Highlights": "Strong quarter with record cloud revenue.",
    }

    result = validate_pre_render(
        ticker="MSFT",
        quarter="2026Q1",
        metrics=metrics,
        section_analysis=section_analysis,
    )

    # Warning-only checks should NOT block rendering; they annotate sections.
    assert result.passed is True, "Warning-only issues should not block PDF rendering"
    assert len(result.warnings) >= 1, f"Expected ≥1 warning, got {len(result.warnings)}"
    not_avail_warnings = [w for w in result.warnings if "Not available" in w.detail]
    assert len(not_avail_warnings) >= 1, "Should have a warning about 'Not available'"
    assert not_avail_warnings[0].section == "EPS & Revenue"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Catches quarter=None via "Not available" in title/sections
# ═══════════════════════════════════════════════════════════════════════════════

def test_detects_missing_quarter():
    """Given deep-dive with quarter=None → validator catches 'Not available' in title."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics()
    section_analysis = {
        "EPS & Revenue": "Quarter: Not available. Revenue data unavailable.",
    }

    result = validate_pre_render(
        ticker="NVDA",
        quarter=None,  # Explicitly None — simulates missing quarter
        metrics=metrics,
        section_analysis=section_analysis,
    )

    # Must detect the missing quarter as a warning, without blocking rendering
    assert result.passed is True
    quarter_warnings = [w for w in result.warnings if w.check == "quarter_missing"]
    assert len(quarter_warnings) >= 1, (
        f"Should flag quarter=None, got warnings: {[w.check for w in result.warnings]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Passes clean data silently
# ═══════════════════════════════════════════════════════════════════════════════

def test_passes_clean_data():
    """Clean section_analysis with no issues → passed=True, no warnings."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics(
        eps_estimate=3.10,
        eps_actual=3.46,
        eps_vs_estimate=0.116,
        eps_yoy=0.22,
        revenue_actual=82_900_000_000,
        revenue_yoy=0.183,
    )
    section_analysis = {
        "EPS & Revenue": "Revenue reached $82.9B, up 18.3% YoY. EPS of $3.46 beat consensus of $3.10 by 11.6%.",
        "Highlights": "All segments showed growth. Cloud revenue up 25%.",
        "Verdict": "Strong BUY. Score 8/10. Positive outlook.",
    }

    result = validate_pre_render(
        ticker="MSFT",
        quarter="FY2026 Q1",
        metrics=metrics,
        section_analysis=section_analysis,
    )

    assert result.passed is True, f"Clean data should pass, but got: {[w.detail for w in result.warnings]}"
    assert len(result.warnings) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: Validator is non-blocking — always returns, never raises
# ═══════════════════════════════════════════════════════════════════════════════

def test_never_blocks_on_bad_input():
    """Validator handles empty/None/malformed input gracefully without raising."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    # Empty section_analysis
    result = validate_pre_render(
        ticker="TEST",
        quarter="2026Q1",
        metrics=FinancialMetrics(),
        section_analysis={},
    )
    assert result is not None
    assert isinstance(result.warnings, list)

    # None section_analysis
    result = validate_pre_render(
        ticker="TEST",
        quarter="2026Q1",
        metrics=FinancialMetrics(),
        section_analysis=None,
    )
    assert result is not None
    assert isinstance(result.warnings, list)

    # All-None metrics
    result = validate_pre_render(
        ticker="TEST",
        quarter=None,
        metrics=FinancialMetrics(),
        section_analysis={"EPS & Revenue": "Data not available"},
    )
    assert result is not None
    # Should still flag the issues as warnings without blocking rendering
    assert result.passed is True
    assert any(w.check == "quarter_missing" for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: Detects score-commentary contradiction
# ═══════════════════════════════════════════════════════════════════════════════

def test_detects_score_commentary_contradiction():
    """If Verdict section text is negative but score appears positive → flag."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics()
    section_analysis = {
        "Verdict": (
            "Score: 8/10 — Strong BUY.\n"
            "However, the outlook is deeply negative. "
            "Multiple headwinds will destroy margins. "
            "We recommend avoiding this stock entirely. "
            "Sell immediately before the crash."
        ),
    }

    result = validate_pre_render(
        ticker="AAPL",
        quarter="2026Q1",
        metrics=metrics,
        section_analysis=section_analysis,
    )

    # Should detect the contradiction: score=8 (positive) but text is overwhelmingly negative
    contradiction_warnings = [w for w in result.warnings if w.check == "score_commentary_contradiction"]
    assert len(contradiction_warnings) >= 1, (
        f"Should flag score-commentary contradiction. Warnings: {[(w.check, w.detail[:60]) for w in result.warnings]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6: Number mismatch detection (±5% tolerance)
# ═══════════════════════════════════════════════════════════════════════════════

def test_detects_number_mismatch():
    """When section text mentions a number far from metrics value → flag."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics(
        revenue_actual=82_900_000_000,  # $82.9B
        eps_actual=3.46,
    )
    # Text says $50B — way off from $82.9B (>5%)
    section_analysis = {
        "EPS & Revenue": "Revenue was $50.0B this quarter. EPS came in at $3.46.",
    }

    result = validate_pre_render(
        ticker="MSFT",
        quarter="2026Q1",
        metrics=metrics,
        section_analysis=section_analysis,
    )

    mismatch_warnings = [w for w in result.warnings if w.check == "number_mismatch"]
    assert len(mismatch_warnings) >= 1, (
        f"Should flag $50B vs actual $82.9B mismatch. Warnings: {[(w.check, w.detail[:60]) for w in result.warnings]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7: annotate_sections_with_warnings injects ⚠️ markers
# ═══════════════════════════════════════════════════════════════════════════════

def test_annotate_sections_with_warnings_adds_warning_prefix():
    """When validation finds issues, affected sections get ⚠️ prefix."""
    from backend.earnings_deep_dive.pre_render_validator import (
        ValidationResult,
        ValidationWarning,
        annotate_sections_with_warnings,
    )

    section_analysis = {
        "EPS & Revenue": "Revenue was $82.9B. EPS of $3.46.",
        "Verdict": "Score: 8/10. Sell immediately before the crash.",
        "Clean Section": "Everything looks good here.",
    }

    warnings = [
        ValidationWarning(
            check="not_available",
            section="EPS & Revenue",
            detail="'Not available' found",
        ),
        ValidationWarning(
            check="score_commentary_contradiction",
            section="Verdict",
            detail="Score is 8/10 but negative phrases found",
        ),
    ]

    result = ValidationResult(passed=False, warnings=warnings)
    annotated = annotate_sections_with_warnings(section_analysis, result)

    # Affected sections get ⚠️ prefix
    assert annotated["EPS & Revenue"].startswith("⚠️"), (
        f"EPS & Revenue should have ⚠️ prefix, got: {annotated['EPS & Revenue'][:50]}"
    )
    assert annotated["Verdict"].startswith("⚠️"), (
        f"Verdict should have ⚠️ prefix, got: {annotated['Verdict'][:50]}"
    )
    # Clean section is untouched
    assert annotated["Clean Section"] == "Everything looks good here."
    # Original is unmutated
    assert not section_analysis["EPS & Revenue"].startswith("⚠️")


def test_annotate_sections_passes_through_when_no_warnings():
    """When validation passes, section_analysis is returned unchanged."""
    from backend.earnings_deep_dive.pre_render_validator import (
        ValidationResult,
        annotate_sections_with_warnings,
    )

    section_analysis = {"EPS & Revenue": "Revenue was $82.9B."}
    result = ValidationResult(passed=True, warnings=[])
    annotated = annotate_sections_with_warnings(section_analysis, result)

    assert annotated is section_analysis, (
        "Should return the same dict when validation passes"
    )


def test_annotate_sections_does_not_double_prefix():
    """⚠️ is not added twice if text already starts with it."""
    from backend.earnings_deep_dive.pre_render_validator import (
        ValidationResult,
        ValidationWarning,
        annotate_sections_with_warnings,
    )

    section_analysis = {"EPS & Revenue": "⚠️ Revenue was $82.9B."}
    warnings = [
        ValidationWarning(
            check="not_available",
            section="EPS & Revenue",
            detail="'Not available' found",
        ),
    ]
    result = ValidationResult(passed=False, warnings=warnings)
    annotated = annotate_sections_with_warnings(section_analysis, result)

    # Should NOT double-prefix
    assert annotated["EPS & Revenue"] == "⚠️ Revenue was $82.9B.", (
        f"Should not double-prefix, got: {annotated['EPS & Revenue']}"
    )


def test_segment_sum_overflow_overlapping_dimensions_warns_not_blocks():
    """MSFT-style overlapping segment dimensions must warn, not block PDF rendering.

    A 10-Q can contain several non-additive segment dimensions in the same XBRL
    extraction (product/service + business segments + geography + cloud subset).
    Summing every row is mathematically invalid even when each individual row is
    plausible and below total revenue.
    """
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics(
        revenue_actual=82_886_000_000,
        segments={
            "Product": {"revenue": 15_089_000_000},
            "Service and Other": {"revenue": 67_797_000_000},
            "Productivity and Business Processes": {"revenue": 35_013_000_000},
            "Intelligent Cloud": {"revenue": 34_681_000_000},
            "More Personal Computing": {"revenue": 13_192_000_000},
            "Microsoft Cloud": {"revenue": 54_500_000_000},
            "total_revenue_quarterly": 82_886_000_000,
            "period": "quarterly",
            "source_form": "10-Q",
        },
    )

    result = validate_pre_render(
        ticker="MSFT",
        quarter="2026Q1",
        metrics=metrics,
        section_analysis={"Segments": "Segment table from SEC 10-Q."},
    )

    assert result.passed is True
    overflow = [w for w in result.warnings if w.check == "segment_sum_overflow"]
    assert overflow
    assert overflow[0].severity == "warning"


def test_segment_individual_revenue_above_total_still_blocks():
    """A single segment above total revenue remains a blocking data-contract error."""
    from backend.earnings_deep_dive.pre_render_validator import validate_pre_render

    metrics = FinancialMetrics(
        revenue_actual=82_886_000_000,
        segments={
            "Impossible Segment": {"revenue": 120_000_000_000},
            "total_revenue_quarterly": 82_886_000_000,
            "period": "quarterly",
            "source_form": "10-Q",
        },
    )

    result = validate_pre_render(
        ticker="TEST",
        quarter="2026Q1",
        metrics=metrics,
        section_analysis={"Segments": "Segment table from SEC 10-Q."},
    )

    errors = [w for w in result.errors if w.check == "segment_coherence"]
    assert result.passed is False
    assert errors

