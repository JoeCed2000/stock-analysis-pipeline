"""Test Patchright+Firefox on Seeking Alpha with cookies."""
import sys, os, json
from pathlib import Path
from patchright.sync_api import sync_playwright

sys.path.insert(0, '/home/ced/codex-projects/stock-analysis-pipeline')
sys.path.insert(0, '/home/ced/codex-projects/stock-analysis-pipeline/backend')
os.chdir('/home/ced/codex-projects/stock-analysis-pipeline')

from backend.seeking_alpha_access import _read_store
store = _read_store()

# Build cookies with domains
pw_cookies = []
cookies_parsed = store.get("cookies_parsed")
if cookies_parsed:
    for c in cookies_parsed:
        pw_cookies.append({"name": c["name"], "value": c["value"], "domain": c.get("domain", ".seekingalpha.com"), "path": c.get("path", "/")})
else:
    for part in store["cookie_header"].split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            pw_cookies.append({"name": name.strip(), "value": value.strip(), "domain": ".seekingalpha.com", "path": "/"})

print(f"Cookies: {len(pw_cookies)}")

with sync_playwright() as p:
    browser = p.firefox.launch(headless=True)
    context = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="en-US")
    context.add_cookies(pw_cookies)
    page = context.new_page()
    
    listing_url = "https://seekingalpha.com/symbol/NVDA/earnings/transcripts"
    print(f"Navigating to {listing_url}")
    page.goto(listing_url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    
    body = page.evaluate("document.body.innerText")
    blocked = any(m in body[:500].lower() for m in ["press & hold", "verify you are human", "access denied"])
    
    if blocked:
        print(f"BLOCKED: {body[:300]}")
    else:
        print(f"OK! Body: {len(body)} chars")
        links = page.query_selector_all('a[href*="/article/"]')
        print(f"Article links: {len(links)}")
        if links:
            href = links[0].get_attribute("href")
            print(f"First: {href}")
    
    browser.close()
