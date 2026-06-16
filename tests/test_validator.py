"""
Tests for pre_render_validator — the validation step between deep-dive and PDF.

Tests cover all 4 checks + edge cases from acceptance criteria.
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import (
    validate_pre_render,
    annotate_sections_with_warnings,
    ValidationResult,
    ValidationWarning,
    _parse_money,
    FORBIDDEN_MARKERS,
)


# ── Test helpers ──────────────────────────────────────────────────────────

def _metrics(**kwargs):
    """Create a FinancialMetrics with specified fields."""
    from backend.earnings_deep_dive.schemas import FinancialMetrics
    defaults = {
        "eps_actual": 1.50,
        "eps_estimate": 1.45,
        "revenue_actual": 82_900_000_000,  # $82.9B
        "revenue_estimate": 82_500_000_000,
        "net_income": 22_000_000_000,
        "free_cash_flow": 15_000_000_000,
    }
    defaults.update(kwargs)
    return FinancialMetrics(**defaults)


# ── Helper detection ──────────────────────────────────────────────────────

def _has_warning(warnings, check: str, section: str = None) -> bool:
    """Check if any warning matches `check` type, optionally in `section`."""
    for w in warnings:
        if w.check == check:
            if section is None or w.section == section:
                return True
    return False


# ── 1. Quarter presence check ─────────────────────────────────────────────

class TestQuarterPresence:
    """AC6: quarter=None → catches 'Not available' in title."""

    def test_quarter_none_flagged(self):
        """Given quarter=None, validator flags quarter_missing.

        Contract update (RULE 4): quarter_missing is a non-blocking warning —
        the deep-dive can still render with a 'Not available' label, so
        validation passes but the warning must be present."""
        result = validate_pre_render(
            ticker="TEST",
            quarter=None,
            metrics=_metrics(),
            section_analysis={"Verdict": "Score: 8/10 — Strong buy."},
        )
        assert _has_warning(result.warnings, "quarter_missing")
        assert all(
            w.severity != "error" for w in result.warnings if w.check == "quarter_missing"
        ), "quarter_missing must stay a non-blocking warning"

    def test_quarter_empty_string_flagged(self):
        """Empty string treated same as None."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="",
            metrics=_metrics(),
            section_analysis={"Verdict": "Score: 8/10"},
        )
        assert not result.passed
        assert _has_warning(result.warnings, "quarter_missing")

    def test_quarter_valid_not_flagged(self):
        """Valid quarter should pass silently."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={"Verdict": "Score: 8/10 — Strong BUY."},
        )
        assert result.passed
        assert not _has_warning(result.warnings, "quarter_missing")


# ── 2. Forbidden markers check ────────────────────────────────────────────

class TestForbiddenMarkers:
    """AC2: No 'Not available' in any field."""

    def test_not_available_in_section_flagged(self):
        """Section text containing 'Not available' is flagged.

        Contract update (RULE 5): the check is named forbidden_marker_leak
        and is a non-blocking warning — §23 post-processing strips the
        marker before rendering."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": "Score: 8/10 — BUY.",
                "EPS & Revenue": "Revenue was $82.9B. Not available for EPS.",
            },
        )
        assert _has_warning(result.warnings, "forbidden_marker_leak", "EPS & Revenue")

    def test_data_not_available_flagged(self):
        """'DATA NOT AVAILABLE' (uppercase) is flagged as forbidden_marker_leak."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": "Score: 8/10",
                "Cash Flow": "DATA NOT AVAILABLE for this quarter.",
            },
        )
        assert _has_warning(result.warnings, "forbidden_marker_leak", "Cash Flow")

    def test_french_not_available_flagged(self):
        """'DONNÉE NON DISPONIBLE' (French) is flagged as forbidden_marker_leak."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": "Score: 8/10",
                "Operating Metrics": "DONNÉE NON DISPONIBLE",
            },
        )
        assert _has_warning(result.warnings, "forbidden_marker_leak", "Operating Metrics")

    def test_clean_text_passes(self):
        """Clean section text with no forbidden markers passes."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": "Score: 8/10 — Strong BUY.",
                "EPS & Revenue": "Revenue was $82.9B, EPS was $1.50.",
            },
        )
        assert result.passed


# ── 3. Number consistency check (±5%) ─────────────────────────────────────

class TestNumberConsistency:
    """AC2: Numbers match source data within ±5%."""

    def test_revenue_matches_within_5pct(self):
        """Revenue in text close to actual → no warning."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(revenue_actual=82_900_000_000),
            section_analysis={
                "Verdict": "Score: 8/10",
                "EPS & Revenue": "Revenue was $82.9B this quarter.",
            },
        )
        assert not _has_warning(result.warnings, "number_mismatch")

    def test_revenue_mismatch_flagged(self):
        """Revenue in text far from actual → flagged."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(revenue_actual=82_900_000_000),
            section_analysis={
                "Verdict": "Score: 8/10",
                "EPS & Revenue": "Revenue was $90.0B this quarter.",
            },
        )
        # $90B vs $82.9B = 8.6% off → flagged
        assert _has_warning(result.warnings, "number_mismatch")

    def test_eps_matches_within_5pct(self):
        """EPS in text close to actual → no warning."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(eps_actual=1.50, eps_estimate=1.45),
            section_analysis={
                "Verdict": "Score: 8/10",
                "EPS & Revenue": "EPS was $1.52 this quarter.",
            },
        )
        # $1.52 vs $1.50 = 1.3% → no mismatch (within 5%)
        assert not _has_warning(result.warnings, "number_mismatch")

    def test_eps_mismatch_flagged(self):
        """EPS in text far from both actual and estimate → flagged."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(eps_actual=1.50, eps_estimate=1.45),
            section_analysis={
                "Verdict": "Score: 8/10",
                "EPS & Revenue": "EPS was $2.10 this quarter.",
            },
        )
        # $2.10 vs $1.50 = 40% → flagged
        assert _has_warning(result.warnings, "number_mismatch")

    def test_eps_matches_estimate_not_actual(self):
        """EPS close to estimate only → not flagged (text may cite consensus)."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(eps_actual=1.50, eps_estimate=1.45),
            section_analysis={
                "Verdict": "Score: 8/10",
                "EPS & Revenue": "Consensus EPS was $1.47.",
            },
        )
        # $1.47 vs $1.45 estimate = 1.4% → within 5% of estimate
        assert not _has_warning(result.warnings, "number_mismatch")


# ── 4. Score-commentary contradiction ─────────────────────────────────────

class TestScoreCommentaryContradiction:
    """AC4: No contradiction between score and commentary."""

    def test_positive_score_no_contradiction(self):
        """Score 8/10 with no negative phrases → passes."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": "Score: 8/10 — Excellent execution, strong buy.",
            },
        )
        assert not _has_warning(result.warnings, "score_commentary_contradiction")

    def test_positive_score_negative_commentary_flagged(self):
        """Score 8/10 with multiple negative phrases → contradiction flagged."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": (
                    "Score: 8/10 — Strong results. However, the stock is "
                    "overvalued and we see significant headwinds. A sell-off "
                    "may be imminent with bearish sentiment."
                ),
            },
        )
        assert _has_warning(result.warnings, "score_commentary_contradiction")

    def test_one_negative_phrase_not_flagged(self):
        """Single negative phrase (≥2 required) → not flagged."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": "Score: 8/10 — Strong buy, though some headwinds exist.",
            },
        )
        assert not _has_warning(result.warnings, "score_commentary_contradiction")

    def test_low_score_no_contradiction_check(self):
        """Score <6 → no contradiction check (negative score matches negative text)."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={
                "Verdict": (
                    "Score: 3/10 — The stock is overvalued, sell immediately, "
                    "significant headwinds point to a crash."
                ),
            },
        )
        assert not _has_warning(result.warnings, "score_commentary_contradiction")


# ── 5. annotate_sections_with_warnings ────────────────────────────────────

class TestAnnotateSections:
    """AC3: Failed validations flag sections with ⚠️ marker."""

    def test_warnings_prepend_emoji(self):
        """Section with warnings gets ⚠️ prepended."""
        sections = {
            "Verdict": "Score: 8/10 — BUY.",
            "EPS & Revenue": "Not available this quarter.",
        }
        result = ValidationResult(
            passed=False,
            warnings=[
                ValidationWarning(
                    check="not_available",
                    section="EPS & Revenue",
                    detail="'Not available' found",
                ),
            ],
        )
        annotated = annotate_sections_with_warnings(sections, result)
        assert annotated["EPS & Revenue"].startswith("⚠️")
        assert "Not available" in annotated["EPS & Revenue"]
        # Unaffected section unchanged
        assert annotated["Verdict"] == "Score: 8/10 — BUY."

    def test_already_prefixed_not_doubled(self):
        """Section already starting with ⚠️ is not double-prefixed."""
        sections = {"Verdict": "⚠️ Score: 8/10 — BUY."}
        result = ValidationResult(
            passed=False,
            warnings=[
                ValidationWarning(
                    check="not_available",
                    section="Verdict",
                    detail="test",
                ),
            ],
        )
        annotated = annotate_sections_with_warnings(sections, result)
        assert annotated["Verdict"] == "⚠️ Score: 8/10 — BUY."

    def test_passed_validation_no_annotations(self):
        """Passed validation returns original dict unchanged."""
        sections = {"Verdict": "Score: 8/10 — BUY."}
        result = ValidationResult(passed=True, warnings=[])
        annotated = annotate_sections_with_warnings(sections, result)
        assert annotated == sections
        assert annotated["Verdict"] == "Score: 8/10 — BUY."

    def test_does_not_mutate_input(self):
        """annotate_sections_with_warnings is side-effect-free."""
        sections = {"Verdict": "Score: 8/10 — BUY."}
        original = dict(sections)
        result = ValidationResult(
            passed=False,
            warnings=[
                ValidationWarning(check="not_available", section="Verdict", detail="test"),
            ],
        )
        annotated = annotate_sections_with_warnings(sections, result)
        assert sections == original  # Input unchanged
        assert annotated is not sections  # New dict returned


# ── 6. Edge cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    """Non-blocking validation — always returns, never raises."""

    def test_none_section_analysis(self):
        """None section_analysis → no crash."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis=None,
        )
        assert result.passed  # No sections = no issues

    def test_empty_section_analysis(self):
        """Empty dict → passes."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis={},
        )
        assert result.passed

    def test_none_metrics(self):
        """None metrics → no crash (number check skipped)."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=None,
            section_analysis={
                "Verdict": "Score: 8/10 — BUY.",
                "EPS & Revenue": "Revenue was $82.9B.",
            },
        )
        # Should not crash and should still check other things
        assert isinstance(result, ValidationResult)

    def test_non_dict_section_analysis(self):
        """Non-dict section_analysis → treated as empty."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(),
            section_analysis="not a dict",
        )
        assert isinstance(result, ValidationResult)

    def test_all_checks_pass(self):
        """Clean data → passes all checks.

        revenue_estimate must sit a realistic distance from the actual:
        check 13e (eps_revenue_estimate_actual_proximity) legitimately flags
        estimates within 1% of the actual as same-source suspicion."""
        result = validate_pre_render(
            ticker="TEST",
            quarter="2026Q1",
            metrics=_metrics(
                revenue_actual=82_900_000_000,
                revenue_estimate=80_600_000_000,  # 2.8% surprise — independent consensus
                eps_actual=1.50,
            ),
            section_analysis={
                "Verdict": "Score: 8/10 — Strong execution. BUY.",
                "EPS & Revenue": "Revenue reached $82.9B, EPS was $1.50.",
            },
        )
        assert result.passed
        assert len(result.warnings) == 0


# ── 7. _parse_money unit tests ────────────────────────────────────────────

class TestParseMoney:
    def test_billions(self):
        assert _parse_money("$82.9B") == pytest.approx(82_900_000_000)

    def test_millions(self):
        assert _parse_money("$500M") == pytest.approx(500_000_000)

    def test_thousands(self):
        assert _parse_money("$250K") == pytest.approx(250_000)

    def test_plain_dollars(self):
        assert _parse_money("$1.50") == pytest.approx(1.50)

    def test_with_commas(self):
        assert _parse_money("$1,234,567") == pytest.approx(1_234_567)

    def test_non_dollar_string(self):
        assert _parse_money("82.9B") is None

    def test_empty(self):
        assert _parse_money("") is None

    def test_invalid(self):
        assert _parse_money("$abc") is None
