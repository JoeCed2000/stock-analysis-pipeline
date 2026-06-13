from backend.models import AnalysisResult, FinancialData, ValuationData, Scoring
from backend.pipeline import _generate_report


def test_generate_report_never_leaves_sources_section_empty():
    result = AnalysisResult(
        ticker="NVDA",
        company_name="NVIDIA Corp",
        retrieved_at="2026-06-13T15:38:06+02:00",
        currency="USD",
        financials=FinancialData(revenue_quarterly=81_615_000_000),
        valuation=ValuationData(pe_current=31.12),
        scoring=Scoring(growth=9, financial_health=10, valuation=6, management=3, moat=4, sentiment=1),
        decision="BUY",
        conviction="Moderate",
        key_phrase="Test phrase",
    )
    report = _generate_report(result, {"_source": "finnhub"}, [])

    sources_section = report.split("## 9. Sources", 1)[1]
    assert "SRC-001" in sources_section
    assert "Finnhub" in sources_section
    assert "https://finnhub.io/" in sources_section
