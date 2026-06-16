"""§7 Numeric consistency checks — EDP-006 — spec tests.

Tests the post-generation validator's numeric consistency enforcement for:
- EDP-006: Revenue and EPS values in the EPS & Revenue section must be consistent
  across table values, prose, and calculations.

Call path: validate_deep_dive(md_path) → _check_numeric_consistency(content)

The EPS & Revenue table uses this column layout (production format):
  | Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
The Actual column is at index 2. _parse_table_values reads from index 2.
"""

import pytest
from pathlib import Path
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive


# ── Test helpers ──────────────────────────────────────────────────────────

_VALID_SECTIONS = """
# Earnings Call Deep-Dive

## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.15 | $1.23 | +$0.08 | +20% | Consensus |
| Revenue | $9.5B | $10.0B | +$0.5B | +15% | Earnings release |

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

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $2.20 | $2.34 | +$0.14 | +12% | Consensus |
| Revenue | $12.0B | $12.5B | +$0.5B | +10% | Earnings release |

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

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.15 | $1.23 | +$0.08 | +20% | Consensus |
| Revenue | $9.5B | $10.0B | +$0.5B | +15% | Earnings release |

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

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.15 | $1.23 | +$0.08 | +20% | Consensus |
| Revenue | $9.5B | $10.0B | +$0.5B | +15% | Earnings release |

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

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.15 | $1.23 | +$0.08 | +20% | Consensus |
| Revenue | $9.5B | $10.0B | +$0.5B | +15% | Earnings release |

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

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.15 | $1.23 | +$0.08 | +20% | Consensus |
| Revenue | $9.5B | $10.0B | +$0.5B | +15% | Earnings release |

> Over 70% of revenue came from recurring sources.

> Data Center grew by 40% year over year.

> One-line summary: Strong growth across segments.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0

    def test_nvda_edp006_no_false_positive(self, tmp_path):
        """NVDA-style prose with EPS beat ($1.87 actual vs $1.77 estimate) should NOT trigger EDP-006.
        
        Regression test for the _parse_table_values cell index bug: the function was reading
        cells[1] (Estimate = $1.77) instead of cells[2] (Actual = $1.87). When prose says
        "EPS of $1.87", it correctly matches the table's Actual column.
        """
        extra = """
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (+5.5%) | +214.5% | Estimate: Company-supplied consensus; Actual: Earnings release |
| Revenue | — | $81.61B | — | +85.2% | Revenue Actual: Earnings release; YoY Change: Calculated |

> EPS: NVIDIA reported EPS of $1.87, beating the consensus estimate of $1.77 by 5.5%

> Revenue reached $81.61 billion, up 85.2% YoY.

> One-line summary: Strong beat on both top and bottom lines.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0, f"Got false positive: {numeric_issues}"

    def test_segment_revenue_not_flagged_as_edp006(self, tmp_path):
        """Segment revenue amounts (e.g. Data Center $75B in the ② numbered item)
        should NOT trigger EDP-006 false positive against the table's total revenue.

        Regression test for: EPS & Revenue ② contains "Data Center revenue of $75
        billion" alongside total "revenue of $81.61 billion". The $75B is a valid
        segment figure, not a total revenue contradiction. Generic: no ticker/company
        values in the filter logic.
        """
        extra = """
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.6%) | +214.5% | Consensus estimate; actual from Company filing |
| Revenue | — | $81.61B | — | +85.2% | Company quarterly filing |

① EPS **BEAT** the consensus estimate of $1.77 by +$0.10 (a 5.6% surprise), driven by explosive data center demand and operating leverage.

② Revenue consensus estimate was not disclosed in the available data; actual revenue of $81.61 billion surged +85.2% year-over-year, reflecting record Data Center revenue of $75 billion (+92% YoY) and a $13.5 billion sequential jump, as noted on the earnings call.

③ Key positives: EPS and revenue both set quarterly records, with Data Center computing revenue up 77% YoY.

> One-line summary: NVIDIA delivered a flawless hypergrowth quarter with record revenue and an EPS beat.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        assert len(numeric_issues) == 0, (
            f"Segment revenue ($75B Data Center) should NOT trigger EDP-006: "
            f"got {numeric_issues}"
        )

    def test_real_revenue_mismatch_still_flagged_with_segment_data(self, tmp_path):
        """True revenue contradictions should still be flagged even when
        segment revenue data is present. Ensures the segment-revenue skip
        does NOT silence legitimate EDP-006 detections."""
        extra = """
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.6%) | +214.5% | Consensus estimate; actual from Company filing |
| Revenue | — | $81.61B | — | +85.2% | Company quarterly filing |

① EPS **BEAT** the consensus estimate of $1.77 by +$0.10.

② Revenue consensus estimate was not disclosed; actual revenue of $90.0 billion surged, reflecting record Data Center revenue of $75 billion and strong demand.

> One-line summary: Revenue beat expectations.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
        # $90B is a real mismatch vs table $81.61B — should still be flagged
        assert len(numeric_issues) >= 1, (
            f"True revenue mismatch ($90B vs $81.61B) SHOULD trigger EDP-006 even "
            f"with segment revenue present: got {numeric_issues}"
        )
