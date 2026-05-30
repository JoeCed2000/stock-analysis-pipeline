"""
V2.4 Valuation Context Engine — Pure calculation functions.

Takes valuation ratios from V2.3 (valuation.py) plus growth rates
from fundamentals, and returns contextual signals — WITHOUT scoring,
recommendations, or buy/sell/cheap/expensive wording.

USD-only. No forward multiples. No analyst consensus.
All functions are pure: zero side effects, zero network, never invent data.

Growth rates are expected as decimals (0.15 = 15%), consistent with
yfinance. They are internally converted to percentage points for
ratio computations (PEG = PE / (growth% * 100)), following
industry convention.

Acceptance criteria from SA-V24-T2:
  - calculate_peg_ttm
  - calculate_sales_multiple_vs_growth
  - calculate_ev_ebitda_vs_ebitda_growth
  - calculate_price_to_fcf_vs_fcf_growth
  - calculate_fcf_yield_context
  - calculate_valuation_support
  - calculate_valuation_context_summary
"""

from typing import Dict, List, Optional

# ═══════════════════════════════════════════════════════════════
#  Thresholds
# ═══════════════════════════════════════════════════════════════

# Multiple-to-Growth ratio thresholds (PEG-like logic)
# Growth is converted from decimal to percentage points internally,
# so these thresholds work with ratios like 0.5, 1.0, 2.0, etc.
GROWTH_SUPPORT_STRONG = 1.5   # multiple/growth_pct < 1.5  → strong
GROWTH_SUPPORT_WEAK = 3.0     # multiple/growth_pct > 3.0  → weak
                               # 1.5–3.0                  → moderate

# PEG thresholds (standalone)
PEG_FAIR = 1.0                 # PEG < 1.0  → below_1
PEG_EXPENSIVE = 2.0            # PEG > 2.0  → above_2
                               # 1.0–2.0   → fair_range

# FCF Yield thresholds (decimal)
FCF_YIELD_STRONG = 0.05        # > 5%
FCF_YIELD_MODERATE = 0.02      # 2–5%
                               # < 2%      → weak


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════


def _growth_pct(growth: float) -> float:
    """Convert decimal growth (0.15) to percentage points (15.0)."""
    return growth * 100.0


# ═══════════════════════════════════════════════════════════════
#  Signal 1: PEG TTM
# ═══════════════════════════════════════════════════════════════


def calculate_peg_ttm(
    pe_ttm: Optional[float],
    eps_growth: Optional[float],
) -> Dict[str, object]:
    """PEG TTM = P/E TTM / EPS Growth.

    eps_growth as decimal (e.g. 0.08 = 8%). Internally converted
    to percentage points: PEG = PE / (growth_pct). Industry standard.

    Returns N/A if EPS growth <= 0 or unavailable.
    """
    if pe_ttm is None or eps_growth is None:
        return {"peg_ratio": None, "level": "n/a", "label": "N/A — insufficient data"}
    if eps_growth <= 0:
        return {"peg_ratio": None, "level": "n/a", "label": "N/A — EPS growth is zero or negative"}

    growth_pct = _growth_pct(eps_growth)
    peg = pe_ttm / growth_pct

    if peg < PEG_FAIR:
        level = "below_1"
        label = f"PEG {peg:.2f} — growth supports current valuation"
    elif peg <= PEG_EXPENSIVE:
        level = "fair_range"
        label = f"PEG {peg:.2f} — fairly valued relative to growth"
    else:
        level = "above_2"
        label = f"PEG {peg:.2f} — price exceeds growth support"

    return {"peg_ratio": round(peg, 2), "level": level, "label": label}


# ═══════════════════════════════════════════════════════════════
#  Generic multiple-vs-growth comparison
# ═══════════════════════════════════════════════════════════════


def _multiple_vs_growth(
    multiple: Optional[float],
    growth: Optional[float],
    multiple_name: str,
    growth_name: str,
    na_condition: bool = False,
    na_reason: str = "insufficient data",
) -> Dict[str, object]:
    """Compare a price multiple against the corresponding growth rate.

    Growth is converted from decimal to percentage points internally.
    Returns strong/moderate/weak based on multiple / growth_pct.
    """
    if multiple is None or growth is None:
        return {"ratio": None, "level": "n/a", "label": f"N/A — {na_reason}"}
    if na_condition:
        return {"ratio": None, "level": "n/a", "label": f"N/A — {na_reason}"}
    if growth <= 0:
        return {"ratio": None, "level": "n/a", "label": f"N/A — {growth_name} is zero or negative"}

    growth_pct = _growth_pct(growth)
    ratio = multiple / growth_pct

    if ratio < GROWTH_SUPPORT_STRONG:
        level = "strong"
        label = (
            f"{multiple_name}/{growth_name} {ratio:.1f}x"
            f" — growth strongly supports valuation"
        )
    elif ratio <= GROWTH_SUPPORT_WEAK:
        level = "moderate"
        label = (
            f"{multiple_name}/{growth_name} {ratio:.1f}x"
            f" — growth moderately supports valuation"
        )
    else:
        level = "weak"
        label = (
            f"{multiple_name}/{growth_name} {ratio:.1f}x"
            f" — growth weakly supports valuation"
        )

    return {"ratio": round(ratio, 1), "level": level, "label": label}


# ═══════════════════════════════════════════════════════════════
#  Signals 2–4: Multiple-vs-Growth comparisons
# ═══════════════════════════════════════════════════════════════


def calculate_sales_multiple_vs_growth(
    ps_ttm: Optional[float],
    revenue_growth: Optional[float],
) -> Dict[str, object]:
    """P/S TTM vs Revenue Growth context.

    revenue_growth as decimal (e.g. 0.12 = 12%).
    """
    return _multiple_vs_growth(ps_ttm, revenue_growth, "P/S", "Revenue Growth")


def calculate_ev_ebitda_vs_ebitda_growth(
    ev_ebitda: Optional[float],
    ebitda_growth: Optional[float],
) -> Dict[str, object]:
    """EV/EBITDA vs EBITDA Growth context.

    ebitda_growth as decimal (e.g. 0.15 = 15%).
    """
    return _multiple_vs_growth(ev_ebitda, ebitda_growth, "EV/EBITDA", "EBITDA Growth")


def calculate_price_to_fcf_vs_fcf_growth(
    p_fcf: Optional[float],
    fcf_growth: Optional[float],
) -> Dict[str, object]:
    """P/FCF vs FCF Growth context.

    Returns N/A if FCF is ≤ 0 or growth is ≤ 0.
    """
    na_condition = p_fcf is not None and p_fcf <= 0
    return _multiple_vs_growth(
        p_fcf,
        fcf_growth,
        "P/FCF",
        "FCF Growth",
        na_condition=na_condition,
        na_reason="FCF is negative or zero",
    )


# ═══════════════════════════════════════════════════════════════
#  Signal 5: FCF Yield Context
# ═══════════════════════════════════════════════════════════════


def calculate_fcf_yield_context(
    fcf_yield: Optional[float],
) -> Dict[str, object]:
    """Interpret FCF Yield as a context signal.

    fcf_yield as decimal (e.g. 0.06 = 6%).
    """
    if fcf_yield is None:
        return {
            "fcf_yield": None,
            "level": "n/a",
            "label": "N/A — FCF data unavailable",
        }
    if fcf_yield < 0:
        return {
            "fcf_yield": round(fcf_yield, 4),
            "level": "negative",
            "label": f"FCF Yield {fcf_yield:.1%} — negative, cash flow concern",
        }

    if fcf_yield > FCF_YIELD_STRONG:
        level = "strong"
        label = f"FCF Yield {fcf_yield:.1%} — strong free cash flow generation"
    elif fcf_yield >= FCF_YIELD_MODERATE:
        level = "moderate"
        label = f"FCF Yield {fcf_yield:.1%} — moderate free cash flow"
    else:
        level = "weak"
        label = (
            f"FCF Yield {fcf_yield:.1%}"
            f" — weak free cash flow relative to price"
        )

    return {"fcf_yield": round(fcf_yield, 4), "level": level, "label": label}


# ═══════════════════════════════════════════════════════════════
#  Signal 6: Valuation Support (aggregate)
# ═══════════════════════════════════════════════════════════════


def calculate_valuation_support(
    peg_signal: Optional[Dict[str, object]] = None,
    ps_vs_growth: Optional[Dict[str, object]] = None,
    ev_ebitda_vs_growth: Optional[Dict[str, object]] = None,
    p_fcf_vs_growth: Optional[Dict[str, object]] = None,
    fcf_yield_signal: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Aggregate individual context signals into support/neutral/concern counts.

    Accepts signals as keyword arguments for clarity.
    Each signal dict must have a 'level' key.
    """
    signals: List[Dict[str, object]] = [
        s
        for s in [
            peg_signal,
            ps_vs_growth,
            ev_ebitda_vs_growth,
            p_fcf_vs_growth,
            fcf_yield_signal,
        ]
        if s is not None
    ]

    support = 0
    neutral = 0
    concern = 0

    for signal in signals:
        level = signal.get("level", "n/a")
        if level in ("strong", "below_1"):
            support += 1
        elif level in ("moderate", "fair_range"):
            neutral += 1
        elif level in ("weak", "above_2", "negative"):
            concern += 1
        # "n/a" is skipped — insufficient data is not a strike

    total = support + neutral + concern

    if total == 0:
        return {
            "support": 0,
            "neutral": 0,
            "concern": 0,
            "total_signals": 0,
            "dominant": "insufficient_data",
        }

    # Dominant signal: "supportive" only when ALL signals support growth (zero concern).
    # "concerning" only when ALL non-neutral signals are concerns (zero support).
    # Any mix of support AND concern → "mixed" (the honest answer).
    if support > 0 and concern == 0:
        dominant = "supportive"
    elif concern > 0 and support == 0:
        dominant = "concerning"
    else:
        dominant = "mixed"

    return {
        "support": support,
        "neutral": neutral,
        "concern": concern,
        "total_signals": total,
        "dominant": dominant,
    }


# ═══════════════════════════════════════════════════════════════
#  Signal 7: Valuation Context Summary Card
# ═══════════════════════════════════════════════════════════════


def calculate_valuation_context_summary(
    peg_signal: Optional[Dict[str, object]] = None,
    ps_vs_growth: Optional[Dict[str, object]] = None,
    ev_ebitda_vs_growth: Optional[Dict[str, object]] = None,
    p_fcf_vs_growth: Optional[Dict[str, object]] = None,
    fcf_yield_signal: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Produce a Valuation Summary Card — context ONLY, no scoring.

    Returns:
        valuation_level: growth_supported | growth_lagging | mixed_signals
                        | insufficient_data
        valuation_level_label: human-readable description
        growth_support: strong | moderate | weak | n/a
        profitability_support: strong | moderate | weak | n/a
        cashflow_support: strong | moderate | weak | negative | n/a
        confidence: high | medium | low
        warnings: list of concern strings
        signals_available: count of signals with data
        signals_total: count of signals provided
    """
    # ── Valuation level (from aggregate) ──
    support_data = calculate_valuation_support(
        peg_signal=peg_signal,
        ps_vs_growth=ps_vs_growth,
        ev_ebitda_vs_growth=ev_ebitda_vs_growth,
        p_fcf_vs_growth=p_fcf_vs_growth,
        fcf_yield_signal=fcf_yield_signal,
    )

    dominant = support_data["dominant"]
    if dominant == "supportive":
        valuation_level = "growth_supported"
    elif dominant == "concerning":
        valuation_level = "growth_lagging"
    elif dominant == "mixed":
        valuation_level = "mixed_signals"
    else:
        valuation_level = "insufficient_data"

    # ── Growth support (P/S, EV/EBITDA, P/FCF vs growth) ──
    growth_signals = [
        s
        for s in [ps_vs_growth, ev_ebitda_vs_growth, p_fcf_vs_growth]
        if s is not None
    ]
    growth_levels = [s["level"] for s in growth_signals if s["level"] != "n/a"]

    if growth_levels:
        strong_count = sum(1 for lvl in growth_levels if lvl == "strong")
        weak_count = sum(1 for lvl in growth_levels if lvl == "weak")
        if strong_count > weak_count:
            growth_support = (
                "strong" if strong_count >= len(growth_levels) * 0.6 else "moderate"
            )
        elif weak_count > strong_count:
            growth_support = (
                "weak" if weak_count >= len(growth_levels) * 0.6 else "moderate"
            )
        else:
            growth_support = "moderate"
    else:
        growth_support = "n/a"

    # ── Profitability support (PEG = PE vs earnings growth) ──
    if peg_signal is not None and peg_signal.get("level") != "n/a":
        peg_level = peg_signal["level"]
        if peg_level == "below_1":
            profitability_support = "strong"
        elif peg_level == "fair_range":
            profitability_support = "moderate"
        else:
            profitability_support = "weak"
    else:
        profitability_support = "n/a"

    # ── Cashflow support (FCF Yield) ──
    if fcf_yield_signal is not None and fcf_yield_signal.get("level") != "n/a":
        cashflow_support = fcf_yield_signal["level"]
    else:
        cashflow_support = "n/a"

    # ── Confidence ──
    all_signals = [
        s
        for s in [
            peg_signal,
            ps_vs_growth,
            ev_ebitda_vs_growth,
            p_fcf_vs_growth,
            fcf_yield_signal,
        ]
        if s is not None
    ]
    available = sum(1 for s in all_signals if s.get("level") != "n/a")

    if available >= 4:
        confidence = "high"
    elif available >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    # ── Warnings ──
    warnings: List[str] = []

    if peg_signal is not None and peg_signal.get("level") == "above_2":
        warnings.append("PEG > 2: price significantly exceeds earnings growth")
    if ps_vs_growth is not None and ps_vs_growth.get("level") == "weak":
        warnings.append("P/S multiple is high relative to revenue growth")
    if ev_ebitda_vs_growth is not None and ev_ebitda_vs_growth.get("level") == "weak":
        warnings.append("EV/EBITDA multiple is high relative to EBITDA growth")
    if p_fcf_vs_growth is not None and p_fcf_vs_growth.get("level") == "weak":
        warnings.append("P/FCF multiple is high relative to FCF growth")
    if fcf_yield_signal is not None and fcf_yield_signal.get("level") == "negative":
        warnings.append("FCF Yield is negative — cash flow concern")
    if available < 2:
        warnings.append("Limited data — confidence is low, more data points needed")

    return {
        "valuation_level": valuation_level,
        "valuation_level_label": _VALUATION_LEVEL_LABELS.get(
            valuation_level, valuation_level
        ),
        "growth_support": growth_support,
        "profitability_support": profitability_support,
        "cashflow_support": cashflow_support,
        "confidence": confidence,
        "warnings": warnings,
        "signals_available": available,
        "signals_total": len(all_signals),
    }


_VALUATION_LEVEL_LABELS: Dict[str, str] = {
    "growth_supported": "Growth supports current valuation",
    "growth_lagging": "Valuation multiples exceed growth rates",
    "mixed_signals": "Mixed signals — some multiples supported, others not",
    "insufficient_data": "Insufficient data for valuation context",
}
