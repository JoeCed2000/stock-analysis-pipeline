"""Scoring engine — 8 criteria × 5 points = /40."""
from typing import Dict, Any, Optional
from backend.models import Scoring, FinancialData, ValuationData


def score_ticker(data: Dict[str, Any], tone_data: Optional[Dict] = None) -> Scoring:
    """Compute the 8-criterion scoring from collected data.
    If tone_data is provided from 10-K analysis, uses real management tone."""
    fin = data.get("financials", {})
    val = data.get("valuation", {})

    # 1. Growth (0-5)
    growth = _score_growth(fin.get("revenue_yoy_growth"), fin.get("revenue_annual_growth"))

    # 2. Profitability (0-5)
    profitability = _score_profitability(fin.get("gross_margin"), fin.get("operating_margin"))

    # 3. Financial strength (0-5)
    financial_strength = _score_financial_strength(fin.get("net_debt"), fin.get("free_cash_flow"), fin.get("net_income"))

    # 4. Moat (0-5)
    moat = _score_moat(data.get("sector"), data.get("market_cap"), fin.get("gross_margin"))

    # 5. Management (0-5) — use tone data if available, else guidance
    management = _score_management_realtime(tone_data) if tone_data else _score_management(fin.get("guidance_official"), fin.get("revenue_yoy_growth"), fin.get("revenue_annual_growth"))

    # 6. Valuation risk (0-5)
    valuation_risk = _score_valuation(val.get("pe_current"), val.get("pe_forward"), val.get("peg_ratio"))

    # 7. Geopolitical risk (0-5)
    geopolitical_risk = _score_geopolitical(data.get("sector"), data.get("industry"))

    # 8. Business momentum (0-5)
    business_momentum = _score_momentum(fin.get("revenue_yoy_growth"), data.get("price"), data.get("52w_high"))

    return Scoring(
        growth=growth,
        profitability=profitability,
        financial_strength=financial_strength,
        moat=moat,
        management=management,
        valuation_risk=valuation_risk,
        geopolitical_risk=geopolitical_risk,
        business_momentum=business_momentum,
    )


def _score_growth(yoy: Any, annual: Any) -> int:
    """Score growth: 5=exceptional (>50%), 4=strong (>25%), 3=good (>10%), 2=modest (>0%), 1=flat/negative."""
    if yoy is None and annual is None:
        return 2  # unknown → neutral
    best = max(yoy or 0, annual or 0)
    if best > 0.50:
        return 5
    if best > 0.25:
        return 4
    if best > 0.10:
        return 3
    if best > 0:
        return 2
    return 1


def _score_profitability(gross: Any, operating: Any) -> int:
    """Score profitability based on margins."""
    op = operating or 0
    if op > 0.30:
        return 5
    if op > 0.20:
        return 4
    if op > 0.10:
        return 3
    if op > 0:
        return 2
    if gross is not None and gross > 0:
        return 2
    return 1


def _score_financial_strength(net_debt: Any, fcf: Any, net_income: Any) -> int:
    """Score balance sheet health."""
    score = 3  # default neutral
    if fcf is not None and fcf > 0:
        score += 1  # positive FCF
    if net_income is not None and net_income > 0:
        score += 1  # profitable
    if net_debt is not None:
        if net_debt < 0:
            score += 1  # net cash
        elif fcf is not None and fcf > 0 and abs(net_debt) / fcf < 3:
            pass  # manageable debt, keep score
        elif fcf is not None and net_debt > 0:
            score -= 1  # heavy debt
    return max(1, min(5, score))


def _score_management_realtime(tone: Dict) -> int:
    """Score management based on real 10-K tone analysis."""
    if not tone:
        return 3
    score = 3
    t = tone.get("tone", "").lower()
    conf = tone.get("confidence", "").lower()
    vis = tone.get("visibility", "").lower()
    promises = tone.get("concrete_promises", [])
    defensive = tone.get("defensive_signals", [])

    if "optimistic" in t or "confident" in t or "optimiste" in t or "confiant" in t:
        score += 1
    if "high" in conf or "strong" in conf or "élevée" in conf:
        score += 1
    elif "low" in conf or "faible" in conf:
        score -= 1
    if "good" in vis or "bonne" in vis or "clear" in vis:
        score += 1
    elif "low" in vis or "faible" in vis or "poor" in vis:
        score -= 1
    if len(promises) >= 3:
        score += 1
    if len(defensive) >= 5:
        score -= 1

    return max(1, min(5, score))


def _score_moat(sector: Any, market_cap: Any, gross_margin: Any) -> int:
    """Score competitive moat — crude heuristic."""
    score = 3  # default
    gm = gross_margin or 0
    if gm > 0.60:
        score += 1  # high gross margin → pricing power
    if gm > 0.40:
        score += 0  # decent
    if market_cap is not None and market_cap > 1e12:
        score += 1  # mega-cap → scale moat
    elif market_cap is not None and market_cap > 1e11:
        score += 0  # large-cap
    sector_str = str(sector or "").lower()
    if "technology" in sector_str or "software" in sector_str:
        score += 0  # tech moats are fragile, don't bonus
    return max(1, min(5, score))


def _score_management(guidance: Any, yoy: Any, annual: Any) -> int:
    """Score management quality — rough from available data."""
    if guidance is None:
        return 3  # unknown
    try:
        g = float(guidance)
        if g > 0.20:
            return 4
        if g > 0.05:
            return 3
        return 2
    except (TypeError, ValueError):
        return 3


def _score_valuation(pe: Any, fpe: Any, peg: Any) -> int:
    """Score valuation: 5=cheap, 1=expensive."""
    # Use forward PE if available, else trailing
    pe_val = fpe if fpe is not None else pe
    if pe_val is None:
        return 3  # unknown
    if pe_val < 15:
        return 5
    if pe_val < 20:
        return 4
    if pe_val < 30:
        return 3
    if pe_val < 45:
        return 2
    return 1


def _score_geopolitical(sector: Any, industry: Any) -> int:
    """Score geopolitical risk: 5=low risk, 1=high risk."""
    sector_str = str(sector or "").lower()
    industry_str = str(industry or "").lower()
    risk_keywords = ["china", "semiconductor", "defense", "energy", "oil", "gas",
                      "mining", "metals", "rare earth", "telecom"]
    low_risk_keywords = ["software", "services", "retail", "consumer", "insurance",
                          "real estate", "healthcare"]

    for kw in risk_keywords:
        if kw in sector_str or kw in industry_str:
            return 2  # elevated geopolitical risk

    for kw in low_risk_keywords:
        if kw in sector_str or kw in industry_str:
            return 4  # lower risk

    return 3  # neutral


def _score_momentum(yoy: Any, price: Any, high_52w: Any) -> int:
    """Score business momentum."""
    score = 3
    if yoy is not None:
        if yoy > 0.30:
            score += 1
        elif yoy < 0:
            score -= 1
    if price is not None and high_52w is not None and high_52w > 0:
        pct_off_high = (high_52w - price) / high_52w
        if pct_off_high < 0.05:
            score += 1  # near highs
        elif pct_off_high > 0.20:
            score -= 1  # well off highs
    return max(1, min(5, score))
