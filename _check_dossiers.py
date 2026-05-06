#!/usr/bin/env python3
"""Check dossier status and Render API availability for known tickers."""
import requests, json

RENDER_BASE = "https://stock-analysis-api-tdtj.onrender.com"

# Check multiple tickers that exist locally
tickers = ["NVDA", "AAPL", "MSFT", "GOOGL", "META", "TSLA", "ASML"]
for t in tickers:
    try:
        resp = requests.get(f"{RENDER_BASE}/api/dossier/{t}/status", timeout=15)
        print(f"{t}: HTTP {resp.status_code} — {resp.text[:300]}")
    except Exception as e:
        print(f"{t}: ERROR — {e}")

# Also check root endpoint
try:
    resp = requests.get(f"{RENDER_BASE}/", timeout=15)
    print(f"\nRoot: HTTP {resp.status_code} — {resp.text[:300]}")
except Exception as e:
    print(f"Root: ERROR — {e}")
