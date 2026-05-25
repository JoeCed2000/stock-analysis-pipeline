"""
Tests for V2.5 Peer Batch Layer (SA-V25-T2).

Covers all 6 acceptance criteria:
  1. test_batch_nvda           — NVDA batch with 5 AI semiconductor peers
  2. test_partial_success      — one peer fails, rest succeed
  3. test_rate_limit_handling  — market data returns cache_state='stale' → still works
  4. test_cache_reuse          — second call within TTL returns cached data
  5. test_empty_peer_list      — ticker with no peers → status='unavailable'
  6. test_all_peers_unavailable — every peer fetch fails → status='error'

All external calls (get_market_snapshot, get_valuation, get_peers) are
mocked so tests run offline — no network, no API keys required.
"""

import pytest
from unittest.mock import patch, MagicMock

from peer_batch import (
    get_peer_benchmark_snapshot,
    clear_benchmark_cache,
    reload_cache,
    get_cache_size,
)


# ═══════════════════════════════════════════════════════════════
#  Shared fixtures / helpers
# ═══════════════════════════════════════════════════════════════


def _make_market_snapshot(ticker: str, price: float = 150.0):
    """Return a MagicMock mimicking a MarketSnapshot Pydantic model."""
    snap = MagicMock()
    snap.model_dump.return_value = {
        "ticker": ticker,
        "retrieved_at": "2026-05-25T17:00:00Z",
        "current_price": price,
        "previous_close": price - 1.0,
        "day_change": 1.0,
        "day_change_pct": 0.67,
        "volume": 50_000_000,
        "avg_volume": 45_000_000,
        "market_cap": 2_000_000_000_000,
        "beta": 1.2,
        "high_52w": price * 1.3,
        "low_52w": price * 0.7,
        "shares_outstanding": 10_000_000_000,
        "pe_ttm": 35.0,
        "ps_ttm": 12.0,
        "pb_ratio": 25.0,
        "dividend_yield": 0.001,
        "cache_state": "fresh",
    }
    return snap


def _make_valuation_response(ticker: str, price: float = 150.0):
    """Return a MagicMock mimicking a ValuationV2Response Pydantic model."""
    val = MagicMock()
    val.model_dump.return_value = {
        "ticker": ticker,
        "exchange": "NASDAQ",
        "quote_currency": "USD",
        "display_currency": "EUR",
        "price": price,
        "price_eur": None,
        "market_cap": 2_000_000_000_000,
        "market_cap_eur": None,
        "enterprise_value": 2_100_000_000_000,
        "enterprise_value_eur": None,
        "ev_source": "computed",
        "shares_outstanding": 10_000_000_000,
        "cash_and_equivalents": 40_000_000_000,
        "total_debt": 100_000_000_000,
        "quote_timestamp": "2026-05-25T17:00:00Z",
        "fundamentals_timestamp": "2026-05-25T17:00:00Z",
        "fx_rate_eur": None,
        "fx_timestamp": None,
        "fx_status": "unavailable",
        "source": "yfinance",
        "served_from": "live",
        "status": "fresh",
    }
    return val


def _make_peer_info(ticker: str, group_id: str, group_label: str, peers: list):
    """Return a dict matching peer_universe.get_peers() output."""
    return {
        "status": "available",
        "source": "curated",
        "timestamp": "2026-05-25T17:00:00Z",
        "ticker": ticker,
        "group_id": group_id,
        "group_label": group_label,
        "peers": peers,
    }


NVDA_PEERS = ["AMD", "AVGO", "TSM", "ASML", "ARM"]
AAPL_PEERS = ["MSFT", "GOOGL", "AMZN", "META"]


# ═══════════════════════════════════════════════════════════════
#  1. test_batch_nvda — Full batch success
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_batch_nvda(mock_get_peers, mock_get_market, mock_get_val):
    """NVDA → 5 AI semiconductor peers, all fetched successfully."""
    mock_get_peers.return_value = _make_peer_info(
        "NVDA", "ai_semiconductor", "AI Semiconductor", NVDA_PEERS
    )
    mock_get_market.side_effect = lambda t: _make_market_snapshot(t)
    mock_get_val.side_effect = lambda t: _make_valuation_response(t)

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("NVDA")

    assert result["status"] == "complete"
    assert result["ticker"] == "NVDA"
    assert result["group_id"] == "ai_semiconductor"
    assert result["group_label"] == "AI Semiconductor"
    assert result["sample_size"] == 5
    assert result["total_peers"] == 5
    assert len(result["errors"]) == 0
    assert len(result["peers"]) == 5

    # Every peer should have both market and valuation data
    for ticker in NVDA_PEERS:
        assert ticker in result["peers"]
        assert "market" in result["peers"][ticker]
        assert "valuation" in result["peers"][ticker]
        assert result["peers"][ticker]["market"]["ticker"] == ticker
        assert result["peers"][ticker]["valuation"]["ticker"] == ticker

    # Verify call count — 5 peers × 2 calls each = 10
    assert mock_get_market.call_count == 5
    assert mock_get_val.call_count == 5


# ═══════════════════════════════════════════════════════════════
#  2. test_partial_success — One peer fails
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_partial_success(mock_get_peers, mock_get_market, mock_get_val):
    """One peer (TSM) fails completely → status='partial', sample_size=4."""
    mock_get_peers.return_value = _make_peer_info(
        "NVDA", "ai_semiconductor", "AI Semiconductor", NVDA_PEERS
    )

    def market_side_effect(ticker):
        if ticker == "TSM":
            raise ConnectionError("timeout connecting to yfinance")
        return _make_market_snapshot(ticker)

    def val_side_effect(ticker):
        if ticker == "TSM":
            raise ConnectionError("timeout connecting to yfinance")
        return _make_valuation_response(ticker)

    mock_get_market.side_effect = market_side_effect
    mock_get_val.side_effect = val_side_effect

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("NVDA")

    assert result["status"] == "partial"
    assert result["sample_size"] == 4
    assert result["total_peers"] == 5
    assert len(result["errors"]) == 1
    assert result["errors"][0]["ticker"] == "TSM"
    assert "ConnectionError" in result["errors"][0]["error"]

    # TSM should NOT be in peers
    assert "TSM" not in result["peers"]
    # Other 4 peers should be present
    assert "AMD" in result["peers"]
    assert "AVGO" in result["peers"]
    assert "ASML" in result["peers"]
    assert "ARM" in result["peers"]


# ═══════════════════════════════════════════════════════════════
#  3. test_rate_limit_handling — Stale cache / partial data
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_rate_limit_handling(mock_get_peers, mock_get_market, mock_get_val):
    """Peers return stale/empty data but don't crash → still partial success."""
    mock_get_peers.return_value = _make_peer_info(
        "AAPL", "mega_cap_consumer_tech", "Mega-Cap Consumer Tech", AAPL_PEERS
    )

    def market_with_rate_limit(ticker):
        snap = _make_market_snapshot(ticker)
        if ticker == "GOOGL":
            # Simulate rate-limited response — empty snapshot with cache_state='stale'
            snap.model_dump.return_value = {
                "ticker": ticker,
                "retrieved_at": "2026-05-25T17:00:00Z",
                "current_price": None,
                "previous_close": None,
                "day_change": None,
                "day_change_pct": None,
                "volume": None,
                "avg_volume": None,
                "market_cap": None,
                "beta": None,
                "high_52w": None,
                "low_52w": None,
                "shares_outstanding": None,
                "pe_ttm": None,
                "ps_ttm": None,
                "pb_ratio": None,
                "dividend_yield": None,
                "cache_state": "stale",
            }
        return snap

    mock_get_market.side_effect = market_with_rate_limit
    mock_get_val.side_effect = lambda t: _make_valuation_response(t)

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("AAPL")

    # All 4 peers should be present — GOOGL has stale market but valid valuation
    assert result["status"] == "complete"  # No peers failed entirely
    assert result["sample_size"] == 4
    assert len(result["errors"]) == 0


# ═══════════════════════════════════════════════════════════════
#  4. test_cache_reuse — Cache hit within TTL
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_cache_reuse(mock_get_peers, mock_get_market, mock_get_val):
    """Second call within TTL reuses cached data (no new network calls)."""
    mock_get_peers.return_value = _make_peer_info(
        "TSLA", "global_automotive", "Global Automotive",
        ["RIVN", "GM", "F", "TM", "BYDDF"],
    )
    mock_get_market.side_effect = lambda t: _make_market_snapshot(t)
    mock_get_val.side_effect = lambda t: _make_valuation_response(t)

    clear_benchmark_cache()

    # First call — populates cache
    result1 = get_peer_benchmark_snapshot("TSLA")
    assert result1["status"] == "complete"
    assert mock_get_market.call_count == 5
    assert mock_get_val.call_count == 5

    # Second call — should hit cache, no new calls
    result2 = get_peer_benchmark_snapshot("TSLA")
    assert result2["status"] == "complete"
    assert result2["sample_size"] == 5
    # Call counts unchanged — cache hit
    assert mock_get_market.call_count == 5
    assert mock_get_val.call_count == 5

    # Cache has 1 entry
    assert get_cache_size() == 1


# ═══════════════════════════════════════════════════════════════
#  5. test_empty_peer_list — No peers configured
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_peers")
def test_empty_peer_list(mock_get_peers):
    """Ticker with no peer group → status='unavailable', sample_size=0."""
    mock_get_peers.return_value = {
        "status": "unavailable",
        "source": "curated",
        "timestamp": "2026-05-25T17:00:00Z",
        "ticker": "ZZZZ",
    }

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("ZZZZ")

    assert result["status"] == "unavailable"
    assert result["ticker"] == "ZZZZ"
    assert result["sample_size"] == 0
    assert result["total_peers"] == 0
    assert result["peers"] == {}
    assert len(result["errors"]) == 1
    assert "no peer group configured" in result["errors"][0]["error"]


# ═══════════════════════════════════════════════════════════════
#  6. test_all_peers_unavailable — Every peer fails
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_all_peers_unavailable(mock_get_peers, mock_get_market, mock_get_val):
    """All peer fetches throw → status='error', sample_size=0."""
    mock_get_peers.return_value = _make_peer_info(
        "NVDA", "ai_semiconductor", "AI Semiconductor", NVDA_PEERS
    )
    mock_get_market.side_effect = ConnectionError("network offline")
    mock_get_val.side_effect = ConnectionError("network offline")

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("NVDA")

    assert result["status"] == "error"
    assert result["sample_size"] == 0
    assert result["total_peers"] == 5
    assert result["peers"] == {}
    assert len(result["errors"]) == 5  # One error per peer
    for err in result["errors"]:
        assert "ConnectionError" in err["error"]


# ═══════════════════════════════════════════════════════════════
#  Bonus: AAPL and TSLA batch tests
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_batch_aapl(mock_get_peers, mock_get_market, mock_get_val):
    """AAPL → 4 mega-cap consumer tech peers, all fetched."""
    mock_get_peers.return_value = _make_peer_info(
        "AAPL", "mega_cap_consumer_tech", "Mega-Cap Consumer Tech", AAPL_PEERS
    )
    mock_get_market.side_effect = lambda t: _make_market_snapshot(t)
    mock_get_val.side_effect = lambda t: _make_valuation_response(t)

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("AAPL")

    assert result["status"] == "complete"
    assert result["sample_size"] == 4
    assert result["total_peers"] == 4
    assert len(result["peers"]) == 4
    assert all(t in result["peers"] for t in AAPL_PEERS)


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_batch_tsla(mock_get_peers, mock_get_market, mock_get_val):
    """TSLA → 5 global automotive peers, all fetched."""
    tsla_peers = ["RIVN", "GM", "F", "TM", "BYDDF"]
    mock_get_peers.return_value = _make_peer_info(
        "TSLA", "global_automotive", "Global Automotive", tsla_peers
    )
    mock_get_market.side_effect = lambda t: _make_market_snapshot(t)
    mock_get_val.side_effect = lambda t: _make_valuation_response(t)

    clear_benchmark_cache()
    result = get_peer_benchmark_snapshot("TSLA")

    assert result["status"] == "complete"
    assert result["sample_size"] == 5
    assert result["total_peers"] == 5
    assert len(result["peers"]) == 5
    assert all(t in result["peers"] for t in tsla_peers)


# ═══════════════════════════════════════════════════════════════
#  Bonus: Cache bypass test
# ═══════════════════════════════════════════════════════════════


@patch("peer_batch.get_valuation")
@patch("peer_batch.get_market_snapshot")
@patch("peer_batch.get_peers")
def test_cache_bypass(mock_get_peers, mock_get_market, mock_get_val):
    """bypass_cache=True forces re-fetch even within TTL."""
    mock_get_peers.return_value = _make_peer_info(
        "NVDA", "ai_semiconductor", "AI Semiconductor", NVDA_PEERS
    )
    mock_get_market.side_effect = lambda t: _make_market_snapshot(t)
    mock_get_val.side_effect = lambda t: _make_valuation_response(t)

    clear_benchmark_cache()

    # Populate cache
    get_peer_benchmark_snapshot("NVDA")
    assert mock_get_market.call_count == 5

    # Bypass cache
    result = get_peer_benchmark_snapshot("NVDA", bypass_cache=True)
    assert result["status"] == "complete"
    assert mock_get_market.call_count == 10  # 5 more calls
    assert mock_get_val.call_count == 10
