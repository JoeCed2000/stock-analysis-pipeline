from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_valuation_context_route_returns_mixed_for_1_1_1(monkeypatch):
    mock_info = {
        "trailingPE": 10.0,
        "priceToSalesTrailing12Months": 20.0,
        "enterpriseToEbitda": 20.0,
        "marketCap": 1_000_000_000.0,
        "freeCashflow": None,
        "earningsGrowth": 0.20,   # support via PEG
        "revenueGrowth": 0.05,    # concern via P/S vs growth
        "ebitdaGrowth": 0.10,     # neutral via EV/EBITDA vs growth
        "regularMarketPrice": 100.0,
    }

    fake_ticker = MagicMock()
    fake_ticker.info = mock_info
    monkeypatch.setattr("backend.routes.valuation_context._yf_ticker_safe", lambda ticker: fake_ticker)

    response = client.get("/api/valuation-context/MIXED")
    assert response.status_code == 200

    data = response.json()
    support = data["context"]["valuation_support"]
    summary = data["context"]["context_summary"]

    assert support["support"] == 1
    assert support["neutral"] == 1
    assert support["concern"] == 1
    assert support["dominant"] == "mixed"
    assert summary["valuation_level"] == "mixed_signals"
