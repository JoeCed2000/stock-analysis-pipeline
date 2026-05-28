"""
Tests for GET /api/peer-benchmark/{ticker} V2.5 endpoint.

Covers: NVDA/AAPL success, unknown ticker, partial data, no peer group,
response structure, and forbidden-label audit.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.models import PeerBenchmarkResponse

# ── V2.5 contract: response must contain these top-level keys ──
REQUIRED_RESPONSE_KEYS = [
    "ticker",
    "peer_context",
    "subject_metrics",
    "benchmarks",
    "summary",
    "warnings",
    "source",
    "status",
    "timestamp",
]

PEER_CONTEXT_KEYS = [
    "available", "group_id", "group_label",
    "sample_size", "total_peers", "status",
]

SUMMARY_KEYS = [
    "relative_valuation", "growth_support", "quality_support", "confidence",
]

# ── Forbidden word list (lowercased) ──
FORBIDDEN_WORDS = [
    "buy", "sell", "cheap", "expensive",
    "undervalued", "overvalued",
]


# ═══════════════════════════════════════════════════════════════
#  Mock data factories
# ═══════════════════════════════════════════════════════════════


def _mock_market_snapshot(ticker: str) -> dict:
    """Return a dict mimicking MarketSnapshot fields."""
    return {
        "ticker": ticker,
        "retrieved_at": "2026-05-25T12:00:00Z",
        "current_price": 150.0,
        "pe_ttm": 30.0,
        "ps_ttm": 10.0,
        "pb_ratio": 5.0,
        "market_cap": 1000000000000.0,
        "cache_state": "fresh",
    }


def _mock_valuation(ticker: str) -> dict:
    """Return a dict mimicking ValuationV2Response fields."""
    data = {
        "ticker": ticker,
        "pe_current": 30.0,
        "pe_forward": 25.0,
        "peg_ratio": 1.5,
        "enterprise_value": 1100000000000.0,
        "total_debt": 50000000000.0,
        "cash_and_equivalents": 30000000000.0,
        "source": "yfinance",
        "status": "fresh",
    }
    return data


def _mock_peers(ticker: str) -> dict:
    """Return a dict mimicking get_peers() output for a known ticker."""
    groups = {
        "NVDA": {
            "status": "available",
            "source": "curated",
            "timestamp": "2026-05-25T12:00:00Z",
            "ticker": "NVDA",
            "group_id": "ai_semiconductor",
            "group_label": "AI Semiconductor",
            "peers": ["AMD", "AVGO", "TSM", "ASML", "ARM"],
        },
        "AAPL": {
            "status": "available",
            "source": "curated",
            "timestamp": "2026-05-25T12:00:00Z",
            "ticker": "AAPL",
            "group_id": "mega_cap_consumer_tech",
            "group_label": "Mega-Cap Consumer Tech",
            "peers": ["MSFT", "GOOGL", "AMZN", "META"],
        },
    }
    if ticker in groups:
        return groups[ticker]
    return {
        "status": "unavailable",
        "source": "curated",
        "timestamp": "2026-05-25T12:00:00Z",
        "ticker": ticker,
    }


def _mock_batch_snapshot(ticker: str, partial: bool = False) -> dict:
    """Return a dict mimicking get_peer_benchmark_snapshot() output."""
    group_peers = {
        "NVDA": ["AMD", "AVGO", "TSM", "ASML", "ARM"],
        "AAPL": ["MSFT", "GOOGL", "AMZN", "META"],
    }
    group_info = {
        "NVDA": ("ai_semiconductor", "AI Semiconductor"),
        "AAPL": ("mega_cap_consumer_tech", "Mega-Cap Consumer Tech"),
    }

    if ticker not in group_peers:
        return {
            "status": "unavailable",
            "source": "curated",
            "timestamp": "2026-05-25T12:00:00Z",
            "ticker": ticker,
            "sample_size": 0,
            "total_peers": 0,
            "peers": {},
            "errors": [],
        }

    peer_list = group_peers[ticker]
    group_id, group_label = group_info[ticker]

    # Build peers with market + valuation
    peers = {}
    actual_peers = peer_list[:4] if partial else peer_list  # drop last peer for partial test
    for p in actual_peers:
        peers[p] = {
            "market": _mock_market_snapshot(p),
            "valuation": _mock_valuation(p),
        }

    errors = []
    if partial:
        missing = peer_list[4]  # ARM or META
        errors.append({"ticker": missing, "error": "RuntimeError: API timeout"})

    sample_size = len(peers)

    return {
        "status": "partial" if partial else "complete",
        "source": "curated",
        "timestamp": "2026-05-25T12:00:00Z",
        "ticker": ticker,
        "group_id": group_id,
        "group_label": group_label,
        "sample_size": sample_size,
        "total_peers": len(peer_list),
        "peers": peers,
        "errors": errors,
    }


# ═══════════════════════════════════════════════════════════════
#  1. NVDA endpoint — full data
# ═══════════════════════════════════════════════════════════════


class TestNvdaEndpoint:
    """GET /api/peer-benchmark/NVDA — full peer group available."""

    def test_nvda_endpoint(self):
        """Full peer data for NVDA returns 200 with benchmarks."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers") as mock_peers:
            with patch("backend.routes.peer_benchmark.get_market_snapshot") as mock_mkt:
                with patch("backend.routes.peer_benchmark.get_valuation") as mock_val:
                    with patch("backend.routes.peer_benchmark.get_peer_benchmark_snapshot") as mock_batch:

                        mock_peers.return_value = _mock_peers("NVDA")
                        mock_mkt.return_value = _mock_market_snapshot("NVDA")
                        mock_val.return_value = _mock_valuation("NVDA")
                        mock_batch.return_value = _mock_batch_snapshot("NVDA")

                        response = client.get("/api/peer-benchmark/NVDA")

        assert response.status_code == 200
        data = response.json()

        # ── Validate PeerBenchmarkResponse model ──
        parsed = PeerBenchmarkResponse(**data)
        assert parsed.ticker == "NVDA"

        # ── Top-level keys ──
        for key in REQUIRED_RESPONSE_KEYS:
            assert key in data, f"Missing top-level key: {key}"

        # ── Peer context ──
        ctx = data["peer_context"]
        assert ctx["available"] is True
        assert ctx["group_id"] == "ai_semiconductor"
        assert ctx["group_label"] == "AI Semiconductor"
        assert ctx["sample_size"] == 5
        assert ctx["total_peers"] == 5
        assert ctx["status"] == "available"

        # ── Subject metrics present ──
        assert "pe_ttm" in data["subject_metrics"]
        assert "ps_ttm" in data["subject_metrics"]

        # ── Benchmarks present ──
        assert len(data["benchmarks"]) > 0

        # ── Summary has all keys ──
        summary = data["summary"]
        for key in SUMMARY_KEYS:
            assert key in summary

        # ── status/source/timestamp ──
        assert data["status"] == "available"
        assert data["source"] == "curated"
        assert data["timestamp"] is not None

    def test_nvda_response_structure(self):
        """Every benchmark entry must have required sub-keys."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA"),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        data = response.json()
        for metric_name, benchmark in data["benchmarks"].items():
            assert "value" in benchmark, f"{metric_name}: missing value"
            assert "peer_median" in benchmark, f"{metric_name}: missing peer_median"
            assert "percentile_rank" in benchmark, f"{metric_name}: missing percentile_rank"
            assert "direction" in benchmark, f"{metric_name}: missing direction"
            assert "label" in benchmark, f"{metric_name}: missing label"
            assert "status" in benchmark, f"{metric_name}: missing status"


# ═══════════════════════════════════════════════════════════════
#  2. AAPL endpoint
# ═══════════════════════════════════════════════════════════════


class TestAaplEndpoint:
    """GET /api/peer-benchmark/AAPL — different peer group."""

    def test_aapl_endpoint(self):
        """AAPL returns benchmarks from mega_cap_consumer_tech group."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("AAPL")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("AAPL")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("AAPL")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("AAPL"),
                    ):
                        response = client.get("/api/peer-benchmark/AAPL")

        assert response.status_code == 200
        data = response.json()

        ctx = data["peer_context"]
        assert ctx["group_id"] == "mega_cap_consumer_tech"
        assert ctx["sample_size"] == 4
        assert ctx["total_peers"] == 4
        assert ctx["available"] is True
        assert data["ticker"] == "AAPL"


# ═══════════════════════════════════════════════════════════════
#  3. Unknown ticker
# ═══════════════════════════════════════════════════════════════


class TestUnknownTicker:
    """Ticker with no peer group returns available=false."""

    def test_unknown_ticker(self):
        """GET /api/peer-benchmark/ZZZZ returns peer_context.available=false."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("ZZZZ")):
            response = client.get("/api/peer-benchmark/ZZZZ")

        assert response.status_code == 200
        data = response.json()

        assert data["peer_context"]["available"] is False
        assert data["peer_context"]["status"] == "unavailable"
        assert data["status"] == "unavailable"

    def test_error_ticker(self):
        """Ticker with peer universe error returns available=false, status=error."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        error_peers = {
            "status": "error",
            "source": "curated",
            "timestamp": "2026-05-25T12:00:00Z",
            "ticker": "ERR",
            "errors": ["config file corrupted"],
        }

        with patch("backend.routes.peer_benchmark.get_peers", return_value=error_peers):
            response = client.get("/api/peer-benchmark/ERR")

        assert response.status_code == 200
        data = response.json()
        assert data["peer_context"]["available"] is False
        assert data["peer_context"]["status"] == "error"
        assert len(data["warnings"]) > 0


# ═══════════════════════════════════════════════════════════════
#  4. Partial peer data
# ═══════════════════════════════════════════════════════════════


class TestPartialPeerData:
    """When some peers fail, partial data with warnings is returned."""

    def test_partial_peer_data(self):
        """4/5 NVDA peers → partial status, warnings present."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA", partial=True),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        assert response.status_code == 200
        data = response.json()

        ctx = data["peer_context"]
        # 4 out of 5 peers → still available (≥2) but with warnings
        assert ctx["sample_size"] == 4
        assert ctx["total_peers"] == 5
        assert len(data["warnings"]) > 0

        # Some benchmarks should be available
        assert len(data["benchmarks"]) > 0

    def test_insufficient_peers(self):
        """1/5 peers → only 1 peer has data, not enough for benchmarks."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        batch_one = _mock_batch_snapshot("NVDA")
        batch_one["peers"] = {"AMD": batch_one["peers"]["AMD"]}
        batch_one["sample_size"] = 1
        batch_one["status"] = "partial"
        batch_one["errors"] = [
            {"ticker": "AVGO", "error": "timeout"},
            {"ticker": "TSM", "error": "timeout"},
            {"ticker": "ASML", "error": "timeout"},
            {"ticker": "ARM", "error": "timeout"},
        ]

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=batch_one,
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        assert response.status_code == 200
        data = response.json()
        assert data["peer_context"]["sample_size"] == 1
        assert data["status"] == "limited"


# ═══════════════════════════════════════════════════════════════
#  5. No peer group
# ═══════════════════════════════════════════════════════════════


class TestNoPeerGroup:
    """Ticker exists but has no configured peer group."""

    def test_no_peer_group(self):
        """GET /api/peer-benchmark/NFLX (not configured) → unavailable."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # get_peers returns unavailable
        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NFLX")):
            response = client.get("/api/peer-benchmark/NFLX")

        assert response.status_code == 200
        data = response.json()
        assert data["peer_context"]["available"] is False
        assert data["peer_context"]["status"] == "unavailable"
        assert data["status"] == "unavailable"


# ═══════════════════════════════════════════════════════════════
#  6. Response structure validation
# ═══════════════════════════════════════════════════════════════


class TestResponseStructure:
    """Validate the response schema matches PeerBenchmarkResponse."""

    def test_response_structure(self):
        """All required fields present with correct types."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA"),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        data = response.json()

        # ── PeerContext sub-structure ──
        ctx = data["peer_context"]
        assert isinstance(ctx["available"], bool)
        assert isinstance(ctx["sample_size"], int)
        assert isinstance(ctx["total_peers"], int)
        for key in PEER_CONTEXT_KEYS:
            assert key in ctx

        # ── Summary sub-structure ──
        summary = data["summary"]
        for key in SUMMARY_KEYS:
            assert key in summary
            assert isinstance(summary[key], str)

        # ── Benchmarks are dict of metric → benchmark ──
        assert isinstance(data["benchmarks"], dict)

        # ── Warnings is a list ──
        assert isinstance(data["warnings"], list)

        # ── Status is a string ──
        assert isinstance(data["status"], str)

    def test_benchmark_metric_structure(self):
        """Every benchmark metric entry follows BenchmarkPerMetric shape."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA"),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        data = response.json()
        for metric_name, b in data["benchmarks"].items():
            assert b["direction"] in ("higher_better", "lower_better", "context_only"), \
                f"{metric_name}: invalid direction {b['direction']}"
            assert b["status"] in ("available", "unavailable", "insufficient_data", "error"), \
                f"{metric_name}: invalid status {b['status']}"

    def test_unknown_ticker_structure(self):
        """Unknown ticker response still has correct structure."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("ZZZZ")):
            response = client.get("/api/peer-benchmark/ZZZZ")

        data = response.json()
        # All top-level keys must still be present
        for key in REQUIRED_RESPONSE_KEYS:
            assert key in data, f"Missing key '{key}' in unknown ticker response"


# ═══════════════════════════════════════════════════════════════
#  7. Forbidden label audit
# ═══════════════════════════════════════════════════════════════


class TestNoForbiddenLabels:
    """No forbidden words anywhere in the response."""

    def test_no_forbidden_labels(self):
        """Response must not contain buy/sell/cheap/expensive/undervalued/overvalued."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA"),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        raw = response.text.lower()
        for word in FORBIDDEN_WORDS:
            assert word not in raw, f"Forbidden word '{word}' found in response"

    def test_aapl_no_forbidden_labels(self):
        """AAPL response must also be free of forbidden labels."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("AAPL")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("AAPL")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("AAPL")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("AAPL"),
                    ):
                        response = client.get("/api/peer-benchmark/AAPL")

        raw = response.text.lower()
        for word in FORBIDDEN_WORDS:
            assert word not in raw, f"Forbidden word '{word}' found in AAPL response"

    def test_partial_data_no_forbidden_labels(self):
        """Partial peer data response still forbids labels."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA", partial=True),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        raw = response.text.lower()
        for word in FORBIDDEN_WORDS:
            assert word not in raw, f"Forbidden word '{word}' found in partial response"


# ═══════════════════════════════════════════════════════════════
#  Summary label audit
# ═══════════════════════════════════════════════════════════════


class TestSummaryLabels:
    """Summary fields must contain informative neutral labels."""

    def test_summary_not_empty_for_full_data(self):
        """Summary fields are non-empty when full data available."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=_mock_market_snapshot("NVDA")):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=_mock_valuation("NVDA")):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=_mock_batch_snapshot("NVDA"),
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        data = response.json()
        summary = data["summary"]
        assert len(summary["relative_valuation"]) > 0
        assert len(summary["confidence"]) > 0

    def test_unknown_ticker_summary_empty(self):
        """Unknown ticker has empty summary fields."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("ZZZZ")):
            response = client.get("/api/peer-benchmark/ZZZZ")

        data = response.json()
        summary = data["summary"]
        # For unavailable ticker, summary uses PeerBenchmarkSummary defaults
        assert isinstance(summary["relative_valuation"], str)
        assert isinstance(summary["confidence"], str)


# ═══════════════════════════════════════════════════════════════
#  Merge guards (null-overwrite regression)
# ═══════════════════════════════════════════════════════════════


class TestMergeGuards:
    """Route must not overwrite valid market metrics with None from valuation."""

    def test_market_pe_ttm_survives_when_valuation_pe_current_is_missing(self):
        """Regression: pe_ttm from market should not be replaced by valuation None."""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        subject_market = _mock_market_snapshot("NVDA")
        subject_market["pe_ttm"] = 32.808575
        subject_market["ps_ttm"] = 11.2

        subject_valuation = _mock_valuation("NVDA")
        subject_valuation["pe_current"] = None  # previously overwrote subject pe_ttm

        peers_batch = {
            "status": "complete",
            "source": "curated",
            "timestamp": "2026-05-25T12:00:00Z",
            "ticker": "NVDA",
            "group_id": "ai_semiconductor",
            "group_label": "AI Semiconductor",
            "sample_size": 3,
            "total_peers": 3,
            "errors": [],
            "peers": {
                "AMD": {
                    "market": {"pe_ttm": 24.1, "ps_ttm": 7.9, "pb_ratio": 3.8},
                    "valuation": {"pe_current": None, "pe_forward": 20.0, "peg_ratio": None, "total_debt": 8.0},
                },
                "AVGO": {
                    "market": {"pe_ttm": 27.3, "ps_ttm": 9.4, "pb_ratio": 4.6},
                    "valuation": {"pe_current": None, "pe_forward": 22.0, "peg_ratio": None, "total_debt": 11.0},
                },
                "TSM": {
                    "market": {"pe_ttm": 19.6, "ps_ttm": 6.1, "pb_ratio": 4.1},
                    "valuation": {"pe_current": None, "pe_forward": 17.0, "peg_ratio": None, "total_debt": 6.0},
                },
            },
        }

        with patch("backend.routes.peer_benchmark.get_peers", return_value=_mock_peers("NVDA")):
            with patch("backend.routes.peer_benchmark.get_market_snapshot", return_value=subject_market):
                with patch("backend.routes.peer_benchmark.get_valuation", return_value=subject_valuation):
                    with patch(
                        "backend.routes.peer_benchmark.get_peer_benchmark_snapshot",
                        return_value=peers_batch,
                    ):
                        response = client.get("/api/peer-benchmark/NVDA")

        assert response.status_code == 200
        data = response.json()

        # Subject keeps market P/E even if valuation pe_current is None.
        assert data["subject_metrics"]["pe_ttm"] == pytest.approx(32.808575)

        pe_ttm_benchmark = data["benchmarks"]["pe_ttm"]
        assert pe_ttm_benchmark["status"] == "available"
        assert "ticker data unavailable" not in pe_ttm_benchmark["label"].lower()

        # Summary should not degrade to a false "valuation data unavailable" for this case.
        assert "valuation data unavailable" not in data["summary"]["relative_valuation"].lower()
