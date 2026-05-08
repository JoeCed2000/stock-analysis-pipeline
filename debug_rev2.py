import re, sys
from pathlib import Path
sys.path.insert(0, "/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")

from backend.pipeline import _extract_quarterly_comparison
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report, _is_placeholder
from backend.earnings_deep_dive.schemas import FinancialMetrics

HEADING_TO_KEY = {
    "📊 EPS & Revenue": "EPS & Revenue",
    "🧠 Operating Metrics": "Operating Metrics",
    "💰 Cash Flow": "Cash Flow",
    "🎯 Capital Efficiency": "Capital Efficiency",
}

md = Path("analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive.md").read_text()
parts = re.split(r"\n##\s+", md)
section_analysis = {}
for part in parts[1:]:
    lines = part.split("\n", 1)
    heading = lines[0].strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    key = HEADING_TO_KEY.get(heading)
    if key:
        section_analysis[key] = content

yf_data = _extract_quarterly_comparison("MSFT")
metrics = FinancialMetrics(
    eps_estimate=yf_data.get("eps_estimate"), eps_actual=yf_data.get("eps_actual"), eps_yoy=yf_data.get("eps_yoy"),
    revenue_actual=yf_data.get("revenue_actual"), revenue_quarterly_prior_year=yf_data.get("revenue_quarterly_prior_year"),
    revenue_yoy=yf_data.get("revenue_yoy"),
    gross_profit=yf_data.get("gross_profit"), gross_profit_prior_year=yf_data.get("gross_profit_prior_year"), gross_profit_yoy=yf_data.get("gross_profit_yoy"),
    opex=yf_data.get("opex"), opex_prior_year=yf_data.get("opex_prior_year"), opex_yoy=yf_data.get("opex_yoy"),
    operating_income=yf_data.get("operating_income"), operating_income_prior_year=yf_data.get("operating_income_prior_year"), operating_income_yoy=yf_data.get("operating_income_yoy"),
    operating_margin=yf_data.get("operating_margin"), operating_margin_prior_year=yf_data.get("operating_margin_prior_year"), operating_margin_yoy=yf_data.get("operating_margin_yoy"),
    net_income_quarterly=yf_data.get("net_income_quarterly"), net_income_quarterly_prior_year=yf_data.get("net_income_quarterly_prior_year"), net_income_yoy=yf_data.get("net_income_yoy"),
)

report = build_earnings_deep_dive_report(
    ticker="MSFT", company="Microsoft Corporation", quarter="FY2026 Q3",
    metrics=metrics, transcript_url="https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/",
    language="en", section_analysis=section_analysis,
)

for section in report.sections:
    if section.key == "Operating Metrics":
        for row in section.table.rows:
            if "revenue" in row.label.lower():
                print(f"Revenue row: {row.cells}")
                for i, c in enumerate(row.cells):
                    if _is_placeholder(c):
                        print(f"  placeholder at idx={i}: '{c}'")
