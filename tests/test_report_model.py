"""
Tests for report_model.py — CompanyOverview, CompetitorRef, CompanyClaim,
and their integration into EarningsDeepDiveReport.

⚠️ LANGUAGE SEPARATION: CompanyClaim and CompetitorRef store bilingual text
in SEPARATE fields (text_en + text_jp). Never mix languages.
CompanyOverview is per-language (EN or JP from cache).
"""

import pytest
from pydantic import ValidationError

from backend.earnings_deep_dive.report_model import (
    CompanyProfile,
    KeyFinancials,
    RecentDevelopment,
    CompanyOverview,
    CompetitorRef,
    CompanyClaim,
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    SourceRef,
)


# ── COMPANY PROFILE ──────────────────────────────────────────────────────

class TestCompanyProfile:
    """Sub-model for company_profile in CompanyOverview."""

    def test_valid_profile(self):
        p = CompanyProfile(
            name="Apple Inc.",
            ticker="AAPL",
            sector="Technology",
            industry="Consumer Electronics",
            country="United States",
            website="https://www.apple.com",
            employees=164000,
            founded=1976,
            headquarters="Cupertino, CA",
        )
        assert p.name == "Apple Inc."
        assert p.employees == 164000

    def test_minimal_profile(self):
        """Only name and ticker are required; rest default to None."""
        p = CompanyProfile(name="TestCo", ticker="TST")
        assert p.name == "TestCo"
        assert p.ticker == "TST"
        assert p.sector is None
        assert p.employees is None

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CompanyProfile(name="NoTicker")
        with pytest.raises(ValidationError):
            CompanyProfile(ticker="NOTICK")


# ── KEY FINANCIALS ───────────────────────────────────────────────────────

class TestKeyFinancials:
    """Sub-model for key_financials in CompanyOverview."""

    def test_valid_financials(self):
        kf = KeyFinancials(
            market_cap=3000000000000,
            market_cap_display="$3.00T",
            revenue=383285000000,
            revenue_display="$383.3B",
            pe_ratio=30.5,
            pe_forward=28.0,
        )
        assert kf.market_cap == 3000000000000
        assert kf.pe_ratio == 30.5

    def test_all_optional(self):
        kf = KeyFinancials()
        assert kf.market_cap is None
        assert kf.pe_ratio is None
        assert kf.beta is None


# ── RECENT DEVELOPMENT ───────────────────────────────────────────────────

class TestRecentDevelopment:
    """Sub-model for recent_developments items."""

    def test_valid_development(self):
        rd = RecentDevelopment(
            title="Apple launches new iPhone",
            summary="Apple launched iPhone 18 with AI features.",
            date="2026-05-15",
            sentiment="positive",
        )
        assert rd.title == "Apple launches new iPhone"
        assert rd.sentiment == "positive"

    def test_minimal_development(self):
        rd = RecentDevelopment(title="News", summary="Summary")
        assert rd.date is None
        assert rd.sentiment is None

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            RecentDevelopment(summary="Missing title")


# ── COMPANY OVERVIEW ─────────────────────────────────────────────────────

class TestCompanyOverview:
    """Per-language CompanyOverview — mirrors company_overview.py output."""

    def test_valid_overview_en(self):
        co = CompanyOverview(
            company_profile=CompanyProfile(name="Apple Inc.", ticker="AAPL"),
            business_description="Apple designs and manufactures consumer electronics.",
            key_financials=KeyFinancials(market_cap=3000000000000),
            recent_developments=[
                RecentDevelopment(title="Launch", summary="iPhone 18."),
            ],
            competitive_position="Dominant in premium smartphones.",
        )
        assert co.company_profile.name == "Apple Inc."
        assert len(co.recent_developments) == 1
        assert co.competitive_position == "Dominant in premium smartphones."

    def test_default_recent_developments(self):
        co = CompanyOverview(
            company_profile=CompanyProfile(name="TestCo", ticker="TST"),
        )
        assert co.recent_developments == []
        assert co.business_description is None
        assert co.competitive_position is None

    def test_overview_model_dump(self):
        """Ensure model_dump() is clean (no PrivateAttr leakage)."""
        co = CompanyOverview(
            company_profile=CompanyProfile(name="Apple", ticker="AAPL"),
            business_description="Designs smartphones.",
            key_financials=KeyFinancials(),
            competitive_position="Market leader.",
        )
        dumped = co.model_dump()
        assert "company_profile" in dumped
        assert dumped["company_profile"]["name"] == "Apple"
        assert "business_description" in dumped
        assert "competitive_position" in dumped


# ── COMPETITOR REF ───────────────────────────────────────────────────────

class TestCompetitorRef:
    """Bilingual competitor reference — text_en + text_jp, must have source."""

    def test_valid_competitor_en(self):
        cr = CompetitorRef(
            competitor_name="Samsung Electronics",
            text_en="Samsung competes in the premium smartphone segment.",
            source_id="S1",
        )
        assert cr.competitor_name == "Samsung Electronics"
        assert cr.text_en == "Samsung competes in the premium smartphone segment."
        assert cr.text_jp == ""  # default empty
        assert cr.source_id == "S1"

    def test_bilingual_competitor(self):
        cr = CompetitorRef(
            competitor_name="Samsung Electronics",
            text_en="Samsung competes in the premium smartphone segment.",
            text_jp="Samsungはプレミアムスマートフォン市場で競合しています。",
            source_id="S1",
            competitive_advantage="Vertical integration (chips + displays).",
        )
        assert cr.text_en != ""
        assert cr.text_jp != ""
        assert cr.competitive_advantage == "Vertical integration (chips + displays)."

    def test_source_id_required(self):
        """source_id is mandatory — every competitor must be source-backed."""
        with pytest.raises(ValidationError):
            CompetitorRef(
                competitor_name="Samsung",
                text_en="Competes.",
            )

    def test_text_jp_defaults_empty(self):
        cr = CompetitorRef(
            competitor_name="Google",
            text_en="Google competes in AI.",
            source_id="S2",
        )
        assert cr.text_jp == ""


# ── COMPANY CLAIM ────────────────────────────────────────────────────────

class TestCompanyClaim:
    """Bilingual analytical claim — text_en + text_jp, must have source_id."""

    def test_valid_claim_en(self):
        cc = CompanyClaim(
            claim_id="CO-001",
            text_en="Apple holds 55% market share in US smartphones.",
            source_id="S1",
            section="competitive_position",
            confidence="high",
        )
        assert cc.claim_id == "CO-001"
        assert cc.text_en == "Apple holds 55% market share in US smartphones."
        assert cc.text_jp == ""
        assert cc.source_id == "S1"
        assert cc.confidence == "high"

    def test_bilingual_claim(self):
        cc = CompanyClaim(
            claim_id="CO-002",
            text_en="Apple's services revenue grew 14% YoY.",
            text_jp="Appleのサービス収益は前年比14%成長しました。",
            source_id="S3",
            section="key_financials",
        )
        assert cc.text_en != ""
        assert cc.text_jp != ""

    def test_source_id_required(self):
        """source_id is mandatory — every claim must be traceable."""
        with pytest.raises(ValidationError):
            CompanyClaim(
                claim_id="CO-003",
                text_en="Claim without source.",
            )

    def test_confidence_default_medium(self):
        cc = CompanyClaim(
            claim_id="CO-004",
            text_en="Moderate confidence claim.",
            source_id="S4",
        )
        assert cc.confidence == "medium"

    def test_missing_claim_id(self):
        with pytest.raises(ValidationError):
            CompanyClaim(
                text_en="Missing claim_id.",
                source_id="S1",
            )


# ── INTEGRATION: EarningDeepDiveReport ─────────────────────────────────

class TestEarningsDeepDiveReportWithOverview:
    """CompanyOverview is an optional field on EarningsDeepDiveReport."""

    def test_report_without_overview(self):
        """Report works fine without company_overview (backward compatible)."""
        report = EarningsDeepDiveReport(
            ticker="AAPL",
            company="Apple Inc.",
            quarter="2026Q1",
            language="en",
            generated_at="2026-05-20T00:00:00Z",
            title="Earnings Deep Dive",
            sections=[],
        )
        assert report.ticker == "AAPL"
        assert report.company_overview is None

    def test_report_with_overview(self):
        overview = CompanyOverview(
            company_profile=CompanyProfile(name="Apple Inc.", ticker="AAPL"),
            business_description="Apple designs consumer electronics.",
            key_financials=KeyFinancials(market_cap=3000000000000),
            competitive_position="Market leader.",
        )
        report = EarningsDeepDiveReport(
            ticker="AAPL",
            company="Apple Inc.",
            quarter="2026Q1",
            language="en",
            generated_at="2026-05-20T00:00:00Z",
            title="Earnings Deep Dive",
            sections=[],
            company_overview=overview,
        )
        assert report.company_overview is not None
        assert report.company_overview.company_profile.name == "Apple Inc."
        assert report.company_overview.business_description == "Apple designs consumer electronics."

    def test_report_with_competitors_and_claims(self):
        """Full integration: report + overview + competitors + claims."""
        overview = CompanyOverview(
            company_profile=CompanyProfile(name="NVIDIA", ticker="NVDA"),
            business_description="NVIDIA designs GPUs for AI and gaming.",
            key_financials=KeyFinancials(market_cap=3000000000000),
            recent_developments=[
                RecentDevelopment(
                    title="Blackwell launch", summary="Next-gen GPU.",
                    sentiment="positive",
                ),
            ],
            competitive_position="Dominant in AI accelerators.",
            competitors=[
                CompetitorRef(
                    competitor_name="AMD",
                    text_en="AMD competes with MI300X series.",
                    text_jp="AMDはMI300Xシリーズで競合しています。",
                    source_id="S1",
                ),
            ],
            company_claims=[
                CompanyClaim(
                    claim_id="CO-001",
                    text_en="NVIDIA holds 80%+ share in AI training GPUs.",
                    text_jp="NVIDIAはAI学習用GPUで80%以上のシェアを持っています。",
                    source_id="S2",
                    section="competitive_position",
                    confidence="high",
                ),
            ],
        )

        report = EarningsDeepDiveReport(
            ticker="NVDA",
            company="NVIDIA",
            quarter="2026Q1",
            language="jp",
            generated_at="2026-05-20T00:00:00Z",
            title="Earnings Deep Dive",
            sections=[],
            company_overview=overview,
        )

        assert len(report.company_overview.competitors) == 1
        assert len(report.company_overview.company_claims) == 1
        assert report.company_overview.competitors[0].text_jp != ""

    def test_report_model_dump_with_overview(self):
        """model_dump() includes company_overview when present."""
        overview = CompanyOverview(
            company_profile=CompanyProfile(name="Meta", ticker="META"),
            business_description="Social media and advertising.",
            key_financials=KeyFinancials(),
        )
        report = EarningsDeepDiveReport(
            ticker="META",
            company="Meta Platforms",
            quarter="2026Q1",
            language="en",
            generated_at="2026-05-20T00:00:00Z",
            title="Report",
            sections=[],
            company_overview=overview,
        )
        dumped = report.model_dump()
        assert dumped["company_overview"] is not None
        assert dumped["company_overview"]["company_profile"]["ticker"] == "META"
