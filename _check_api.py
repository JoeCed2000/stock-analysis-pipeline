"""Check Render API for recent analyses and dossier statuses."""
import requests
import json

print("=== /api/analyses ===")
resp = requests.get("https://stock-analysis-api-tdtj.onrender.com/api/analyses", timeout=120)
print(f"Status: {resp.status_code}")
data = resp.json()
analyses = data.get("analyses", [])
print(f"Total analyses: {len(analyses)}")
for a in analyses[:20]:
    print(f"  - {a.get('directory', '?')}  | stage={a.get('stage', '?')}  | ticker={a.get('ticker', '?')}")
if len(analyses) > 20:
    print(f"  ... and {len(analyses)-20} more")
if not analyses:
    print("(no analyses returned)")
    # Try to see raw response
    print(f"Raw keys: {list(data.keys())}")
    print(f"Raw (first 500 chars): {json.dumps(data)[:500]}")

print()

# Try a few common tickers to see dossier status
for ticker in ["NVDA", "AAPL", "MSFT"]:
    print(f"=== /api/dossier/{ticker}/status ===")
    try:
        resp = requests.get(f"https://stock-analysis-api-tdtj.onrender.com/api/dossier/{ticker}/status", timeout=60)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"  stage: {data.get('stage', '?')}")
        files_list = data.get("files", [])
        if isinstance(files_list, dict):
            files_list = list(files_list.keys())
        print(f"  files ({len(files_list)}): {files_list[:10]}")
        print(f"  needs: {data.get('needs', data.get('missing', '?'))}")
    except Exception as e:
        print(f"  Error: {e}")
    print()
