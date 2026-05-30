#!/usr/bin/env python3
"""Watchdog: deliver pending chat exports to Ced via Telegram.

Run periodically via cron. Reads .pending_delivery/ directory,
sends each file, and moves delivered files to .delivered/.
"""
import os, sys, shutil
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "chat_exports"
PENDING_DIR = EXPORT_DIR / ".pending_delivery"
DELIVERED_DIR = EXPORT_DIR / ".delivered"

def main():
    if not PENDING_DIR.exists():
        return

    pending = list(PENDING_DIR.iterdir())
    if not pending:
        return

    DELIVERED_DIR.mkdir(parents=True, exist_ok=True)

    for marker in pending:
        try:
            export_path = Path(marker.read_text().strip())
            if not export_path.exists():
                print(f"MISSING: {export_path} — removing marker")
                marker.unlink()
                continue

            # Send via Hermes CLI  
            import subprocess
            result = subprocess.run(
                ["hermes", "send-message", "--target", "telegram",
                 "--message", f"📋 Chat export: {export_path.name}",
                 "--file", str(export_path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                # Move marker to delivered
                shutil.move(str(marker), str(DELIVERED_DIR / marker.name))
                print(f"DELIVERED: {export_path.name}")
            else:
                print(f"FAILED: {export_path.name} — {result.stderr[:200]}")

        except Exception as e:
            print(f"ERROR: {marker.name} — {e}")

if __name__ == "__main__":
    main()
