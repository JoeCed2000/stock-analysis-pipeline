from backend.earnings_deep_dive.deep_dive_validator import validate_render_model
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.template import (
    EARNINGS_TEMPLATE,
    TEMPLATE_LANGUAGE_CODES,
    TEMPLATE_SECTION_KEYS,
    get_earnings_template,
)


def test_template_contains_all_model_sections_in_order():
    assert TEMPLATE_SECTION_KEYS == (
        "EPS & Revenue",
        "Highlights",
        "Operating Metrics",
        "Cash Flow",
        "Capital Efficiency",
        "Segments",
        "Forward P/E",
        "Backlog",
        "Guidance",
        "Verdict",
    )
    assert [section.key for section in EARNINGS_TEMPLATE] == list(TEMPLATE_SECTION_KEYS)
    assert EARNINGS_TEMPLATE[0].title == "EPS & Revenue"
    assert EARNINGS_TEMPLATE[-1].title == "Verdict / Overall Assessment"


def test_template_tables_match_model_expectations():
    tables = {section.key: section.table_columns for section in EARNINGS_TEMPLATE}

    assert tables["EPS & Revenue"] == (
        "Metric",
        "Estimate",
        "Actual",
        "vs Estimate",
        "YoY Change",
        "Source",
    )
    assert tables["Operating Metrics"] == ("Metric", "Actual", "Prior Year", "YoY", "Source")
    assert tables["Cash Flow"] == ("Metric", "Actual", "Prior Year", "YoY", "Quality", "Source")
    assert tables["Guidance"] == ("Metric", "Guidance", "QoQ", "Medium-term Signal", "Source")


def test_template_has_distinct_english_and_japanese_variants():
    assert TEMPLATE_LANGUAGE_CODES == ("en", "jp")

    english_template = get_earnings_template("en")
    japanese_template = get_earnings_template("jp")

    assert [section.key for section in english_template] == list(TEMPLATE_SECTION_KEYS)
    assert [section.key for section in japanese_template] == list(TEMPLATE_SECTION_KEYS)
    assert english_template[0].question.startswith("Please summarize")
    assert "以下" in japanese_template[0].question
    assert english_template[0].question != japanese_template[0].question
    assert english_template[-1].title == "Verdict / Overall Assessment"
    assert japanese_template[-1].title == "総合評価"


def test_mapper_replaces_examples_with_requested_ticker():
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(
            eps_estimate=3.10,
            eps_actual=3.46,
            revenue_estimate=80_000_000_000,
            revenue_actual=82_900_000_000,
            revenue_yoy=0.183,
            gross_margin=0.676,
            operating_margin=0.463,
            net_income=101_800_000_000,
            free_cash_flow=71_600_000_000,
            pe_forward=21.19,
            guidance="Revenue growth expected to remain double-digit.",
        ),
        transcript_url="https://example.com/msft-transcript",
    )

    text = report.model_dump_json()

    assert report.language == "en"
    assert report.ticker == "MSFT"
    assert report.company == "Microsoft Corporation"
    assert "MSFT" in text
    assert "Microsoft Corporation" in text
    assert "GEV" not in text
    assert "GE Vernova" not in text
    assert "$17.44" not in text
    assert "$111.18B" not in text
    assert "SanDisk" not in text


def test_mapper_prefers_codex_generated_section_tables_over_sparse_metrics():
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(),
        transcript_url="https://example.com/msft-transcript",
        section_analysis={
            "EPS & Revenue": """
## EPS & Revenue

| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |
|---|---:|---:|---:|---:|---|
| EPS | $3.66 | $4.13 | +12.8% | +23.0% | Earnings release |
| Revenue | $75.39B | $77.67B | +3.0% | +18.4% | Earnings release |

> One-line summary: Microsoft beat both EPS and revenue expectations.
"""
        },
    )

    eps_section = report.sections[0]
    table_text = " ".join(
        cell
        for row in eps_section.table.rows
        for cell in [row.label, *row.cells]
    )

    assert "$4.13" in table_text
    assert "$77.67B" in table_text
    assert "DONNÉE NON DISPONIBLE" not in table_text


def test_mapper_uses_donnee_non_disponible_for_missing_metrics():
    report = build_earnings_deep_dive_report(
        ticker="ABC",
        company="ABC Corp",
        quarter="latest quarter",
        language="jp",
        metrics=FinancialMetrics(),
        transcript_url=None,
    )

    assert report.language == "jp"
    assert report.sections[-1].title == "総合評価"
    for section in report.sections:
        assert section.table.rows
        for row in section.table.rows:
            assert all(cell.strip() for cell in row.cells)
            assert "DONNÉE NON DISPONIBLE" in row.cells


def test_render_model_validation_rejects_pdf_placeholders():
    report = build_earnings_deep_dive_report(
        ticker="ABC",
        company="ABC Corp",
        quarter="latest quarter",
        language="en",
        metrics=FinancialMetrics(),
        transcript_url=None,
    )

    issues = validate_render_model(report)

    assert any("Forbidden marker" in issue for issue in issues)
