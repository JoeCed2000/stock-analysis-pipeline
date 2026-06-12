"""Test Patchright browser availability."""
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    for name, launcher in [("firefox", p.firefox), ("chromium", p.chromium)]:
        try:
            browser = launcher.launch(headless=True)
            print(f"{name}: OK")
            browser.close()
        except Exception as e:
            print(f"{name}: {e}")
