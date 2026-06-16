"""§14 Net Debt presence check — EDP-014 — spec tests.

Tests the post-generation validator's Net Debt / Net Cash presence detection:
- EDP-014: If Cash/Cash Equivalents/Marketable Securities and Total Debt rows
  are both present in the Capital Efficiency table, require a Net Debt or
  Net Cash row.

Call path: validate_deep_dive(md_path) → _check_net_debt_presence(content)
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
| Free Cash Flow | $2.5B |
| Revenue | $10.0B |

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


def _make_deep_dive(tmp_path: Path, cap_eff_section: str = "") -> str:
    """Create a temporary earnings_deep_dive.md with custom Capital Efficiency section."""
    md_path = tmp_path / "earnings_deep_dive.md"
    if cap_eff_section:
        import re
        content = _VALID_SECTIONS.strip()
        content = re.sub(
            r"## Capital Efficiency\n\n\|[^\n]+\|[^\n]+\|\n\|[^\n]+\|[^\n]+\|\n(?:[^#\n][^\n]*\n)*",
            cap_eff_section + "\n\n",
            content,
        )
        md_path.write_text(content, encoding="utf-8")
    else:
        md_path.write_text(_VALID_SECTIONS.strip(), encoding="utf-8")
    return str(md_path)


# ── EDP-014: Net Debt / Net Cash presence ────────────────────────────────


class TestEdp014NetDebtPresence:
    """EDP-014: If Cash/Cash Equivalents/Marketable Securities and Total Debt
    rows are both present, Net Debt or Net Cash row must exist."""

    def test_net_debt_present_passes(self, tmp_path):
        """When Capital Efficiency has cash, debt, and Net Debt rows → no EDP-014 issue."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value | Evaluation | Driver | Source |
|-------|-------|-----------|-------|--------|
| ROIC | 25% | Strong | Operating leverage | Source |
| Cash And Cash Equivalents | $5.2B | Adequate | Strong ops | Source |
| Total Debt | $3.1B | Manageable | Low leverage | Source |
| Net Debt | -$2.1B | Net Cash position | Strong balance sheet | Source |

> One-line summary: Capital-efficient business with net cash position."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) == 0

    def test_net_cash_present_passes(self, tmp_path):
        """When Capital Efficiency has cash, debt, and Net Cash rows → no EDP-014 issue."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value | Evaluation | Driver | Source |
|-------|-------|-----------|-------|--------|
| ROIC | 25% | Strong | Operating leverage | Source |
| Cash And Cash Equivalents | $5.2B | Adequate | Strong ops | Source |
| Total Debt | $3.1B | Manageable | Low leverage | Source |
| Net Cash | $2.1B | Healthy | Strong balance sheet | Source |

> One-line summary: Capital-efficient business with net cash position."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) == 0

    def test_missing_net_debt_flagged(self, tmp_path):
        """When Capital Efficiency has cash and debt rows but no Net Debt/Cash → EDP-014 issue."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value | Evaluation | Driver | Source |
|-------|-------|-----------|-------|--------|
| ROIC | 25% | Strong | Operating leverage | Source |
| Cash And Cash Equivalents | $5.2B | Adequate | Strong ops | Source |
| Total Debt | $3.1B | Manageable | Low leverage | Source |

> One-line summary: Capital-efficient business."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) >= 1

    def test_no_issue_when_cash_absent(self, tmp_path):
        """When Capital Efficiency has Total Debt but no cash row → no EDP-014 issue (input missing)."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value | Evaluation | Driver | Source |
|-------|-------|-----------|-------|--------|
| ROIC | 25% | Strong | Operating leverage | Source |
| Total Debt | $3.1B | Manageable | Low leverage | Source |

> One-line summary: Capital-efficient business."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) == 0

    def test_no_issue_when_debt_absent(self, tmp_path):
        """When Capital Efficiency has cash but no Total Debt row → no EDP-014 issue (input missing)."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value | Evaluation | Driver | Source |
|-------|-------|-----------|-------|--------|
| ROIC | 25% | Strong | Operating leverage | Source |
| Cash And Cash Equivalents | $5.2B | Adequate | Strong ops | Source |

> One-line summary: Capital-efficient business."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) == 0

    def test_no_issue_when_no_cap_eff_section(self, tmp_path):
        """When no Capital Efficiency section exists at all → no EDP-014 issue."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value |
|--------|-------|
| ROIC | 25% |

> One-line summary: Capital-efficient business."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) == 0

    def test_marketable_securities_variant_flagged(self, tmp_path):
        """Marketable Securities + Total Debt without Net Debt/Cash → EDP-014 issue."""
        cap_eff = """\
## Capital Efficiency

| Metric | Value | Evaluation | Driver | Source |
|-------|-------|-----------|-------|--------|
| ROIC | 25% | Strong | Operating leverage | Source |
| Marketable Securities | $5.2B | Adequate | Strong ops | Source |
| Total Debt | $3.1B | Manageable | Low leverage | Source |

> One-line summary: Capital-efficient business."""
        md_path = _make_deep_dive(tmp_path, cap_eff)
        passed, issues = validate_deep_dive(md_path)
        edp014_issues = [i for i in issues if "EDP-014" in i]
        assert len(edp014_issues) >= 1
