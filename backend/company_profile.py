"""Company profile document generator — fills 01_official_company_sources."""
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any


def generate_company_profile(output_dir: str, ticker: str, data: Dict[str, Any]) -> str:
    """Generate a structured company profile markdown in 01_official_company_sources.
    
    Uses Finnhub profile + quote + metrics data to create a comprehensive overview.
    Returns the file path.
    """
    profile_dir = os.path.join(output_dir, "01_official_company_sources")
    os.makedirs(profile_dir, exist_ok=True)
    
    fin = data.get("financials", {})
    
    lines = []
    lines.append(f"# {data.get('company_name', ticker)} ({ticker}) — Company Profile")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Data source:** Finnhub / Yahoo Finance")
    lines.append("")
    
    # Company Overview
    lines.append("## Company Overview")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Ticker | {ticker} |")
    lines.append(f"| Company Name | {data.get('company_name', 'N/A')} |")
    lines.append(f"| Sector | {data.get('sector', 'N/A')} |")
    lines.append(f"| Industry | {data.get('industry', 'N/A')} |")
    lines.append(f"| Currency | {data.get('currency', 'N/A')} |")
    lines.append("")
    
    # Market Data
    lines.append("## Market Data")
    lines.append("")
    price = data.get("price")
    prev = data.get("prev_close")
    cap = data.get("market_cap")
    
    if price:
        lines.append(f"- **Current Price:** ${price:,.2f}")
    if prev:
        lines.append(f"- **Previous Close:** ${prev:,.2f}")
        if price and prev and prev > 0:
            change = ((price - prev) / prev) * 100
            lines.append(f"- **Change:** {change:+.2f}%")
    if cap:
        if cap >= 1e12:
            lines.append(f"- **Market Cap:** ${cap/1e12:.2f}T")
        elif cap >= 1e9:
            lines.append(f"- **Market Cap:** ${cap/1e9:.2f}B")
        else:
            lines.append(f"- **Market Cap:** ${cap/1e6:,.0f}M")
    
    high_52 = data.get("52w_high")
    low_52 = data.get("52w_low")
    if high_52 and low_52 and price:
        pct_from_high = ((price - high_52) / high_52) * 100 if high_52 > 0 else 0
        lines.append(f"- **52-Week Range:** ${low_52:,.2f} — ${high_52:,.2f}")
        lines.append(f"- **Price vs 52W High:** {pct_from_high:+.1f}%")
    lines.append("")
    
    # Financial Highlights
    lines.append("## Financial Highlights")
    lines.append("")
    
    rev_annual = fin.get("revenue_annual")
    rev_growth = fin.get("revenue_annual_growth")
    rev_q_growth = fin.get("revenue_yoy_growth")
    gm = fin.get("gross_margin")
    om = fin.get("operating_margin")
    ni = fin.get("net_income")
    fcf = fin.get("free_cash_flow")
    debt = fin.get("net_debt")
    
    if rev_annual:
        if rev_annual >= 1e9:
            lines.append(f"- **Annual Revenue:** ${rev_annual/1e9:.1f}B")
        else:
            lines.append(f"- **Annual Revenue:** ${rev_annual/1e6:,.0f}M")
    if rev_growth is not None:
        lines.append(f"- **Revenue Growth (Annual):** {rev_growth*100:+.1f}%")
    if rev_q_growth is not None:
        lines.append(f"- **Revenue Growth (YoY Q):** {rev_q_growth*100:+.1f}%")
    if gm is not None:
        lines.append(f"- **Gross Margin:** {gm*100:.1f}%")
    if om is not None:
        lines.append(f"- **Operating Margin:** {om*100:.1f}%")
    if ni:
        if abs(ni) >= 1e9:
            lines.append(f"- **Net Income:** ${ni/1e9:.1f}B")
        else:
            lines.append(f"- **Net Income:** ${ni/1e6:,.0f}M")
    if fcf:
        if abs(fcf) >= 1e9:
            lines.append(f"- **Free Cash Flow:** ${fcf/1e9:.1f}B")
        else:
            lines.append(f"- **Free Cash Flow:** ${fcf/1e6:,.0f}M")
    if debt is not None:
        if abs(debt) >= 1e9:
            lines.append(f"- **Net Debt:** ${debt/1e9:.1f}B")
        else:
            lines.append(f"- **Net Debt:** ${debt/1e6:,.0f}M")
    lines.append("")
    
    # Valuation
    lines.append("## Valuation Metrics")
    lines.append("")
    pe = data.get("pe_current")
    fpe = data.get("pe_forward")
    peg = data.get("peg_ratio")
    beta = data.get("beta")
    
    if pe:
        lines.append(f"- **P/E (Trailing):** {pe:.1f}")
    if fpe:
        lines.append(f"- **P/E (Forward):** {fpe:.1f}")
    if peg:
        lines.append(f"- **PEG Ratio:** {peg:.2f}")
    if beta:
        lines.append(f"- **Beta:** {beta:.2f}")
    lines.append("")
    
    # Business Description
    desc = data.get("description", "")
    if desc:
        lines.append("## Business Description")
        lines.append("")
        lines.append(desc[:2000])
        lines.append("")
    
    # Write file
    profile_path = os.path.join(profile_dir, f"company_profile_{ticker}.md")
    with open(profile_path, "w") as f:
        f.write("\n".join(lines))
    
    return profile_path
