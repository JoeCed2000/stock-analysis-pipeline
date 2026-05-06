# Financial Data Correctness — Multi-Provider Pitfalls

When aggregating financial data from multiple providers (Yahoo Finance, Finnhub, TwelveData, SEC EDGAR), **every field mapping must be verified for unit and semantic correctness**. These bugs are silent — no crash, no error log, just wrong numbers in the final report.

## Bug Class 1: Semantic Confusion (wrong field mapped)

**Pattern**: A provider field is mapped to a data model field with a similar name but different meaning.

| Provider | Field | Wrongly mapped to | Actually means |
|----------|-------|-------------------|----------------|
| TwelveData | `percent_change` | `revenue_yoy_growth` | **Price change** (daily %), not revenue growth |
| Finnhub | `revenueGrowthTTMYoy` | `guidance_official` (raw %) | Same as `revenue_annual_growth` but stored as percentage (15.3) not decimal (0.153) |

**Case study (stock-analysis-pipeline, 2026-05-05):**
```python
# sources_collector.py:331 — WRONG
"revenue_yoy_growth": change_pct,  # TwelveData percent_change = PRICE change, not revenue

# Fix:
"revenue_yoy_growth": None,  # TwelveData doesn't provide revenue growth
```

## Bug Class 2: Unit Conversion Errors (multiply vs divide)

**Pattern**: Currency or unit conversion uses the wrong arithmetic operation because the exchange rate convention is misunderstood.

**EURUSD=X in yfinance**: The ticker `EURUSD=X` returns the price of **1 EUR in USD** (e.g., 1.08). 

To convert USD → EUR: divide by the rate.
To convert EUR → USD: multiply by the rate.

```python
# WRONG — converts 100 USD to 108 EUR (should be ~92.59 EUR)
amount_usd * rate  # rate = 1.08 → 108

# CORRECT
amount_usd / rate  # rate = 1.08 → 92.59
```

**Check**: Always verify the direction with a known pair. If EURUSD=1.08, then $100 should give ~€92.59, not ~€108.

## Bug Class 3: Percentage vs Decimal (raw value not normalized)

**Pattern**: A provider returns metrics as percentages (15.3 = 15.3%) but the data model expects decimals (0.153 = 15.3%).

```python
# Finnhub returns raw percentages
metrics.get("revenueGrowthTTMYoy")  # Returns 15.3 (means 15.3%)

# Some fields use _pct_to_decimal():
revenue_annual_growth = _pct_to_decimal(metrics.get("revenueGrowthTTMYoy"))  # → 0.153 ✅

# But guidance_official was missed:
guidance_official = metrics.get("revenueGrowthTTMYoy")  # → 15.3 ❌ (should be 0.153)
```

The scorer checks `if g > 0.20` — with a raw value of 15.3, this is ALWAYS true, giving max score regardless.

**Fix**: Every Finnhub metric that represents a percentage MUST go through `_pct_to_decimal()`.

## Bug Class 4: Currency-Agnostic Conversion (EUR-on-EUR double conversion)

**Pattern**: A conversion function is called unconditionally without checking the source currency.

```python
# WRONG — converts MC.PA price from EUR to EUR (double conversion)
price_eur = convert_to_eur(price_native)

# CORRECT — only convert if source is USD
currency = yf_data.get("currency", "USD")
price_eur = convert_to_eur(price_native) if (price_native and currency == "USD") else None
```

## Audit Checklist

When code touches multiple financial data providers:

- [ ] For each field in the data model, trace back to which provider(s) supply it
- [ ] Verify the **unit** (percentage vs decimal, millions vs raw, USD vs EUR)
- [ ] Verify the **semantics** (price change ≠ revenue growth, market cap in millions ≠ raw)
- [ ] Verify conversion directions (multiply vs divide, which currency is the base)
- [ ] Check for fields that bypass normalization (raw % instead of decimal)
- [ ] Check currency-guarded conversions (don't convert EUR to EUR)
