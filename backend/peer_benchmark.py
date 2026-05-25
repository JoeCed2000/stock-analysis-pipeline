"""
V2.5 Peer Benchmark Engine — Pure calculation functions.

Computes peer-relative benchmarks using curated peer universe (V2.5 T1)
and valuation multiples / growth rates from V2.3 / V2.4 context engine.

All functions are pure: zero side effects, zero network, never invent data.
All labels are neutral — no buy/sell/cheap/expensive/undervalued/overvalued.

Acceptance criteria from SA-V25-T3:
  - calculateMedian            — median correct for odd/even lists
  - calculatePercentileRank    — 0–100 percentile rank among peers
  - calculateSpreadVsMedian    — spread relative to peer median
  - getMetricDirection         — higher_better | lower_better | context_only
  - getPeerContextLabel        — neutral label, zero forbidden labels
  - buildPeerBenchmarkSummary  — aggregate all peer benchmarks
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

# ═══════════════════════════════════════════════════════════════
#  Metric direction table (V2.5 spec)
# ═══════════════════════════════════════════════════════════════

_METRIC_DIRECTION: Dict[str, str] = {
    # Growth — higher is better
    "eps_growth": "higher_better",
    "revenue_growth": "higher_better",
    "ebitda_growth": "higher_better",
    "fcf_growth": "higher_better",
    # Margins — higher is better
    "gross_margin": "higher_better",
    "operating_margin": "higher_better",
    "net_margin": "higher_better",
    # Profitability / ROIC — higher is better
    "roic": "higher_better",
    "roe": "higher_better",
    "roa": "higher_better",
    # FCF yield — higher is better
    "fcf_yield": "higher_better",
    # Debt ratios — lower is better
    "debt_to_equity": "lower_better",
    "debt_to_ebitda": "lower_better",
    "net_debt": "lower_better",
    "total_debt": "lower_better",
    # Valuation multiples — context only (no better/worse)
    "pe_ttm": "context_only",
    "ps_ttm": "context_only",
    "ev_ebitda": "context_only",
    "p_fcf": "context_only",
    "peg_ratio": "context_only",
    "pe_forward": "context_only",
    "pb_ratio": "context_only",
}

# ── Forbidden label words (lowercased for comparison) ──
_FORBIDDEN = frozenset({
    "buy", "sell", "cheap", "expensive",
    "undervalued", "overvalued",
})

# ── Minimum peer count for statistical validity ──
MIN_PEER_SAMPLE = 2


# ═══════════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════════


def _check_forbidden(label: str) -> None:
    """Raise ValueError if *label* contains a forbidden word (case-insensitive)."""
    lower = label.lower()
    for word in _FORBIDDEN:
        if word in lower:
            raise ValueError(
                f"Forbidden label detected: '{word}' found in '{label}'"
            )


def _clean_none(values: List[Optional[float]]) -> List[float]:
    """Filter out None entries from a list of optional floats."""
    return [v for v in values if v is not None]


# ═══════════════════════════════════════════════════════════════
#  Core calculation functions
# ═══════════════════════════════════════════════════════════════


def calculateMedian(values: List[float]) -> Optional[float]:
    """Compute the median of a list of numeric values.

    Returns None if the list is empty.
    Uses ``statistics.median`` which handles both odd and even lengths.
    """
    if not values:
        return None
    return statistics.median(values)


def calculatePercentileRank(
    value: float,
    peers: List[float],
) -> Optional[float]:
    """Percentile rank (0–100) of *value* among *peers*.

    Formula: (count of peers strictly less than value) / len(peers) × 100.
    0 = lowest among peers, 100 = highest.  Ties are rounded down (strict <).

    Returns None when *peers* is empty.
    """
    if not peers:
        return None
    n = len(peers)
    count_less = sum(1 for p in peers if p < value)
    return round(count_less / n * 100, 1)


def calculateSpreadVsMedian(
    value: float,
    median: float,
) -> Dict[str, Any]:
    """Spread of *value* relative to *median*.

    Returns a dict with:
      - ``ratio``: value / median (>1 = above, <1 = below)
      - ``percentage``: ((value - median) / median) × 100
      - ``absolute``: value - median
    """
    if median == 0:
        return {
            "ratio": None,
            "percentage": None,
            "absolute": value - median,
            "label": "N/A — peer median is zero",
        }

    ratio = value / median
    percentage = (value - median) / abs(median) * 100.0

    return {
        "ratio": round(ratio, 3),
        "percentage": round(percentage, 1),
        "absolute": round(value - median, 6),
    }


# ═══════════════════════════════════════════════════════════════
#  Metric direction
# ═══════════════════════════════════════════════════════════════


def getMetricDirection(metric_name: str) -> str:
    """Return the directional interpretation of *metric_name*.

    Returns one of:
      - ``"higher_better"``   — higher values are more favourable
      - ``"lower_better"``    — lower values are more favourable
      - ``"context_only"``    — no better/worse; valuation multiple, context only

    Unknown metrics default to ``"context_only"`` (conservative).
    """
    return _METRIC_DIRECTION.get(metric_name.lower(), "context_only")


# ═══════════════════════════════════════════════════════════════
#  Peer context labels
# ═══════════════════════════════════════════════════════════════


def getPeerContextLabel(
    metric_name: str,
    value: float,
    peer_median: float,
    *,
    percentile_rank: Optional[float] = None,
    _enforce: bool = True,  # test escape hatch
) -> str:
    """Build a neutral, human-readable label describing *value* relative to *peer_median*.

    Labels are direction-aware but NEVER use forbidden words.
    Acceptable phrasing per V2.5 spec:
      - "above peer median" / "below peer median"
      - "premium vs peers" (valuation multiples only)
      - "premium supported by growth" (when growth percentile also high)

    Args:
        metric_name: e.g. ``"pe_ttm"``, ``"revenue_growth"``
        value: the ticker's metric value
        peer_median: the peer group median
        percentile_rank: optional percentile rank (0–100) for enrichment
        _enforce: if True (default), raise on forbidden labels (test safety)

    Returns:
        A neutral label string.
    """
    direction = getMetricDirection(metric_name)
    above = value > peer_median
    below = value < peer_median

    if value == peer_median:
        label = f"{metric_name} matches peer median"
    elif direction == "higher_better":
        if above:
            label = f"{metric_name} above peer median"
        else:
            label = f"{metric_name} below peer median"
    elif direction == "lower_better":
        if below:
            label = f"{metric_name} below peer median"
        else:
            label = f"{metric_name} above peer median"
    else:  # context_only — intentionally neutral, no "better/worse"
        if above:
            label = f"{metric_name} trades at a premium vs peers"
        else:
            label = f"{metric_name} trades at a discount vs peers"

    # Enrich with percentile when available
    if percentile_rank is not None:
        label += f" (rank: {percentile_rank:.0f}th percentile)"

    if _enforce:
        _check_forbidden(label)

    return label


# ═══════════════════════════════════════════════════════════════
#  Full benchmark summary builder
# ═══════════════════════════════════════════════════════════════


def buildPeerBenchmarkSummary(
    ticker: str,
    ticker_metrics: Mapping[str, Optional[float]],
    peers_metrics: Mapping[str, Mapping[str, Optional[float]]],
) -> Dict[str, Any]:
    """Build a complete peer benchmark summary for *ticker*.

    Args:
        ticker: e.g. ``"NVDA"``
        ticker_metrics: dict of metric_name → float (or None if unavailable)
        peers_metrics: dict of peer_ticker → dict of metric_name → float

    Returns:
        A dict with ``ticker``, ``peer_count``, and ``benchmarks`` — a dict
        of metric_name → per-metric benchmark result.

    Each benchmark entry contains:
      - ``value``: the ticker's value for this metric
      - ``peer_median``: median of peer values
      - ``peer_values``: number of peers with data for this metric
      - ``percentile_rank``: 0–100 percentile rank
      - ``spread_vs_median``: dict with ratio, percentage, absolute
      - ``direction``: higher_better | lower_better | context_only
      - ``label``: neutral context label
      - ``status``: ``"available"`` | ``"insufficient_data"``
    """
    peer_count = len(peers_metrics)
    benchmarks: Dict[str, Dict[str, Any]] = {}

    for metric_name, ticker_value in ticker_metrics.items():
        if ticker_value is None:
            benchmarks[metric_name] = {
                "value": None,
                "peer_median": None,
                "peer_values": 0,
                "percentile_rank": None,
                "spread_vs_median": None,
                "direction": getMetricDirection(metric_name),
                "label": "N/A — ticker data unavailable",
                "status": "unavailable",
            }
            continue

        # Collect peer values for this metric
        peer_values = _clean_none(
            [peer.get(metric_name) for peer in peers_metrics.values()]
        )

        if len(peer_values) < MIN_PEER_SAMPLE:
            benchmarks[metric_name] = {
                "value": ticker_value,
                "peer_median": None,
                "peer_values": len(peer_values),
                "percentile_rank": None,
                "spread_vs_median": None,
                "direction": getMetricDirection(metric_name),
                "label": f"N/A — insufficient peer data ({len(peer_values)} peer(s))",
                "status": "insufficient_data",
            }
            continue

        median = calculateMedian(peer_values)
        # median is never None here — peer_values has ≥ MIN_PEER_SAMPLE (2) items
        if median is None:
            # Defensive: should not happen, but satisfies pyright
            benchmarks[metric_name] = {
                "value": ticker_value,
                "peer_median": None,
                "peer_values": len(peer_values),
                "percentile_rank": None,
                "spread_vs_median": None,
                "direction": getMetricDirection(metric_name),
                "label": "N/A — median calculation failed",
                "status": "error",
            }
            continue

        percentile = calculatePercentileRank(ticker_value, peer_values)
        spread = calculateSpreadVsMedian(ticker_value, median)
        label = getPeerContextLabel(
            metric_name, ticker_value, median, percentile_rank=percentile
        )

        benchmarks[metric_name] = {
            "value": ticker_value,
            "peer_median": median,
            "peer_values": len(peer_values),
            "percentile_rank": percentile,
            "spread_vs_median": spread,
            "direction": getMetricDirection(metric_name),
            "label": label,
            "status": "available",
        }

    return {
        "ticker": ticker.upper(),
        "peer_count": peer_count,
        "benchmarks": benchmarks,
    }
