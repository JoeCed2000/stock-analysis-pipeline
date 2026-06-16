"""§13 FCF Margin presence check — EDP-013 — spec tests.

Tests the post-generation validator's FCF Margin presence detection:
- EDP-013: Include FCF Margin when Free Cash Flow and Revenue are both available.
  Formula: FCF Margin = Free Cash Flow / Revenue × 100%.

Call path: validate_deep_dive(md_path) → _check_fcf_margin_presence(content)
"""

import pytest
from pathlib import Path
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive


# ── Test helpers ──────────────────────────────────────────────────────────

_VALID_SECTIONS = """\
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


def _make_deep_dive(tmp_path: Path, cash_flow_section: str = "") -> str:
    """"Create a temporary earnings_deep_dive.md with custom Cash Flow section."""
    md_path = tmp_path / "earnings_deep_dive.md"
    if cash_flow_section:
        # Replace the default Cash Flow section with the custom one
        import re
        content = _VALID_SECTIONS.strip()
        content = re.sub(
            r"## Cash Flow\n\n\|[^\n]+\|[^\n]+\|\n\|[^\n]+\|[^\n]+\|\n(?:[^#\n][^\n]*\n)*",
            cash_flow_section + "\n\n",
            content,
        )
        md_path.write_text(content, encoding="utf-8")
    else:
        md_path.write_text(_VALID_SECTIONS.strip(), encoding="utf-8")
    return str(md_path)


# ── EDP-013: FCF Margin presence ─────────────────────────────────────────


class TestEdp013FcfMarginPresence:
    """EDP-013: Include FCF Margin when Free Cash Flow and Revenue are both available."""

    def test_fcf_margin_present_passes(self, tmp_path):
        """When Cash Flow section has FCF, Revenue, and FCF Margin rows → no EDP-013 issue."""
        cash_flow = """\
## Cash Flow

| Metric | Value |
|--------|-------|
| Free Cash Flow | $2.5B |
| Revenue | $10.0B |
| FCF Margin | 25% |

> One-line summary: Strong cash generation."""
        md_path = _make_deep_dive(tmp_path, cash_flow)
        passed, issues = validate_deep_dive(md_path)
        edp013_issues = [i for i in issues if "EDP-013" in i]
        assert len(edp013_issues) == 0

    def test_missing_fcf_margin_flagged(self, tmp_path):
        """When Cash Flow has FCF and Revenue rows but no FCF Margin → EDP-013 issue."""
        cash_flow = """\
## Cash Flow

| Metric | Value |
|--------|-------|
| Free Cash Flow | $2.5B |
| Revenue | $10.0B |

> One-line summary: Strong cash generation."""
        md_path = _make_deep_dive(tmp_path, cash_flow)
        passed, issues = validate_deep_dive(md_path)
        edp013_issues = [i for i in issues if "EDP-013" in i]
        assert len(edp013_issues) >= 1

    def test_no_issue_when_fcf_absent(self, tmp_path):
        """When Cash Flow section has Revenue but no FCF → no EDP-013 issue (input missing)."""
        cash_flow = """\
## Cash Flow

| Metric | Value |
|--------|-------|
| Revenue | $10.0B |

> One-line summary: Strong cash generation."""
        md_path = _make_deep_dive(tmp_path, cash_flow)
        passed, issues = validate_deep_dive(md_path)
        edp013_issues = [i for i in issues if "EDP-013" in i]
        assert len(edp013_issues) == 0

    def test_no_issue_when_revenue_absent(self, tmp_path):
        """When Cash Flow section has FCF but no Revenue → no EDP-013 issue (input missing)."""
        cash_flow = """\
## Cash Flow

| Metric | Value |
|--------|-------|
| Free Cash Flow | $2.5B |

> One-line summary: Strong cash generation."""
        md_path = _make_deep_dive(tmp_path, cash_flow)
        passed, issues = validate_deep_dive(md_path)
        edp013_issues = [i for i in issues if "EDP-013" in i]
        assert len(edp013_issues) == 0

    def test_fcf_margin_in_prose_not_table_flagged(self, tmp_path):
        """When FCF Margin is mentioned in prose but not as a table row → still flagged (needs table presence)."""
        cash_flow = """\
## Cash Flow

| Metric | Value |
|--------|-------|
| Free Cash Flow | $2.5B |
| Revenue | $10.0B |

The FCF Margin of 25% reflects strong cash conversion.

> One-line summary: Strong cash generation."""
        md_path = _make_deep_dive(tmp_path, cash_flow)
        passed, issues = validate_deep_dive(md_path)
        edp013_issues = [i for i in issues if "EDP-013" in i]
        # FCF Margin mentioned in prose but not in table → still an issue since
        # the rule requires the PRESENCE of FCF Margin as a calculated metric
        assert len(edp013_issues) >= 1

    def test_valid_section_no_fcf_margin_no_issue(self, tmp_path):
        """The default valid section (FCF only, no Revenue in Cash Flow) → no EDP-013 issue."""
        md_path = _make_deep_dive(tmp_path)
        passed, issues = validate_deep_dive(md_path)
        edp013_issues = [i for i in issues if "EDP-013" in i]
        assert len(edp013_issues) == 0
