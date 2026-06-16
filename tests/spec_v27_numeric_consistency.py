"""§7 Numeric consistency checks — EDP-006 — spec tests.

Tests the post-generation validator's numeric consistency enforcement for:
- EDP-006: Revenue and EPS values in the EPS & Revenue section must be consistent
  across table values, prose, and calculations.

Call path: validate_deep_dive(md_path) → _check_numeric_consistency(content)
"""

import pytest
from pathlib import Path
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive


# ── Test helpers ──────────────────────────────────────────────────────────

_VALID_SECTIONS = """
# Earnings Call Deep-Dive

## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $1.23 | $1.15 |
| Revenue | $10.0B | $9.5B |

> Revenue of $10.0B exceeded estimates driven by Data Center strength.

> EPS of $1.23 came in above the $1.15 consensus.

> One-line summary: Strong revenue growth driven by Data Center.

## Highlights & Lowlights

**Data Center strength**
- Record revenue of $7.0B, up 40% YoY

> One-line summary: Data Center remains the key growth engine.

## Operating Metrics

| Metric | Q1 | Q2 | YoY |
|--------|-----|-----|-----|
| Gross Margin | 65% | 63% | +2pp |

> One-line summary: Gross margin expanded on mix shift.

## Cash Flow

| Metric | Value |
|--------|-------|
| FCF | $2.5B |

> One-line summary: Strong cash generation.

## Capital Efficiency

| Metric | Value |
|--------|-------|
| ROIC | 25% |

> One-line summary: Capital-efficient business.

## Segments

| Segment | Revenue |
|---------|---------|
| Data Center | $7.0B |

> One-line summary: Data Center dominates.

## Forward P/E

| Metric | Value |
|--------|-------|
| Fwd P/E | 35x |

> One-line summary: Premium valuation justified by growth.

## Backlog Quality

| Metric | Value |
|--------|-------|
| Backlog | $5.0B |

> One-line summary: Strong backlog visibility.

## Guidance

| Metric | Guidance |
|--------|----------|
| Revenue | $11.0B |

> One-line summary: Guidance above consensus.

## Verdict

> One-line summary: BUY — strong execution.
"""


def _make_deep_dive(tmp_path: Path, extra_content: str = "") -> str:
    """Create a temporary earnings_deep_dive.md with valid sections + optional extra content."""
    md_path = tmp_path / "earnings_deep_dive.md"
    content = _VALID_SECTIONS.strip() + "\n\n" + extra_content
    md_path.write_text(content, encoding="utf-8")
    return str(md_path)


# ── EDP-006: EPS & Revenue numeric consistency ──────────────────────────

class TestEdp006EpsRevenueNumericConsistency:
    """EDP-006: EPS and Revenue values in the EPS & Revenue section must be
    consistent across table values and prose."""

    def test_consistent_values_pass(self, tmp_path):
        """Prose that matches table values should pass cleanly."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0

    def test_consistent_values_in_compact_section_pass(self, tmp_path):
        """Compact matching values in a tight EPS & Revenue section should pass."""
        extra = """
## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $2.34 | $2.20 |
| Revenue | $12.5B | $12.0B |

> Revenue came in at $12.5B, above the $12.0B estimate.

> EPS of $2.34 topped consensus by $0.14.

> One-line summary: Beat on both top and bottom lines.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0

    def test_eps_mismatch_flagged(self, tmp_path):
        """Prose that states a different EPS value than the table should be flagged."""
        extra = """
## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $1.23 | $1.15 |
| Revenue | $10.0B | $9.5B |

> Revenue of $10.0B exceeded expectations.

> EPS of $1.18 came in above consensus.

> One-line summary: Mixed results.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) >= 1
        # The issue should mention EPS
        assert any("EPS" in i for i in numeric_issues)

    def test_revenue_mismatch_flagged(self, tmp_path):
        """Prose that states a different Revenue value than the table should be flagged."""
        extra = """
## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $1.23 | $1.15 |
| Revenue | $10.0B | $9.5B |

> Revenue of $9.8B was slightly below expectations.

> EPS of $1.23 matched estimates.

> One-line summary: Revenue slightly soft.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) >= 1
        # The issue should mention Revenue
        assert any("Revenue" in i for i in numeric_issues)

    def test_no_false_positive_without_values(self, tmp_path):
        """When no explicit EPS/Revenue values appear in prose, no issue should be raised."""
        extra = """
## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $1.23 | $1.15 |
| Revenue | $10.0B | $9.5B |

> The company beat on both top and bottom lines this quarter.

> Growth was driven by strong execution across segments.

> One-line summary: Strong quarter across the board.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0

    def test_no_false_positive_ambiguous_numbers(self, tmp_path):
        """When prose mentions numbers that aren't clearly EPS or Revenue, no false positive."""
        extra = """
## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $1.23 | $1.15 |
| Revenue | $10.0B | $9.5B |

> Over 70% of revenue came from recurring sources.

> Data Center grew by 40% year over year.

> One-line summary: Strong growth across segments.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0
