"""Tests for _build_peer_benchmark() and helpers — V2.7 T5."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import sys
sys.path.insert(0, '/home/ced/codex-projects/stock-analysis-pipeline')

from backend.earnings_deep_dive.mapper import (
    _build_peer_benchmark,
    _extract_peer_subject_metrics,
    _extract_peer_valuation_metrics_from_batch,
    _compute_peer_labels,
    _safe_f,
)
from backend.earnings_deep_dive.report_model import PeerBenchmarkSection

NOW = datetime.now(timezone.utc).isoformat()

# ═══════════════════════════════════════════════════════════════════
#  _safe_f
# ═══════════════════════════════════════════════════════════════════


class TestSafeF:
    def test_valid_float(self):
        assert _safe_f(42.5) == 42.5

    def test_int(self):
        assert _safe_f(42) == 42.0

    def test_string(self):
        assert _safe_f("3.14") == 3.14

    def test_none(self):
        assert _safe_f(None) is None

    def test_invalid_string(self):
        assert _safe_f("abc") is None

    def test_nan(self):
        assert _safe_f(float("nan")) is None

    def test_inf(self):
        assert _safe_f(float("inf")) is None

    def test_neg_inf(self):
        assert _safe_f(float("-inf")) is None


# ═══════════════════════════════════════════════════════════════════
#  _extract_peer_subject_metrics
# ═══════════════════════════════════════════════════════════════════


class TestExtractPeerSubjectMetrics:
    """Extract valuation multiples from yf_info dict."""

    def test_all_fields_populated(self):
        yf = {
            "trailingPE": 33.0,
            "forwardPE": 17.5,
            "pegRatio": 0.66,
            "priceToSalesTrailing12Months": 20.5,
            "priceToBook": 45.2,
            "enterpriseToEbitda": 31.2,
            "totalDebt": 12_000_000_000,
        }
        result = _extract_peer_subject_metrics(yf, None)
        assert result["pe_ttm"] == 33.0
        assert result["pe_forward"] == 17.5
        assert result["peg_ratio"] == 0.66
        assert result["ps_ttm"] == 20.5
        assert result["pb_ratio"] == 45.2
        assert result["ev_ebitda"] == 31.2
        assert result["total_debt"] == 12_000_000_000
        assert len(result) == 7

    def test_partial_fields(self):
        yf = {"trailingPE": 25.0, "forwardPE": None}
        result = _extract_peer_subject_metrics(yf, None)
        assert result == {"pe_ttm": 25.0}

    def test_empty_yf(self):
        result = _extract_peer_subject_metrics({}, None)
        assert result == {}

    def test_nan_values_filtered(self):
        yf = {"trailingPE": float("nan"), "forwardPE": 18.0}
        result = _extract_peer_subject_metrics(yf, None)
        assert result == {"pe_forward": 18.0}

    def test_metrics_param_ignored_for_now(self):
        """metrics is reserved for quality metrics — not extracted yet."""
        yf = {"trailingPE": 30.0}
        result = _extract_peer_subject_metrics(yf, "anything")
        assert result == {"pe_ttm": 30.0}


# ═══════════════════════════════════════════════════════════════════
#  _extract_peer_valuation_metrics_from_batch
# ═══════════════════════════════════════════════════════════════════


class TestExtractPeerValuationMetricsFromBatch:
    """Extract peer metrics from a batch snapshot dict."""

    def _batch(self, peers: dict) -> dict:
        return {"peers": peers}

    def test_two_peers_full_data(self):
        batch = self._batch({
            "AMD": {
                "market": {"pe_ttm": 120.0, "ps_ttm": 8.5, "pb_ratio": 4.2},
                "valuation": {"pe_current": 115.0, "pe_forward": 25.0,
                              "peg_ratio": 1.8, "total_debt": 3_000_000_000},
            },
            "AVGO": {
                "market": {"pe_ttm": 45.0, "ps_ttm": 12.0, "pb_ratio": 8.0},
                "valuation": {"pe_current": 44.0, "pe_forward": 22.0,
                              "peg_ratio": 1.2, "total_debt": 68_000_000_000},
            },
        })
        result = _extract_peer_valuation_metrics_from_batch(batch)
        assert len(result) == 2
        # AMD: pe_current overrides market pe_ttm
        assert result["AMD"]["pe_ttm"] == 115.0
        assert result["AMD"]["pe_forward"] == 25.0
        assert result["AVGO"]["pe_ttm"] == 44.0
        assert result["AVGO"]["total_debt"] == 68_000_000_000

    def test_market_only_no_valuation(self):
        batch = self._batch({
            "TSM": {"market": {"pe_ttm": 18.0, "ps_ttm": 7.0, "pb_ratio": 5.0}},
        })
        result = _extract_peer_valuation_metrics_from_batch(batch)
        assert result["TSM"] == {"pe_ttm": 18.0, "ps_ttm": 7.0, "pb_ratio": 5.0}

    def test_valuation_only_no_market(self):
        batch = self._batch({
            "ASML": {"valuation": {"pe_current": 30.0, "pe_forward": 25.0}},
        })
        result = _extract_peer_valuation_metrics_from_batch(batch)
        assert result["ASML"] == {"pe_ttm": 30.0, "pe_forward": 25.0}

    def test_all_none_values_dropped(self):
        batch = self._batch({
            "BROKEN": {"market": {"pe_ttm": None, "ps_ttm": None}},
        })
        result = _extract_peer_valuation_metrics_from_batch(batch)
        assert "BROKEN" not in result  # No valid metrics → excluded

    def test_empty_peers(self):
        result = _extract_peer_valuation_metrics_from_batch({"peers": {}})
        assert result == {}

    def test_nan_in_peer_data(self):
        batch = self._batch({
            "AMD": {"market": {"pe_ttm": float("nan"), "ps_ttm": 8.5}},
        })
        result = _extract_peer_valuation_metrics_from_batch(batch)
        assert result["AMD"] == {"ps_ttm": 8.5}


# ═══════════════════════════════════════════════════════════════════
#  _compute_peer_labels
# ═══════════════════════════════════════════════════════════════════


class TestComputePeerLabels:
    """Aggregate benchmarks into category labels."""

    def _bm(self, status="available", label="In Line — P/E 33.0x vs peer median 28.5x"):
        return {"status": status, "label": label, "value": 33.0,
                "peer_median": 28.5, "peer_values": 5}

    def test_all_valuation_above(self):
        benchmarks = {
            "pe_ttm": self._bm(label="Above — P/E 45.0x vs peer median 25.0x"),
            "pe_forward": self._bm(label="Above — Fwd P/E 30.0x vs peer median 18.0x"),
            "ps_ttm": self._bm(label="Above — P/S 12.0x vs peer median 5.0x"),
        }
        labels = _compute_peer_labels(benchmarks)
        assert "Above Peer Median (3/3)" in labels["val_label"]
        assert labels["val_detail"] is not None
        assert "No Growth peer data" in labels["growth_label"]

    def test_all_valuation_below(self):
        benchmarks = {
            "pe_ttm": self._bm(label="Below — P/E 15.0x vs peer median 25.0x"),
            "ps_ttm": self._bm(label="Below — P/S 3.0x vs peer median 5.0x"),
        }
        labels = _compute_peer_labels(benchmarks)
        assert "Below Peer Median (2/2)" in labels["val_label"]

    def test_mixed_in_line(self):
        benchmarks = {
            "pe_ttm": self._bm(label="Above — P/E 30.0x vs peer median 28.0x"),
            "ps_ttm": self._bm(label="Below — P/S 4.0x vs peer median 5.0x"),
        }
        labels = _compute_peer_labels(benchmarks)
        assert "In Line with Peers" in labels["val_label"]

    def test_summary_includes_valuation(self):
        benchmarks = {
            "pe_ttm": self._bm(label="Above — P/E 33.0x vs peer median 28.0x"),
        }
        labels = _compute_peer_labels(benchmarks)
        assert labels["summary"] is not None
        assert "Valuation:" in labels["summary"]

    def test_empty_benchmarks(self):
        labels = _compute_peer_labels({})
        assert "No Valuation peer data" in labels["val_label"]
        assert labels["summary"] is None

    def test_insufficient_data_metrics_ignored(self):
        benchmarks = {
            "pe_ttm": self._bm(label="Above", status="available"),
            "roe": self._bm(label="N/A", status="insufficient_data"),
            "fcf_yield": self._bm(label="N/A", status="unavailable"),
        }
        labels = _compute_peer_labels(benchmarks)
        assert "Above Peer Median (1/1)" in labels["val_label"]
        assert "No Quality peer data" in labels["qual_label"]

    def test_detail_string_format(self):
        benchmarks = {
            "pe_ttm": self._bm(label="Above — P/E 33.0x vs peer median 28.5x"),
            "ps_ttm": self._bm(label="Below — P/S 5.0x vs peer median 8.0x"),
        }
        labels = _compute_peer_labels(benchmarks)
        assert labels["val_detail"] is not None
        assert "P/E" in labels["val_detail"]
        assert "P/S" in labels["val_detail"]


# ═══════════════════════════════════════════════════════════════════
#  _build_peer_benchmark — integration
# ═══════════════════════════════════════════════════════════════════


class TestBuildPeerBenchmark:
    """Integration tests for _build_peer_benchmark()."""

    def _yf_info(self, **overrides) -> dict:
        base = {
            "trailingPE": 33.0,
            "forwardPE": 17.5,
            "pegRatio": 0.66,
            "priceToSalesTrailing12Months": 20.5,
            "priceToBook": 45.2,
            "enterpriseToEbitda": 31.2,
            "totalDebt": 12_000_000_000,
        }
        base.update(overrides)
        return base

    def _mock_peers(self, *tickers: str) -> dict:
        """Build a minimal peers dict for batch mocking."""
        result = {}
        for t in tickers:
            result[t] = {
                "market": {"pe_ttm": 28.0, "ps_ttm": 10.0, "pb_ratio": 5.0},
                "valuation": {"pe_current": 27.5, "pe_forward": 20.0,
                              "peg_ratio": 1.5, "total_debt": 50_000_000_000},
            }
        return result

    def _mock_batch(self, ticker="NVDA", status="complete", sample_size=5,
                    peers=None, group_label="AI Semiconductor",
                    peer_tickers=None):
        if peers is None:
            peers = self._mock_peers("AMD", "AVGO", "TSM", "ASML", "ARM")
        if peer_tickers is None:
            peer_tickers = ["AMD", "AVGO", "TSM", "ASML", "ARM"]
        return {
            "status": status, "sample_size": sample_size,
            "total_peers": 5, "peers": peers,
            "errors": [],
            "ticker": ticker,
        }

    def _mock_peer_info(self, status="available", group_label="AI Semiconductor",
                        peers=None):
        if peers is None:
            peers = ["AMD", "AVGO", "TSM", "ASML", "ARM"]
        return {
            "status": status, "group_label": group_label,
            "group_id": "ai_semiconductor", "peers": peers,
        }

    def test_returns_empty_section_when_no_yf_info(self):
        result = _build_peer_benchmark(
            ticker="NVDA", yf_info=None, metrics=None, generated_at=NOW,
        )
        assert isinstance(result, PeerBenchmarkSection)
        assert result.peer_group is None
        assert result.relative_valuation_label is None

    def test_returns_empty_when_universe_unavailable(self):
        with patch("backend.peer_universe.get_peers") as mock_peers:
            mock_peers.return_value = {"status": "unavailable"}
            result = _build_peer_benchmark(
                ticker="ZZZZ", yf_info=self._yf_info(), metrics=None,
                generated_at=NOW,
            )
            assert result.peer_group is None
            assert result.peer_tickers == []

    def test_populates_group_and_tickers_on_success(self):
        with patch("backend.peer_universe.get_peers") as mock_peers, \
             patch("backend.peer_batch.get_peer_benchmark_snapshot") as mock_batch, \
             patch("backend.peer_benchmark.buildPeerBenchmarkSummary") as mock_engine:

            mock_peers.return_value = self._mock_peer_info()
            mock_batch.return_value = self._mock_batch()
            mock_engine.return_value = _mock_benchmark_result()

            result = _build_peer_benchmark(
                ticker="NVDA", yf_info=self._yf_info(), metrics=None,
                generated_at=NOW,
            )

            assert result.peer_group == "AI Semiconductor"
            assert "AMD" in result.peer_tickers
            assert "AVGO" in result.peer_tickers

    def test_populates_labels_from_benchmark(self):
        with patch("backend.peer_universe.get_peers") as mock_peers, \
             patch("backend.peer_batch.get_peer_benchmark_snapshot") as mock_batch, \
             patch("backend.peer_benchmark.buildPeerBenchmarkSummary") as mock_engine:

            mock_peers.return_value = self._mock_peer_info()
            mock_batch.return_value = self._mock_batch()
            mock_engine.return_value = _mock_benchmark_result()

            result = _build_peer_benchmark(
                ticker="NVDA", yf_info=self._yf_info(), metrics=None,
                generated_at=NOW,
            )

            assert result.relative_valuation_label is not None
            assert result.relative_growth_label is not None
            assert result.relative_quality_label is not None
            assert result.benchmark_summary is not None

    def test_graceful_on_batch_error(self):
        with patch("backend.peer_universe.get_peers") as mock_peers, \
             patch("backend.peer_batch.get_peer_benchmark_snapshot") as mock_batch:

            mock_peers.return_value = self._mock_peer_info()
            mock_batch.return_value = {"status": "error", "sample_size": 0,
                                       "errors": [{"ticker": "AMD", "error": "timeout"}]}

            result = _build_peer_benchmark(
                ticker="NVDA", yf_info=self._yf_info(), metrics=None,
                generated_at=NOW,
            )
            # Should return empty but valid section — no crash
            assert isinstance(result, PeerBenchmarkSection)
            assert result.relative_valuation_label is None

    def test_graceful_on_insufficient_peers(self):
        with patch("backend.peer_universe.get_peers") as mock_peers, \
             patch("backend.peer_batch.get_peer_benchmark_snapshot") as mock_batch:

            mock_peers.return_value = self._mock_peer_info(peers=["AMD"])
            mock_batch.return_value = self._mock_batch(sample_size=1,
                peers=self._mock_peers("AMD"))

            result = _build_peer_benchmark(
                ticker="NVDA", yf_info=self._yf_info(), metrics=None,
                generated_at=NOW,
            )
            assert result.relative_valuation_label is None

    def test_graceful_on_exception(self):
        with patch("backend.peer_universe.get_peers") as mock_peers:
            mock_peers.side_effect = RuntimeError("network down")

            result = _build_peer_benchmark(
                ticker="NVDA", yf_info=self._yf_info(), metrics=None,
                generated_at=NOW,
            )
            # No crash, returns empty section
            assert isinstance(result, PeerBenchmarkSection)
            assert result.currency == "USD"
            assert result.generated_at == NOW


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════


def _mock_benchmark_result() -> dict:
    """Minimal buildPeerBenchmarkSummary return value."""
    return {
        "ticker": "NVDA",
        "peer_count": 5,
        "benchmarks": {
            "pe_ttm": {
                "value": 33.0, "peer_median": 28.5,
                "peer_values": 5, "percentile_rank": 80,
                "spread_vs_median": {"ratio": 1.16, "percentage": 15.8, "absolute": 4.5},
                "direction": "lower_better",
                "label": "Above — P/E 33.0x vs peer median 28.5x",
                "status": "available",
            },
            "pe_forward": {
                "value": 17.5, "peer_median": 20.0,
                "peer_values": 5, "percentile_rank": 60,
                "spread_vs_median": {"ratio": 0.875, "percentage": -12.5, "absolute": -2.5},
                "direction": "lower_better",
                "label": "Below — Fwd P/E 17.5x vs peer median 20.0x",
                "status": "available",
            },
            "ps_ttm": {
                "value": 20.5, "peer_median": 10.0,
                "peer_values": 5, "percentile_rank": 100,
                "spread_vs_median": {"ratio": 2.05, "percentage": 105.0, "absolute": 10.5},
                "direction": "lower_better",
                "label": "Above — P/S 20.5x vs peer median 10.0x",
                "status": "available",
            },
        },
    }
