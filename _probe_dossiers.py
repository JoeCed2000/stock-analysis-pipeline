"""Quick probe: check dossier status for common tickers."""
import requests, json

BASE = "https://stock-analysis-api-tdtj.onrender.com"

# Try a few likely tickers
tickers = ["NVDA", "AAPL", "MSFT", "TSLA", "GOOGL"]
for t in tickers:
    try:
        r = requests.get(f"{BASE}/api/dossier/{t}/status", timeout=15)
        data = r.json()
        files = data.get("files", [])
        stage = data.get("stage", "?")
        print(f"{t}: stage={stage}, files={len(files)}, status_code={r.status_code}")
    except Exception as e:
        print(f"{t}: ERROR — {e}")
