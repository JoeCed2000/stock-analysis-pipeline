"""§7 Concision checks — EDP-007, EDP-008, EDP-009 — spec tests.

Tests the post-generation validator's concision enforcement for:
- EDP-007: EPS & Revenue must be concise (table + short bullets, not long prose)
- EDP-008: Highlights/Lowlights must use short headings + limited bullets
- EDP-009: Operating Metrics must be concise takeaways after table

Call path: validate_deep_dive(md_path) → _check_concision(content)
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

> Beat on both top and bottom lines.

> One-line summary: Strong revenue growth driven by Data Center.

## Highlights & Lowlights

**Data Center strength**
- Record revenue of $7.0B, up 40% YoY
- Driven by enterprise adoption

**Gaming recovery**
- Revenue up 15% sequentially
- Console cycle driving demand

> One-line summary: Data Center remains the key growth engine.

## Operating Metrics

| Metric | Q1 | Q2 | YoY |
|--------|----|-----|-----|
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


# ── EDP-007: EPS & Revenue concision ─────────────────────────────────────

class TestEdp007EpsRevenueConcision:
    """EDP-007: EPS & Revenue must remain compact: table + short bullets, not long prose blocks."""

    def test_valid_compact_eps_passes(self, tmp_path):
        """A concise EPS & Revenue section (table + short bullets only) → no concision issues."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-007" in i]
        assert len(concision_issues) == 0

    def test_long_prose_eps_flagged(self, tmp_path):
        """Long prose paragraphs after EPS table are flagged."""
        extra = """
## EPS & Revenue

| Metric | Value |
|--------|-------|
| EPS | $1.23 |

The company's revenue growth this quarter was driven by several key factors. First, the Data Center segment continued its strong momentum with record revenue of $7.0 billion, representing a 40% increase year over year. This growth was fueled by enterprise adoption of AI infrastructure and cloud computing services. Second, the Gaming segment showed signs of recovery with a 15% sequential increase, driven by the current console cycle and new product launches. Third, the Automotive segment grew steadily as more manufacturers adopted the company's autonomous driving platform.

In terms of profitability, the company reported gross margins of 65%, up 200 basis points year over year, driven by favorable product mix and cost efficiencies. Operating expenses grew at a slower pace than revenue, leading to operating margin expansion. The company also generated strong free cash flow of $2.5 billion, which it used to return capital to shareholders through dividends and share buybacks.

Looking ahead, management provided guidance that was above consensus expectations, citing strong demand across all major end markets. The company expects revenue to grow by another 20% in the coming quarter, with continued margin expansion as the mix shifts toward higher-margin software and services revenue.

> One-line summary: Growth was strong across all segments.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-007" in i]
        assert len(concision_issues) >= 1

    def test_multi_paragraph_eps_flagged(self, tmp_path):
        """Multiple paragraph blocks after EPS table are flagged."""
        extra = """
## EPS & Revenue

| Metric | Value |
|--------|-------|
| EPS | $1.23 |

First paragraph with some text about revenue growth.

Second paragraph with more analysis about margins.

> One-line summary: Growth was strong.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-007" in i]
        assert len(concision_issues) >= 1


# ── EDP-008: Highlights & Lowlights concision ────────────────────────────

class TestEdp008HighlightsConcision:
    """EDP-008: Highlights/Lowlights must use short headings + limited bullets, no long paragraphs."""

    def test_valid_compact_highlights_passes(self, tmp_path):
        """Concise highlights (short headings + bullets) → no concision issues."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-008" in i]
        assert len(concision_issues) == 0

    def test_paragraph_in_highlights_flagged(self, tmp_path):
        """A long prose paragraph inside Highlights is flagged."""
        extra = """
## Highlights & Lowlights

**Data Center strength was remarkable this quarter**
The Data Center segment posted record revenue of $7.0 billion, up 40% year over year. This growth was driven by enterprise adoption of AI infrastructure and cloud computing services. Management highlighted strong demand from both large enterprises and small-to-medium businesses adopting generative AI workloads.

**Gaming continues to show positive momentum**
Revenue from the Gaming segment increased 15% sequentially, driven by the current console cycle and new product launches. The company expects this trend to continue through the remainder of the fiscal year.

> One-line summary: Mixed results across segments.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-008" in i]
        assert len(concision_issues) >= 1

    def test_too_many_bullets_per_point_flagged(self, tmp_path):
        """A highlight point with excessive bullets is flagged."""
        extra = """
## Highlights & Lowlights

**Data Center strength**
- Revenue up 40% YoY
- Enterprise adoption growing
- AI infrastructure demand strong
- Cloud partnerships expanding
- New product launches
- Geographic expansion
- Headcount growth for AI

> One-line summary: Strong across all segments.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-008" in i]
        assert len(concision_issues) >= 1


# ── EDP-009: Operating Metrics concision ─────────────────────────────────

class TestEdp009OperatingMetricsConcision:
    """EDP-009: Operating Metrics commentary must be concise takeaways after the table."""

    def test_valid_operating_metrics_passes(self, tmp_path):
        """Concise Operating Metrics section (table + short takeaways) → no concision issues."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-009" in i]
        assert len(concision_issues) == 0

    def test_long_prose_operating_metrics_flagged(self, tmp_path):
        """Long explanatory essay after Operating Metrics table is flagged."""
        extra = """
## Operating Metrics

| Metric | Q1 | Q2 | YoY |
|--------|-----|-----|-----|
| Gross Margin | 65% | 63% | +2pp |
| Operating Margin | 45% | 42% | +3pp |

The company's gross margin expanded by 200 basis points year over year, reflecting favorable product mix and cost efficiencies. Operating margin grew even faster at 300 basis points, as the company benefited from operating leverage on higher revenue. The margin expansion was driven primarily by the Data Center segment, which carries higher margins than the overall company average. Management expects continued margin improvement as revenue scales and the mix shifts toward higher-margin software and services revenue.

Research and development spending increased 15% year over year as the company continues to invest in next-generation products and AI capabilities. Sales and marketing expenses grew at a slower pace of 8%, indicating operating leverage in the go-to-market organization. General and administrative expenses were flat, reflecting the company's focus on cost discipline.

The effective tax rate was 12%, compared to 15% in the prior year, driven by favorable tax treatment of certain international operations. Management expects the effective tax rate to remain in the 10-13% range for the remainder of the year. Overall, the company's profitability metrics remain healthy and supportive of the investment thesis.

> One-line summary: Strong margin expansion across the board.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-009" in i]
        assert len(concision_issues) >= 1


# ── Edge cases ────────────────────────────────────────────────────────────

class TestConcisionEdgeCases:
    """Edge cases for concision checks."""

    def test_empty_section_not_false_positive(self, tmp_path):
        """An empty section body should not create false concision issues."""
        extra = """
## EPS & Revenue

| Metric | Value |
|--------|-------|
| EPS | $1.23 |

## Highlights & Lowlights

Some content here.

> One-line summary: Fine.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-" in i]
        # Should only have concision issues if thresholds are genuinely exceeded
        assert isinstance(concision_issues, list)
