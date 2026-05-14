import pytest

from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf, resolve_pdf_fonts
from backend.earnings_deep_dive.schemas import FinancialMetrics


fitz = pytest.importorskip("fitz")


def _sample_report():
    return build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="en",
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
            roic=0.28,
            pe_forward=21.19,
            guidance="Revenue growth expected to remain double-digit.",
            segments={"Cloud": {"revenue": 45_000_000_000, "yoy": 0.26}},
        ),
        transcript_url="https://example.com/msft-transcript",
    )


def test_pdf_renderer_uses_letter_page_size(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive.pdf"

    render_earnings_deep_dive_pdf(_sample_report(), pdf_path)

    doc = fitz.open(pdf_path)
    page = doc[0]
    assert round(page.rect.width, 2) == 612.00
    assert round(page.rect.height, 2) == 792.00


def test_pdf_renderer_generates_extractable_text_and_tables(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive.pdf"

    render_earnings_deep_dive_pdf(_sample_report(), pdf_path)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 10_000

    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)

    for expected in (
        "Microsoft Corporation (MSFT)",
        "EPS & Revenue",
        "Highlights",
        "Operating Metrics",
        "Cash Flow",
        "Capital Efficiency",
        "Segments",
        "Forward P/E",
        "Backlog",
        "Guidance",
        "Verdict / Overall Assessment",
        "Metric",
        "Estimate",
        "Actual",
        "Source",
    ):
        assert expected in text

    assert "GE Vernova" not in text
    assert "SanDisk" not in text


def test_pdf_renderer_generates_language_specific_japanese_report(tmp_path):
    pdf_path = tmp_path / "earnings_deep_dive_jp.pdf"
    report = build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter="FY2026 Q1",
        language="jp",
        metrics=FinancialMetrics(revenue_actual=82_900_000_000),
        transcript_url="https://example.com/msft-transcript",
    )

    render_earnings_deep_dive_pdf(report, pdf_path)

    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    normalized_text = " ".join(text.split())

    assert pdf_path.exists()
    assert "Microsoft Corporation (MSFT)" in text
    assert "総合評価" in text
    assert "DONNÉE NON DISPONIBLE" not in normalized_text


def test_pdf_renderer_resolves_model_fonts_when_available():
    english_fonts = resolve_pdf_fonts("en")
    japanese_fonts = resolve_pdf_fonts("jp")

    assert english_fonts.regular in {"Arial", "Helvetica"}
    assert english_fonts.bold in {"Arial-Bold", "Helvetica-Bold"}
    assert japanese_fonts.regular in {"MS-PGothic", "HeiseiMin-W3", "Helvetica"}
