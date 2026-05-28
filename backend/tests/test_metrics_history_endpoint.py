"""Tests for /api/metrics-history/{ticker} data completeness behavior."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.main import app


client = TestClient(app)


def _mock_ticker(financials: pd.DataFrame, cashflow: pd.DataFrame, balance_sheet: pd.DataFrame):
    ticker = MagicMock()
    ticker.quarterly_financials = financials
    ticker.quarterly_cashflow = cashflow
    ticker.quarterly_balance_sheet = balance_sheet
    return ticker


def test_metrics_history_drops_fully_empty_quarters_and_reports_drop_metadata():
    """Rows with every metric=None are removed and reported explicitly."""
    col_recent = pd.Timestamp("2026-04-30")
    col_empty = pd.Timestamp("2024-12-31")

    fin = pd.DataFrame(
        {
            col_recent: {
                "Total Revenue": 100.0,
                "Net Income": 20.0,
                "Basic EPS": 1.5,
            }
        }
    )
    cf = pd.DataFrame(
        {
            col_recent: {
                "Operating Cash Flow": 25.0,
                "Capital Expenditure": -5.0,
            },
            col_empty: {
                "Operating Cash Flow": None,
                "Capital Expenditure": None,
            },
        }
    )
    bs = pd.DataFrame(
        {
            col_recent: {
                "Total Debt": 30.0,
            },
            col_empty: {
                "Total Debt": None,
            },
        }
    )

    with patch("yfinance.Ticker", return_value=_mock_ticker(fin, cf, bs)):
        response = client.get("/api/metrics-history/TEST")

    assert response.status_code == 200
    data = response.json()

    quarters = [q["quarter"] for q in data["quarters"]]
    assert "2024Q4" not in quarters
    assert data.get("dropped_count") == 1
    assert "2024Q4" in data.get("dropped_empty_quarters", [])
    assert data["count"] == len(data["quarters"]) == 1


def test_metrics_history_keeps_partial_quarter_and_backfills_date_from_bs_cf():
    """Quarters with at least one metric remain, even without income-statement rows."""
    col_recent = pd.Timestamp("2026-04-30")
    col_partial = pd.Timestamp("2025-12-31")

    fin = pd.DataFrame(
        {
            col_recent: {
                "Total Revenue": 150.0,
                "Net Income": 30.0,
            }
        }
    )
    cf = pd.DataFrame(
        {
            col_recent: {
                "Operating Cash Flow": 40.0,
                "Capital Expenditure": -8.0,
            }
        }
    )
    bs = pd.DataFrame(
        {
            col_recent: {
                "Total Debt": 45.0,
            },
            col_partial: {
                "Total Debt": 33.0,
            },
        }
    )

    with patch("yfinance.Ticker", return_value=_mock_ticker(fin, cf, bs)):
        response = client.get("/api/metrics-history/TEST")

    assert response.status_code == 200
    data = response.json()

    by_quarter = {row["quarter"]: row for row in data["quarters"]}
    assert "2025Q4" in by_quarter
    assert by_quarter["2025Q4"]["total_debt"] == 33.0
    assert by_quarter["2025Q4"]["date"] == "2025-12-31"

    # No fully-empty row in this fixture.
    assert data.get("dropped_count", 0) == 0
