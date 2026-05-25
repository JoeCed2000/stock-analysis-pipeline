"""
V2.5 Peer Benchmark API route.

GET /api/peer-benchmark/{ticker}

Fetches market + valuation data for the subject ticker and its peer group,
computes peer-relative benchmarks using the T3 pure-function engine,
and returns a structured response.  No forbidden labels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from backend.models import (
    PeerBenchmarkResponse,
    PeerContextInfo,
    PeerBenchmarkSummary,
    SpreadVsMedian,
)
from backend.peer_universe import get_peers
from backend.peer_batch import get_peer_benchmark_snapshot
from backend.market_data import get_market_snapshot
from backend.valuation import get_valuation
from backend.peer_benchmark import (
    buildPeerBenchmarkSummary,
    getMetricDirection,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["peer-benchmark"])

# ── Metrics to extract from market + valuation data sources ─────
_MARKET_METRICS = {
    "pe_ttm": "pe_ttm",
    "ps_ttm": "ps_ttm",
    "pb_ratio": "pb_ratio",
}
_VALUATION_METRICS = {
    "pe_ttm": "pe_current",
    "pe_forward": "pe_forward",
    "peg_ratio": "peg_ratio",
    "total_debt": "total_debt",
}


@router.get(
    "/api/peer-benchmark/{ticker}",
    response_model=PeerBenchmarkResponse,
)
async def get_peer_benchmark(ticker: str):
    """Return peer-relative benchmarks for *ticker*.

    Data sources: curated peer universe (T1), market snapshot + valuation
    (V2.3), peer batch layer (T2), peer benchmark engine (T3).

    Returns neutral labels — no buy/sell/cheap/expensive/undervalued/overvalued.
    """
    now = datetime.now(timezone.utc).isoformat()
    ticker = ticker.upper().strip()
    warnings: List[str] = []

    # ── 1. Peer universe check ────────────────────────────────────
    peer_info = get_peers(ticker)

    if peer_info["status"] == "unavailable":
        return PeerBenchmarkResponse(
            ticker=ticker,
            peer_context=PeerContextInfo(
                available=False,
                status="unavailable",
            ),
            source="curated",
            status="unavailable",
            timestamp=now,
        )

    if peer_info["status"] == "error":
        return PeerBenchmarkResponse(
            ticker=ticker,
            peer_context=PeerContextInfo(
                available=False,
                status="error",
            ),
            warnings=peer_info.get("errors", []),
            source="curated",
            status="error",
            timestamp=now,
        )

    group_id = peer_info.get("group_id")
    group_label = peer_info.get("group_label")
    total_peers = len(peer_info.get("peers", []))

    # ── 2. Fetch subject ticker data ──────────────────────────────
    subject_metrics: Dict[str, Optional[float]] = {}
    try:
        market_snap = get_market_snapshot(ticker)
        subject_metrics.update(_extract_from_market(market_snap))
    except Exception as exc:
        logger.warning("peer_benchmark: market data failed for %s — %s", ticker, exc)
        warnings.append(f"market_data: {_short_error(exc)}")

    try:
        valuation_resp = get_valuation(ticker)
        subject_metrics.update(_extract_from_valuation(valuation_resp))
    except Exception as exc:
        logger.warning("peer_benchmark: valuation failed for %s — %s", ticker, exc)
        warnings.append(f"valuation: {_short_error(exc)}")

    # If we have zero metrics for the subject, still try peers
    if not subject_metrics:
        warnings.append("No subject metrics available — benchmark will be limited")

    # ── 3. Fetch peer data ────────────────────────────────────────
    batch = get_peer_benchmark_snapshot(ticker)
    sample_size = batch.get("sample_size", 0)
    batch_warnings = batch.get("errors", [])

    if sample_size < 2 and total_peers >= 2:
        warnings.append(f"Only {sample_size}/{total_peers} peers available — insufficient for statistical benchmarks")
    if batch["status"] == "partial":
        warnings.append(f"Partial peer data: {sample_size}/{total_peers} peers fetched")
    if batch["status"] == "error":
        warnings.append(f"All peers failed: {batch_warnings}")

    # ── 4. Build peers_metrics from batch ─────────────────────────
    peers_metrics: Dict[str, Dict[str, Optional[float]]] = {}
    for peer_ticker, peer_data in batch.get("peers", {}).items():
        peer_metrics: Dict[str, Optional[float]] = {}
        if "market" in peer_data:
            peer_metrics.update(_extract_from_market_dict(peer_data["market"]))
        if "valuation" in peer_data:
            peer_metrics.update(_extract_from_valuation_dict(peer_data["valuation"]))
        if peer_metrics:
            peers_metrics[peer_ticker] = peer_metrics

    # ── 5. Compute benchmarks (T3 pure functions) ─────────────────
    benchmark_result = buildPeerBenchmarkSummary(ticker, subject_metrics, peers_metrics)

    # ── 6. Build summary ──────────────────────────────────────────
    summary = _build_summary(benchmark_result)

    # ── 7. Determine status ───────────────────────────────────────
    if sample_size >= 2:
        status = "available"
    elif sample_size == 1:
        status = "limited"
    else:
        status = "unavailable"

    return PeerBenchmarkResponse(
        ticker=ticker,
        peer_context=PeerContextInfo(
            available=sample_size >= 2,
            group_id=group_id,
            group_label=group_label,
            sample_size=sample_size,
            total_peers=total_peers,
            status=status,
        ),
        subject_metrics={
            k: v for k, v in subject_metrics.items() if v is not None
        },
        benchmarks=benchmark_result.get("benchmarks", {}),
        summary=summary,
        warnings=warnings,
        source="curated",
        status=status,
        timestamp=now,
    )


# ═══════════════════════════════════════════════════════════════
#  Metric extraction helpers
# ═══════════════════════════════════════════════════════════════


def _extract_from_market(model_or_dict: Any) -> Dict[str, Optional[float]]:
    """Extract metrics from a MarketSnapshot or raw dict."""
    return _extract_from_market_dict(_to_dict(model_or_dict))


def _extract_from_market_dict(data: dict) -> Dict[str, Optional[float]]:
    """Extract metrics from a market data dict."""
    result: Dict[str, Optional[float]] = {}
    for metric_key, data_key in _MARKET_METRICS.items():
        val = data.get(data_key)
        result[metric_key] = _safe_float(val)
    return result


def _extract_from_valuation(model_or_dict: Any) -> Dict[str, Optional[float]]:
    """Extract metrics from a ValuationV2Response or raw dict."""
    return _extract_from_valuation_dict(_to_dict(model_or_dict))


def _extract_from_valuation_dict(data: dict) -> Dict[str, Optional[float]]:
    """Extract metrics from a valuation data dict."""
    result: Dict[str, Optional[float]] = {}
    for metric_key, data_key in _VALUATION_METRICS.items():
        val = data.get(data_key)
        result[metric_key] = _safe_float(val)
    return result


def _to_dict(obj: Any) -> dict:
    """Safely convert a Pydantic model to dict. Returns empty dict on failure."""
    if isinstance(obj, dict):
        return obj
    try:
        return obj.model_dump()
    except AttributeError:
        try:
            return dict(obj)
        except (TypeError, ValueError):
            return {}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
#  Summary builder
# ═══════════════════════════════════════════════════════════════


def _build_summary(benchmark_result: dict) -> PeerBenchmarkSummary:
    """Aggregate benchmarks into a neutral summary.

    Groups benchmarks by category (valuation, growth, quality) and
    generates neutral labels. Confidence reflects data completeness.
    """
    benchmarks: dict = benchmark_result.get("benchmarks", {})

    # ── Category groupings ────────────────────────────────────────
    valuation_metrics = {"pe_ttm", "ps_ttm", "ev_ebitda", "p_fcf", "pe_forward", "peg_ratio"}
    growth_metrics = {"eps_growth", "revenue_growth", "ebitda_growth", "fcf_growth"}
    quality_metrics = {
        "gross_margin", "operating_margin", "net_margin",
        "roic", "roe", "roa", "fcf_yield",
        "debt_to_equity", "debt_to_ebitda", "net_debt", "total_debt",
    }

    # ── Valuation summary ─────────────────────────────────────────
    relative_valuation = _categorize_group(benchmarks, valuation_metrics, "valuation")

    # ── Growth summary ────────────────────────────────────────────
    growth_support = _categorize_group(benchmarks, growth_metrics, "growth")

    # ── Quality summary ───────────────────────────────────────────
    quality_support = _categorize_group(benchmarks, quality_metrics, "quality")

    # ── Confidence ────────────────────────────────────────────────
    available = sum(1 for b in benchmarks.values() if b.get("status") == "available")
    total = len(benchmarks)
    if total == 0:
        confidence = "no data available"
    elif available == total:
        confidence = "high"
    elif available >= total * 0.5:
        confidence = "medium"
    elif available > 0:
        confidence = "low"
    else:
        confidence = "insufficient data"

    return PeerBenchmarkSummary(
        relative_valuation=relative_valuation,
        growth_support=growth_support,
        quality_support=quality_support,
        confidence=confidence,
    )


def _categorize_group(benchmarks: dict, metric_set: set, group_name: str) -> str:
    """Generate a neutral group label from available metrics in this category."""
    relevant = {
        k: v for k, v in benchmarks.items()
        if k in metric_set and v.get("status") == "available"
    }

    if not relevant:
        return f"{group_name} data unavailable"

    above_count = 0
    below_count = 0
    at_median_count = 0

    for b in relevant.values():
        label = b.get("label", "")
        if "above" in label:
            above_count += 1
        elif "below" in label:
            below_count += 1
        elif "matches" in label:
            at_median_count += 1

    total = above_count + below_count + at_median_count

    if total == 0:
        return f"{group_name} data unavailable"

    if above_count > below_count:
        return f"{group_name} metrics predominantly above peer median ({above_count}/{total})"
    elif below_count > above_count:
        return f"{group_name} metrics predominantly below peer median ({below_count}/{total})"
    else:
        return f"{group_name} metrics mixed vs peer median ({above_count} above, {below_count} below, {at_median_count} at median)"


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════


def _safe_float(value) -> Optional[float]:
    """Convert value to float, returning None for invalid/nan/inf values."""
    if value is None:
        return None
    try:
        f = float(value)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _short_error(exc: BaseException) -> str:
    """Return a concise error string (no traceback)."""
    return f"{type(exc).__name__}: {exc}"
