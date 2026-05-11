import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
from backend.earnings_deep_dive.schemas import FinancialMetrics


fitz = pytest.importorskip("fitz")


def _metrics() -> FinancialMetrics:
    return FinancialMetrics(
        eps_estimate=3.10,
        eps_actual=3.46,
        eps_vs_estimate=0.116,
        eps_yoy=0.22,
        revenue_estimate=80_000_000_000,
        revenue_actual=82_900_000_000,
        revenue_yoy=0.183,
        gross_profit=56_000_000_000,
        gross_profit_prior_year=48_000_000_000,
        gross_profit_yoy=0.167,
        gross_margin=0.676,
        gross_margin_prior_year=0.650,
        gross_margin_yoy=0.026,
        opex=18_000_000_000,
        opex_prior_year=17_000_000_000,
        opex_yoy=0.059,
        operating_income=38_400_000_000,
        operating_income_prior_year=31_000_000_000,
        operating_income_yoy=0.239,
        operating_margin=0.463,
        operating_margin_prior_year=0.442,
        operating_margin_yoy=0.021,
        net_income=27_200_000_000,
        net_income_quarterly_prior_year=22_000_000_000,
        net_income_yoy=0.236,
        operating_cash_flow=95_000_000_000,
        operating_cash_flow_prior_year=78_000_000_000,
        operating_cash_flow_yoy=0.218,
        capex=23_400_000_000,
        capex_prior_year=21_000_000_000,
        capex_yoy=0.114,
        free_cash_flow=71_600_000_000,
        free_cash_flow_prior_year=57_000_000_000,
        free_cash_flow_yoy=0.256,
        roe=0.35,
        roe_prior_year=0.31,
        roe_yoy=0.04,
        roic=0.28,
        roic_prior_year=0.25,
        roic_yoy=0.03,
        buybacks=8_000_000_000,
        dividends=6_000_000_000,
        pe_forward=21.19,
        backlog=18_000_000_000,
        guidance="Revenue growth expected to remain double-digit with disciplined operating expense.",
        segments={
            "Cloud": {"revenue": 45_000_000_000, "yoy": 0.26, "driver": "Azure demand"},
            "Productivity": {"revenue": 29_000_000_000, "yoy": 0.13, "driver": "Microsoft 365 seats"},
            "More Personal Computing": {"revenue": 14_000_000_000, "yoy": 0.07, "driver": "Windows OEM"},
        },
        quarter="2026Q1",
        company_website="https://www.microsoft.com",
        investor_relations_url="https://www.microsoft.com/en-us/investor",
        press_release_url="https://www.microsoft.com/en-us/investor/earnings/fy-2026-q1",
        earnings_presentation_url="https://www.microsoft.com/en-us/investor/presentations/fy-2026-q1",
    )


def _report(quarter: str = "FY2026 Q1"):
    return build_earnings_deep_dive_report(
        ticker="MSFT",
        company="Microsoft Corporation",
        quarter=quarter,
        language="en",
        metrics=_metrics(),
        transcript_url="https://www.microsoft.com/en-us/investor/events/fy-2026/q1-transcript",
    )


def _rendered_pdf(tmp_path, report=None):
    pdf_path = tmp_path / "msft_deep_dive.pdf"
    render_earnings_deep_dive_pdf(report or _report(), pdf_path)
    return fitz.open(pdf_path)


def test_highlights_have_at_least_three_numbered_items():
    highlights = next(section for section in _report().sections if section.key == "Highlights")
    text = "\n".join(highlights.analysis)

    numbered_items = re.findall(r"(?m)^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+\.)\s+", text)

    assert len(numbered_items) >= 3
    assert "🧠" in text
    assert "🎯" in text


def test_each_major_section_has_more_than_200_chars_of_commentary():
    for section in _report().sections:
        commentary = "\n".join(section.analysis).strip()
        assert len(commentary) > 200, section.key


def test_pdf_has_no_footer_page_numbers(tmp_path):
    doc = _rendered_pdf(tmp_path)

    for index, page in enumerate(doc, start=1):
        page_number_spans = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span["text"].strip() == str(index) and span["bbox"][1] > page.rect.height - 70:
                        page_number_spans.append(span)
        assert not page_number_spans, f"footer page number found on page {index}"


def test_sources_start_on_their_own_page(tmp_path):
    doc = _rendered_pdf(tmp_path)
    source_pages = [
        index
        for index, page in enumerate(doc)
        if page.get_text().lstrip().startswith("Sources")
    ]

    assert source_pages, "Sources page not found"
    source_text = doc[source_pages[0]].get_text()
    assert "Verdict / Overall Assessment" not in source_text
    assert "Earnings Transcript" in source_text


def test_title_uses_explicit_quarter_not_latest_quarter(tmp_path):
    report = _report(quarter="latest quarter")

    assert report.quarter == "2026Q1"

    doc = _rendered_pdf(tmp_path, report)
    text = "\n".join(page.get_text() for page in doc)

    assert "Earnings Deep-Dive - 2026Q1" in text
    assert "latest quarter" not in text.lower()
