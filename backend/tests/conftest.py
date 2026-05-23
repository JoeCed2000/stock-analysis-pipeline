"""
Shared pytest fixtures for company_overview tests.

Provides deterministic mock data for yfinance responses, Tavily search results,
LLM outputs, and a temporary cache directory.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ── Sample data fixtures ────────────────────────────────────────────────────


@pytest.fixture
def sample_yf_info() -> dict:
    """Complete yfinance Ticker.info for a healthy large-cap company."""
    return {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "country": "United States",
        "website": "https://www.apple.com",
        "employees": 164000,
        "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.",
        "market_cap": 3000000000000,
        "enterprise_value": 3100000000000,
        "current_price": 185.50,
        "previous_close": 184.00,
        "pe_trailing": 30.5,
        "pe_forward": 28.0,
        "dividend_yield": 0.0052,
        "beta": 1.25,
        "52w_high": 199.62,
        "52w_low": 124.17,
        "revenue_growth": 0.05,
        "earnings_growth": 0.08,
        "total_revenue": 383285000000,
        "currency": "USD",
        "exchange": "NASDAQ",
        "headquarters": "Cupertino, CA, United States",
    }


@pytest.fixture
def thin_yf_info() -> dict:
    """Minimal yfinance info — simulates a thin/unknown ticker."""
    return {
        "ticker": "PENNY",
        "name": None,
        "sector": None,
        "industry": None,
        "country": None,
        "website": None,
        "employees": None,
        "description": None,
        "market_cap": None,
        "enterprise_value": None,
        "current_price": 0.05,
        "previous_close": None,
        "pe_trailing": None,
        "pe_forward": None,
        "dividend_yield": None,
        "beta": None,
        "52w_high": None,
        "52w_low": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "total_revenue": None,
        "currency": "USD",
        "exchange": None,
        "headquarters": None,
    }


@pytest.fixture
def empty_yf_info() -> dict:
    """Completely empty yfinance info (ticker not found)."""
    return {
        "ticker": "ZZZZZ",
        "name": None,
        "sector": None,
        "industry": None,
        "country": None,
        "website": None,
        "employees": None,
        "description": None,
        "market_cap": None,
        "enterprise_value": None,
        "current_price": None,
        "previous_close": None,
        "pe_trailing": None,
        "pe_forward": None,
        "dividend_yield": None,
        "beta": None,
        "52w_high": None,
        "52w_low": None,
        "revenue_growth": None,
        "earnings_growth": None,
        "total_revenue": None,
        "currency": "USD",
        "exchange": None,
        "headquarters": None,
    }


@pytest.fixture
def sample_tavily_results() -> list:
    """Typical Tavily search results for a well-known company."""
    return [
        {
            "title": "Apple Reports Record Q2 2026 Earnings",
            "url": "https://example.com/apple-q2-2026",
            "content": "Apple Inc. reported record revenue of $95 billion for Q2 2026, driven by strong iPhone 17 sales and services growth of 14% YoY.",
            "date": "2026-05-01",
        },
        {
            "title": "Apple Vision Pro v2 Expected Fall 2026",
            "url": "https://example.com/vision-pro-v2",
            "content": "Supply chain reports indicate Apple is preparing Vision Pro v2 for a fall 2026 launch with significant weight reduction and lower price point.",
            "date": "2026-05-15",
        },
        {
            "title": "Apple Expands Buyback Program to $110B",
            "url": "https://example.com/apple-buyback",
            "content": "Apple's board authorized an additional $110 billion share buyback program, the largest in corporate history.",
            "date": "2026-05-02",
        },
    ]


@pytest.fixture
def sample_en_overview() -> dict:
    """Complete English company overview matching the expected output schema."""
    return {
        "company_profile": {
            "name": "Apple Inc.",
            "ticker": "AAPL",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "United States",
            "website": "https://www.apple.com",
            "employees": 164000,
            "founded": 1976,
            "headquarters": "Cupertino, CA, United States",
        },
        "business_description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide. The company operates through five segments: iPhone, Services, Mac, Wearables/Home/Accessories, and iPad.",
        "key_financials": {
            "market_cap": 3000000000000,
            "market_cap_display": "$3.00T",
            "revenue": 383285000000,
            "revenue_display": "$383.3B",
            "pe_ratio": 30.5,
            "pe_forward": 28.0,
            "dividend_yield": 0.0052,
            "beta": 1.25,
            "52w_high": 199.62,
            "52w_low": 124.17,
        },
        "recent_developments": [
            {
                "title": "Apple Reports Record Q2 2026 Earnings",
                "summary": "Apple Inc. reported record revenue of $95 billion for Q2 2026.",
                "date": "2026-05-01",
                "sentiment": "positive",
            },
            {
                "title": "Apple Expands Buyback Program",
                "summary": "Board authorized an additional $110 billion buyback.",
                "date": "2026-05-02",
                "sentiment": "positive",
            },
        ],
        "competitive_position": "Apple holds dominant market share in premium smartphones with unmatched brand loyalty and ecosystem lock-in.",
    }


@pytest.fixture
def sample_en_overview_json() -> str:
    """Complete overview as a JSON string (as returned by LLM)."""
    return json.dumps({
        "company_profile": {
            "name": "Apple Inc.",
            "ticker": "AAPL",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "United States",
            "website": "https://www.apple.com",
            "employees": 164000,
            "founded": 1976,
            "headquarters": "Cupertino, CA, United States",
        },
        "business_description": "Apple designs smartphones and computers.",
        "key_financials": {
            "market_cap": 3000000000000,
            "market_cap_display": "$3.00T",
            "revenue": 383285000000,
            "revenue_display": "$383.3B",
            "pe_ratio": 30.5,
            "pe_forward": 28.0,
            "dividend_yield": 0.0052,
            "beta": 1.25,
            "52w_high": 199.62,
            "52w_low": 124.17,
        },
        "recent_developments": [
            {
                "title": "iPhone 17 Launch",
                "summary": "Apple launched iPhone 17 with AI features.",
                "date": "2026-05-15",
                "sentiment": "positive",
            },
        ],
        "competitive_position": "Market leader in premium smartphones.",
    })


@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch) -> Path:
    """Temporary cache directory isolated per test."""
    import backend.company_overview as cov

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(cov, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(cov, "OVERVIEW_CACHE_VERSION", 42)  # Unique test version
    return cache_dir


@pytest.fixture
def mock_codex_success(sample_en_overview_json):
    """Patch _codex_chat to return valid JSON."""
    with patch("backend.codex_provider._codex_chat", return_value=sample_en_overview_json) as mock:
        yield mock


@pytest.fixture
def mock_codex_failure():
    """Patch _codex_chat to simulate LLM failure."""
    with patch("backend.codex_provider._codex_chat", return_value=None) as mock:
        yield mock
