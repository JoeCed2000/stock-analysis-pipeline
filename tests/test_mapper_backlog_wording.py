from backend.earnings_deep_dive.mapper import _default_section_analysis
from backend.earnings_deep_dive.schemas import FinancialMetrics


def test_backlog_fallback_wording_avoids_titlecase_not_available():
    metrics = FinancialMetrics(backlog=None)

    text = _default_section_analysis("en", "NVDA", "Backlog", metrics)[0]

    # No-NA policy (Ced 2026-06-12): placeholder labels are replaced by an
    # informative sentence pointing to the actual forward-visibility sources.
    assert "Backlog status is not part of reported disclosures" in text
    assert "guidance and purchase commitments" in text
    assert "Backlog is Not available" not in text
