import sys
sys.path.insert(0, ".")

from backend.feedback_store import get_unprocessed
import json

items = get_unprocessed()
if not items:
    print("NO_FEEDBACK")
else:
    for item in items:
        ticker = item.get("_ticker", "?")
        item_id = item.get("id", "?")
        text = item.get("text", "")[:200]
        files = item.get("files", [])
        print(f"TICKER: {ticker} | ID: {item_id} | TEXT: {text} | FILES: {files}")
