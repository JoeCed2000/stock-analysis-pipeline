"""Tests for Pydantic models."""
import pytest
from backend.models import (
    TickerRequest, Scoring, FinancialData, AnalysisResult,
    Source, Claim, AnalysisJobResponse, AnalysisJobStatus
)


class TestTickerRequest:
    def test_valid_single_ticker(self):
        req = TickerRequest(tickers=["NVDA"])
        assert req.tickers == ["NVDA"]

    def test_valid_multiple_tickers(self):
        req = TickerRequest(tickers=["NVDA", "MSFT", "ASML"])
        assert len(req.tickers) == 3

    def test_empty_tickers_rejected(self):
        with pytest.raises(ValueError):
            TickerRequest(tickers=[])

    def test_max_10_tickers(self):
        with pytest.raises(ValueError):
            TickerRequest(tickers=[f"TICK{i}" for i in range(11)])


class TestScoring:
    def test_total_sums_all_criteria(self):
        s = Scoring(growth=5, profitability=4, financial_strength=3,
                     moat=5, management=4, valuation_risk=3,
                     geopolitical_risk=4, business_momentum=4)
        assert s.total == 32

    def test_default_all_zero(self):
        s = Scoring()
        assert s.total == 0

    def test_decision_buy(self):
        s = Scoring(growth=5, profitability=5, financial_strength=5,
                     moat=5, management=4, valuation_risk=3,
                     geopolitical_risk=3, business_momentum=5)
        assert s.total == 35
        assert s.decision() == "BUY"

    def test_decision_hold_pullback(self):
        s = Scoring(growth=4, profitability=4, financial_strength=3,
                     moat=4, management=3, valuation_risk=3,
                     geopolitical_risk=3, business_momentum=4)
        assert s.total == 28
        assert "HOLD" in s.decision()

    def test_decision_hold_fragile(self):
        s = Scoring(growth=3, profitability=3, financial_strength=2,
                     moat=3, management=3, valuation_risk=2,
                     geopolitical_risk=3, business_momentum=3)
        assert s.total == 22
        assert s.decision() == "HOLD fragile"

    def test_decision_sell(self):
        s = Scoring(growth=2, profitability=2, financial_strength=1,
                     moat=2, management=2, valuation_risk=2,
                     geopolitical_risk=2, business_momentum=2)
        assert s.total == 15
        assert "SELL" in s.decision()


class TestFinancialData:
    def test_defaults_all_none(self):
        fd = FinancialData()
        assert fd.revenue_quarterly is None
        assert fd.gross_margin is None

    def test_partial_data(self):
        fd = FinancialData(revenue_quarterly=10.5, gross_margin=0.65)
        assert fd.revenue_quarterly == 10.5
        assert fd.gross_margin == 0.65
        assert fd.net_income is None


class TestAnalysisResult:
    def test_default_factory_creates_submodels(self):
        result = AnalysisResult(ticker="NVDA", company_name="NVIDIA", retrieved_at="2026-05-04")
        assert result.financials.revenue_quarterly is None
        assert result.scoring.total == 0
        assert result.risks == []


class TestSource:
    def test_valid_source(self):
        s = Source(
            id="SRC-001", category="financial", title="Q4 Earnings",
            url="https://example.com", retrieved_at="2026-05-04",
            source_type="earnings_release", publisher="NVIDIA IR",
            used_for=["revenue"]
        )
        assert s.reliability == "medium"


class TestClaim:
    def test_valid_claim(self):
        c = Claim(
            claim_id="C001", claim="Revenue was 10B",
            source_id="SRC-001", confidence="high"
        )
        assert c.used_in_report is True


class TestAnalysisJobResponse:
    def test_default_status_processing(self):
        resp = AnalysisJobResponse(job_id="abc", tickers=["NVDA"])
        assert resp.status == "processing"


class TestAnalysisJobStatus:
    def test_empty_results_by_default(self):
        status = AnalysisJobStatus(job_id="abc", status="completed")
        assert status.results == []
        assert status.errors == []
