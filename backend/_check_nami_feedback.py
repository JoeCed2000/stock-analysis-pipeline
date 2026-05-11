"""
Check for unprocessed Nami feedback items.
Usage: backend/.venv/bin/python3 backend/_check_nami_feedback.py
"""
import sys
sys.path.insert(0, ".")

from backend.feedback_store import get_unprocessed

items = get_unprocessed()
if not items:
    print("NO_FEEDBACK")
else:
    for item in items:
        ticker = item.get("_ticker", "?")
        item_id = item.get("id", "?")
        text = item.get("text", "")
        files = item.get("files", [])
        print(f"TICKER: {ticker} | ID: {item_id} | TEXT: {text[:200]} | FILES: {files}")
