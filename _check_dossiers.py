#!/usr/bin/env python3
"""Check dossier status for common tickers that might have dossiers on Render."""
import requests, json, sys

tickers_to_check = ["NVDA", "AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META"]

for ticker in tickers_to_check:
    try:
        r = requests.get(f"https://stock-analysis-api-tdtj.onrender.com/api/dossier/{ticker}/status", timeout=60)
        if r.status_code == 200:
            data = r.json()
            stage = data.get("stage", "unknown")
            files = data.get("files", [])
            missing = data.get("missing", [])
            print(f"{ticker}: stage={stage} | files={len(files)} | missing={missing}")
        elif r.status_code == 404:
            print(f"{ticker}: 404 — no dossier found")
        else:
            print(f"{ticker}: HTTP {r.status_code}")
    except Exception as e:
        print(f"{ticker}: ERROR — {e}")
