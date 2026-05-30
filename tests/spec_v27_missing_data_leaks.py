"""§22+§23 Missing-data language + internal leaks — spec tests.

Tests RULE 5 (FORBIDDEN_MARKERS now blocking) and RULE 30 (null artifacts, Reason: leaks).
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


class TestRule5ForbiddenMarkersBlocking:
    """RULE 5: FORBIDDEN_MARKERS now severity=error (was warning)."""

    def test_not_available_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Financials": "Revenue is Not available for this period."},
        )
        assert result.passed is False
        assert any("forbidden_marker_leak" == e.check for e in result.errors)

    def test_section_unavailable_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Segments": "Section unavailable for this quarter."},
        )
        assert result.passed is False
        assert any("forbidden_marker_leak" == e.check for e in result.errors)

    def test_critical_override_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"EPS & Revenue": "CRITICAL OVERRIDE: EPS is $2.94."},
        )
        assert result.passed is False

    def test_model_example_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Highlights": "Model example company figures are never reused."},
        )
        assert result.passed is False

    def test_nami_san_allowed(self):
        """'For Nami-san:' is legitimate client-facing content, not a forbidden marker."""
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Notes": "For Nami-san: this is a test."},
        )
        assert not any("forbidden_marker_leak" == e.check for e in result.errors)

    def test_clean_text_passes(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Financials": "Revenue is Unavailable from reviewed sources."},
        )
        assert not any("forbidden_marker_leak" == e.check for e in result.errors)


class TestRule30MissingDataAndLeaks:
    """RULE 30: No Reason: leaks, no null/None/NaN/undefined/debug."""

    def test_30a_reason_leak_blocked(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Financials": "Data missing. Reason: primary returned no content."},
        )
        assert result.passed is False
        assert any("missing_data_reason_leak" == e.check for e in result.errors)

    def test_30a_no_reason_passes(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Financials": "Unavailable from reviewed sources."},
        )
        assert not any("missing_data_reason_leak" == e.check for e in result.errors)

    def test_30b_null_warned(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Valuation": "PE ratio is null for this quarter."},
        )
        assert result.passed is True  # Phase 1: warning, not error
        assert any("null_artifact" in w.check for w in result.warnings)

    def test_30b_none_warned(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Valuation": "Dividend yield is None."},
        )
        assert result.passed is True
        assert any("null_artifact" in w.check for w in result.warnings)

    def test_30b_nan_warned(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Financials": "Growth rate returned NaN."},
        )
        assert result.passed is True
        assert any("null_artifact" in w.check for w in result.warnings)

    def test_30b_undefined_warned(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Financials": "Value is undefined."},
        )
        assert result.passed is True
        assert any("null_artifact" in w.check for w in result.warnings)

    def test_30b_debug_warned(self):
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={"Notes": "Debug: yfinance returned empty."},
        )
        assert result.passed is True
        assert any("null_artifact" in w.check for w in result.warnings)

    def test_30b_word_boundary_respected(self):
        """Words containing these substrings should NOT be blocked."""
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": (
                    "The company announced a dividend. There is none planned for Q3. "
                    "Revenue growth was notable. The debugger tool is not used. "
                    "The announcer stated that margins are healthy."
                ),
            },
        )
        # "none" as a word (not "None"), "notable" contains "null"? No.
        # These should all pass — word boundaries prevent false positives
        assert not any("null_artifact" in e.check for e in result.errors)

    def test_safe_words_not_blocked(self):
        """'nullify', 'debugging', 'announcement' should NOT be blocked."""
        result = validate_pre_render(
            ticker="NVDA", quarter="Q1 FY2026", metrics=None,
            section_analysis={
                "Financials": "The debugging process is complete. Announcing the results.",
            },
        )
        assert not any("null_artifact" in e.check for e in result.errors)
