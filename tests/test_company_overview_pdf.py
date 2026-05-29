"""Tests for render_company_overview() in pdf_renderer.py.

Covers: None skip, all 6 subsections, EN/JP bilingual, source IDs.
"""
from __future__ import annotations

import pytest  # noqa: F401 — used by pytest test discovery

from backend.earnings_deep_dive.pdf_renderer import (
    render_company_overview,
    resolve_pdf_fonts,
    _styles,
)
from backend.earnings_deep_dive.report_model import (
    CompanyOverview,
    CompanyProfile,
    CompetitorRef,
    EarningsDeepDiveReport,
    KeyFinancials,
    RecentDevelopment,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _sample_co_en() -> CompanyOverview:
    """Full English CompanyOverview with all 6 subsections populated."""
    return CompanyOverview(
        company_profile=CompanyProfile(
            name="NVIDIA Corporation",
            ticker="NVDA",
            sector="Technology",
            industry="Semiconductors",
            country="United States",
            website="https://www.nvidia.com",
            employees=32000,
            founded=1993,
            headquarters="Santa Clara, CA, United States",
        ),
        business_description=(
            "NVIDIA designs and manufactures graphics processing units (GPUs) "
            "for gaming, data centers, and AI workloads."
        ),
        key_financials=KeyFinancials(
            market_cap=3_200_000_000_000,
            market_cap_display="$3.20T",
            revenue=130_000_000_000,
            revenue_display="$130.0B",
            pe_ratio=45.5,
            pe_forward=32.0,
            dividend_yield=0.0001,
            beta=1.75,
            window_52w_high=199.62,
            window_52w_low=75.15,
        ),
        recent_developments=[
            RecentDevelopment(
                title="Blackwell GPU Ramp",
                summary="Next-gen AI GPU entering volume production in H2 2026.",
                date="2026-04-15",
                sentiment="positive",
            ),
            RecentDevelopment(
                title="China Export Restrictions",
                summary="New restrictions limit GPU exports to China.",
                date="2026-03-20",
                sentiment="negative",
            ),
        ],
        competitive_position=(
            "NVIDIA holds a dominant ~85% share in AI training GPUs. "
            "CUDA ecosystem lock-in provides durable moat. "
            "Main risk: custom ASIC competition from hyperscalers."
        ),
        competitors=[
            CompetitorRef(
                competitor_name="AMD",
                text_en="AMD MI300 series gaining traction in inference.",
                text_jp="AMD MI300シリーズが推論で存在感を増している。",
                source_id="S1",
                competitive_advantage="CUDA ecosystem",
            ),
            CompetitorRef(
                competitor_name="Intel",
                text_en="Gaudi 3 AI accelerator — still behind in software.",
                text_jp="Gaudi 3 AIアクセラレーター — ソフトウェア面で遅れ。",
                source_id="S2",
                competitive_advantage="Performance lead",
            ),
        ],
    )


def _sample_co_jp() -> CompanyOverview:
    """Full Japanese CompanyOverview."""
    return CompanyOverview(
        company_profile=CompanyProfile(
            name="NVIDIA Corporation",
            ticker="NVDA",
            sector="テクノロジー",
            industry="半導体",
            country="アメリカ合衆国",
            website="https://www.nvidia.com",
            employees=32000,
            founded=1993,
            headquarters="カリフォルニア州サンタクララ",
        ),
        business_description=(
            "NVIDIAはゲーミング、データセンター、AIワークロード向けの"
            "グラフィックスプロセッシングユニット（GPU）を設計・製造しています。"
        ),
        key_financials=KeyFinancials(
            market_cap=3_200_000_000_000,
            market_cap_display="$3.20T",
            revenue=130_000_000_000,
            revenue_display="$130.0B",
            pe_ratio=45.5,
            pe_forward=32.0,
            dividend_yield=0.0001,
            beta=1.75,
            window_52w_high=199.62,
            window_52w_low=75.15,
        ),
        recent_developments=[
            RecentDevelopment(
                title="Blackwell GPU量産開始",
                summary="次世代AI GPUが2026年下半期に量産開始。",
                date="2026-04-15",
                sentiment="positive",
            ),
        ],
        competitive_position=(
            "NVIDIAはAIトレーニングGPUで約85%のシェアを占めている。"
            "CUDAエコシステムのロックインが持続的な競争優位性を提供。"
        ),
        competitors=[
            CompetitorRef(
                competitor_name="AMD",
                text_en="AMD gaining traction.",
                text_jp="AMDが存在感を増している。",
                source_id="S1",
                competitive_advantage="CUDAエコシステム",
            ),
        ],
    )


def _minimal_report(language: str = "en", co: CompanyOverview | None = None) -> EarningsDeepDiveReport:
    """Minimal EarningsDeepDiveReport for render_company_overview testing."""
    return EarningsDeepDiveReport(
        ticker="NVDA",
        company="NVIDIA Corporation",
        quarter="FY2026 Q1",
        language=language,
        generated_at="2026-05-21T00:00:00Z",
        title="NVIDIA (NVDA) - Earnings Deep-Dive (FY2026 Q1)",
        sections=[],
        company_overview=co,
    )


# ── Tests ─────────────────────────────────────────────────────────────────

class TestRenderCompanyOverview:
    """render_company_overview() unit tests."""

    def test_returns_empty_list_when_overview_is_none(self):
        """When report.company_overview is None, returns []."""
        report = _minimal_report(co=None)
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        assert result == []

    def test_renders_company_overview_section_header_en(self):
        """Section header uses translated label."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        assert len(result) > 0
        # First flowable should be the section header
        header = result[0]
        assert "Company Overview" in str(header.__dict__)

    def test_renders_company_overview_section_header_jp(self):
        """Section header uses Japanese label."""
        report = _minimal_report(language="jp", co=_sample_co_jp())
        fonts = resolve_pdf_fonts("jp")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        assert len(result) > 0
        header = result[0]
        assert "会社概要" in str(header.__dict__)

    def test_business_description_rendered(self):
        """Business description text block is included."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        # Search for business description content in flowables
        all_text = " ".join(str(f.__dict__) for f in result)
        assert "designs and manufactures" in all_text
        assert "Business Description" in all_text

    def test_key_financials_rendered(self):
        """Key financials bullet list with all metrics."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)
        assert "Market Cap" in all_text
        assert "$3.20T" in all_text
        assert "P/E Ratio" in all_text
        assert "45.5x" in all_text

    def test_competitive_position_rendered(self):
        """Competitive position analysis text block."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)
        assert "Competitive Position" in all_text
        assert "85%" in all_text

    def test_recent_developments_rendered_with_sentiment(self):
        """Recent developments bullet list includes sentiment tags."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)
        assert "Recent Developments" in all_text
        assert "Blackwell" in all_text
        assert "positive" in all_text
        assert "negative" in all_text

    def test_competitors_table_rendered_en(self):
        """Competitors table uses text_en for English reports."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)
        assert "Competitors" in all_text
        assert "AMD" in all_text
        assert "gaining traction" in all_text
        assert "S1" in all_text
        assert "S2" in all_text

    def test_competitors_table_rendered_jp(self):
        """Competitors table uses text_jp for Japanese reports."""
        report = _minimal_report(language="jp", co=_sample_co_jp())
        fonts = resolve_pdf_fonts("jp")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)
        assert "競合他社" in all_text
        assert "AMD" in all_text
        assert "存在感を増している" in all_text
        assert "S1" in all_text

    def test_profile_table_has_all_fields(self):
        """Company profile includes ticker, sector, industry, country, HQ, employees, founded, website."""
        report = _minimal_report(co=_sample_co_en())
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)
        for expected in ["Ticker", "NVDA", "Technology", "Semiconductors",
                         "United States", "Santa Clara", "32,000", "1993",
                         "nvidia.com"]:
            assert expected in all_text, f"Missing: {expected}"

    def test_competitor_advantage_keeps_long_sentence_context(self):
        """Long advantage text should not be clipped to fragments like 'rather than p'."""
        co = _sample_co_en()
        co.competitors[0].competitive_advantage = (
            "NVIDIA offers a more integrated AI compute and networking platform rather than "
            "primarily custom or component-level solutions."
        )
        report = _minimal_report(co=co)
        fonts = resolve_pdf_fonts("en")
        styles = _styles(fonts)
        result = render_company_overview(report, styles, fonts)
        all_text = " ".join(str(f.__dict__) for f in result)

        assert "rather than primarily custom or component-level solutions" in all_text

