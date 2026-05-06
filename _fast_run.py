"""Fast pipeline — core analysis only, no dossier generation.
Returns decision + score for each ticker in under 60s total."""
import os, sys, json, logging
logging.basicConfig(level=logging.WARNING)  # suppress info logs

env_path = os.path.join(os.path.dirname(__file__), ".env")
with open(env_path) as f:
    for line in f:
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.strip().split("=", 1)
            os.environ[k] = v

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from zoneinfo import ZoneInfo
PARIS = ZoneInfo("Europe/Paris")

from backend.models import (
    AnalysisResult, FinancialData, SegmentInfo, ManagementTone,
    RiskItem, ValuationData, Scoring, Source, Claim
)
from backend.sources_collector import get_stock_data
from backend.scorer import score_ticker

def fast_core(ticker: str) -> dict:
    """Return only the core scoring result — no dossier, no deep dive."""
    yf_data = get_stock_data(ticker)
    company_name = yf_data.get("company_name", ticker)
    price_native = yf_data.get("price")
    currency = yf_data.get("currency", "USD")
    fin = yf_data.get("financials", {})

    # Enrich with EDGAR XBRL
    try:
        from backend.sources_collector import get_edgar_financials
        edgar = get_edgar_financials(ticker)
        if edgar:
            for attr, edgar_key in [("revenue_annual","revenue"),("net_income","net_income"),("free_cash_flow","free_cash_flow")]:
                if (fin.get(attr) is None or fin.get(attr) == 0) and edgar.get(edgar_key) is not None:
                    fin[attr] = edgar[edgar_key]
            if (fin.get("operating_margin") is None or fin.get("operating_margin") == 0):
                rev = edgar.get("revenue")
                op_inc = edgar.get("operating_income")
                if rev and op_inc and rev > 0:
                    fin["operating_margin"] = round(op_inc / rev, 4)
    except Exception:
        pass

    # Management analysis via Codex (with timeout safeguard)
    tone_data = None
    try:
        from backend.sources_collector import extract_10k_sections
        from backend.codex_provider import codex_analyze_management
        sec_10k = extract_10k_sections(ticker, output_dir="/tmp")
        mda_text = sec_10k.get("mda", "")
        risk_text = sec_10k.get("risk_factors", "")
        if len(mda_text) > 500:
            tone_data = codex_analyze_management(mda_text, risk_text)
    except Exception:
        pass

    # Risks from data
    risks = []
    sector = str(yf_data.get("sector", "")).lower()
    if "technology" in sector or "semiconductor" in str(yf_data.get("industry","")).lower():
        risks.append(RiskItem(category="Sector", description="Tech/semiconductor cyclicality risk", severity="medium", source="Yahoo Finance"))
    if yf_data.get("market_cap") and yf_data.get("market_cap", 0) > 5e11:
        risks.append(RiskItem(category="Size", description="Mega-cap → growth harder to sustain", severity="low", source="Market cap analysis"))
    nd = fin.get("net_debt")
    if nd is not None and nd > 1e10:
        risks.append(RiskItem(category="Financial", description=f"Significant net debt ({nd/1e9:.1f}B)", severity="medium", source="Yahoo Finance balance sheet"))
    if tone_data and tone_data.get("risks"):
        risks = tone_data.get("risks") + risks

    scoring = score_ticker({
        "financials": fin,
        "valuation": {"pe_current": yf_data.get("pe_current"), "pe_forward": yf_data.get("pe_forward"), "peg_ratio": yf_data.get("peg_ratio")},
        "sector": yf_data.get("sector"),
        "industry": yf_data.get("industry"),
        "market_cap": yf_data.get("market_cap"),
        "price": yf_data.get("price"),
        "52w_high": yf_data.get("52w_high"),
    }, tone_data=tone_data)

    decision = scoring.decision()
    total = scoring.total

    # Conviction
    if total >= 32:
        conviction = "High"
    elif total >= 26:
        conviction = "Moderate"
    else:
        conviction = "Low"

    return {
        "ticker": ticker,
        "company": company_name,
        "decision": decision,
        "score": total,
        "conviction": conviction,
        "price": price_native,
        "currency": currency,
    }

# Run all tickers
TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "ASML", "MC.PA"]
results = []
errors = []

for t in TICKERS:
    try:
        r = fast_core(t)
        results.append(r)
        print(f"RESULT|{t}|{r['decision']}|{r['score']}/40|{r['conviction']}|{r['company']}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors.append((t, str(e)))
        print(f"RESULT|{t}|ERROR|0/40|N/A|{e}")

if errors:
    print(f"\n{len(errors)} errors: {[e[0] for e in errors]}")
print(f"\nDONE: {len(results)}/{len(TICKERS)} tickers analyzed.")
