from backend.earnings_deep_dive.mapper import _default_section_analysis
from backend.earnings_deep_dive.schemas import FinancialMetrics


def test_backlog_fallback_wording_avoids_titlecase_not_available():
    metrics = FinancialMetrics(backlog=None)

    text = _default_section_analysis("en", "NVDA", "Backlog", metrics)[0]

    assert "Backlog status is not disclosed / not applicable" in text
    assert "Backlog is Not available" not in text
