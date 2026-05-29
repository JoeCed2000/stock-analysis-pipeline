"""Company profile document generator — fills 01_official_company_sources."""
import os
import json
from datetime import datetime, timezone
from typing import Dict, Any


def generate_company_profile(
    output_dir: str,
    ticker: str,
    data: Dict[str, Any],
    company_overview: Dict[str, Any] | None = None,
) -> str:
    """Generate a structured company profile markdown in 01_official_company_sources.

    Uses Finnhub/Yahoo snapshots plus optional company_overview synthesis
    to create an investor-oriented company overview document.
    Returns the output markdown path.
    """
    profile_dir = os.path.join(output_dir, "01_official_company_sources")
    os.makedirs(profile_dir, exist_ok=True)
    
    fin = data.get("financials", {})
    overview = company_overview or {}

    def _ov_text(key: str, fallback: str = "N/A") -> str:
        val = overview.get(key)
        if val is None:
            return fallback
        if isinstance(val, str):
            txt = val.strip()
            return txt if txt else fallback
        return str(val)

    def _ov_list(key: str) -> list[str]:
        val = overview.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            out = []
            for item in val:
                if item is None:
                    continue
                txt = str(item).strip()
                if txt:
                    out.append(txt)
            return out
        if isinstance(val, str):
            txt = val.strip()
            if not txt:
                return []
            if "\n" in txt:
                return [p.strip(" -•\t") for p in txt.split("\n") if p.strip()]
            if "," in txt:
                return [p.strip() for p in txt.split(",") if p.strip()]
            return [txt]
        return [str(val)]

    def _write_bullets(title: str, items: list[str]):
        if not items:
            return
        lines.append(title)
        lines.append("")
        for item in items[:8]:
            lines.append(f"- {item}")
        lines.append("")
    
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
    desc = _ov_text("business_description", fallback="")
    if not desc:
        desc = data.get("description", "")
    if desc:
        lines.append("## Business Description")
        lines.append("")
        lines.append(desc[:3000])
        lines.append("")

    # Investor Perspective (feedback-driven checklist)
    lines.append("## Investor Perspective")
    lines.append("")

    revenue_model = _ov_text("revenue_model", fallback="")
    if revenue_model and revenue_model != "N/A":
        lines.append("### How the company makes money")
        lines.append("")
        lines.append(revenue_model)
        lines.append("")

    _write_bullets("### Business segments", _ov_list("business_segments"))
    _write_bullets("### Main growth drivers", _ov_list("growth_drivers"))
    _write_bullets("### Competitive advantages (moats)", _ov_list("moats"))
    _write_bullets("### Key metrics / KPIs", _ov_list("key_kpis"))
    _write_bullets("### Biggest business risks", _ov_list("business_risks"))

    strengths = _ov_text("strengths_vs_competitors", fallback="")
    if strengths and strengths != "N/A":
        lines.append("### Strengths vs competitors")
        lines.append("")
        lines.append(strengths)
        lines.append("")

    weaker = _ov_text("weaker_areas_vs_competitors", fallback="")
    if weaker and weaker != "N/A":
        lines.append("### Weaker areas vs competitors")
        lines.append("")
        lines.append(weaker)
        lines.append("")

    client_types = _ov_text("client_types", fallback="")
    if client_types and client_types != "N/A":
        lines.append("### Client types / end markets")
        lines.append("")
        lines.append(client_types)
        lines.append("")

    mgmt_weak = _ov_text("management_weaknesses", fallback="")
    if mgmt_weak and mgmt_weak != "N/A":
        lines.append("### Management weaknesses / governance risks")
        lines.append("")
        lines.append(mgmt_weak)
        lines.append("")

    takeaway = _ov_text("investor_takeaway", fallback="")
    if takeaway and takeaway != "N/A":
        lines.append("### Investor takeaway")
        lines.append("")
        lines.append(takeaway)
        lines.append("")

    competitors = overview.get("competitors")
    if isinstance(competitors, list) and competitors:
        lines.append("### Competitors")
        lines.append("")
        for comp in competitors[:8]:
            if not isinstance(comp, dict):
                continue
            name = (comp.get("competitor_name") or "Competitor").strip()
            text = (comp.get("text_en") or "").strip()
            adv = (comp.get("competitive_advantage") or "").strip()
            row = f"- **{name}**"
            if text:
                row += f": {text}"
            if adv:
                row += f" (Relative strength: {adv})"
            lines.append(row)
        lines.append("")

    ceo_style = _ov_text("ceo_leadership_style", fallback="")
    if ceo_style and ceo_style != "N/A":
        lines.append("### CEO leadership style")
        lines.append("")
        lines.append(ceo_style)
        lines.append("")

    long_term_vision = _ov_text("long_term_vision", fallback="")
    if long_term_vision and long_term_vision != "N/A":
        lines.append("### Long-term vision")
        lines.append("")
        lines.append(long_term_vision)
        lines.append("")
    
    # Write file
    profile_path = os.path.join(profile_dir, f"company_profile_{ticker}.md")
    with open(profile_path, "w") as f:
        f.write("\n".join(lines))
    
    return profile_path
