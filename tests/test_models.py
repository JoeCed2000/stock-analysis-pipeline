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
    """Tests for 6-category Scoring model with new thresholds."""

    def test_total_sums_all_categories(self):
        s = Scoring(financial_health=7, growth=8, valuation=6,
                     management=4, moat=3, sentiment=2)
        assert s.total == 30

    def test_default_all_zero(self):
        s = Scoring()
        assert s.total == 0
        assert s.decision() == "SELL"

    def test_decision_buy(self):
        s = Scoring(financial_health=8, growth=8, valuation=6,
                     management=4, moat=3, sentiment=3)
        assert s.total == 32
        assert s.decision() == "BUY"

    def test_decision_buy_boundary(self):
        """Exactly 28 = BUY."""
        s = Scoring(financial_health=7, growth=7, valuation=5,
                     management=4, moat=3, sentiment=2)
        assert s.total == 28
        assert s.decision() == "BUY"

    def test_decision_hold(self):
        s = Scoring(financial_health=6, growth=5, valuation=4,
                     management=3, moat=2, sentiment=2)
        assert s.total == 22
        assert s.decision() == "HOLD"

    def test_decision_hold_boundary(self):
        """Exactly 18 = HOLD (lowest HOLD)."""
        s = Scoring(financial_health=5, growth=4, valuation=3,
                     management=3, moat=2, sentiment=1)
        assert s.total == 18
        assert s.decision() == "HOLD"

    def test_decision_sell(self):
        s = Scoring(financial_health=4, growth=3, valuation=3,
                     management=2, moat=2, sentiment=1)
        assert s.total == 15
        assert s.decision() == "SELL"

    def test_decision_sell_boundary(self):
        """17 = SELL (just below HOLD)."""
        s = Scoring(financial_health=5, growth=4, valuation=2,
                     management=3, moat=2, sentiment=1)
        assert s.total == 17
        assert s.decision() == "SELL"

    def test_private_attr_not_serialized(self):
        """_raw_subscores must NOT appear in model_dump()."""
        s = Scoring(financial_health=7, growth=8, valuation=6,
                     management=4, moat=3, sentiment=2)
        s._raw_subscores = {"growth": 4, "profitability": 3, "financial_strength": 4,
                            "moat": 5, "management": 3, "valuation_risk": 4,
                            "geopolitical_risk": 3, "business_momentum": 3}
        dumped = s.model_dump()
        assert "_raw_subscores" not in dumped
        assert "financial_health" in dumped
        assert "growth" in dumped

    def test_private_attr_direct_access(self):
        """_raw_subscores is directly accessible in Python."""
        s = Scoring(financial_health=7, growth=8, valuation=6,
                     management=4, moat=3, sentiment=2)
        s._raw_subscores = {"profitability": 3, "financial_strength": 4}
        assert s._raw_subscores["profitability"] == 3
        assert s._raw_subscores["financial_strength"] == 4

    def test_max_total_is_40(self):
        """Maximum possible: 10 + 10 + 8 + 5 + 4 + 3 = 40."""
        s = Scoring(financial_health=10, growth=10, valuation=8,
                     management=5, moat=4, sentiment=3)
        assert s.total == 40
        assert s.decision() == "BUY"


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
