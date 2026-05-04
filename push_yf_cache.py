#!/usr/bin/env python3
"""One-shot: push yfinance financials to Render cache for all recent tickers."""
import os, sys, json, requests
from pathlib import Path

PROJECT_DIR = Path("/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")
sys.path.insert(0, str(PROJECT_DIR))

# Load .env
with open(PROJECT_DIR / ".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

from backend.sources_collector import get_yahoo_data

RENDER_BASE = "https://stock-analysis-api-tdtj.onrender.com"
SECRET = os.getenv("DOSSIER_UPLOAD_SECRET", "")

# Get recent tickers
resp = requests.get(f"{RENDER_BASE}/api/analyses", timeout=15)
analyses = resp.json().get("analyses", [])
tickers = set()
for a in analyses:
    parts = a["directory"].split("_")
    if len(parts) >= 2:
        tickers.add(parts[1])

print(f"Tickers: {tickers}")

for ticker in sorted(tickers):
    print(f"\n=== {ticker} ===")
    yf = get_yahoo_data(ticker)
    fin = yf.get("financials", {})
    print(f"  Revenue: {fin.get('revenue_annual')}")
    print(f"  Net Income: {fin.get('net_income')}")
    print(f"  FCF: {fin.get('free_cash_flow')}")
    
    r = requests.post(
        f"{RENDER_BASE}/api/cache/financials/{ticker}",
        json=yf,
        headers={"X-Upload-Secret": SECRET},
        timeout=30,
    )
    print(f"  Upload: {r.status_code} - {r.text[:150]}")
