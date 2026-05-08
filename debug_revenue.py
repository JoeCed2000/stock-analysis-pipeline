import re, sys
from pathlib import Path
sys.path.insert(0, "/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")

from backend.pipeline import _extract_quarterly_comparison
from backend.earnings_deep_dive.mapper import _enrich_codex_table, _extract_markdown_table, _rows_for_section
from backend.earnings_deep_dive.schemas import FinancialMetrics

md = Path("/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive.md").read_text()
HEADING_TO_KEY = {"🧠 Operating Metrics": "Operating Metrics"}

for part in re.split(r"\n##\s+", md)[1:]:
    heading = part.split("\n")[0]
    if "Operating Metrics" in heading:
        content = part.split("\n", 1)[1].strip()

yf_data = _extract_quarterly_comparison("MSFT")
metrics = FinancialMetrics(
    revenue_actual=yf_data.get("revenue_actual"),
    revenue_quarterly_prior_year=yf_data.get("revenue_quarterly_prior_year"),
    revenue_yoy=yf_data.get("revenue_yoy"),
    gross_profit=yf_data.get("gross_profit"),
    gross_profit_prior_year=yf_data.get("gross_profit_prior_year"),
    gross_profit_yoy=yf_data.get("gross_profit_yoy"),
)

codex_table = _extract_markdown_table(content, ("Metric","Actual","Prior Year","YoY","Source"))
print("LLM table Revenue row:")
for row in codex_table.rows:
    if 'revenue' in row.label.lower():
        print(f"  {row.label}: {row.cells}")

# Test enrichment
enriched = _enrich_codex_table(
    codex_table, "Operating Metrics",
    ("Gross profit", "Gross margin", "OpEx", "Operating income", "Operating margin", "Net income"),
    metrics
)
print("\nEnriched Revenue row:")
for row in enriched.rows:
    if 'revenue' in row.label.lower():
        print(f"  {row.label}: {row.cells}")
