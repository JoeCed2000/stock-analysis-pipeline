"""Check Render API for analyses."""
import requests, json

resp = requests.get("https://stock-analysis-api-tdtj.onrender.com/api/analyses", timeout=60)
print(f"Status: {resp.status_code}")
data = resp.json()
if isinstance(data, dict):
    print(f"Keys: {list(data.keys())}")
    analyses = data.get("analyses", [])
    print(f"Number of analyses: {len(analyses)}")
    for a in analyses[:5]:
        print(f"  - {a.get('directory', 'N/A')}")
else:
    print(f"List: {len(data)} items")
    print(json.dumps(data[:3], indent=2)[:2000])
