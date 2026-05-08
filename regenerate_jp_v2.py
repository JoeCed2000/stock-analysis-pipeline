#!/usr/bin/env python3
"""Regenerate MSFT JP PDF — v3 with debug."""
import json, re, sys
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")

from backend.pipeline import _extract_quarterly_comparison
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report, _is_placeholder, _rows_for_section
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf

HEADING_TO_KEY = {
    "📊 EPS & Revenue": "EPS & Revenue",
    "🌟 Highlights & ⚠️ Lowlights": "Highlights",
    "🧠 Operating Metrics": "Operating Metrics",
    "💰 Cash Flow": "Cash Flow",
    "🎯 Capital Efficiency": "Capital Efficiency",
    "🧩 Segments": "Segments",
    "📈 Forward P/E": "Forward P/E",
    "📦 Backlog Quality": "Backlog",
    "🔮 Guidance": "Guidance",
    "🏆 Verdict": "Verdict",
}

def parse_markdown_sections(md_path: str) -> dict[str, str]:
    text = Path(md_path).read_text(encoding="utf-8")
    parts = re.split(r"\n##\s+", text)
    result = {}
    for part in parts[1:]:
        lines = part.split("\n", 1)
        heading = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""
        key = HEADING_TO_KEY.get(heading)
        if key is None:
            for h, k in HEADING_TO_KEY.items():
                if heading.startswith(h) or h in heading:
                    key = k
                    break
        if key:
            result[key] = content
    return result

md_path = "analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive.md"
section_analysis = parse_markdown_sections(md_path)
print(f"Parsed {len(section_analysis)} sections")

# Check Operating Metrics content
om = section_analysis.get("Operating Metrics", "")
print(f"\nOperating Metrics content first 500 chars:")
print(om[:500])

yf_data = _extract_quarterly_comparison("MSFT")
metrics = FinancialMetrics(
    eps_estimate=yf_data.get("eps_estimate"),
    eps_actual=yf_data.get("eps_actual"), eps_prior_year=yf_data.get("eps_prior_year"),
    eps_yoy=yf_data.get("eps_yoy"),
    revenue_actual=yf_data.get("revenue_actual"), revenue_quarterly_prior_year=yf_data.get("revenue_quarterly_prior_year"),
    revenue_yoy=yf_data.get("revenue_yoy"),
    gross_profit=yf_data.get("gross_profit"),
    gross_profit_prior_year=yf_data.get("gross_profit_prior_year"),
    gross_profit_yoy=yf_data.get("gross_profit_yoy"),
    gross_margin=yf_data.get("gross_margin"),
    gross_margin_prior_year=yf_data.get("gross_margin_prior_year"),
    gross_margin_yoy=yf_data.get("gross_margin_yoy"),
    opex=yf_data.get("opex"),
    opex_prior_year=yf_data.get("opex_prior_year"),
    opex_yoy=yf_data.get("opex_yoy"),
    operating_income=yf_data.get("operating_income"),
    operating_income_prior_year=yf_data.get("operating_income_prior_year"),
    operating_income_yoy=yf_data.get("operating_income_yoy"),
    operating_margin=yf_data.get("operating_margin"),
    operating_margin_prior_year=yf_data.get("operating_margin_prior_year"),
    operating_margin_yoy=yf_data.get("operating_margin_yoy"),
    net_income_quarterly=yf_data.get("net_income_quarterly"),
    net_income_quarterly_prior_year=yf_data.get("net_income_quarterly_prior_year"),
    net_income_yoy=yf_data.get("net_income_yoy"),
    operating_cash_flow=yf_data.get("operating_cash_flow"),
    operating_cash_flow_prior_year=yf_data.get("operating_cash_flow_prior_year"),
    operating_cash_flow_yoy=yf_data.get("operating_cash_flow_yoy"),
    capex=yf_data.get("capex"),
    capex_prior_year=yf_data.get("capex_prior_year"),
    capex_yoy=yf_data.get("capex_yoy"),
    free_cash_flow=yf_data.get("free_cash_flow"),
    free_cash_flow_prior_year=yf_data.get("free_cash_flow_prior_year"),
    free_cash_flow_yoy=yf_data.get("free_cash_flow_yoy"),
    net_debt=yf_data.get("net_debt"),
    roe=yf_data.get("roe"), roe_prior_year=yf_data.get("roe_prior_year"), roe_yoy=yf_data.get("roe_yoy"),
    rotce=yf_data.get("rotce"), rotce_prior_year=yf_data.get("rotce_prior_year"), rotce_yoy=yf_data.get("rotce_yoy"),
    roa=yf_data.get("roa"), roa_prior_year=yf_data.get("roa_prior_year"), roa_yoy=yf_data.get("roa_yoy"),
    roic=yf_data.get("roic"), roic_prior_year=yf_data.get("roic_prior_year"), roic_yoy=yf_data.get("roic_yoy"),
    buybacks=yf_data.get("buybacks"),
    dividends=yf_data.get("dividends"),
    pe_forward=yf_data.get("pe_forward"),
    investor_relations_url=yf_data.get("investor_relations_url"),
    company_website=yf_data.get("company_website"),
)

report = build_earnings_deep_dive_report(
    ticker="MSFT", company="Microsoft Corporation", quarter="FY2026 Q3",
    metrics=metrics,
    transcript_url="https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/",
    language="jp", section_analysis=section_analysis,
)

# Check with _is_placeholder
for section_key in ["EPS & Revenue", "Operating Metrics", "Cash Flow", "Capital Efficiency"]:
    for section in report.sections:
        if section.key == section_key:
            placeholder_cells = []
            for row in section.table.rows:
                for cell in row.cells:
                    if _is_placeholder(cell):
                        placeholder_cells.append(f"{row.label}: {cell}")
            status = "❌ HAS PLACEHOLDERS" if placeholder_cells else "✅ CLEAN"
            print(f"\n{section_key}: {status}")
            if placeholder_cells:
                for p in placeholder_cells:
                    print(f"  {p}")
            for row in section.table.rows:
                print(f"  {row.label}: {row.cells}")

output_jp = "analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive_jp_v3.pdf"
render_earnings_deep_dive_pdf(report, output_jp)
print(f"\n✅ JP PDF: {output_jp} ({Path(output_jp).stat().st_size} bytes)")
