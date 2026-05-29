"""§10 Highlights/Lowlights Quality Gate — tests for RULE 12.

Covers corrections.txt §10 requirements:
- 12a: no empty bullets
- 12b: no duplicate highlights
- 12c: "no major red flags" paradox detection
- 12d: unsubstantiated claims detection
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import validate_pre_render


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_sections(highlights_text: str) -> dict:
    """Build minimal section_analysis dict with just Highlights."""
    return {"Highlights": highlights_text}


def _errors_for(result, check_prefix: str) -> list:
    """Extract errors matching a given check prefix."""
    return [e for e in result.errors if e.check == check_prefix]


# ═══════════════════════════════════════════════════════════════════════════
# 12a — Empty bullets
# ═══════════════════════════════════════════════════════════════════════════


class TestEmptyBullets:
    """RULE 12a: no empty or near-empty bullets."""

    def test_empty_bullet_line_blocked(self):
        sections = _make_sections("🌟 Highlights\n\n• \n\n⚠️ Lowlights\n\nGrowth was strong.")
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_empty_bullets")
        assert len(errs) == 1

    def test_bullet_with_one_char_blocked(self):
        sections = _make_sections("🌟 Highlights\n\n• x\n\n⚠️ Lowlights\n\nRevenue beat.")
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_empty_bullets")
        assert len(errs) == 1

    def test_substantive_bullets_pass(self):
        sections = _make_sections(
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1B, beating consensus by 3.2%. "
            "Management cited AI chip demand as the primary driver.\n\n"
            "⚠️ Lowlights\n\n"
            "• Gross margin contracted 120bps to 72.4% due to ramp costs "
            "for next-gen Blackwell platform."
        )
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_empty_bullets")
        assert len(errs) == 0

    def test_no_highlights_section_skips(self):
        result = validate_pre_render("NVDA", "FY2026 Q1", None, {})
        errs = _errors_for(result, "highlights_empty_bullets")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 12b — Duplicate highlights
# ═══════════════════════════════════════════════════════════════════════════


class TestDuplicateHighlights:
    """RULE 12b: no duplicate or near-duplicate highlights."""

    def test_exact_duplicate_blocked(self):
        text = (
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1 billion, beating consensus "
            "estimates by a wide margin driven by data center demand.\n\n"
            "• Revenue grew 18% YoY to $22.1 billion, beating consensus "
            "estimates by a wide margin driven by data center demand.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_duplicates")
        assert len(errs) >= 1

    def test_near_duplicate_blocked(self):
        text = (
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1 billion, beating consensus "
            "estimates by a wide margin driven by data center demand.\n\n"
            "• Revenue increased 18% YoY to $22.1 billion, beating analyst "
            "estimates by a wide margin thanks to data center growth.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_duplicates")
        # High overlap expected
        assert len(errs) >= 1

    def test_distinct_highlights_pass(self):
        text = (
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1 billion, beating consensus "
            "by a wide margin driven by data center demand.\n\n"
            "• Operating margin expanded 220bps to 64.8%, showing strong "
            "operating leverage as revenue growth outpaced OpEx.\n\n"
            "• Free cash flow reached $14.9 billion, up 45% YoY, providing "
            "ample capacity for buybacks and strategic investments.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_duplicates")
        assert len(errs) == 0

    def test_short_lines_skipped(self):
        """Lines under 30 chars normalized should not trigger false duplicates."""
        text = "🌟 Highlights\n\n• Beat.\n\n• Miss.\n\n"
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_duplicates")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 12c — "No major red flags" paradox
# ═══════════════════════════════════════════════════════════════════════════


class TestRedFlagsParadox:
    """RULE 12c: "no major red flags" when risks/concerns are listed."""

    def test_paradox_blocked(self):
        text = (
            "🌟 Highlights\n\n• Strong quarter overall.\n\n"
            "⚠️ Lowlights\n\n• Gross margin under pressure.\n\n"
            "• Geopolitical risk in Taiwan.\n\n"
            "Overall assessment: No major red flags for this quarter."
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_red_flags_paradox")
        assert len(errs) == 1

    def test_no_red_flags_without_risks_passes(self):
        text = (
            "🌟 Highlights\n\n• Revenue beat by 18%.\n\n"
            "• Strong guidance.\n\n"
            "No major red flags this quarter."
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_red_flags_paradox")
        assert len(errs) == 0

    def test_risks_without_red_flags_claim_passes(self):
        """Listing risks is fine as long as you don't claim 'no red flags'."""
        text = (
            "🌟 Highlights\n\n• Strong quarter.\n\n"
            "⚠️ Lowlights\n\n• Margin pressure.\n\n"
            "• Supply chain risk.\n\n"
            "• Competitive threat from AMD.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_red_flags_paradox")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 12d — Unsubstantiated claims
# ═══════════════════════════════════════════════════════════════════════════


class TestUnsubstantiatedClaims:
    """RULE 12d: highlights must have numbers or source references."""

    def test_unsubstantiated_blocked(self):
        text = (
            "🌟 Highlights\n\n"
            "• The company had a great quarter with strong performance.\n\n"
            "• Management is optimistic about the future.\n\n"
            "• Competitive position remains solid.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_unsubstantiated")
        assert len(errs) == 1

    def test_substantiated_with_numbers_passes(self):
        text = (
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1B.\n\n"
            "• Operating margin reached 64.8%.\n\n"
            "• FCF of $14.9B, up 45%.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_unsubstantiated")
        assert len(errs) == 0

    def test_substantiated_with_source_passes(self):
        text = (
            "🌟 Highlights\n\n"
            "• According to the CEO in the earnings call, demand visibility "
            "has improved significantly across all segments.\n\n"
            "• The press release highlighted a major new customer win.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_unsubstantiated")
        assert len(errs) == 0

    def test_only_one_unsubstantiated_passes(self):
        """One unsubstantiated claim is a warning, not a blocker. Gate fires at 2+."""
        text = (
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1B.\n\n"
            "• The company had a great quarter.\n\n"  # unsubstantiated, but only 1
            "• Operating margin reached 64.8%.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        errs = _errors_for(result, "highlights_unsubstantiated")
        assert len(errs) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Integration: RULE 12 with other rules
# ═══════════════════════════════════════════════════════════════════════════


class TestRule12Integration:
    """RULE 12 doesn't interfere with existing rules."""

    def test_clean_highlights_all_rules_pass(self):
        text = (
            "🌟 Highlights\n\n"
            "• Revenue grew 18% YoY to $22.1B, beating consensus by 3.2%. "
            "Data center revenue accounted for 87% of total, up from 80% a year ago. "
            "This is structural, not cyclical — AI deployment is still in early innings.\n\n"
            "• Operating margin expanded 220bps to 64.8%, demonstrating strong "
            "operating leverage. Management guided for margins to remain above 60% "
            "through FY2027.\n\n"
            "⚠️ Lowlights\n\n"
            "• Gross margin contracted 120bps sequentially to 72.4% as Blackwell "
            "ramp costs weighed. Management expects this to normalize by Q3.\n\n"
            "• China revenue exposure remains a regulatory overhang — 17% of "
            "total revenue subject to export controls.\n\n"
        )
        sections = _make_sections(text)
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        hl_errors = [e for e in result.errors if e.check.startswith("highlights_")]
        assert len(hl_errors) == 0, \
            f"Clean highlights should pass all rules, got: {[(e.check, e.detail[:80]) for e in hl_errors]}"

    def test_existing_rules_still_work(self):
        """RULE 3 (cross-section contradiction) still works alongside RULE 12."""
        sections = {
            "EPS & Revenue": "EPS beat consensus by 5%.",
            "Highlights": "🌟 Highlights\n\n• Revenue grew 18% YoY to $22.1B.\n\n",
            "Verdict": "EPS missed consensus by 3%. SELL.",
        }
        result = validate_pre_render("NVDA", "FY2026 Q1", None, sections)
        contradict_errors = _errors_for(result, "eps_direction_contradiction")
        assert len(contradict_errors) >= 1, "RULE 3 should still fire"
