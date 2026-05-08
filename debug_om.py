import re, sys
from pathlib import Path
sys.path.insert(0, "/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")
from backend.earnings_deep_dive.mapper import _extract_markdown_table, _rows_for_section, _enrich_codex_table, _is_placeholder
from backend.pipeline import _extract_quarterly_comparison
from backend.earnings_deep_dive.schemas import FinancialMetrics

md = Path("/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive.md").read_text()

parts = re.split(r"\n##\s+", md)
for part in parts[1:]:
    heading = part.split("\n")[0]
    if "Operating Metrics" in heading:
        content = part.split("\n", 1)[1].strip() if "\n" in part else ""
        
        result = _extract_markdown_table(content, ("Metric", "Actual", "Prior Year", "YoY", "Source"))
        if result:
            print(f"Parsed table: {len(result.rows)} rows")
            for row in result.rows:
                print(f"  {row.label}: {row.cells}")
            
            # Now enrich
            yf_data = _extract_quarterly_comparison("MSFT")
            metrics = FinancialMetrics(
                gross_profit=yf_data.get("gross_profit"),
                gross_profit_prior_year=yf_data.get("gross_profit_prior_year"),
                gross_profit_yoy=yf_data.get("gross_profit_yoy"),
                opex=yf_data.get("opex"),
                opex_prior_year=yf_data.get("opex_prior_year"),
                opex_yoy=yf_data.get("opex_yoy"),
                operating_income=yf_data.get("operating_income"),
                operating_income_prior_year=yf_data.get("operating_income_prior_year"),
                operating_income_yoy=yf_data.get("operating_income_yoy"),
                net_income_quarterly=yf_data.get("net_income_quarterly"),
                net_income_quarterly_prior_year=yf_data.get("net_income_quarterly_prior_year"),
                net_income_yoy=yf_data.get("net_income_yoy"),
            )
            
            enriched = _enrich_codex_table(
                result, "Operating Metrics",
                ("Gross profit", "Gross margin", "OpEx", "Operating income", "Operating margin", "Net income"),
                metrics
            )
            print("\nEnriched table:")
            for row in enriched.rows:
                marked = "← ENRICHED" if row.cells != next(r.cells for r in result.rows if r.label == row.label) else ""
                print(f"  {row.label}: {row.cells} {marked}")
        else:
            print("NO TABLE PARSED!")
        break
