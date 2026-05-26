from backend.earnings_deep_dive.deep_dive_validator import validate_render_model
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.prompts import build_prompt, system_prompt
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.template import (
    EARNINGS_TEMPLATE,
    TEMPLATE_LANGUAGE_CODES,
    TEMPLATE_SECTION_KEYS,
    get_earnings_template,
)
from backend.models import Scoring


def test_deep_dive_prompts_do_not_request_forbidden_placeholders():
    prompt = build_prompt(
        "Cash Flow",
        "jp",
        "MSFT",
        "Microsoft Corporation",
        "FY2026 Q1",
        {"operating_cash_flow": 95_000_000_000},
        "",
    )
    combined = f"{system_prompt('jp')}\n{system_prompt('en')}\n{prompt}"

    assert "Data not available in transcript" not in combined
    assert "Every table cell must contain a sourced value or —" not in combined
    assert "otherwise write —" not in combined
    assert "Section unavailable. Not disclosed" not in combined
    assert "Not retrieved" in combined


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


def test_mapper_documents_target_company_earnings_sources():
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(
            transcript_source="Google Search Transcript",
            investor_relations_url="https://www.microsoft.com/en-us/investor",
            company_website="https://www.microsoft.com",
        ),
        transcript_url="https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q1",
    )

    text = report.model_dump_json()

    assert "Candidate Transcript Source - Seeking Alpha" in text
    assert "https://seekingalpha.com/symbol/MSFT/earnings/transcripts" in text
    assert "Transcript - Google Search Transcript" in text
    assert "https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q1" in text
    assert "Official Investor Relations" in text
    assert "https://www.microsoft.com/en-us/investor" in text
    assert "GE Vernova" not in text
    assert "https://www.gevernova.com/investors" not in text


def test_mapper_preserves_duckduckgo_transcript_source_label():
    report = build_earnings_deep_dive_report(
        ticker="AMD",
        company="Advanced Micro Devices",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(
            transcript_source="DuckDuckGo Transcript Search",
            company_website="https://www.amd.com",
        ),
        transcript_url="https://example.com/amd-earnings-call-transcript",
    )

    text = report.model_dump_json()

    assert "Transcript - DuckDuckGo Transcript Search" in text
    assert "https://example.com/amd-earnings-call-transcript" in text


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
            assert any(label in row.cells for label in ("データ未取得", "開示なし", "該当なし", "計算不可"))


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

    assert any("Missing transcript/source URL" in issue for issue in issues)


def test_mapper_never_generates_generic_section_takeaways():
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
            operating_cash_flow=95_000_000_000,
            capex=23_400_000_000,
            free_cash_flow=71_600_000_000,
        ),
        transcript_url="https://example.com/msft-transcript",
    )

    text = report.model_dump_json()

    assert "is assessed from available sourced data" not in text
    assert "EPS & Revenue is assessed" not in text
    assert "Cash Flow is assessed" not in text
    assert any("beat" in section.summary.lower() or "revenue" in section.summary.lower() for section in report.sections)


def test_japanese_template_outputs_nami_style_explanation_markers():
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="jp",
        metrics=FinancialMetrics(
            eps_actual=3.46,
            revenue_actual=82_900_000_000,
            revenue_yoy=0.183,
            free_cash_flow=71_600_000_000,
        ),
        transcript_url="https://example.com/msft-transcript",
    )

    highlights = next(section for section in report.sections if section.key == "Highlights")
    rendered = "\n".join(highlights.analysis + [highlights.summary])

    assert "🌟 ハイライト（良かった点）" in rendered
    assert "⚠️ ローライト（懸念点）" in rendered
    assert "🧠 総合評価（Namiさん向け）" in rendered
    assert "🎯 投資視点の一言" in rendered
    assert "👉" in rendered
    assert "●" in rendered
    assert "①" in rendered


def test_mapper_scoring_section_has_6_categories():
    """Mapper reads all 6 canonical Scoring fields and produces weighted chart data."""
    scoring = Scoring(
        financial_health=7,   # /10
        growth=8,              # /10
        valuation=6,           # /8
        management=3,          # /5
        moat=3,                # /4
        sentiment=2,           # /3
    )

    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(
            eps_actual=3.46,
            revenue_actual=82_900_000_000,
            revenue_yoy=0.183,
            free_cash_flow=71_600_000_000,
            operating_margin=0.463,
            eps_vs_estimate=0.116,
            pe_forward=21.19,
        ),
        scoring=scoring,
    )

    charts = report.charts
    assert charts is not None, "ChartData should not be None when scoring is provided"

    # Verify all 6 canonical categories are present in chart data
    assert charts.scoring_financial_health == 7
    assert charts.scoring_growth == 8
    assert charts.scoring_valuation == 6
    assert charts.scoring_management == 3
    assert charts.scoring_moat == 3
    assert charts.scoring_sentiment == 2

    # Total should be 7+8+6+3+3+2 = 29
    assert charts.scoring_total == 29

    # Verify Verdict section reflects canonical scoring
    verdict_section = next(s for s in report.sections if s.key == "Verdict")
    verdict_text = verdict_section.model_dump_json()
    assert "Score:" in verdict_text
    assert "FH:" in verdict_text
    assert "Gr:" in verdict_text
    assert "Va:" in verdict_text
    assert "Mg:" in verdict_text
    assert "Mo:" in verdict_text
    assert "Se:" in verdict_text
    assert "29/40" in verdict_text


def test_mapper_scoring_includes_decision_badge():
    """Mapper produces decision badge (BUY/HOLD/SELL) from canonical Scoring."""

    # BUY case: total >= 28
    scoring_buy = Scoring(
        financial_health=9, growth=9, valuation=7, management=4, moat=3, sentiment=2
    )
    report_buy = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(eps_actual=3.46, revenue_actual=82_900_000_000),
        scoring=scoring_buy,
    )
    assert report_buy.charts.scoring_decision == "BUY"
    assert report_buy.charts.scoring_total == 34

    # HOLD case: 18 <= total < 28
    scoring_hold = Scoring(
        financial_health=5, growth=5, valuation=4, management=3, moat=2, sentiment=1
    )
    report_hold = build_earnings_deep_dive_report(
        ticker="IBM",
        company="IBM",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(eps_actual=1.80, revenue_actual=15_000_000_000),
        scoring=scoring_hold,
    )
    assert report_hold.charts.scoring_decision == "HOLD"
    assert report_hold.charts.scoring_total == 20

    # SELL case: total < 18
    scoring_sell = Scoring(
        financial_health=3, growth=2, valuation=3, management=1, moat=1, sentiment=1
    )
    report_sell = build_earnings_deep_dive_report(
        ticker="GE",
        company="General Electric",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(eps_actual=0.90, revenue_actual=8_000_000_000),
        scoring=scoring_sell,
    )
    assert report_sell.charts.scoring_decision == "SELL"
    assert report_sell.charts.scoring_total == 11
