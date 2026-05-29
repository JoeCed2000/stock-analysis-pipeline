"""Spec tests for RULE 33 — Company Overview Download Gate.

Covers:
  - 33a: Forbidden internal pipeline markers in text fields
  - 33b: CEO must be identified by name
  - 33c: Business segments must not be number words
"""

import pytest
from backend.earnings_deep_dive.pre_render_validator import (
    validate_pre_render,
    ValidationWarning,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_co(**overrides):
    """Build a minimal CompanyOverview-like object for testing."""
    class FakeCompanyProfile:
        def __init__(self):
            self.name = None
            self.ticker = "TEST"
            self.sector = None
            self.industry = None
            self.country = None
            self.website = None
            self.employees = None
            self.founded = None
            self.headquarters = None

    class FakeCompanyOverview:
        def __init__(self, **kwargs):
            self.company_profile = FakeCompanyProfile()
            self.business_description = kwargs.get("business_description", "")
            self.revenue_model = kwargs.get("revenue_model", "")
            self.business_segments = kwargs.get("business_segments", [])
            self.growth_drivers = kwargs.get("growth_drivers", [])
            self.moats = kwargs.get("moats", [])
            self.key_kpis = kwargs.get("key_kpis", [])
            self.business_risks = kwargs.get("business_risks", [])
            self.competitive_position = kwargs.get("competitive_position", "")
            self.strengths_vs_competitors = kwargs.get("strengths_vs_competitors", "")
            self.weaker_areas_vs_competitors = kwargs.get("weaker_areas_vs_competitors", "")
            self.client_types = kwargs.get("client_types", "")
            self.management_weaknesses = kwargs.get("management_weaknesses", "")
            self.investor_takeaway = kwargs.get("investor_takeaway", "")
            self.ceo_leadership_style = kwargs.get("ceo_leadership_style", "")
            self.long_term_vision = kwargs.get("long_term_vision", "")
            self.competitors = kwargs.get("competitors", [{"competitor_name": "Peer Inc"}])
            self.company_claims = kwargs.get("company_claims", [])
            for k, v in kwargs.items():
                if not hasattr(self, k):
                    setattr(self, k, v)

    return FakeCompanyOverview(**overrides)


def _run_validation(company_overview=None):
    """Run pre-render validation with given company_overview."""
    result = validate_pre_render(
        ticker="TEST",
        quarter="Q2 2026",
        metrics={},
        section_analysis={},
        company_overview=company_overview,
    )
    return result


# ── 33a: Forbidden markers ───────────────────────────────────────────

FORBIDDEN_MARKER_CASES = [
    "Revenue model could not be reliably synthesized because LLM synthesis was unavailable.",
    "Client types require transcript-level validation for accurate segmentation.",
    "This overview uses a fallback dataset due to provider limitations.",
    "Competitive position could not be reliably synthesized because LLM synthesis was unavailable; using fallback.",
]


@pytest.mark.parametrize("field_name", [
    "revenue_model",
    "competitive_position",
    "strengths_vs_competitors",
    "weaker_areas_vs_competitors",
    "ceo_leadership_style",
    "long_term_vision",
])
@pytest.mark.parametrize("bad_text", FORBIDDEN_MARKER_CASES)
def test_33a_forbidden_marker_in_field(bad_text, field_name):
    """Any forbidden marker in any text field → error."""
    co = _make_co(**{field_name: bad_text})
    result = _run_validation(company_overview=co)
    forbidden = [w for w in result.warnings
                 if w.check == "company_overview_forbidden_marker"]
    assert len(forbidden) >= 1, (
        f"Expected forbidden marker warning for '{bad_text[:60]}...' in {field_name}"
    )
    assert forbidden[0].severity == "error"


def test_33a_clean_text_passes():
    """Clean investor-facing text should pass."""
    co = _make_co(
        revenue_model="The company generates revenue from cloud services and advertising.",
        ceo_leadership_style="CEO Jane Smith leads with a focus on operational efficiency.",
    )
    result = _run_validation(company_overview=co)
    forbidden = [w for w in result.warnings
                 if w.check == "company_overview_forbidden_marker"]
    assert len(forbidden) == 0, f"Clean text flagged as forbidden: {forbidden}"


# ── 33b: CEO naming ──────────────────────────────────────────────────

def test_33b_ceo_not_named_flag():
    """Generic CEO reference without name → error."""
    co = _make_co(
        ceo_leadership_style="The CEO has demonstrated strong strategic vision."
    )
    result = _run_validation(company_overview=co)
    ceo_warnings = [w for w in result.warnings
                    if w.check == "company_overview_ceo_not_named"]
    assert len(ceo_warnings) >= 1, "Expected CEO-not-named warning"
    assert ceo_warnings[0].severity == "error"


def test_33b_ceo_named_passes():
    """CEO identified by name → passes."""
    co = _make_co(
        ceo_leadership_style="CEO Jensen Huang leads NVIDIA with a focus on accelerated computing."
    )
    result = _run_validation(company_overview=co)
    ceo_warnings = [w for w in result.warnings
                    if w.check == "company_overview_ceo_not_named"]
    assert len(ceo_warnings) == 0, f"Named CEO incorrectly flagged: {ceo_warnings}"


def test_33b_empty_ceo_passes():
    """Empty CEO field → passes (no false positive on missing data)."""
    co = _make_co(ceo_leadership_style="")
    result = _run_validation(company_overview=co)
    ceo_warnings = [w for w in result.warnings
                    if w.check == "company_overview_ceo_not_named"]
    assert len(ceo_warnings) == 0, f"Empty CEO incorrectly flagged: {ceo_warnings}"


# ── 33c: Segment number words ────────────────────────────────────────

@pytest.mark.parametrize("bad_segment", [
    "two",
    "three",
    "four",
    "One",      # case-insensitive
])
def test_33c_segment_is_number_word(bad_segment):
    """Business segment that is a number word → error."""
    co = _make_co(business_segments=[bad_segment, "Cloud"])
    result = _run_validation(company_overview=co)
    seg_warnings = [w for w in result.warnings
                    if w.check == "company_overview_segment_is_number"]
    assert len(seg_warnings) >= 1, f"Expected segment-number warning for '{bad_segment}'"
    assert seg_warnings[0].severity == "error"


def test_33c_named_segments_pass():
    """Actual segment names → passes."""
    co = _make_co(business_segments=[
        "Compute & Networking",
        "Graphics",
        "Google Cloud",
    ])
    result = _run_validation(company_overview=co)
    seg_warnings = [w for w in result.warnings
                    if w.check == "company_overview_segment_is_number"]
    assert len(seg_warnings) == 0, f"Valid segments incorrectly flagged: {seg_warnings}"


def test_33c_empty_segments_pass():
    """Empty segments list → passes (caught by RULE 31b instead)."""
    co = _make_co(business_segments=[])
    result = _run_validation(company_overview=co)
    seg_warnings = [w for w in result.warnings
                    if w.check == "company_overview_segment_is_number"]
    assert len(seg_warnings) == 0, f"Empty segments incorrectly flagged: {seg_warnings}"


# ── Integration: RULE 33 doesn't break existing RULE 31 ─────────────

def test_rule_33_does_not_break_rule_31():
    """RULE 31 (competitors, segments) still fires alongside RULE 33."""
    co = _make_co(
        competitors=[],           # RULE 31a
        business_segments=[],     # RULE 31b
        strengths_vs_competitors="",  # RULE 31c
        weaker_areas_vs_competitors="",
        ceo_leadership_style="The CEO runs the company.",  # RULE 33b
    )
    result = _run_validation(company_overview=co)
    checks = {w.check for w in result.warnings if w.severity == "error"}
    assert "company_overview_no_competitors" in checks, "RULE 31a should fire"
    assert "company_overview_no_segments" in checks, "RULE 31b should fire"
    assert "company_overview_no_strengths_weaknesses" in checks, "RULE 31c should fire"
    assert "company_overview_ceo_not_named" in checks, "RULE 33b should fire"
