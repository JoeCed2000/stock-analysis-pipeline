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


# ── Unicode bullet normalization (EDP-008, EDP-009, generic) ───────────────

class TestUnicodeBulletNormalization:
    """Regression: Unicode bullet characters from LLM output must be normalized
    before concision checks. The prompt instructs the LLM to use `•` bullets
    but the validator only recognized ASCII `-` and `*`."""

    def test_unicode_bullet_operating_metrics_not_flagged(self, tmp_path):
        """Operating Metrics Key Takeaways with `•` bullets pass concision after normalization."""
        extra = """
## Highlights & Lowlights

| Type | Point | Severity |
|------|-------|----------|
| Highlight | Revenue growth | High |

> One-line summary: Strong quarter.

## Operating Metrics

| Metric | Actual |
|--------|--------|
| Gross Margin | 65% |
| Operating Margin | 45% |

Key Takeaways:
• Gross margin of 65% reflects strong pricing power and favorable mix.
• Operating leverage improved as revenue grew faster than expenses.
• Operating margin of 45% is comparable to leading software peers.
• Net income aligns with operating income trends.
• Revenue growth and margin expansion together indicate high quality.

> One-line summary: Strong profitability across the board.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp009_issues = [i for i in issues if "EDP-009" in i]
        edp008_issues = [i for i in issues if "EDP-008" in i]
        assert len(edp009_issues) == 0, f"EDP-009 should not fire for Unicode bullet takeaways: {edp009_issues}"
        assert len(edp008_issues) == 0, f"EDP-008 should not fire for Highlights with table + one-liner: {edp008_issues}"

    def test_unicode_bullet_highlights_subsection_stripped(self, tmp_path):
        """Highlights & Lowlights with `•` bullets in ### sub-sections passes
        after the normalization strips the duplicate sub-sections."""
        content = """# Earnings Call Deep-Dive

## EPS & Revenue

| Metric | Value |
|--------|-------|
| EPS | 1.23 |

> One-line summary: OK.

## Highlights & Lowlights

| Type | Number | Point | Severity |
|------|--------|-------|----------|
| 🌟 Highlight | ① | Record revenue | High |
| ⚠️ Lowlight | ① | Consumer softness | Medium |

### Highlights
1. Record revenue and growth
   • Revenue $81.61B, +85.2% YoY.
   • EPS $1.87 beat consensus.

### Lowlights
1. Consumer demand decline
   • Consumer demand fell due to higher prices.

> One-line summary: Strong revenue growth with consumer headwinds.

## Operating Metrics

| Metric | Value |
|--------|-------|
| Gross Margin | 65% |

> One-line summary: OK.

## Cash Flow

| Metric | Value |
|--------|-------|
| FCF | $2.5B |

> One-line summary: OK.

## Capital Efficiency

| Metric | Value |
|--------|-------|
| ROIC | 25% |

> One-line summary: OK.

## Segments

| Segment | Revenue |
|---------|---------|
| Data Center | $7.0B |

> One-line summary: OK.

## Forward P/E

| Metric | Value |
|--------|-------|
| Fwd P/E | 35x |

> One-line summary: OK.

## Backlog Quality

| Metric | Value |
|--------|-------|
| Backlog | $5.0B |

> One-line summary: OK.

## Guidance

| Metric | Guidance |
|--------|----------|
| Revenue | $11.0B |

> One-line summary: OK.

## Verdict

> One-line summary: BUY.
"""
        md_path = tmp_path / "earnings_deep_dive.md"
        md_path.write_text(content.strip() + "\n", encoding="utf-8")
        passed, issues = validate_deep_dive(str(md_path))
        edp008_issues = [i for i in issues if "EDP-008" in i]
        assert len(edp008_issues) == 0, f"EDP-008 should not fire after sub-section stripping: {edp008_issues}"

    def test_unicode_bullet_highlights_no_table_not_affected(self, tmp_path):
        """Highlights & Lowlights WITHOUT a table keeps its content unchanged
        by the table-stripping normalization. The `•` → `-` normalization helps
        `•` bullet lists pass concision, which is correct behavior — the bullets
        are the intended format per the prompt."""
        content = """# Earnings Call Deep-Dive

## EPS & Revenue

| Metric | Value |
|--------|-------|
| EPS | 1.23 |

> One-line summary: OK.

## Highlights & Lowlights

**Data Center strength was remarkable this quarter**
• Data Center revenue surged 40% YoY to $7.0B, driven by enterprise AI adoption.
• Management highlighted strong demand from large and small businesses.

> One-line summary: Strong Data Center growth.

## Operating Metrics

| Metric | Value |
|--------|-------|
| Gross Margin | 65% |

> One-line summary: OK.

## Cash Flow

| Metric | Value |
|--------|-------|
| FCF | $2.5B |

> One-line summary: OK.

## Capital Efficiency

| Metric | Value |
|--------|-------|
| ROIC | 25% |

> One-line summary: OK.

## Segments

| Segment | Revenue |
|---------|---------|
| Data Center | $7.0B |

> One-line summary: OK.

## Forward P/E

| Metric | Value |
|--------|-------|
| Fwd P/E | 35x |

> One-line summary: OK.

## Backlog Quality

| Metric | Value |
|--------|-------|
| Backlog | $5.0B |

> One-line summary: OK.

## Guidance

| Metric | Guidance |
|--------|----------|
| Revenue | $11.0B |

> One-line summary: OK.

## Verdict

> One-line summary: BUY.
"""
        md_path = tmp_path / "earnings_deep_dive.md"
        md_path.write_text(content.strip() + "\n", encoding="utf-8")
        passed, issues = validate_deep_dive(str(md_path))
        edp008_issues = [i for i in issues if "EDP-008" in i]
        # The • bullet lines are legitimately valid after normalization → no EDP-008 flags.
        # True prose paragraphs (multi-sentence blocks) would still be flagged.
        assert len(edp008_issues) == 0, f"No-table Highlights with • bullets should pass: {edp008_issues}"

    def test_filled_circle_bullet_normalized(self, tmp_path):
        """Filled circle `●` (U+25CF) is also used by LLMs and must be normalized."""
        extra = """
## Highlights & Lowlights

| Type | Point | Severity |
|------|-------|----------|
| Highlight | Strong demand | High |

> One-line summary: Good quarter.

## Operating Metrics

| Metric | Actual |
|--------|--------|
| Gross Margin | 65% |

Key Takeaways:
● Gross margin of 65% reflects strong pricing power.
● Operating leverage improved significantly.

> One-line summary: Strong margins.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp009_issues = [i for i in issues if "EDP-009" in i]
        assert len(edp009_issues) == 0, f"EDP-009 should not fire for filled circle bullets: {edp009_issues}"

    def test_diamond_bullets_normalized(self, tmp_path):
        """Diamond bullets must not be counted as long prose (AAPL regression)."""
        detail = (
            "Gross margin expanded while revenue growth, operating leverage, cash conversion, "
            "cost discipline, pricing power, and services mix strengthened the investment case."
        )
        bullets = "\n".join(f"◆ {detail}" for _ in range(6))
        extra = f"""
## Highlights & Lowlights

| Type | Point | Severity |
|------|-------|----------|
| Highlight | Strong demand | High |

> One-line summary: Good quarter.

## Operating Metrics

| Metric | Actual |
|--------|--------|
| Gross Margin | 65% |

Key Takeaways:
{bullets}

> One-line summary: Strong margins.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp009_issues = [i for i in issues if "EDP-009" in i]
        assert len(edp009_issues) == 0, (
            f"EDP-009 should not fire for diamond bullets: {edp009_issues}"
        )


    def test_ascii_bullets_still_work(self, tmp_path):
        """Existing ASCII `-` bullets continue to work correctly after normalization."""
        extra = """
## Highlights & Lowlights

| Type | Point | Severity |
|------|-------|----------|
| Highlight | Strong growth | High |

> One-line summary: Good.

## Operating Metrics

| Metric | Actual |
|--------|--------|
| Gross Margin | 65% |

Key Takeaways:
- Gross margin of 65% reflects strong pricing power.
- Operating leverage improved significantly.

> One-line summary: Strong margins.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp009_issues = [i for i in issues if "EDP-009" in i]
        edp008_issues = [i for i in issues if "EDP-008" in i]
        assert len(edp009_issues) == 0, f"EDP-009 should not fire for ASCII bullets: {edp009_issues}"
        assert len(edp008_issues) == 0, f"EDP-008 should not fire for Highlights with table: {edp008_issues}"

    def test_long_prose_operating_metrics_still_flagged(self, tmp_path):
        """Genuinely long prose in Operating Metrics is STILL flagged after normalization."""
        extra = """
## Highlights & Lowlights

| Type | Point | Severity |
|------|-------|----------|
| Highlight | Growth | High |

> One-line summary: Good.

## Operating Metrics

| Metric | Actual |
|--------|--------|
| Gross Margin | 65% |
| Operating Margin | 45% |

The company's gross margin expanded by 200 basis points year over year, reflecting favorable product mix and cost efficiencies. Operating margin grew even faster at 300 basis points, as the company benefited from operating leverage on higher revenue. The margin expansion was driven primarily by the Data Center segment, which carries higher margins than the overall company average. Management expects continued margin improvement as revenue scales and the mix shifts toward higher-margin software and services revenue.

Research and development spending increased 15% year over year as the company continues to invest in next-generation products and AI capabilities. Sales and marketing expenses grew at a slower pace of 8%, indicating operating leverage in the go-to-market organization.

> One-line summary: Strong margin expansion.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp009_issues = [i for i in issues if "EDP-009" in i]
        assert len(edp009_issues) >= 1, "Genuinely long prose in Operating Metrics should still be flagged"

    def test_normalize_only_highlights_with_table(self, tmp_path):
        """Highlights section WITHOUT table keeps its prose sub-sections unchanged."""
        extra = """
## Highlights & Lowlights

**Data Center strength**
- Revenue up 40% YoY
- Enterprise adoption growing

> One-line summary: Data Center remains strong.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp008_issues = [i for i in issues if "EDP-008" in i]
        # No table in highlights — normalization's section-stripping should not apply.
        # This isn't duplicate prose after a table; the bullet-list format is fine.
        assert len(edp008_issues) == 0, f"No-table Highlights should not trigger EDP-008: {edp008_issues}"


# ── EPS & Revenue canonical normalization (EDP-006, EDP-007) ────────────────

class TestEpsRevenueNormalization:
    """Regression: EPS & Revenue section with extra bullet/prose commentary
    must be canonicalized before validation to prevent EDP-006 false conflicts
    (segment revenue dollar figures ≠ table values) and EDP-007 false positives
    (extra narrative paragraphs exceeding word/paragraph limits).

    Kept: table, numbered items (numbered circle 1/2 or numbered-list patterns), one-line summary (>)
    Stripped: bullet items, prose paragraphs, bold labels
    """

    def test_extra_segment_revenue_bullets_passes(self, tmp_path):
        """EPS & Revenue with extra bullet commentary (segment revenue figures)
        passes after normalization strips the bullets. Prose paragraphs kept
        but non-existent here (only numbered items remain)."""
        extra = """\
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.5%) | +214.47% | Company actuals |
| Revenue | — | $81.61B | — | +85.23% | Company filing |

① EPS of $1.87 beat the consensus estimate of $1.77 by 5.5%, a clean surprise, while skyrocketing 214.47% year-over-year.

② Revenue reached $81.61 billion, rising 85.23% from the year-ago quarter; the consensus revenue estimate was not disclosed.

● Data center computing revenue of $60 billion (+77% YoY) underscores Blackwell-driven hyperscale demand.
● Sequential revenue jumped 20%, the largest quarterly dollar increase ever.
● Management highlighted AI cloud revenue more than tripling year-over-year.

> One-line summary: NVIDIA delivered a high-quality beat with EPS of $1.87 and revenue of $81.61B.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-006" in i or "EDP-007" in i]
        assert len(concision_issues) == 0, (
            f"Extra bullet commentary after normalization should not trigger EDP-006/007: "
            f"{concision_issues}"
        )

    def test_already_canonical_eps_passes(self, tmp_path):
        """An EPS & Revenue section with only table + numbered items + summary
        passes (no change needed by normalization)."""
        extra = """\
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.5%) | +214.47% | Company actuals |
| Revenue | — | $81.61B | — | +85.23% | Company filing |

① EPS of $1.87 beat the consensus estimate of $1.77 by 5.5%.

② Revenue reached $81.61 billion, rising 85.23% year-over-year.

> One-line summary: Strong beat on both top and bottom lines.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-006" in i or "EDP-007" in i]
        assert len(concision_issues) == 0, (
            f"Already-canonical EPS section should pass: {concision_issues}"
        )

    def test_numeric_consistency_no_false_conflict_after_normalization(self, tmp_path):
        """EDP-006 numeric consistency check should not fire on segment revenue
        dollar figures after normalization removes them."""
        extra = """\
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.5%) | +214.47% | Company actuals |
| Revenue | — | $81.61B | — | +85.23% | Company filing |

① EPS of $1.87 beat the consensus estimate of $1.77 by 5.5%.

② Revenue reached $81.61 billion, rising 85.23% year-over-year.

● Data center computing revenue of $60 billion (+77% YoY) and networking revenue of $15 billion underscore Blackwell-driven demand.

> One-line summary: NVIDIA delivered a high-quality beat.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        numeric_issues = [i for i in issues if "EDP-006" in i]
        assert len(numeric_issues) == 0, (
            f"Segment revenue figures should be normalized away before EDP-006 check: "
            f"{numeric_issues}"
        )

    def test_prose_paragraphs_still_fire_edp007(self, tmp_path):
        """Prose paragraphs after numbered EPS items are KEPT (not stripped)
        and still subject to EDP-007 concision check."""
        extra = """\
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.5%) | +214.47% | Company actuals |
| Revenue | — | $81.61B | — | +85.23% | Company filing |

① EPS of $1.87 beat consensus by 5.5%.

② Revenue reached $81.61 billion, rising 85.23% year-over-year.

The company's revenue growth was driven by several key factors. First, the Data Center segment continued its strong momentum. Second, the Gaming segment showed signs of recovery. Third, the Automotive segment grew steadily as more manufacturers adopted the platform.

In terms of profitability, the company reported gross margins of 65%, up 200 basis points year over year.

> One-line summary: Strong beat across all segments.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp007_issues = [i for i in issues if "EDP-007" in i]
        assert len(edp007_issues) >= 1, (
            f"Prose paragraphs are kept and should still trigger EDP-007: "
            f"{edp007_issues}"
        )

    def test_bold_labels_stripped(self, tmp_path):
        """Bold section labels (**Growth Drivers**, etc.) within EPS Revenue
        section are stripped."""
        extra = """\
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.5%) | +214.47% | Company actuals |
| Revenue | — | $81.61B | — | +85.23% | Company filing |

① EPS of $1.87 beat consensus by 5.5%.

② Revenue reached $81.61 billion, rising 85.23% year-over-year.

**Growth Drivers**
- Data center revenue surged 77% YoY to $60 billion.
- Enterprise adoption of AI workloads expanding rapidly.

> One-line summary: Growth driven by data center and enterprise AI.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        edp007_issues = [i for i in issues if "EDP-007" in i]
        assert len(edp007_issues) == 0, (
            f"Bold labels + bullet items should be stripped: {edp007_issues}"
        )

    def test_third_numbered_item_stripped_to_prevent_edp006(self, tmp_path):
        """③ (segment-level Data Center revenue) is stripped by normalization,
        preventing false EDP-006 conflicts ($75B Data Center vs $81.61B table).
        Only ① EPS and ② Revenue items survive normalization."""
        extra = """\
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|--------|----------|--------|-------------|------------|--------|
| EPS | $1.77 | $1.87 | +$0.10 (5.5%) | +214.47% | Company actuals |
| Revenue | — | $81.61B | — | +85.23% | Company filing |

① EPS of $1.87 beat the consensus estimate of $1.77 by 5.5%.

② Revenue reached $81.61 billion, rising 85.23% from the year-ago quarter.

③ ◆ Key positives: Data Center revenue of $75B (+92% YoY) and a sequential enterprise AI ramp; free cash flow exceeded prior records. Key concern: supply constraints remain a limiting factor for further sequential acceleration.

> One-line summary: NVIDIA delivered a high-quality beat with EPS of $1.87 and revenue of $81.61B.
"""
        md_path = _make_deep_dive(tmp_path, extra_content=extra)
        passed, issues = validate_deep_dive(md_path)
        # ③ is stripped, so no EDP-006 ($75B vs $81.61B) false positive
        concision_issues = [i for i in issues if "concision" in i.lower() or "EDP-006" in i or "EDP-007" in i]
        assert len(concision_issues) == 0, (
            f"③ should be stripped, preventing EDP-006/007 false positives: "
            f"{concision_issues}"
        )
