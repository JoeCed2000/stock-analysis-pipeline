from pathlib import Path

from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
from backend.earnings_deep_dive.schemas import FinancialMetrics
from scripts.validate_pdf_against_model import validate_pdf_against_model


def test_pdf_validation_blocks_generic_phrases_and_empty_tables(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive.pdf"
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
        metrics=FinancialMetrics(),
        transcript_url=None,
    )

    render_earnings_deep_dive_pdf(report, pdf_path)

    result = validate_pdf_against_model(
        generated_pdf=pdf_path,
        model_pdf=Path("docs/specs/modele.pdf"),
        ticker="MSFT",
        company="Microsoft Corporation",
        structured_report=report,
    )

    assert result.passed is False
    assert any("source URL" in issue for issue in result.blocking_issues)
    assert any("mostly empty" in issue for issue in result.blocking_issues)


def test_pdf_validation_passes_structured_fixture_with_model_categories(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive.pdf"
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="jp",
        metrics=FinancialMetrics(
            eps_estimate=3.10,
            eps_actual=3.46,
            eps_vs_estimate=0.116,
            eps_yoy=0.22,
            revenue_estimate=80_000_000_000,
            revenue_actual=82_900_000_000,
            revenue_yoy=0.183,
            gross_profit=56_000_000_000,
            gross_margin=0.676,
            opex=18_000_000_000,
            operating_income=38_400_000_000,
            operating_margin=0.463,
            net_income=101_800_000_000,
            operating_cash_flow=95_000_000_000,
            capex=23_400_000_000,
            free_cash_flow=71_600_000_000,
            roe=0.35,
            rotce=0.41,
            roa=0.18,
            roic=0.28,
            pe_forward=21.19,
            backlog=250_000_000_000,
            guidance="会社開示: revenue growth expected to remain double-digit.",
            segments={
                "Cloud": {"revenue": 45_000_000_000, "yoy": 0.26, "driver": "Azure demand"},
                "Productivity": {"revenue": 33_000_000_000, "yoy": 0.12, "driver": "Commercial cloud"},
            },
        ),
        transcript_url="https://example.com/msft-transcript",
    )

    render_earnings_deep_dive_pdf(report, pdf_path)

    result = validate_pdf_against_model(
        generated_pdf=pdf_path,
        model_pdf=Path("docs/specs/modele.pdf"),
        ticker="MSFT",
        company="Microsoft Corporation",
        structured_report=report,
    )

    assert result.passed is True
    assert result.blocking_issues == []
    assert result.page_count == result.model_page_count == 14
