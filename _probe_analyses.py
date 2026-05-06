"""Quick probe: what does /api/analyses return?"""
import requests, json, sys

r = requests.get("https://stock-analysis-api-tdtj.onrender.com/api/analyses", timeout=30)
print(f"Status: {r.status_code}")
data = r.json()
print(json.dumps(data, indent=2)[:3000])

# Check key structure
analyses = data.get("analyses", [])
print(f"\nTotal analyses returned: {len(analyses)}")
if analyses:
    print(f"First item keys: {list(analyses[0].keys()) if isinstance(analyses[0], dict) else type(analyses[0])}")
    print(f"First item: {json.dumps(analyses[0], indent=2)[:500]}")
