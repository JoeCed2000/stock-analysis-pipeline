"""Regression tests for AVGO/Broadcom PDF pre-render quality gates."""

from types import SimpleNamespace

from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


def test_revenue_consistency_uses_actual_column_not_estimate():
    """EPS & Revenue table has Estimate before Actual; gate must compare Actual."""
    sections = {
        "EPS & Revenue": """
| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|---|---|---|---|---|---|
| Revenue | $22.06B | $19.31B | -$2.75B (-12.5%), MISSED | +29.47% | Actual: Yahoo |
""",
        "Operating Metrics": """
| Metric | Actual | Prior Year | YoY | Source |
|---|---|---|---|---|
| Revenue | $19.31B | $14.92B | +29.47% | yfinance |
""",
    }
    metrics = SimpleNamespace(segments={}, revenue_actual=19.31e9)

    result = validate_pre_render("AVGO", "FY2026 Q2", metrics, sections)

    assert not any(w.check == "cross_section_revenue_mismatch" for w in result.errors)


def test_segment_gate_ignores_balance_sheet_rows_named_like_metrics():
    """Press-release balance sheet rows must not be treated as revenue segments."""
    metrics = SimpleNamespace(
        revenue_actual=19.31e9,
        segments={
            "total_revenue_quarterly": 19.31e9,
            "Additional paid-in capital": {"revenue": 713.08e9},
            "Products": {"revenue": 14.13e9},
            "Subscriptions and services": {"revenue": 5.18e9},
        },
    )

    result = validate_pre_render("AVGO", "FY2026 Q2", metrics, {})

    assert not any(
        w.check == "segment_coherence" and "Additional paid-in capital" in w.detail
        for w in result.errors
    )
