import sys
sys.path.insert(0, '.')
from backend.feedback_store import get_unprocessed
items = get_unprocessed()
if not items:
    print('NO_FEEDBACK')
else:
    import json
    for item in items:
        print(f'TICKER: {item["_ticker"]} | ID: {item["id"]} | TEXT: {item["text"][:200]} | FILES: {item["files"]}')
