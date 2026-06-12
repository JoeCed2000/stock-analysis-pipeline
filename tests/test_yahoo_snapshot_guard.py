"""Anti-degradation guard for Yahoo snapshots.

Regression (NVDA 2026-06-12): a partially failed yfinance fetch (rate
limit during a heavy test run) produced a snapshot with None in most
financial fields (fiscal_period_label, revenue_estimate, net_debt,
eps_actual...). It was persisted and fed a client PDF with a wrong fiscal
title and inconsistent metrics. A stale-but-rich snapshot must win over a
fresh-but-degraded one.
"""
import json

import pytest

from backend import sources_collector as sc


RICH_FINANCIALS = {
    "revenue_quarterly": 10.5e9, "revenue_estimate": 10.0e9,
    "eps_actual": 2.10, "eps_estimate": 2.00,
    "net_debt": -5.0e9, "operating_cash_flow": 4.0e9, "capex": -0.8e9,
    "free_cash_flow": 3.2e9, "fiscal_period_label": "FY2027 Q1",
    "period_end_date": "2026-04-27", "gross_margin": 0.55,
    "operating_margin": 0.30, "net_income": 2.4e9,
}

DEGRADED_FINANCIALS = {
    "revenue_quarterly": 10.5e9, "revenue_estimate": None,
    "eps_actual": None, "eps_estimate": 2.00,
    "net_debt": None, "operating_cash_flow": None, "capex": None,
    "free_cash_flow": 3.2e9, "fiscal_period_label": None,
    "period_end_date": None, "gross_margin": None,
    "operating_margin": None, "net_income": None,
}


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "CACHE_DIR", tmp_path)
    yield


def _snapshot(financials):
    return {"ticker": "ACME", "company_name": "Acme Corp", "financials": dict(financials)}


def test_degraded_fresh_snapshot_does_not_replace_rich_cache():
    rich = _snapshot(RICH_FINANCIALS)
    sc._cache_set("ACME", rich)
    # Expire the cache: the guard must still consider the stale-but-rich copy
    path = sc._cache_path("ACME")
    entry = json.loads(path.read_text())
    entry["timestamp"] = 0
    path.write_text(json.dumps(entry))
    assert sc._cache_get("ACME") is None, "precondition: TTL expired"

    result = sc._guard_against_degraded_snapshot("ACME", _snapshot(DEGRADED_FINANCIALS))

    assert result["financials"]["fiscal_period_label"] == "FY2027 Q1"
    assert result["financials"]["net_debt"] == -5.0e9
    # The degraded snapshot must not have poisoned the cache either
    persisted = json.loads(sc._cache_path("ACME").read_text())["data"]
    assert persisted["financials"]["fiscal_period_label"] == "FY2027 Q1"


def test_normal_fresh_snapshot_is_persisted():
    sc._cache_set("ACME", _snapshot(DEGRADED_FINANCIALS))  # old poor cache
    fresh = _snapshot(RICH_FINANCIALS)

    result = sc._guard_against_degraded_snapshot("ACME", fresh)

    assert result is fresh
    persisted = json.loads(sc._cache_path("ACME").read_text())["data"]
    assert persisted["financials"]["fiscal_period_label"] == "FY2027 Q1"


def test_no_previous_cache_persists_whatever_we_got():
    fresh = _snapshot(DEGRADED_FINANCIALS)
    result = sc._guard_against_degraded_snapshot("ACME", fresh)
    assert result is fresh
    assert sc._cache_path("ACME").exists()


def test_losing_critical_fields_keeps_previous_even_above_count_ratio():
    """A rate-limited fetch can keep ~70%+ of field count while losing the
    fields that drive the client PDF (fiscal label, net_debt, eps_actual)
    — observed 2026-06-12 14:04. Any lost critical field = degradation."""
    rich = _snapshot(RICH_FINANCIALS)
    sc._cache_set("ACME", rich)
    mostly_full = dict(RICH_FINANCIALS)
    mostly_full.update({"fiscal_period_label": None, "net_debt": None, "eps_actual": None})

    result = sc._guard_against_degraded_snapshot("ACME", _snapshot(mostly_full))

    assert result["financials"]["fiscal_period_label"] == "FY2027 Q1"
    assert result["financials"]["net_debt"] == -5.0e9
