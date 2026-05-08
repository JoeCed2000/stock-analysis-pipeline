#!/usr/bin/env python3
"""Debug enrichment issue."""
import re, sys
from pathlib import Path

sys.path.insert(0, "/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")

from backend.pipeline import _extract_quarterly_comparison
from backend.earnings_deep_dive.mapper import (
    _enrich_codex_table,
    _rows_for_section,
    _extract_markdown_table,
    _is_placeholder,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics

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
    operating_margin=yf_data.get("operating_margin"),
    operating_margin_prior_year=yf_data.get("operating_margin_prior_year"),
    operating_margin_yoy=yf_data.get("operating_margin_yoy"),
    net_income_quarterly=yf_data.get("net_income_quarterly"),
    net_income_quarterly_prior_year=yf_data.get("net_income_quarterly_prior_year"),
    net_income_yoy=yf_data.get("net_income_yoy"),
    operating_cash_flow=yf_data.get("operating_cash_flow"),
    operating_cash_flow_prior_year=yf_data.get("operating_cash_flow_prior_year"),
    free_cash_flow=yf_data.get("free_cash_flow"),
    free_cash_flow_prior_year=yf_data.get("free_cash_flow_prior_year"),
    capex=yf_data.get("capex"),
    capex_prior_year=yf_data.get("capex_prior_year"),
)

# Check attribute access
print(f"metrics.gross_profit = {getattr(metrics, 'gross_profit', 'NOT FOUND')}")
print(f"metrics.gross_profit_prior_year = {getattr(metrics, 'gross_profit_prior_year', 'NOT FOUND')}")
print(f"metrics.opex = {getattr(metrics, 'opex', 'NOT FOUND')}")

# Check _is_placeholder
print(f"\n_is_placeholder('—') = {_is_placeholder('—')}")
print(f"_is_placeholder('?') = {_is_placeholder('?')}")

# Get yfinance rows
rows = _rows_for_section("Operating Metrics", ("Gross profit", "Gross margin", "OpEx", "Operating income", "Operating margin", "Net income"), metrics)
print(f"\nyfinance Operating Metrics rows:")
for r in rows:
    print(f"  {r[0]}: {r[1:]}")

# Parse a sample LLM table
sample = """| Metric | Actual | Prior Year | YoY | Source |
|---|---|---|---|---|
| Gross Profit | — | — | — | — |
| Gross Margin | 68% | — | 減少 | (Transcript) |
| OpEx | — | — | — | — |"""
codex_table = _extract_markdown_table(sample, ("Metric", "Actual", "Prior Year", "YoY", "Source"))
print(f"\nLLM table rows:")
for row in codex_table.rows:
    print(f"  {row.label}: {row.cells}")

# Enrich
enriched = _enrich_codex_table(codex_table, "Operating Metrics", ("Gross profit", "Gross margin", "OpEx", "Operating income", "Operating margin", "Net income"), metrics)
print(f"\nEnriched table rows:")
for row in enriched.rows:
    print(f"  {row.label}: {row.cells}")
