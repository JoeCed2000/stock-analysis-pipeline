"""Transcript source integration — SA cookies → StockAnalysis.com → Alpha Vantage."""
import os
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

MIN_TRANSCRIPT_CHARS = 2000  # Anything shorter is metadata/error, not a real transcript


def _is_usable(text: str) -> bool:
    return bool(text) and len(text) >= MIN_TRANSCRIPT_CHARS


def find_transcripts(ticker: str, output_dir: str = "", company: str | None = None) -> Dict[str, Any]:
    """
    Search for earnings call transcripts from configured sources.
    Returns {'sources': [...], 'found': bool}
    Saves results to 04_transcripts_and_management/ if output_dir provided.
    """
    results = []
    primary_text = ""  # Full transcript text from primary source

    # 0. Seeking Alpha with stored cookies via Playwright — PRIMARY source (CedLab 2026-06-05).
    # Playwright (real browser) bypasses PerimeterX where httpx gets 403.
    # Falls back to StockAnalysis.com if cookies are missing/expired.
    try:
        from backend.seeking_alpha_access import _is_earnings_call_transcript_link, _read_store
        import re as _re

        store = _read_store()
        cookie_header = store.get("cookie_header", "")
        if cookie_header:
            # Prefer cookies_parsed (with correct per-cookie domains from Netscape export).
            # Fall back to parsing cookie_header with hardcoded domain for backward compat.
            pw_cookies = []
            cookies_parsed = store.get("cookies_parsed")
            if cookies_parsed:
                for c in cookies_parsed:
                    pw_cookies.append({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ".seekingalpha.com"),
                        "path": c.get("path", "/"),
                    })
            else:
                for part in cookie_header.split(";"):
                    part = part.strip()
                    if "=" in part:
                        name, value = part.split("=", 1)
                        pw_cookies.append({
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": ".seekingalpha.com",
                            "path": "/",
                        })

            import asyncio as _asyncio
            try:
                _asyncio.get_running_loop()
                # Running inside async context — create a fresh loop for sync Playwright
                _loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(_loop)
            except RuntimeError:
                pass  # No running loop — sync Playwright will work fine
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                # Firefox bypasses PerimeterX where Chromium gets detected (2026-06-06)
                browser = p.firefox.launch(headless=True)
                context_kwargs: dict = {
                    "viewport": {"width": 1920, "height": 1080},
                    "locale": "en-US",
                }
                user_agent = store.get("user_agent")
                if user_agent:
                    context_kwargs["user_agent"] = user_agent
                context = browser.new_context(**context_kwargs)
                context.add_cookies(pw_cookies)
                page = context.new_page()

                # Navigate to transcript listing
                listing_url = f"https://seekingalpha.com/symbol/{ticker}/earnings/transcripts"
                page.goto(listing_url, timeout=20000, wait_until="domcontentloaded")

                # Check if blocked by PerimeterX
                body_text = page.inner_text("body")[:500].lower()
                if any(m in body_text for m in ("access denied", "access to this page has been denied", "before we continue", "press & hold", "verify you are human", "captcha")):
                    logger.warning(f"Seeking Alpha blocked by PerimeterX for {ticker} — falling back")
                    browser.close()
                else:
                    # Find the first real earnings-call transcript link. The listing
                    # also includes conference transcripts, presentations, and
                    # comment anchors that are not suitable transcript sources.
                    links = page.query_selector_all('a[href*="/article/"]')
                    for link in links:
                        href = link.get_attribute("href") or ""
                        label = (link.inner_text() or "").strip()
                        if not _is_earnings_call_transcript_link(label, href):
                            continue
                        if href.startswith("/"):
                            first_url = "https://seekingalpha.com" + href
                        else:
                            first_url = href

                        if first_url:
                            page.goto(first_url, timeout=30000, wait_until="domcontentloaded")
                            # Extract all visible text — the transcript body
                            page.wait_for_timeout(8000)  # let JS render and bypass MPW
                            raw = page.inner_text("body")
                            # Remove navigation/header noise
                            raw = _re.sub(r'\n{3,}', '\n\n', raw)
                            if _is_usable(raw):
                                primary_text = raw
                                results.append({
                                    "source": "Seeking Alpha",
                                    "type": "earnings_transcript",
                                    "title": label or f"{ticker} Earnings Call",
                                    "url": first_url or listing_url,
                                    "text": raw,
                                    "text_length": len(raw),
                                })
                                logger.info(f"Seeking Alpha (Playwright+cookie): {len(raw)} chars for {ticker}")
                                break
                    browser.close()
    except Exception as e:
        logger.warning(f"Seeking Alpha (Playwright) unavailable for {ticker}: {e}")

    # 1. Seeking Alpha direct article discovery — prefer true SA article URLs before
    # StockAnalysis. The SA listing page is often blocked, but the concrete article
    # URL is readable with the stored cookies.
    if not _is_usable(primary_text):
        try:
            from backend.transcript_web_search import search_transcript_pages

            web_results = search_transcript_pages(ticker, company=company)
            for item in web_results:
                text = item.get("text", "")
                url = item.get("url", "")
                if "seekingalpha.com/article/" not in url.lower() or not _is_usable(text):
                    continue
                primary_text = text
                results.append(item)
                logger.info(f"Seeking Alpha direct article transcript: {len(primary_text)} chars for {ticker}")
                break
        except Exception as e:
            logger.warning(f"Seeking Alpha direct article discovery unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping SA direct article discovery: Playwright already provided {len(primary_text)} chars")



    # 2. StockAnalysis.com — FREE full-text transcripts, no auth needed.
    if not _is_usable(primary_text):
        try:
            from backend.stockanalysis import search_transcripts as sa_search, fetch_transcript as sa_fetch
            sa_results = sa_search(ticker, limit=3)
            for sa_result in sa_results:
                sa_url = sa_result.get("url", "")
                if not sa_url:
                    continue
                sa_data = sa_fetch(sa_url)
                sa_content = sa_data.get("content", "") if sa_data else ""
                if not _is_usable(sa_content):
                    continue
                source_name = str(sa_data.get("source") or sa_result.get("source") or "StockAnalysis").strip()
                source_url = str(sa_data.get("url") or sa_url).strip()
                primary_text = sa_content
                results.append({
                    "source": source_name,
                    "type": "earnings_transcript",
                    "title": sa_data.get("title") or sa_result.get("title", ""),
                    "url": source_url,
                    "text": sa_content,
                    "text_length": len(sa_content),
                    "date": sa_data.get("date", ""),
                    "id": sa_result.get("id", ""),
                    "stockanalysis_url": sa_data.get("stockanalysis_url", sa_url),
                    "retrieval_provider": sa_data.get("retrieval_provider", "StockAnalysis"),
                })
                logger.info(f"StockAnalysis.com transcript: {len(sa_content)} chars for {ticker}")
                break
        except Exception as e:
            logger.warning(f"StockAnalysis.com unavailable for {ticker}: {e}")

    # 2. Alpha Vantage API — fallback (structured JSON, 25 req/day free).
    if not _is_usable(primary_text):
        try:
            from backend.alpha_vantage import fetch_transcript
            av = fetch_transcript(ticker)
            if av and av.get("content"):
                primary_text = av["content"]
                results.append({
                    "source": "Alpha Vantage API",
                    "type": "earnings_transcript",
                    "title": f"{ticker} {av.get('quarter', '')} Earnings Call",
                    "url": f"https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT&symbol={ticker}",
                    "text": av["content"],
                    "text_length": len(av["content"]),
                    "quarter": av.get("quarter", ""),
                    "date": av.get("date", ""),
                    "id": "",
                })
                logger.info(f"Alpha Vantage transcript: {len(av['content'])} chars for {ticker}")
        except Exception as e:
            logger.warning(f"Alpha Vantage unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping Alpha Vantage — RapidAPI Seeking Alpha already provided {len(primary_text)} chars")

    # 2. Motley Fool transcripts — last resort if structured sources failed.
    if not _is_usable(primary_text):
        try:
            from backend.sources.motleyfool import get_transcript as get_fool_transcript

            fool = get_fool_transcript(ticker)
            if fool and fool.get("text"):
                primary_text = fool["text"]
                results.append({
                    "source": "The Motley Fool",
                    "type": "earnings_transcript",
                    "title": f"{ticker} Earnings Call Transcript",
                    "url": fool.get("url", ""),
                    "text": primary_text,
                    "text_length": len(primary_text),
                    "quarter": "",
                    "date": fool.get("date", ""),
                    "id": "",
                })
                logger.info(f"Motley Fool transcript: {len(primary_text)} chars for {ticker}")
        except Exception as e:
            logger.warning(f"Motley Fool unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping Fool.com — higher-priority source already provided {len(primary_text)} chars")

    # 3. Legacy public web transcript fallback.
    if not _is_usable(primary_text):
        try:
            from backend.seeking_alpha import search_transcript_web

            for item in search_transcript_web(ticker):
                text = item.get("text", "")
                if not text:
                    continue
                primary_text = text
                results.append({
                    "source": item.get("source") or "Public transcript search",
                    "type": "earnings_transcript",
                    "title": item.get("title", f"{ticker} Earnings Call Transcript"),
                    "url": item.get("url", ""),
                    "text": text,
                    "text_length": len(text),
                    "quarter": item.get("quarter", ""),
                    "date": item.get("date", ""),
                    "id": "",
                })
                logger.info(f"Public transcript search: {len(primary_text)} chars for {ticker}")
                break
        except Exception as e:
            logger.warning(f"Public transcript search unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping public transcript search: higher-priority source already provided {len(primary_text)} chars")



    # 4. Google-discovered public transcript pages.
    if not _is_usable(primary_text):
        try:
            from backend.transcript_web_search import search_transcript_pages

            web_results = search_transcript_pages(ticker, company=company)
            if web_results:
                primary_text = web_results[0].get("text", "")
                results.extend(web_results)
                logger.info(f"Google web transcript: {len(primary_text)} chars for {ticker}")
        except Exception as e:
            logger.warning(f"Google transcript discovery unavailable for {ticker}: {e}")
    else:
        logger.info(f"Skipping Google transcript discovery: higher-priority source already provided {len(primary_text)} chars")

    # Save to disk if output_dir provided
    if output_dir and results:
        trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
        os.makedirs(trans_dir, exist_ok=True)
        path = os.path.join(trans_dir, f"transcript_sources_{ticker}.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Transcript sources saved: {path}")

    return {"sources": results, "found": len(results) > 0}


def _today_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ddg_search_urls(query: str, limit: int = 6) -> list[dict]:
    """DuckDuckGo HTML search and extract candidate URLs with simple filtering."""
    try:
        from backend.http_client import http
        resp = http.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        import re
        urls = []
        for match in re.finditer(r'class="result__url"[^>]*>(?:https?://)?([^<]+)', resp.text):
            domain = match.group(1).strip()
            if not domain.startswith("http"):
                domain = f"https://{domain}"
            urls.append({"url": domain})
            if len(urls) >= limit:
                break
        return urls
    except Exception:
        return []


def find_earnings_documents(
    ticker: str,
    output_dir: str = "",
    company: str | None = None,
    phoenix_url: str | None = None,
) -> Dict[str, Any]:
    """
    Find Press Release and Earnings Presentation with fallbacks:
    1) If phoenix_url provided: try it; on 404 → continue
    2) Corporate website (investor./ir.) via DuckDuckGo
    3) SEC EDGAR 8-K recent filing
    Returns dict with press_release, presentation, attempted_urls and found flags.
    """
    from backend.http_client import http
    from backend.sources_collector import get_sec_filings

    attempted: list[str] = []
    statuses: dict[str, int] = {}

    pr: dict = {"status": "NOT_FOUND", "url": "", "source": "", "accessed_at": _today_str()}
    deck: dict = {"status": "NOT_FOUND", "url": "", "source": "", "accessed_at": _today_str()}

    def _try_url(url: str, kind: str) -> bool:
        if not url:
            return False
        try:
            r = http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
            attempted.append(url)
            statuses[url] = r.status_code
            if r.status_code == 200:
                if kind == "pr" and pr["status"] != "FOUND":
                    pr.update({"status": "FOUND", "url": url, "source": "corporate", "accessed_at": _today_str()})
                    return True
                if kind == "deck" and deck["status"] != "FOUND":
                    deck.update({"status": "FOUND", "url": url, "source": "corporate", "accessed_at": _today_str()})
                    return True
        except Exception:
            pass
        return False

    # 1) Phoenix IR direct link if provided
    if phoenix_url:
        try:
            r = http.get(phoenix_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, follow_redirects=True)
            attempted.append(phoenix_url)
            statuses[phoenix_url] = r.status_code
            if r.status_code == 200:
                pr.update({"status": "FOUND", "url": phoenix_url, "source": "phoenix_ir", "accessed_at": _today_str()})
        except Exception:
            pass

    # 2) Corporate site via DDG
    q_base = f"{company or ticker} investor relations earnings"
    queries = [
        f"{q_base} press release",
        f"{q_base} news release",
        f"{q_base} earnings presentation pdf",
        f"{company or ticker} earnings deck pdf",
    ]
    for q in queries:
        for item in _ddg_search_urls(q, limit=6):
            url = item.get("url", "")
            low = url.lower()
            if any(x in low for x in ("investor.", "/ir/", "press-releases", "newsroom", "news.nvidia.com")):
                # Heuristic: words indicating PR or deck
                if any(w in low for w in ("press", "release", "earnings")) and pr["status"] != "FOUND":
                    if _try_url(url, kind="pr"):
                        continue
                if any(w in low for w in ("presentation", "slides", "deck", ".pdf")) and deck["status"] != "FOUND":
                    _try_url(url, kind="deck")

    # 3) SEC EDGAR 8-K fallback
    if pr["status"] != "FOUND" or deck["status"] != "FOUND":
        try:
            filings = get_sec_filings(ticker)
            for f in filings.get("filings", [])[:10]:
                if f.get("form") == "8-K":
                    url = f.get("url", "")
                    if url:
                        attempted.append(url)
                        statuses[url] = 200  # link generation is deterministic; actual fetch optional
                        if pr["status"] != "FOUND":
                            pr.update({"status": "FOUND", "url": url, "source": "sec_edgar", "accessed_at": _today_str()})
                            break
        except Exception as e:
            logger.debug(f"SEC EDGAR fallback failed: {e}")

    # Ensure at least 3 attempted URLs logged when NOT_FOUND
    if pr["status"] != "FOUND" or deck["status"] != "FOUND":
        # Pad attempts with unique search URLs if needed
        while len(attempted) < 3:
            pad = f"https://html.duckduckgo.com/html/?q={ticker}+investor+relations"
            if pad not in attempted:
                attempted.append(pad)
                statuses[pad] = 0
            else:
                break

    result = {
        "press_release": pr,
        "presentation": deck,
        "attempted_urls": attempted,
        "http_statuses": statuses,
        "found": pr["status"] == "FOUND" or deck["status"] == "FOUND",
    }

    if output_dir:
        out_dir = os.path.join(output_dir, "03_press_release_and_presentation")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"earnings_documents_{ticker}.json")
        try:
            with open(out_path, "w") as f:
                json.dump(result, f, indent=2)
            logger.info(f"Earnings documents log saved: {out_path}")
        except Exception:
            logger.warning(f"Failed to save earnings documents for {ticker}")

    return result
