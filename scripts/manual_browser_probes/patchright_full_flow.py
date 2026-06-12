"""Test Patchright Chromium full flow: listing -> article -> extract."""
import sys, os, json, re
from pathlib import Path
from patchright.sync_api import sync_playwright

sys.path.insert(0, '/home/ced/codex-projects/stock-analysis-pipeline')
sys.path.insert(0, '/home/ced/codex-projects/stock-analysis-pipeline/backend')
os.chdir('/home/ced/codex-projects/stock-analysis-pipeline')

from backend.seeking_alpha_access import _read_store
store = _read_store()

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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="en-US")
    context.add_cookies(pw_cookies)
    page = context.new_page()
    
    # Step 1: Listing
    listing_url = "https://seekingalpha.com/symbol/NVDA/earnings/transcripts"
    print(f"Step 1: Listing {listing_url}")
    page.goto(listing_url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)
    
    body = page.inner_text("body")[:500].lower()
    if any(m in body for m in ["press & hold", "verify", "access denied"]):
        print(f"BLOCKED at listing")
        browser.close()
        exit()
    print("Listing OK")
    
    # Step 2: Find first article
    links = page.query_selector_all('a[href*="/article/"]')
    print(f"Found {len(links)} article links")
    
    if not links:
        browser.close()
        exit()
    
    first_href = links[0].get_attribute("href")
    if first_href and first_href.startswith("/"):
        article_url = "https://seekingalpha.com" + first_href
    else:
        article_url = first_href
    
    print(f"Step 2: Article {article_url}")
    page.goto(article_url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    
    article_body = page.inner_text("body")
    article_text = article_body[:500].lower()
    
    if any(m in article_text for m in ["press & hold", "verify", "access denied"]):
        print(f"BLOCKED at article")
    else:
        print(f"Article OK! Body: {len(article_body)} chars")
        # Clean up
        raw = re.sub(r'\n{3,}', '\n\n', article_body)
        print(f"Cleaned: {len(raw)} chars")
        print(f"First 300: {raw[:300]}")
        print(f"Last 300: ...{raw[-300:]}")
    
    browser.close()
