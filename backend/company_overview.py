"""
Company Overview Service — fetches yfinance + Tavily data,
synthesizes via LLM into structured JSON, caches for 7 days.

async get_company_overview(ticker, language="en") → Dict[str, Any]

⚠️ LANGUAGE SEPARATION:
  Step 1 — English: LLM generates EN content → cache
  Step 2 — Japanese: translate EN content via separate LLM call → cache
  NEVER generate mixed-language content in a single LLM call.

Phases:
  1. yfinance Ticker.info + Tavily web search
  2. LLM synthesis to strict JSON (EN only)
  3. Optional: LLM translation to JP (separate call)
  4. 7-day file-based JSON cache (ticker + language keyed)
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ── Cache layer ───────────────────────────────────────────────────────────
# Cache key format: company_overview:{ticker}:en:v1 / company_overview:{ticker}:jp:v1

CACHE_DIR = Path(__file__).parent / ".cache"
OVERVIEW_CACHE_TTL = 7 * 24 * 3600  # 7 days
OVERVIEW_CACHE_VERSION = 1  # bump to invalidate all cached overviews


def _overview_cache_path(ticker: str, language: str) -> Path:
    """Cache file: .cache/company_overview_AAPL_en_v1.json"""
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"company_overview_{ticker.upper()}_{language}_v{OVERVIEW_CACHE_VERSION}.json"


def _overview_cache_get(ticker: str, language: str) -> Optional[Dict[str, Any]]:
    """Read cached overview if fresh and version matches."""
    path = _overview_cache_path(ticker, language)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            entry = json.load(f)
        if entry.get("version") != OVERVIEW_CACHE_VERSION:
            logger.info(f"Overview cache VERSION mismatch for {ticker}/{language}")
            return None
        age = datetime.now(timezone.utc).timestamp() - entry.get("timestamp", 0)
        if age > OVERVIEW_CACHE_TTL:
            logger.info(f"Overview cache EXPIRED for {ticker}/{language} (age: {age/86400:.1f}d)")
            return None
        logger.info(f"Overview cache HIT for {ticker}/{language} (age: {age/86400:.1f}d)")
        return entry["data"]
    except Exception as e:
        logger.debug(f"Overview cache read error for {ticker}/{language}: {e}")
    return None


def _overview_cache_set(ticker: str, language: str, data: Dict[str, Any]) -> None:
    """Write overview to cache with version stamp."""
    try:
        entry = {
            "version": OVERVIEW_CACHE_VERSION,
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "data": data,
        }
        with open(_overview_cache_path(ticker, language), "w") as f:
            json.dump(entry, f, default=str)
        logger.info(f"Overview cache SET for {ticker}/{language}")
    except Exception as e:
        logger.warning(f"Overview cache SET failed for {ticker}/{language}: {e}")


# ── Phase 1: Data fetching ────────────────────────────────────────────────


async def _fetch_yahoo_info(ticker: str) -> Dict[str, Any]:
    """Fetch yfinance Ticker.info for a ticker.

    Wraps synchronous yfinance call in a thread to avoid blocking.
    """
    import asyncio
    import concurrent.futures

    def _sync_fetch():
        import yfinance as yf  # lazy import — slow startup
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        return _build_yahoo_info_dict(ticker, info)

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return await loop.run_in_executor(pool, _sync_fetch)
        except Exception as e:
            logger.warning(f"yfinance fetch failed for {ticker}: {e}")
            return {"ticker": ticker, "error": str(e)}


def _build_yahoo_info_dict(ticker: str, info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured company data from yfinance Ticker.info."""
    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
        "description": (info.get("longBusinessSummary") or "")[:3000] or None,
        # Financial metrics
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
        "pe_trailing": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "total_revenue": info.get("totalRevenue"),
        "currency": info.get("currency", "USD"),
        "exchange": info.get("exchange"),
        # Location
        "headquarters": _format_headquarters(info),
    }


def _format_headquarters(info: Dict[str, Any]) -> Optional[str]:
    """Format city, state, country into a display string."""
    parts = []
    for key in ("city", "state", "country"):
        val = info.get(key)
        if val:
            parts.append(val)
    return ", ".join(parts) if parts else None


async def _search_tavily_overview(ticker: str, yf_info: Dict[str, Any]) -> List[Dict[str, str]]:
    """Search Tavily for recent company news and developments."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.debug(f"Tavily skipped for {ticker} overview — TAVILY_API_KEY not set")
        return []

    import asyncio
    import concurrent.futures

    def _sync_search():
        from backend.http_client import http

        company_name = yf_info.get("name", ticker)
        queries = [
            f"{company_name} latest news 2026",
            f"{company_name} recent developments products",
        ]
        all_results = []

        for query in queries:
            try:
                resp = http.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": 5,
                        "search_depth": "basic",
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get("results", [])[:5]:
                        all_results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": (r.get("content", "") or "")[:500],
                            "date": r.get("published_date", ""),
                        })
                else:
                    logger.warning(f"Tavily search HTTP {resp.status_code} for {ticker}")
            except Exception as e:
                logger.warning(f"Tavily search failed for {ticker}: {e}")

        seen = set()
        unique = []
        for item in all_results:
            if item["url"] not in seen:
                seen.add(item["url"])
                unique.append(item)
        return unique[:8]

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return await loop.run_in_executor(pool, _sync_search)
        except Exception as e:
            logger.warning(f"Tavily overview search failed for {ticker}: {e}")
            return []


# ── Phase 2: LLM synthesis (EN only) ──────────────────────────────────────


def _synthesize_overview_en(
    ticker: str,
    yf_info: Dict[str, Any],
    tavily_results: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Step 1 — English: LLM generates structured company overview in English.

    Returns a dict matching the company_overview schema with text_en fields.
    """
    from backend.codex_provider import _codex_chat

    yf_str = json.dumps(yf_info, indent=2, default=str)

    if tavily_results:
        items = []
        for r in tavily_results[:8]:
            items.append(f"- {r['title']}\n  URL: {r['url']}\n  {r['content'][:300]}")
        tavily_str = "\n".join(items)
    else:
        tavily_str = "(No recent news results available)"

    prompt = f"""Synthesize a professional company overview for {yf_info.get('name', ticker)} ({ticker}) in English.

Data from Yahoo Finance:
```json
{yf_str}
```

Recent web search results:
{tavily_str}

Return ONLY a valid JSON object (no markdown, no explanation) with EXACTLY this structure:

{{
  "company_profile": {{
    "name": "full company name",
    "ticker": "{ticker}",
    "sector": "sector name",
    "industry": "industry name",
    "country": "country name",
    "website": "URL",
    "employees": 12345,
    "founded": null,
    "headquarters": "City, State, Country"
  }},
  "business_description": "2-3 sentences describing what the company does, its main products/services, and its business model. Be concise and professional.",
  "key_financials": {{
    "market_cap": 1230000000000,
    "market_cap_display": "$1.23T",
    "revenue": 383000000000,
    "revenue_display": "$383.0B",
    "pe_ratio": 30.5,
    "pe_forward": 28.0,
    "dividend_yield": 0.0052,
    "beta": 1.25,
    "52w_high": 199.62,
    "52w_low": 124.17
  }},
  "recent_developments": [
    {{
      "title": "descriptive title",
      "summary": "1-2 sentence summary in English",
      "date": "YYYY-MM-DD if known, else omit",
      "sentiment": "positive|neutral|negative"
    }}
  ],
  "competitive_position": "2-3 sentences analyzing the company's market position, competitive advantages, and threats. Data-backed assessment."
}}

RULES:
- Use actual numbers from the Yahoo Finance data when available. If a field is missing, use null (not "N/A" or 0).
- Format large numbers with standard suffixes (B for billions, T for trillions) in the _display fields.
- business_description: synthesize from longBusinessSummary + your knowledge. Don't just repeat raw data.
- recent_developments: synthesize from Tavily search results. Pick 3-5 most important items. Write original summaries — don't copy-paste raw content.
- competitive_position: synthesize from ALL available data (company profile + financials + news). Be analytical, not promotional.
- sentiment: assess each development as positive, neutral, or negative from an investor's perspective.

Return ONLY the JSON object. No markdown fences, no explanations."""

    system = "You are a senior equity research analyst synthesizing company overviews. You write in English. You return ONLY valid JSON with no markdown fences."

    response = _codex_chat(prompt, system=system, max_tokens=2500)

    if response:
        parsed = _parse_llm_response(response, ticker, yf_info)
        return parsed if parsed is not None else _fallback_overview(ticker, yf_info)
    else:
        return _fallback_overview(ticker, yf_info)


def _translate_overview_to_jp(en_overview: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Step 2 — Japanese: translate EN overview text fields to JP via separate LLM call.

    NEVER generate mixed-language content. This is a standalone translation call.
    Only text fields are translated; numeric data and structure are preserved.
    """
    from backend.codex_provider import _codex_chat

    # Build a compact representation of text fields that need translation
    text_fields = {
        "business_description": en_overview.get("business_description", ""),
        "competitive_position": en_overview.get("competitive_position", ""),
    }

    # Translate recent_developments summaries
    devs = en_overview.get("recent_developments", [])
    for i, dev in enumerate(devs):
        text_fields[f"dev_{i}_title"] = dev.get("title", "")
        text_fields[f"dev_{i}_summary"] = dev.get("summary", "")

    prompt = f"""Translate the following English company overview text fields into professional Japanese (日本語).

Translation rules:
- Use natural, financial-analyst-level Japanese. No machine-translation feel.
- Preserve all factual information and numerical precision.
- Company names and tickers remain in English.
- For recent_developments sentiment, keep as "positive", "neutral", or "negative" in English.
- Return ONLY a valid JSON object with the translated fields. No markdown, no explanations.

Fields to translate:
```json
{json.dumps(text_fields, indent=2, ensure_ascii=False)}
```

Return a JSON object with the SAME keys but Japanese values:
{{
  "business_description": "(Japanese translation)",
  "competitive_position": "(Japanese translation)",
  "dev_0_title": "(Japanese translation)",
  "dev_0_summary": "(Japanese translation)",
  ...
}}

Return ONLY the JSON object."""

    system = "You are a professional financial translator specializing in English→Japanese. You return ONLY valid JSON with translated fields. Natural Japanese, no machine-translation feel."

    response = _codex_chat(prompt, system=system, max_tokens=2000)

    if not response:
        logger.warning(f"JP translation LLM unavailable for {ticker} — returning EN content")
        return _wrap_jp_fallback(en_overview)

    translated = _parse_llm_response(response, ticker, {})
    if translated is None:
        return _wrap_jp_fallback(en_overview)

    # Build JP overview: copy structure, replace text fields with translations
    jp = json.loads(json.dumps(en_overview, default=str))  # deep copy
    jp["business_description"] = translated.get("business_description", en_overview.get("business_description", ""))
    jp["competitive_position"] = translated.get("competitive_position", en_overview.get("competitive_position", ""))

    # Replace development titles and summaries
    for i, dev in enumerate(jp.get("recent_developments", [])):
        dev["title"] = translated.get(f"dev_{i}_title", dev.get("title", ""))
        dev["summary"] = translated.get(f"dev_{i}_summary", dev.get("summary", ""))

    return jp


def _wrap_jp_fallback(en_overview: Dict[str, Any]) -> Dict[str, Any]:
    """When JP translation fails, return EN content with a marker."""
    result = json.loads(json.dumps(en_overview, default=str))
    result["_translation_note"] = "JP translation unavailable — showing EN content"
    return result


# ── Parsing and fallback ──────────────────────────────────────────────────


def _parse_llm_response(response: str, ticker: str, yf_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse LLM JSON response, stripping markdown fences if present.

    Returns None if parsing fails (caller should use fallback).
    """
    text = response.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    # Extract JSON object bounds
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        data = json.loads(text)
        data.setdefault("company_profile", {})
        data.setdefault("business_description", "")
        data.setdefault("key_financials", {})
        data.setdefault("recent_developments", [])
        data.setdefault("competitive_position", "")
        # ── Normalize dividend_yield: LLM may output percentage (0.23) instead of decimal (0.0023) ──
        kf = data.get("key_financials", {})
        dy = kf.get("dividend_yield")
        if isinstance(dy, (int, float)) and dy is not None and dy > 0.5:
            # > 50% dividend is nearly impossible → LLM used percentage form, convert to decimal
            logger.info(f"Normalizing dividend_yield: {dy} → {dy/100:.6f} for {ticker}")
            kf["dividend_yield"] = round(dy / 100, 6)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"LLM JSON parse failed for {ticker}: {e} | raw: {response[:200]}")
        return None


def _fallback_overview(ticker: str, yf_info: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal overview from raw data when LLM is unavailable."""
    mc = yf_info.get("market_cap")
    rev = yf_info.get("total_revenue")
    return {
        "company_profile": {
            "name": yf_info.get("name", ticker),
            "ticker": ticker,
            "sector": yf_info.get("sector"),
            "industry": yf_info.get("industry"),
            "country": yf_info.get("country"),
            "website": yf_info.get("website"),
            "employees": yf_info.get("employees"),
            "founded": None,
            "headquarters": yf_info.get("headquarters"),
        },
        "business_description": yf_info.get("description") or f"{ticker} — data from Yahoo Finance.",
        "key_financials": {
            "market_cap": mc,
            "market_cap_display": _format_currency(mc),
            "revenue": rev,
            "revenue_display": _format_currency(rev),
            "pe_ratio": yf_info.get("pe_trailing"),
            "pe_forward": yf_info.get("pe_forward"),
            "dividend_yield": yf_info.get("dividend_yield"),
            "beta": yf_info.get("beta"),
            "52w_high": yf_info.get("52w_high"),
            "52w_low": yf_info.get("52w_low"),
        },
        "recent_developments": [],
        "competitive_position": "LLM synthesis unavailable — raw data only.",
    }


def _format_currency(value) -> Optional[str]:
    """Format a number into human-readable currency string."""
    if value is None:
        return None
    if abs(value) >= 1e12:
        return f"${value/1e12:.2f}T"
    if abs(value) >= 1e9:
        return f"${value/1e9:.1f}B"
    if abs(value) >= 1e6:
        return f"${value/1e6:.0f}M"
    return f"${value:,.0f}"


# ── Main public API ───────────────────────────────────────────────────────


async def get_company_overview(ticker: str, language: str = "en") -> Dict[str, Any]:
    """Get structured company overview — cached for 7 days.

    ⚠️ LANGUAGE SEPARATION:
      EN: LLM generates English content directly.
      JP: First fetches/caches EN overview, then translates via separate LLM call.
      NEVER generates mixed-language content in a single LLM call.

    Args:
        ticker: Stock symbol (e.g. "AAPL", "NVDA")
        language: "en" (English) or "jp" (Japanese)

    Returns:
        Dict with keys: company_profile, business_description,
        key_financials, recent_developments, competitive_position
    """
    ticker = ticker.upper()
    lang = language.lower()
    if lang not in ("en", "jp"):
        logger.warning(f"Unsupported language '{language}', defaulting to 'en'")
        lang = "en"

    # ── Check cache ─────────────────────────────────────────────────
    cached = _overview_cache_get(ticker, lang)
    if cached is not None:
        return cached

    logger.info(f"Fetching company overview for {ticker}/{lang}...")

    # ── Phase 1: Fetch raw data ─────────────────────────────────────
    yf_info = await _fetch_yahoo_info(ticker)
    tavily_results = await _search_tavily_overview(ticker, yf_info)

    if lang == "en":
        # ── Phase 2a: LLM synthesis (EN) ────────────────────────────
        overview = _synthesize_overview_en(ticker, yf_info, tavily_results)
    else:
        # ── Phase 2b: EN → JP translation (two-step) ─────────────────
        # Step 1: Get English overview (from cache or generate)
        en_cached = _overview_cache_get(ticker, "en")
        if en_cached is None:
            en_cached = _synthesize_overview_en(ticker, yf_info, tavily_results)
            _overview_cache_set(ticker, "en", en_cached)

        # Step 2: Translate EN → JP via separate LLM call
        logger.info(f"Translating overview EN→JP for {ticker}...")
        overview = _translate_overview_to_jp(en_cached, ticker)

    # ── Cache and return ────────────────────────────────────────────
    _overview_cache_set(ticker, lang, overview)
    return overview
