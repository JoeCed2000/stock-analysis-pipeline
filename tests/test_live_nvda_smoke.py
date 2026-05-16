"""
Live NVDA smoke test — uses real external data. Manual/nightly only.
Validates that the live pipeline still works with actual market data.
Not for pre-commit — too slow and depends on external APIs.
"""
import pytest
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

pytestmark = [pytest.mark.slow, pytest.mark.live]


@pytest.fixture(scope="module")
def nvda_live():
    """Run full pipeline on NVDA with live data. Module-scoped."""
    from backend.pipeline import analyze_ticker_fast
    return analyze_ticker_fast("NVDA", output_base=str(PROJECT / "tests" / "tmp"))


class TestLiveNVDA:
    """Live pipeline — validates real API integration."""

    def test_live_pipeline_does_not_crash(self, nvda_live):
        assert nvda_live is not None
        assert nvda_live.ticker == "NVDA"

    def test_live_score_in_range(self, nvda_live):
        assert 0 <= nvda_live.score <= 40, f"Score {nvda_live.score} out of range"

    def test_live_pdf_generated(self, nvda_live):
        import glob
        pdf_path = getattr(nvda_live, 'pdf_path', None)
        if pdf_path is None:
            candidates = glob.glob(str(PROJECT / "tests" / "tmp" / "NVDA" / "*.pdf"))
            pdf_path = candidates[0] if candidates else None
        assert pdf_path and Path(pdf_path).exists(), "No PDF"
        assert Path(pdf_path).stat().st_size > 50000

    def test_live_decision_maps_to_score(self, nvda_live):
        score = nvda_live.score
        decision = nvda_live.decision.upper()
        if score >= 28:
            assert decision == "BUY"
        elif score >= 15:
            assert decision == "HOLD"
        else:
            assert decision == "SELL"

    def test_live_data_contract(self, nvda_live):
        """pre_render_validator rejects on live data."""
        if hasattr(nvda_live, 'deep_dive') and nvda_live.deep_dive:
            dd = nvda_live.deep_dive
            if dd:
                assert dd.report is not None
                sections = getattr(dd.report, 'sections', {})
                required = ['summary', 'financial_highlights', 'valuation', 
                          'growth_outlook', 'risks', 'verdict']
                for section in required:
                    assert section in sections, f"Missing section: {section}"
