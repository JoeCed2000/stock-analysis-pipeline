"""§ EDP-001, EDP-003 — Fiscal-period consistency validator tests.

Tests the post-generation validator's fiscal-period label consistency check:
- EDP-001: Flag contradictory current-quarter fiscal labels.
- EDP-003: Allow prior-year and forward-looking/guidance labels.

Call path: validate_deep_dive(md_path) → _check_fiscal_period_consistency(content)
"""

import pytest
from pathlib import Path
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive
from backend.earnings_deep_dive.deep_dive_validator import _try_parse_quarter


# ── Test _try_parse_quarter helper ────────────────────────────────────────

class TestTryParseQuarter:
    """Test the standalone _try_parse_quarter helper."""

    @pytest.mark.parametrize("label,year,quarter", [
        ("FY2026 Q1", 2026, 1),
        ("FY2025 Q4", 2025, 4),
        ("FY 2027 Q2", 2027, 2),
        ("2026Q1", 2026, 1),
        ("2025Q3", 2025, 3),
        ("Q1 2026", 2026, 1),
        ("Q4 2025", 2025, 4),
    ])
    def test_parse_valid_labels(self, label, year, quarter):
        assert _try_parse_quarter(label) == (year, quarter)

    @pytest.mark.parametrize("label", [
        "", "garbage", "latest quarter", "FY2026", "Q1", "2026-Q1",
        "2026", "January 2026",
    ])
    def test_parse_invalid_returns_none(self, label):
        assert _try_parse_quarter(label) == (None, None)

    def test_matches_mapper_parse(self):
        """_try_parse_quarter should produce same results as mapper's _parse_fiscal_quarter."""
        from backend.earnings_deep_dive.mapper import _parse_fiscal_quarter
        labels = ["FY2026 Q1", "2026Q3", "Q4 2025", "", "garbage", "FY 2027 Q2"]
        for label in labels:
            assert _try_parse_quarter(label) == _parse_fiscal_quarter(label), \
                f"Mismatch for '{label}'"


# ── Test helpers ──────────────────────────────────────────────────────────

_VALID_SECTIONS = """\
# Earnings Call Deep-Dive

## EPS & Revenue

| Metric | Actual | Estimate |
|--------|--------|----------|
| EPS | $1.23 | $1.15 |
| Revenue | $10.0B | $9.5B |

> Beat on both top and bottom lines for FY2026 Q1.

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
|--------|-----|-----|-----|
| Gross Margin | 65% | 63% | +2pp |

> One-line summary: Gross margin expanded on mix shift.

## Cash Flow

| Metric | Value |
|--------|-------|
| Free Cash Flow | $2.5B |

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

Guidance for FY2026 Q2 suggests continued momentum.

> One-line summary: Guidance above consensus.

## Verdict

> One-line summary: BUY — strong execution.
"""


def _make_deep_dive(tmp_path: Path, content: str = "") -> str:
    """Create a temporary earnings_deep_dive.md with custom content."""
    md_path = tmp_path / "earnings_deep_dive.md"
    if content:
        md_path.write_text(content.strip(), encoding="utf-8")
    else:
        md_path.write_text(_VALID_SECTIONS.strip(), encoding="utf-8")
    return str(md_path)


# ── EDP-001: Fiscal-period consistency ────────────────────────────────────

class TestEdp001FiscalPeriodConsistency:
    """EDP-001: Detect contradictory current-quarter fiscal labels."""

    def test_consistent_labels_pass(self, tmp_path):
        """All fiscal labels match the canonical FY2026 Q1 → no EDP-001 issues."""
        content = _VALID_SECTIONS  # Contains FY2026 Q1 (most frequent)
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) == 0, \
            f"Expected 0 EDP-001 issues, got: {edp001_issues}"

    def test_contradictory_quarter_flagged(self, tmp_path):
        """When most labels say FY2026 Q1 but one says FY2026 Q2 → EDP-001 flagged."""
        content = _VALID_SECTIONS.replace(
            "FY2026 Q1", "FY2026 Q1"
        ) + "\nAdditional note for Q2 2026 period.\n"
        # Make FY2026 Q1 still the canonical (more mentions), but add Q2 2026
        content = content.replace("FY2026 Q2", "FY2026 Q2")  # already has FY2026 Q1 in Guidance

        # Actually, let me build a cleaner test case
        content = """\
# Earnings Call Deep-Dive

## EPS & Revenue

Revenue grew strongly in FY2026 Q1, driven by Data Center.

> One-line summary: Strong growth in FY2026 Q1.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        # All labels are FY2026 Q1 → consistent → no issues
        assert len(edp001_issues) == 0

    def test_wrong_quarter_flagged(self, tmp_path):
        """Prior-year FY2025 Q4 is allowed (year-1 any quarter, per TTM patterns).
        A genuinely contradictory label would need to be from year-2+ or far future.
        """
        content = """\
# Earnings Call Deep-Dive

Revenue grew strongly in FY2026 Q1, driven by Data Center.
The company reported FY2026 Q1 results above expectations.

However, the FY2025 Q4 comparison shows a different picture.

> One-line summary: Strong growth in FY2026 Q1.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        # FY2025 Q4 has year == canonical_year - 1 → allowed by TTM allowance
        assert len(edp001_issues) == 0, \
            f"Expected 0 EDP-001 issues for year-1 period, got: {edp001_issues}"

    def test_guidance_not_forward_blocked(self, tmp_path):
        """Prior-year FY2025 Q4 is still allowed (year-1 TTM allowance).
        No longer flagged — year-1 references are legitimate in MD&A context.
        """
        content = """\
# Earnings Call Deep-Dive

FY2026 Q1 was a strong quarter. Revenue grew across segments.
The FY2026 Q1 performance exceeded expectations.

However, prior guidance for FY2025 Q4 was below actual results.

> One-line summary: Strong quarter.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        # FY2025 Q4: year == canonical_year - 1 → allowed by TTM allowance
        assert len(edp001_issues) == 0, \
            f"Expected 0 EDP-001 issues for year-1 period, got: {edp001_issues}"

    def test_two_year_old_wrong_quarter_fires_edp001(self, tmp_path):
        """EDP-001 MUST fire for year-2+ references with wrong quarter.
        A report about FY2026 Q2 referencing FY2024 Q1 data should be flagged.
        """
        content = """\
# Earnings Call Deep-Dive

## EPS & Revenue

Revenue grew strongly in FY2026 Q2, driven by Data Center.
The company reported FY2026 Q2 results above expectations.
Management highlighted FY2026 Q2 as a record quarter.

However, the FY2024 Q1 comparison is not relevant to current results.

> One-line summary: Strong growth in FY2026 Q2.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) >= 1, \
            f"Expected ≥1 EDP-001 issue for FY2024 Q1 (year-2+ wrong quarter), got 0"


# ── EDP-003: Allowed prior-year and guidance labels ──────────────────────

class TestEdp003AllowedLabels:
    """EDP-003: Prior-year and forward-looking labels must NOT be flagged."""

    def test_prior_year_allowed(self, tmp_path):
        """Prior-year FY2025 Q1 is allowed when canonical period is FY2026 Q1."""
        content = """\
# Earnings Call Deep-Dive

Revenue grew strongly in FY2026 Q1, driven by Data Center.
In FY2025 Q1, revenue was only $7.0B. The FY2026 Q1 growth reflects strong demand.

The FY2026 Q1 results exceeded the prior year period.

> One-line summary: Strong growth in FY2026 Q1.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp_issues) == 0, \
            f"Prior-year FY2025 Q1 should be allowed, got: {edp_issues}"

    def test_forward_looking_guidance_allowed(self, tmp_path):
        """Forward-looking FY2026 Q2 guidance is allowed when canonical is FY2026 Q1."""
        content = """\
# Earnings Call Deep-Dive

FY2026 Q1 was a strong quarter. Revenue grew across all segments.
The FY2026 Q1 performance exceeded expectations.

Management guided FY2026 Q2 revenue above consensus.

> One-line summary: Strong quarter with positive guidance.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp_issues) == 0, \
            f"Forward-looking FY2026 Q2 should be allowed, got: {edp_issues}"

    def test_future_fiscal_year_allowed(self, tmp_path):
        """Future fiscal year FY2027 labels are allowed (guidance/forward-looking)."""
        content = """\
# Earnings Call Deep-Dive

FY2026 Q1 was a strong quarter. Revenue grew across segments.
The FY2026 Q1 EPS came in above the high end of guidance.

Management provided FY2027 Q1 guidance above consensus expectations.

> One-line summary: Strong quarter with positive forward guidance.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp_issues) == 0, \
            f"Future FY2027 Q1 should be allowed, got: {edp_issues}"

    def test_multiple_periods_all_consistent(self, tmp_path):
        """Multiple references to FY2026 Q1 and FY2025 Q1 (prior year) and FY2026 Q2 (guidance) all pass."""
        content = """\
# Earnings Call Deep-Dive

FY2026 Q1 revenue exceeded expectations at $10.0B vs FY2025 Q1's $7.0B.
The FY2026 Q1 EPS of $1.23 compares to $0.90 in FY2025 Q1.
Looking ahead, FY2026 Q2 guidance calls for $11.0B in revenue.
We are raising our FY2026 Q1 estimates based on this outperformance.

> One-line summary: Strong FY2026 Q1 results.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp_issues) == 0, \
            f"Consistent periods (current + prior year + guidance) should all pass, got: {edp_issues}"


# ── Edge cases and false positive prevention ──────────────────────────────

class TestEdp001EdgeCases:
    """Edge cases: calendar dates, sparse labels, multi-year labels."""

    def test_no_false_positive_on_calendar_dates(self, tmp_path):
        """Plain calendar dates like 'Q1 2025' without FY prefix should NOT trigger false positives.

        When all labels are consistent (all FY2026 Q1), there should be no issues.
        """
        content = """\
# Earnings Call Deep-Dive

FY2026 Q1 results highlighted strong operating performance.
The quarter ending January 2026 showed revenue growth.
As of Q1 2026, the company reported $10.0B in revenue.

> One-line summary: Strong FY2026 Q1 results.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        # FY2026 Q1 appears 2+ times → canonical, Q1 2026 also matches → consistent
        assert len(edp_issues) == 0

    def test_sparse_labels_no_issues(self, tmp_path):
        """Content with fewer than 2 period labels should produce no EDP-001 issues."""
        content = """\
# Earnings Call Deep-Dive

The quarter was strong across all segments. Revenue grew 20% YoY.
Data Center remained the primary growth driver.

> One-line summary: Strong quarter.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp_issues) == 0

    def test_single_period_label_no_issues(self, tmp_path):
        """Content with exactly one distinct period label → no issues (insufficient to detect contradiction)."""
        content = """\
# Earnings Call Deep-Dive

FY2026 Q1 revenue grew 20% YoY driven by strong AI demand.

> One-line summary: Strong quarter.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp_issues) == 0

    def test_regex_no_q10_false_positive(self):
        """Q10 milestone text should NOT be parsed as Q1 + trailing 0 (regex lookahead fix)."""
        from backend.earnings_deep_dive.deep_dive_validator import _FISCAL_PERIOD_RE
        text = "2026Q10 milestone achieved"  # Should NOT match Q1
        matches = _FISCAL_PERIOD_RE.findall(text)
        assert len(matches) == 0, f"Q10 should not match as Q1, got: {matches}"

        text = "Year 2026 Q10 review"  # Should NOT match Q1
        matches = _FISCAL_PERIOD_RE.findall(text)
        assert len(matches) == 0, f"Q10 should not match as Q1, got: {matches}"

    def test_heading_line_range_helper(self):
        """_get_heading_line_ranges correctly identifies markdown heading positions."""
        from backend.earnings_deep_dive.deep_dive_validator import _get_heading_line_ranges
        content = """# Title
## Q4 2025 Recap
Body text with FY2026 Q1 period.
### Subsection
More body text.
"""
        ranges = _get_heading_line_ranges(content)
        assert len(ranges) == 3, f"Expected 3 heading ranges, got {len(ranges)}"
        # Verify the Q4 2025 Recap heading is detected
        heading_text = content[ranges[1][0]:ranges[1][1]]
        assert "Q4 2025" in heading_text, f"Heading text wrong: {heading_text}"


# ── Real-report regression tests ──────────────────────────────────────────────
# These simulate the false-positive cases identified in the t_7db887d6 audit.
# With widened EDP-003 + section-header exclusion, none should trigger EDP-001.

class TestEdp001RealReportRegression:
    """Real-report regression: previously-false-positive cases must now pass."""

    def test_aapl_20260612_prior_year_column_allowed(self, tmp_path):
        """AAPL 2026-06-12: Prior Year (FQ2 2025) in Cash Flow table must be allowed.
        Simulates: 4× stale FY2026 Q1 mentions + 1× Q2 2026 (correct current)
        + 1× Q2 2025 (prior year column). Widened EDP-003 allows all prior year
        periods (year-1, any quarter).
        """
        content = """\
# Earnings Call Deep-Dive

## Cash Flow

| Metric | Actual (FQ2 2026) | Prior Year (FQ2 2025) | YoY |
|--------|-------------------|----------------------|-----|
| Operating Cash Flow | $28.70B | — | — |

Revenue grew strongly in FY2026 Q1, driven by Data Center.
The FY2026 Q1 results exceeded expectations across all segments.
Management highlighted FY2026 Q1 as a record quarter for net income.
The FY2026 Q1 growth was driven by broad-based strength.

Q2 2026 continues the momentum with strong guidance.

> One-line summary: Strong quarter.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) == 0, \
            f"AAPL 2026-06-12 regression: expected 0 EDP-001, got: {edp001_issues}"

    def test_aapl_20260604_section_header_excluded(self, tmp_path):
        """AAPL 2026-06-04: Section header 'Q4 2025 Recap' must be excluded from
        canonical frequency. Body has only FY2026 Q1 labels → single period → no issues.
        """
        content = """\
# Q4 2025 Earnings Report

## EPS & Revenue

Revenue grew strongly in FY2026 Q1, driven by Data Center.
The company reported FY2026 Q1 results above expectations.

> One-line summary: Strong growth in FY2026 Q1.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) == 0, \
            f"AAPL 2026-06-04 regression: expected 0 EDP-001, got: {edp001_issues}"

    def test_googl_20260531_ttm_multi_year_allowed(self, tmp_path):
        """GOOGL 2026-05-31 alt: TTM columns FY2025 Q4 + FY2025 Q3 must be allowed
        when canonical is FY2026 Q2. Year-1 TTM quarters are legitimate table columns.
        """
        content = """\
# Earnings Call Deep-Dive

## EPS & Revenue

| Metric | Q2 2026 | Q1 2026 | Q4 2025 | Q3 2025 |
|--------|---------|---------|---------|---------|
| Revenue | $10.0B | $9.5B | $9.0B | $8.5B |

The FY2026 Q2 results exceeded expectations.
Revenue grew 15% YoY in FY2026 Q2.
Operating income improved in FY2026 Q2.

> One-line summary: Strong FY2026 Q2 results.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) == 0, \
            f"GOOGL 2026-05-31 regression: expected 0 EDP-001, got: {edp001_issues}"

    def test_prior_quarter_same_year_allowed(self, tmp_path):
        """Prior quarter of same fiscal year (e.g. FY2026 Q1 when canonical is FY2026 Q2)
        must be allowed — legitimate sequential comparison.
        """
        content = """\
# Earnings Call Deep-Dive

The FY2026 Q2 results continued the momentum from FY2026 Q1.
Revenue in FY2026 Q2 grew 10% sequentially from FY2026 Q1.
The FY2026 Q2 EPS of $1.35 compares to $1.23 in Q1.

> One-line summary: Strong Q2 results building on Q1 momentum.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) == 0, \
            f"Prior quarter allowed: expected 0 EDP-001, got: {edp001_issues}"

    def test_ttm_ending_period_not_flagged(self, tmp_path):
        """TTM (trailing twelve months) ending a prior period should not be flagged.
        'TTM Ending FY2025 Q4' when canonical is FY2026 Q2 → year-1 → allowed.
        """
        content = """\
# Earnings Call Deep-Dive

The FY2026 Q2 results reflect strong execution.
Revenue for FY2026 Q2 was $10.0B.
FY2026 Q2 operating income improved 20%.

The TTM ending FY2025 Q4 showed free cash flow of $15.0B.

> One-line summary: Strong FY2026 Q2 results.

## Verdict

> One-line summary: BUY.
"""
        md_path = _make_deep_dive(tmp_path, content)
        passed, issues = validate_deep_dive(md_path)
        edp001_issues = [i for i in issues if "EDP-001" in i]
        assert len(edp001_issues) == 0, \
            f"TTM ending allowed: expected 0 EDP-001, got: {edp001_issues}"

