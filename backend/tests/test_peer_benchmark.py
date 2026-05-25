"""
Tests for V2.5 Peer Benchmark Engine.

Covers all 10 acceptance criteria from SA-V25-T3:
  1. test_median_odd           — median of odd-length list
  2. test_median_even          — median of even-length list
  3. test_percentile           — percentile rank calculation
  4. test_rank                 — rank edge cases (lowest, highest, tie)
  5. test_spread_vs_median     — spread ratio + percentage
  6. test_insufficient_sample  — <2 peers → N/A
  7. test_growth_direction     — growth → higher_better
  8. test_valuation_direction  — valuation → context_only
  9. test_debt_direction       — debt → lower_better
  10. test_forbidden_labels_absent — no buy/sell/cheap/expensive/undervalued/overvalued
"""

import pytest
from peer_benchmark import (
    calculateMedian,
    calculatePercentileRank,
    calculateSpreadVsMedian,
    getMetricDirection,
    getPeerContextLabel,
    buildPeerBenchmarkSummary,
    _check_forbidden,
)


# ═══════════════════════════════════════════════════════════════
#  1. Median — odd-length list
# ═══════════════════════════════════════════════════════════════

class TestMedianOdd:
    def test_three_elements(self):
        """Median of [10, 30, 20] → 20."""
        assert calculateMedian([10.0, 30.0, 20.0]) == 20.0

    def test_five_elements(self):
        """Median of [5, 3, 7, 1, 9] → 5."""
        assert calculateMedian([5.0, 3.0, 7.0, 1.0, 9.0]) == 5.0

    def test_single_element(self):
        """Median of [42.0] → 42.0."""
        assert calculateMedian([42.0]) == 42.0

    def test_unsorted_input(self):
        """Unsorted input [100, 50, 75] → 75 (sort invariant)."""
        assert calculateMedian([100.0, 50.0, 75.0]) == 75.0


# ═══════════════════════════════════════════════════════════════
#  2. Median — even-length list
# ═══════════════════════════════════════════════════════════════

class TestMedianEven:
    def test_two_elements(self):
        """Median of [10, 30] → 20.0 (average)."""
        assert calculateMedian([10.0, 30.0]) == 20.0

    def test_four_elements(self):
        """Median of [2, 4, 6, 8] → 5.0."""
        assert calculateMedian([2.0, 4.0, 6.0, 8.0]) == 5.0

    def test_six_elements(self):
        """Median of [1, 2, 3, 4, 5, 6] → 3.5."""
        assert calculateMedian([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]) == 3.5

    def test_float_result(self):
        """Median of [1, 2, 100, 200] → 51.0."""
        assert calculateMedian([1.0, 2.0, 100.0, 200.0]) == 51.0


# ═══════════════════════════════════════════════════════════════
#  Common fixture: empty-list median
# ═══════════════════════════════════════════════════════════════

def test_median_empty_list():
    """Empty list returns None."""
    assert calculateMedian([]) is None


# ═══════════════════════════════════════════════════════════════
#  3. Percentile rank
# ═══════════════════════════════════════════════════════════════

class TestPercentileRank:
    def test_middle_of_pack(self):
        """Value 50 among [10, 30, 50, 70, 90] → 40th percentile (2/5)."""
        result = calculatePercentileRank(50.0, [10.0, 30.0, 50.0, 70.0, 90.0])
        assert result == 40.0  # 2 peers strictly below 50

    def test_highest(self):
        """Value 100 among [10, 30, 50] → 100th percentile."""
        result = calculatePercentileRank(100.0, [10.0, 30.0, 50.0])
        assert result == 100.0

    def test_lowest(self):
        """Value 0 among [10, 30, 50] → 0th percentile."""
        result = calculatePercentileRank(0.0, [10.0, 30.0, 50.0])
        assert result == 0.0

    def test_tie(self):
        """Value 30 among [10, 30, 30, 50] → 25th percentile (tie = strict <)."""
        result = calculatePercentileRank(30.0, [10.0, 30.0, 30.0, 50.0])
        assert result == 25.0  # only 10.0 is strictly less

    def test_empty_peers(self):
        """Empty peers list → None."""
        assert calculatePercentileRank(50.0, []) is None


# ═══════════════════════════════════════════════════════════════
#  4. Rank edge cases  (combined with percentile above, adding
#     spread validation here)
# ═══════════════════════════════════════════════════════════════

class TestRankSpread:
    def test_best_in_class_rank(self):
        """NVDA 85% growth vs peers [15, 20, 25, 30, 35] → 100th percentile."""
        result = calculatePercentileRank(85.0, [15.0, 20.0, 25.0, 30.0, 35.0])
        assert result == 100.0

    def test_worst_in_class_rank(self):
        """5% growth vs peers [15, 20, 25] → 0th percentile."""
        result = calculatePercentileRank(5.0, [15.0, 20.0, 25.0])
        assert result == 0.0


# ═══════════════════════════════════════════════════════════════
#  5. Spread vs median
# ═══════════════════════════════════════════════════════════════

class TestSpreadVsMedian:
    def test_above_median(self):
        """Value 30, median 20 → ratio 1.5, percentage +50%."""
        result = calculateSpreadVsMedian(30.0, 20.0)
        assert result["ratio"] == 1.5
        assert result["percentage"] == 50.0
        assert result["absolute"] == 10.0

    def test_below_median(self):
        """Value 10, median 20 → ratio 0.5, percentage -50%."""
        result = calculateSpreadVsMedian(10.0, 20.0)
        assert result["ratio"] == 0.5
        assert result["percentage"] == -50.0
        assert result["absolute"] == -10.0

    def test_equal_to_median(self):
        """Value 42, median 42 → ratio 1.0, percentage 0%."""
        result = calculateSpreadVsMedian(42.0, 42.0)
        assert result["ratio"] == 1.0
        assert result["percentage"] == 0.0
        assert result["absolute"] == 0.0

    def test_zero_median(self):
        """Median zero → ratio/percentage are None, graceful fallback."""
        result = calculateSpreadVsMedian(15.0, 0.0)
        assert result["ratio"] is None
        assert result["percentage"] is None
        assert result["absolute"] == 15.0
        assert "zero" in result["label"].lower()

    def test_negative_median(self):
        """Value -5, median -10 → ratio 0.5, percentage +50%."""
        result = calculateSpreadVsMedian(-5.0, -10.0)
        assert result["ratio"] == 0.5
        assert result["percentage"] == 50.0
        assert result["absolute"] == 5.0


# ═══════════════════════════════════════════════════════════════
#  6. Insufficient sample
# ═══════════════════════════════════════════════════════════════

class TestInsufficientSample:
    def test_zero_peers(self):
        """Zero peers → all metrics marked insufficient_data."""
        summary = buildPeerBenchmarkSummary(
            "SOLO",
            {"revenue_growth": 15.0},
            {},  # no peers
        )
        assert summary["ticker"] == "SOLO"
        assert summary["peer_count"] == 0
        bench = summary["benchmarks"]["revenue_growth"]
        assert bench["status"] == "insufficient_data"
        assert bench["peer_values"] == 0
        assert "insufficient" in bench["label"].lower()

    def test_one_peer(self):
        """1 peer is below MIN_PEER_SAMPLE (2) → insufficient_data."""
        summary = buildPeerBenchmarkSummary(
            "ALONE",
            {"pe_ttm": 25.0},
            {"PEER1": {"pe_ttm": 30.0}},
        )
        bench = summary["benchmarks"]["pe_ttm"]
        assert bench["status"] == "insufficient_data"
        assert bench["peer_values"] == 1
        assert bench["peer_median"] is None

    def test_null_ticker_value(self):
        """Ticker metric is None → unavailable, not insufficient."""
        summary = buildPeerBenchmarkSummary(
            "NONE",
            {"pe_ttm": None},
            {"P1": {"pe_ttm": 20.0}, "P2": {"pe_ttm": 25.0}},
        )
        bench = summary["benchmarks"]["pe_ttm"]
        assert bench["status"] == "unavailable"
        assert bench["value"] is None


# ═══════════════════════════════════════════════════════════════
#  7. Growth direction
# ═══════════════════════════════════════════════════════════════

class TestGrowthDirection:
    def test_revenue_growth(self):
        assert getMetricDirection("revenue_growth") == "higher_better"

    def test_eps_growth(self):
        assert getMetricDirection("eps_growth") == "higher_better"

    def test_ebitda_growth(self):
        assert getMetricDirection("ebitda_growth") == "higher_better"

    def test_fcf_growth(self):
        assert getMetricDirection("fcf_growth") == "higher_better"

    def test_roic(self):
        assert getMetricDirection("roic") == "higher_better"

    def test_fcf_yield(self):
        assert getMetricDirection("fcf_yield") == "higher_better"

    def test_gross_margin(self):
        assert getMetricDirection("gross_margin") == "higher_better"

    def test_unknown_metric_defaults_context_only(self):
        """Unknown metrics default to context_only (conservative)."""
        assert getMetricDirection("some_future_metric") == "context_only"


# ═══════════════════════════════════════════════════════════════
#  8. Valuation direction
# ═══════════════════════════════════════════════════════════════

class TestValuationDirection:
    def test_pe_ttm_context_only(self):
        assert getMetricDirection("pe_ttm") == "context_only"

    def test_ps_ttm_context_only(self):
        assert getMetricDirection("ps_ttm") == "context_only"

    def test_ev_ebitda_context_only(self):
        assert getMetricDirection("ev_ebitda") == "context_only"

    def test_p_fcf_context_only(self):
        assert getMetricDirection("p_fcf") == "context_only"

    def test_peg_ratio_context_only(self):
        assert getMetricDirection("peg_ratio") == "context_only"

    def test_case_insensitive(self):
        assert getMetricDirection("PE_TTM") == "context_only"
        assert getMetricDirection("Revenue_Growth") == "higher_better"


# ═══════════════════════════════════════════════════════════════
#  9. Debt direction
# ═══════════════════════════════════════════════════════════════

class TestDebtDirection:
    def test_debt_to_equity(self):
        assert getMetricDirection("debt_to_equity") == "lower_better"

    def test_debt_to_ebitda(self):
        assert getMetricDirection("debt_to_ebitda") == "lower_better"

    def test_net_debt(self):
        assert getMetricDirection("net_debt") == "lower_better"

    def test_total_debt(self):
        assert getMetricDirection("total_debt") == "lower_better"


# ═══════════════════════════════════════════════════════════════
#  10. Forbidden labels absent
# ═══════════════════════════════════════════════════════════════

class TestForbiddenLabelsAbsent:
    FORBIDDEN = {"buy", "sell", "cheap", "expensive", "undervalued", "overvalued"}

    def _has_forbidden(self, label: str) -> bool:
        lower = label.lower()
        return any(word in lower for word in self.FORBIDDEN)

    def test_context_labels_no_forbidden(self):
        """Every label from getPeerContextLabel is forbidden-free."""
        cases = [
            # (metric, value, median, direction_expected)
            ("revenue_growth", 25.0, 15.0),      # above, higher_better
            ("revenue_growth", 5.0, 15.0),       # below, higher_better
            ("debt_to_equity", 0.3, 0.8),        # below, lower_better
            ("debt_to_equity", 1.5, 0.8),        # above, lower_better
            ("pe_ttm", 35.0, 25.0),              # above, context_only
            ("pe_ttm", 15.0, 25.0),              # below, context_only
            ("gross_margin", 60.0, 50.0),
            ("fcf_yield", 0.07, 0.04),
            ("net_debt", 100.0, 500.0),
        ]
        for metric, value, median in cases:
            label = getPeerContextLabel(metric, value, median)
            assert not self._has_forbidden(label), (
                f"Forbidden word in label: {label!r}"
            )

    def test_forbidden_labels_raise(self):
        """Labels containing forbidden words raise ValueError."""
        with pytest.raises(ValueError, match="buy"):
            _check_forbidden("value: buy recommendation")
        with pytest.raises(ValueError, match="cheap"):
            _check_forbidden("something cheap")

    def test_valid_labels_pass_check(self):
        """Clean labels do not raise."""
        _check_forbidden("above peer median")
        _check_forbidden("trades at a premium vs peers")
        _check_forbidden("below peer median")

    def test_build_summary_labels_clean(self):
        """Full buildPeerBenchmarkSummary output is forbidden-free."""
        ticker_metrics = {
            "pe_ttm": 35.0,
            "revenue_growth": 25.0,
            "debt_to_equity": 0.3,
            "gross_margin": 60.0,
            "fcf_yield": 0.07,
        }
        peers_metrics = {
            "P1": {"pe_ttm": 20.0, "revenue_growth": 15.0, "debt_to_equity": 0.8,
                   "gross_margin": 55.0, "fcf_yield": 0.05},
            "P2": {"pe_ttm": 25.0, "revenue_growth": 12.0, "debt_to_equity": 0.5,
                   "gross_margin": 50.0, "fcf_yield": 0.03},
            "P3": {"pe_ttm": 30.0, "revenue_growth": 18.0, "debt_to_equity": 0.6,
                   "gross_margin": 52.0, "fcf_yield": 0.04},
        }

        summary = buildPeerBenchmarkSummary("TEST", ticker_metrics, peers_metrics)

        for metric, bench in summary["benchmarks"].items():
            label = bench.get("label", "")
            assert not self._has_forbidden(label), (
                f"Forbidden in {metric} label: {label!r}"
            )


# ═══════════════════════════════════════════════════════════════
#  Integration: realistic NVDA scenario
# ═══════════════════════════════════════════════════════════════

class TestRealisticNVDA:
    def test_nvda_vs_ai_semiconductor_peers(self):
        """NVDA metrics vs AMD, AVGO, TSM, ASML, ARM — full benchmark."""
        nvda = {
            "pe_ttm": 45.0,
            "revenue_growth": 78.0,
            "gross_margin": 75.0,
            "fcf_yield": 0.02,
            "debt_to_equity": 0.15,
        }
        peers = {
            "AMD":  {"pe_ttm": 35.0, "revenue_growth": 15.0, "gross_margin": 52.0,
                     "fcf_yield": 0.04, "debt_to_equity": 0.05},
            "AVGO": {"pe_ttm": 28.0, "revenue_growth": 25.0, "gross_margin": 65.0,
                     "fcf_yield": 0.06, "debt_to_equity": 0.50},
            "TSM":  {"pe_ttm": 18.0, "revenue_growth": 30.0, "gross_margin": 55.0,
                     "fcf_yield": 0.05, "debt_to_equity": 0.30},
            "ASML": {"pe_ttm": 33.0, "revenue_growth": 20.0, "gross_margin": 52.0,
                     "fcf_yield": 0.03, "debt_to_equity": 0.20},
            "ARM":  {"pe_ttm": 85.0, "revenue_growth": 35.0, "gross_margin": 95.0,
                     "fcf_yield": 0.01, "debt_to_equity": 0.02},
        }

        summary = buildPeerBenchmarkSummary("NVDA", nvda, peers)

        assert summary["ticker"] == "NVDA"
        assert summary["peer_count"] == 5

        # Revenue growth — NVDA should be 100th percentile (78% >> peers)
        rg = summary["benchmarks"]["revenue_growth"]
        assert rg["status"] == "available"
        assert rg["percentile_rank"] == 100.0
        assert rg["direction"] == "higher_better"
        assert "above" in rg["label"].lower()

        # Gross margin — NVDA at 75% vs peers [52, 52, 55, 65, 95] → rank = 80%
        gm = summary["benchmarks"]["gross_margin"]
        assert gm["status"] == "available"
        assert gm["percentile_rank"] == 80.0  # 4 of 5 peers below 75

        # Debt to equity — NVDA 0.15 is low, good for lower_better
        de = summary["benchmarks"]["debt_to_equity"]
        assert de["direction"] == "lower_better"
        # Peers: 0.05, 0.50, 0.30, 0.20, 0.02 → NVDA 0.15 → rank 40% (2 below)
        assert de["percentile_rank"] == 40.0

        # PE TTM — context only
        pe = summary["benchmarks"]["pe_ttm"]
        assert pe["direction"] == "context_only"
        assert pe["status"] == "available"
        # "premium" or "discount" in label
        assert "premium" in pe["label"].lower() or "discount" in pe["label"].lower()
