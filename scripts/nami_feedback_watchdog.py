#!/usr/bin/env python3
"""Nami Feedback Watchdog — polls /api/admin/feedback for new submissions.

Runs as a no_agent cron job every 5min. When a new feedback entry is detected,
prints a Telegram-formatted alert to stdout (delivered verbatim). Quiet when idle.
Language: output MUST be in English.
"""

import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

SA_API = "http://127.0.0.1:8780/api/admin/feedback"
SA_PDF = "http://127.0.0.1:8780/api/report/{ticker}/pdf"
SA_ZIP = "http://127.0.0.1:8780/api/dossier/{ticker}/download?lang=en"
STATE_FILE = Path.home() / ".hermes" / "scripts" / "nami_feedback_state.json"


def check_endpoint(url: str, label: str) -> str:
    """Hit an endpoint and return a status emoji + summary."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            size = len(resp.read())
            if resp.status == 200 and size > 1000:
                return f"✅ {label} HTTP 200, {size//1024} KB"
            elif resp.status == 200:
                return f"⚠️ {label} HTTP 200 but only {size} B (suspicious)"
            else:
                return f"❌ {label} HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return f"❌ {label} HTTP {e.code}"
    except Exception as e:
        return f"❌ {label} — {e}"


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_seen_id": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_feedback():
    try:
        req = urllib.request.Request(SA_API)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"⚠️ Nami watchdog: failed to fetch feedback — {e}", file=sys.stderr)
        return None


def main():
    state = load_state()
    feedbacks = fetch_feedback()
    if feedbacks is None:
        return  # silent — fetch error logged to stderr
    if not feedbacks:
        return  # silent — no feedback at all

    # Sort by submission time descending
    feedbacks.sort(key=lambda f: f.get("submitted_at", ""), reverse=True)

    last_id = state.get("last_seen_id")
    new_ids = []
    for fb in feedbacks:
        if fb["id"] == last_id:
            break
        new_ids.append(fb["id"])

    if not new_ids:
        return  # silent — already seen all

    # Reverse to print oldest first
    new_ids.reverse()
    new_fbs = [fb for fb in feedbacks if fb["id"] in new_ids]

    # Update state to newest ID
    state["last_seen_id"] = new_fbs[-1]["id"]
    save_state(state)

    # Build Telegram alert
    for fb in new_fbs:
        ticker = fb["ticker"]
        ts = fb["submitted_at"].replace("T", " ")[:16]
        text = fb["text"].strip()
        files = ", ".join(fb.get("files", [])) if fb.get("files") else "none"

        print(f"🔔 *New Nami feedback* — {ticker} · {ts}")
        print(f"> {text}")
        print(f"📎 Files: {files}")

        # Auto-verify the endpoints Nami is likely trying to use
        pdf_status = check_endpoint(SA_PDF.format(ticker=ticker), "Deep Dive PDF")
        zip_status = check_endpoint(SA_ZIP.format(ticker=ticker), "Dossier ZIP")
        print(f"🔍 Endpoint check: {pdf_status}  |  {zip_status}")
        print()


if __name__ == "__main__":
    main()
