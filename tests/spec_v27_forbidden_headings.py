"""§7 Forbidden heading checks — EDP-004 and EDP-011 — spec tests.

Tests the post-generation validator's forbidden heading detection for:
- EDP-004: Stable background headings (Company Overview, Business Model, etc.)
- EDP-011: Generic Quality subsections/headings

Call path: validate_deep_dive(md_path) → ... → _check_forbidden_headings(content)
"""

import pytest
from pathlib import Path
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive


# ── Test helpers ──────────────────────────────────────────────────────────

_VALID_SECTIONS = """
# Earnings Call Deep-Dive

## EPS & Revenue

Table data here.

## Highlights & Lowlights

Highlights here.

## Operating Metrics

Table data here.

## Cash Flow

Table data here.

## Capital Efficiency

Table data here.

## Segments

Table data here.

## Forward P/E

Table data here.

## Backlog Quality

Table data here.

## Guidance

Table data here.

## Verdict

> One-line summary: Strong quarter.
"""


def _make_deep_dive(tmp_path: Path, extra_content: str = "") -> str:
    """Create a temporary earnings_deep_dive.md with valid sections + optional extra content."""
    md_path = tmp_path / "earnings_deep_dive.md"
    content = _VALID_SECTIONS.strip() + "\n\n" + extra_content
    md_path.write_text(content, encoding="utf-8")
    return str(md_path)


# ── EDP-004: Forbidden background headings ────────────────────────────────

class TestEdp004ForbiddenBackgroundHeadings:
    """EDP-004: Earnings Deep Dive must exclude stable background sections."""

    def test_valid_deep_dive_no_forbidden_headings(self, tmp_path):
        """A valid deep-dive with only canonical sections → no forbidden-heading issues."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) == 0

    def test_company_overview_flagged(self, tmp_path):
        """'Company Overview' heading at section level is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="## Company Overview\n\nCompany background.\n")
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) >= 1
        assert any("Company Overview" in i for i in heading_issues)

    def test_business_model_flagged(self, tmp_path):
        """'Business Model' heading is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="## Business Model\n\nBusiness description.\n")
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) >= 1
        assert any("Business Model" in i for i in heading_issues)

    def test_revenue_generation_overview_flagged(self, tmp_path):
        """'Revenue Generation Overview' heading is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="## Revenue Generation Overview\n\nRevenue details.\n")
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) >= 1
        assert any("Revenue Generation" in i for i in heading_issues)

    def test_competitive_landscape_flagged(self, tmp_path):
        """'Competitive Landscape' heading is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="## Competitive Landscape\n\nCompetitor analysis.\n")
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) >= 1
        assert any("Competitive Landscape" in i for i in heading_issues)

    def test_multiple_forbidden_headings_all_flagged(self, tmp_path):
        """Multiple forbidden headings produce multiple issues."""
        md_path = _make_deep_dive(
            tmp_path,
            extra_content=(
                "## Company Overview\n\nCompany background.\n\n"
                "## Business Model\n\nBusiness description.\n\n"
                "## Competitive Landscape\n\nCompetitor analysis.\n"
            ),
        )
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) >= 3

    def test_legitimate_competitive_context_not_flagged(self, tmp_path):
        """'Competitive Context' is NOT a forbidden background heading (valid sub-section)."""
        md_path = _make_deep_dive(tmp_path, extra_content="### Competitive Context\n\nBrief context.\n")
        passed, issues = validate_deep_dive(md_path)
        heading_issues = [i for i in issues if "forbidden" in i.lower() and "heading" in i.lower()]
        assert len(heading_issues) == 0


# ── EDP-011: Forbidden generic Quality subsections ────────────────────────

class TestEdp011ForbiddenQualityHeadings:
    """EDP-011: Remove generic Quality subsections when they don't add earnings-specific insight."""

    def test_generic_quality_subheading_flagged(self, tmp_path):
        """Generic 'Quality' subheading at ### level is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="### Quality Assessment\n\nGeneric quality text.\n")
        passed, issues = validate_deep_dive(md_path)
        quality_issues = [i for i in issues if "quality" in i.lower() and "forbidden" in i.lower()]
        assert len(quality_issues) >= 1

    def test_generic_quality_section_heading_flagged(self, tmp_path):
        """Generic 'Quality' heading at ## level is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="## Quality Analysis\n\nGeneric quality text.\n")
        passed, issues = validate_deep_dive(md_path)
        quality_issues = [i for i in issues if "quality" in i.lower() and "forbidden" in i.lower()]
        assert len(quality_issues) >= 1

    def test_backlog_quality_not_flagged(self, tmp_path):
        """'Backlog Quality' is a legitimate required section, NOT flagged."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        quality_issues = [i for i in issues if "quality" in i.lower() and "forbidden" in i.lower()]
        assert len(quality_issues) == 0

    def test_quality_with_earnings_metric_not_flagged(self, tmp_path):
        """Quality heading containing a specific earnings metric name is NOT flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="### Earnings Quality\n\nEarnings quality is strong.\n")
        passed, issues = validate_deep_dive(md_path)
        quality_issues = [i for i in issues if "quality" in i.lower() and "forbidden" in i.lower()]
        assert len(quality_issues) == 0

    def test_leading_quality_word_not_part_of_heading_flagged(self, tmp_path):
        """Heading that starts with 'Quality' (bare word at start) without earnings context is flagged."""
        md_path = _make_deep_dive(tmp_path, extra_content="### Quality\n\nA generic quality section.\n")
        passed, issues = validate_deep_dive(md_path)
        quality_issues = [i for i in issues if "quality" in i.lower() and "forbidden" in i.lower()]
        assert len(quality_issues) >= 1
