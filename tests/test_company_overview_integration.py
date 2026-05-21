"""
Integration tests for company_overview wired into pipeline report generation.

Tests:
  1. company_overview included in AnalysisResult when available
  2. company_overview section appears in generated report markdown
  3. Graceful None handling -- pipeline succeeds without overview
"""
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


# ── Mock company overview data ───────────────────────────────────────────

MOCK_OVERVIEW_EN = {
    "company_profile": {
        "text_en": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide. Founded in 1976 and headquartered in Cupertino, California, Apple is the world's largest technology company by revenue.",
        "sources": ["Yahoo Finance", "Tavily"],
    },
    "business_description": {
        "text_en": "Apple operates through five segments: iPhone (~52% of revenue), Services (~22%), Mac (~10%), Wearables/Home/Accessories (~10%), and iPad (~6%). The company generates over $380B in annual revenue.",
        "sources": ["Yahoo Finance"],
    },
    "key_financials": {
        "text_en": "Revenue $383B (FY2024), Net Income $97B, FCF $100B. Gross margin 46%, operating margin 31%. Cash $162B, total debt $108B. P/E 28.5x, market cap $2.8T.",
        "sources": ["Yahoo Finance"],
    },
    "recent_developments": {
        "text_en": "iPhone 17 launch with AI features, Vision Pro v2 expected in 2026. Services revenue growing 14% YoY. $110B share buyback program.",
        "sources": ["Tavily"],
    },
    "competitive_position": {
        "text_en": "Apple holds dominant market share in premium smartphones with unmatched brand loyalty. Major competitive advantages include ecosystem lock-in, vertical integration (M-series chips), and massive services recurring revenue stream.",
        "sources": ["Tavily", "Yahoo Finance"],
    },
}


# ── Mock pipeline dependencies ──────────────────────────────────────────

def _mock_yf_data():
    """Realistic Yahoo Finance mock for a healthy company."""
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "price": 185.0,
        "prev_close": 183.5,
        "currency": "USD",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 2.8e12,
        "pe_current": 28.5,
        "pe_forward": 25.0,
        "peg_ratio": 2.1,
        "beta": 1.2,
        "52w_high": 200.0,
        "52w_low": 160.0,
        "expected_growth": 0.12,
        "financials": {
            "revenue_quarterly": 9e10,
            "revenue_yoy_growth": 0.08,
            "revenue_annual": 3.8e11,
            "revenue_annual_growth": 0.06,
            "gross_margin": 0.45,
            "operating_margin": 0.30,
            "net_income": 9.5e10,
            "free_cash_flow": 1e11,
            "net_debt": 8e10,
            "guidance_official": 0.10,
        },
    }


# ═══════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCompanyOverviewWired:
    """Verify company_overview is wired into the pipeline correctly."""

    @patch("backend.sources_collector.get_stock_data")
    @patch("backend.sources_collector.extract_10k_sections")
    @patch("backend.sources_collector.get_finnhub_data")
    @patch("backend.codex_provider.codex_analyze_management")
    @patch("backend.company_overview.get_company_overview")
    @patch("backend.pipeline._add_earnings_deep_dive_if_transcript")
    def test_result_has_company_overview_when_available(
        self,
        mock_deep_dive,
        mock_get_overview,
        mock_codex,
        mock_fh,
        mock_10k,
        mock_yf,
        tmp_path,
    ):
        """company_overview is populated in AnalysisResult when service succeeds."""
        from backend.pipeline import analyze_ticker_fast

        mock_yf.return_value = _mock_yf_data()
        mock_fh.return_value = {}
        mock_10k.return_value = {"mda": "", "risk_factors": ""}
        mock_codex.return_value = {
            "tone": "Positive", "confidence": "High", "visibility": "Clear",
            "concrete_promises": [], "defensive_signals": [], "risks": [],
        }
        mock_get_overview.return_value = MOCK_OVERVIEW_EN
        mock_deep_dive.return_value = False

        result = analyze_ticker_fast(
            "AAPL",
            output_base=str(tmp_path / "analyses"),
            language="en",
        )

        # company_overview should be present and non-empty
        assert result.company_overview is not None, (
            "Expected company_overview to be set when service succeeds"
        )
        assert result.company_overview["company_profile"]["text_en"].startswith("Apple Inc.")

    @patch("backend.sources_collector.get_stock_data")
    @patch("backend.sources_collector.extract_10k_sections")
    @patch("backend.sources_collector.get_finnhub_data")
    @patch("backend.codex_provider.codex_analyze_management")
    @patch("backend.company_overview.get_company_overview")
    @patch("backend.pipeline._add_earnings_deep_dive_if_transcript")
    def test_company_overview_section_in_generated_report(
        self,
        mock_deep_dive,
        mock_get_overview,
        mock_codex,
        mock_fh,
        mock_10k,
        mock_yf,
        tmp_path,
    ):
        """Generated report markdown includes a company overview section."""
        from backend.pipeline import analyze_ticker_fast

        mock_yf.return_value = _mock_yf_data()
        mock_fh.return_value = {}
        mock_10k.return_value = {"mda": "", "risk_factors": ""}
        mock_codex.return_value = {
            "tone": "Positive", "confidence": "High", "visibility": "Clear",
            "concrete_promises": [], "defensive_signals": [], "risks": [],
        }
        mock_get_overview.return_value = MOCK_OVERVIEW_EN
        mock_deep_dive.return_value = False

        result = analyze_ticker_fast(
            "AAPL",
            output_base=str(tmp_path / "analyses"),
            language="en",
        )

        # Read the generated report markdown
        report_path = result.report_path
        if report_path:
            with open(report_path) as f:
                report_text = f.read()

            assert "## 3. Company Overview" in report_text, (
                "Expected '## 3. Company Overview' section in report"
            )
            assert "iPhone" in report_text, (
                "Expected business description content in company overview"
            )
            assert "$383B" in report_text or "revenue" in report_text.lower(), (
                "Expected financial data in company overview"
            )

    @patch("backend.sources_collector.get_stock_data")
    @patch("backend.sources_collector.extract_10k_sections")
    @patch("backend.sources_collector.get_finnhub_data")
    @patch("backend.codex_provider.codex_analyze_management")
    @patch("backend.company_overview.get_company_overview")
    @patch("backend.pipeline._add_earnings_deep_dive_if_transcript")
    def test_graceful_none_when_overview_unavailable(
        self,
        mock_deep_dive,
        mock_get_overview,
        mock_codex,
        mock_fh,
        mock_10k,
        mock_yf,
        tmp_path,
    ):
        """Pipeline succeeds with company_overview=None when service fails."""
        from backend.pipeline import analyze_ticker_fast

        mock_yf.return_value = _mock_yf_data()
        mock_fh.return_value = {}
        mock_10k.return_value = {"mda": "", "risk_factors": ""}
        mock_codex.return_value = {
            "tone": "Positive", "confidence": "High", "visibility": "Clear",
            "concrete_promises": [], "defensive_signals": [], "risks": [],
        }
        # Simulate service failure — overview unavailable
        mock_get_overview.side_effect = Exception("LLM service unavailable")
        mock_deep_dive.return_value = False

        result = analyze_ticker_fast(
            "AAPL",
            output_base=str(tmp_path / "analyses"),
            language="en",
        )

        # Pipeline should complete without error
        assert result.ticker == "AAPL"
        assert result.decision != ""  # scoring still worked

        # company_overview should be None on failure
        assert result.company_overview is None, (
            "Expected company_overview to be None when service fails"
        )

        # Report should not contain the company overview section
        report_path = result.report_path
        if report_path:
            with open(report_path) as f:
                report_text = f.read()
            assert "## 3. Company Overview" not in report_text, (
                "Expected no company overview section when overview unavailable"
            )
