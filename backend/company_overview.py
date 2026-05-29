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


def overview_cache_info(ticker: str, language: str) -> Dict[str, Any]:
    """Return cache metadata: whether cached, age, timestamp, TTL.

    Used by the frontend to show cache freshness and allow flushing.
    """
    path = _overview_cache_path(ticker, language)
    if not path.exists():
        return {"cached": False, "ticker": ticker.upper(), "language": language,
                "ttl_days": OVERVIEW_CACHE_TTL / 86400}

    try:
        with open(path) as f:
            entry = json.load(f)
        ts = entry.get("timestamp", 0)
        age = datetime.now(timezone.utc).timestamp() - ts
        return {
            "cached": True,
            "ticker": ticker.upper(),
            "language": language,
            "cache_version": entry.get("version"),
            "cached_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "age_seconds": round(age),
            "age_days": round(age / 86400, 1),
            "ttl_seconds": OVERVIEW_CACHE_TTL,
            "ttl_days": OVERVIEW_CACHE_TTL / 86400,
            "expired": age > OVERVIEW_CACHE_TTL,
        }
    except Exception as e:
        logger.warning(f"Overview cache info error for {ticker}/{language}: {e}")
        return {"cached": False, "ticker": ticker.upper(), "language": language,
                "error": str(e), "ttl_days": OVERVIEW_CACHE_TTL / 86400}


def overview_cache_flush(ticker: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Delete cached overview(s). If language is None, flush all languages for this ticker.

    Returns summary of what was deleted.
    """
    deleted = []
    not_found = []

    if language:
        languages = [language]
    else:
        # Discover all language variants for this ticker
        languages = []
        raw_pattern = f"company_overview_{ticker.upper()}_"
        for p in CACHE_DIR.glob(f"{raw_pattern}*_v{OVERVIEW_CACHE_VERSION}.json"):
            # Extract language from filename: company_overview_AAPL_en_v1.json → en
            stem = p.stem  # company_overview_AAPL_en_v1
            parts = stem.split("_")
            if len(parts) >= 4:
                languages.append(parts[-2])  # "en" or "jp"

    for lang in languages:
        path = _overview_cache_path(ticker, lang)
        if path.exists():
            try:
                path.unlink()
                deleted.append(lang)
                logger.info(f"Overview cache FLUSHED for {ticker}/{lang}")
            except Exception as e:
                logger.warning(f"Overview cache flush error for {ticker}/{lang}: {e}")
        else:
            not_found.append(lang)

    return {
        "ticker": ticker.upper(),
        "deleted": deleted,
        "not_found": not_found,
        "cache_version": OVERVIEW_CACHE_VERSION,
    }


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
  "business_description": "2-3 sentences describing what the company does.",
  "revenue_model": "2-3 sentences explaining how the company makes money (major revenue engines).",
  "business_segments": ["segment 1", "segment 2"],
  "growth_drivers": ["driver 1", "driver 2", "driver 3"],
  "moats": ["moat 1", "moat 2"],
  "key_kpis": ["KPI 1 with value if known", "KPI 2 with value if known"],
  "business_risks": ["risk 1", "risk 2", "risk 3"],
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
  "competitive_position": "2-3 sentences analyzing market position, advantages, and threats.",
  "strengths_vs_competitors": "2-3 sentences on strengths relative to direct peers.",
  "weaker_areas_vs_competitors": "2-3 sentences on weaker areas vs peers.",
  "client_types": "2-3 sentences describing main customer types and end markets.",
  "management_weaknesses": "2-3 sentences on management team weaknesses, turnover, or governance risks.",
  "investor_takeaway": "2-3 sentence bottom-line investment takeaway summarizing the bull/bear case balance.",
  "ceo_leadership_style": "2-3 sentences on leadership style based on public signals.",
  "long_term_vision": "2-3 sentences on long-term strategy and vision.",
  "competitors": [
    {{
      "competitor_name": "competitor ticker/name",
      "text_en": "short comparative note",
      "text_jp": "",
      "source_id": "S1",
      "competitive_advantage": "what this company does better"
    }}
  ],
  "company_claims": [
    {{
      "claim_id": "C1",
      "text_en": "investor-relevant claim",
      "text_jp": "",
      "source_id": "S1",
      "section": "growth_drivers",
      "confidence": "medium"
    }}
  ]
}}

RULES:
- Use actual numbers from Yahoo Finance when available. If a field is missing, use null (not "N/A" or 0) for numbers.
- For list fields, always return arrays (possibly empty), never strings.
- Keep each bullet concise and investor-facing; avoid marketing language.
- business_segments should cover major business lines/geographies when known.
- growth_drivers, moats, key_kpis, and business_risks should be grounded in available data/news.
- recent_developments: pick 2-5 meaningful items from Tavily; write original summaries.
- strengths_vs_competitors and weaker_areas_vs_competitors must be balanced (not one-sided hype).
- ceo_leadership_style and long_term_vision: if evidence is weak, state uncertainty explicitly.

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
    text_fields: Dict[str, Any] = {
        "business_description": en_overview.get("business_description", ""),
        "revenue_model": en_overview.get("revenue_model", ""),
        "competitive_position": en_overview.get("competitive_position", ""),
        "strengths_vs_competitors": en_overview.get("strengths_vs_competitors", ""),
        "weaker_areas_vs_competitors": en_overview.get("weaker_areas_vs_competitors", ""),
        "ceo_leadership_style": en_overview.get("ceo_leadership_style", ""),
        "long_term_vision": en_overview.get("long_term_vision", ""),
    }

    list_fields = [
        "business_segments",
        "growth_drivers",
        "moats",
        "key_kpis",
        "business_risks",
    ]
    for field in list_fields:
        values = en_overview.get(field, []) or []
        if isinstance(values, list):
            for i, item in enumerate(values[:12]):
                text_fields[f"{field}_{i}"] = str(item)

    # Translate recent_developments summaries
    devs = en_overview.get("recent_developments", [])
    for i, dev in enumerate(devs[:8]):
        text_fields[f"dev_{i}_title"] = dev.get("title", "")
        text_fields[f"dev_{i}_summary"] = dev.get("summary", "")

    # Translate competitors free text fields
    competitors = en_overview.get("competitors", []) or []
    for i, comp in enumerate(competitors[:8]):
        text_fields[f"comp_{i}_text_en"] = comp.get("text_en", "")
        text_fields[f"comp_{i}_adv"] = comp.get("competitive_advantage", "")

    # Translate company claims
    claims = en_overview.get("company_claims", []) or []
    for i, claim in enumerate(claims[:16]):
        text_fields[f"claim_{i}_text_en"] = claim.get("text_en", "")

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

Return a JSON object with the SAME keys but Japanese values.
Return ONLY the JSON object."""

    system = "You are a professional financial translator specializing in English→Japanese. You return ONLY valid JSON with translated fields. Natural Japanese, no machine-translation feel."

    response = _codex_chat(prompt, system=system, max_tokens=2400)

    if not response:
        logger.warning(f"JP translation LLM unavailable for {ticker} — returning EN content")
        return _wrap_jp_fallback(en_overview)

    translated = _parse_llm_response(response, ticker, {})
    if translated is None:
        return _wrap_jp_fallback(en_overview)

    # Build JP overview: copy structure, replace text fields with translations
    jp = json.loads(json.dumps(en_overview, default=str))  # deep copy

    for key in (
        "business_description",
        "revenue_model",
        "competitive_position",
        "strengths_vs_competitors",
        "weaker_areas_vs_competitors",
        "ceo_leadership_style",
        "long_term_vision",
    ):
        jp[key] = translated.get(key, en_overview.get(key, ""))

    # Replace list fields
    for field in list_fields:
        current = jp.get(field, []) or []
        if not isinstance(current, list):
            current = []
        rebuilt = []
        for i, item in enumerate(current[:12]):
            rebuilt.append(translated.get(f"{field}_{i}", item))
        jp[field] = rebuilt

    # Replace development titles and summaries
    for i, dev in enumerate(jp.get("recent_developments", [])[:8]):
        dev["title"] = translated.get(f"dev_{i}_title", dev.get("title", ""))
        dev["summary"] = translated.get(f"dev_{i}_summary", dev.get("summary", ""))

    # Replace competitor text fields
    for i, comp in enumerate(jp.get("competitors", [])[:8]):
        comp["text_jp"] = translated.get(f"comp_{i}_text_en", comp.get("text_jp") or comp.get("text_en", ""))
        if comp.get("competitive_advantage"):
            comp["competitive_advantage"] = translated.get(f"comp_{i}_adv", comp.get("competitive_advantage"))

    # Replace claim bilingual text
    for i, claim in enumerate(jp.get("company_claims", [])[:16]):
        claim["text_jp"] = translated.get(f"claim_{i}_text_en", claim.get("text_jp") or claim.get("text_en", ""))

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

    def _ensure_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if item is None:
                    continue
                s = str(item).strip()
                if s:
                    out.append(s)
            return out
        if isinstance(value, str):
            # tolerate newline/comma-separated output
            parts = [p.strip(" -•\t") for p in value.replace("\r", "\n").split("\n")]
            items = [p for p in parts if p]
            if len(items) <= 1 and "," in value:
                items = [p.strip() for p in value.split(",") if p.strip()]
            return items
        return [str(value)]

    try:
        data = json.loads(text)
        data.setdefault("company_profile", {})
        data.setdefault("business_description", "")
        data.setdefault("revenue_model", "")
        data.setdefault("business_segments", [])
        data.setdefault("growth_drivers", [])
        data.setdefault("moats", [])
        data.setdefault("key_kpis", [])
        data.setdefault("business_risks", [])
        data.setdefault("key_financials", {})
        data.setdefault("recent_developments", [])
        data.setdefault("competitive_position", "")
        data.setdefault("strengths_vs_competitors", "")
        data.setdefault("weaker_areas_vs_competitors", "")
        data.setdefault("ceo_leadership_style", "")
        data.setdefault("long_term_vision", "")
        data.setdefault("competitors", [])
        data.setdefault("company_claims", [])

        for list_key in ("business_segments", "growth_drivers", "moats", "key_kpis", "business_risks"):
            data[list_key] = _ensure_str_list(data.get(list_key))

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
    """Build a deterministic investor-oriented overview when LLM is unavailable."""
    mc = yf_info.get("market_cap")
    rev = yf_info.get("total_revenue")
    desc = (yf_info.get("description") or "").strip()

    def _first_sentences(text: str, max_sentences: int = 2) -> str:
        if not text:
            return ""
        parts = [p.strip() for p in text.replace("\n", " ").split(".") if p.strip()]
        return ". ".join(parts[:max_sentences]) + ("." if parts else "")

    business_description = desc[:3000] if desc else f"{ticker} — data from Yahoo Finance."
    revenue_model = _first_sentences(desc, max_sentences=3) or (
        "Revenue model could not be reliably synthesized because LLM synthesis was unavailable."
    )

    sector = yf_info.get("sector")
    industry = yf_info.get("industry")
    business_segments: list[str] = []

    # Try extracting explicit segment names from longBusinessSummary text
    lower_desc = desc.lower()
    marker = "operates through "
    if marker in lower_desc and " segment" in lower_desc:
        start = lower_desc.find(marker) + len(marker)
        end = lower_desc.find(" segment", start)
        if end > start:
            segment_blob = desc[start:end]
            raw_parts = segment_blob.replace(" and ", ",").split(",")
            parsed_segments = [p.strip(" .") for p in raw_parts if p.strip()]
            for seg in parsed_segments[:6]:
                business_segments.append(seg)

    if sector:
        business_segments.append(f"Primary sector exposure: {sector}.")
    if industry:
        business_segments.append(f"Core industry: {industry}.")

    # De-duplicate while preserving order
    dedup_segments: list[str] = []
    for seg in business_segments:
        if seg not in dedup_segments:
            dedup_segments.append(seg)
    business_segments = dedup_segments

    if not business_segments:
        business_segments.append("Business segment breakdown not available from current structured sources.")

    growth_drivers: list[str] = []
    rev_growth = yf_info.get("revenue_growth")
    earn_growth = yf_info.get("earnings_growth")
    if isinstance(rev_growth, (int, float)):
        growth_drivers.append(f"Revenue growth signal: {rev_growth * 100:+.1f}% YoY.")
    if isinstance(earn_growth, (int, float)):
        growth_drivers.append(f"Earnings growth signal: {earn_growth * 100:+.1f}% YoY.")
    if yf_info.get("enterprise_value") and yf_info.get("market_cap"):
        growth_drivers.append("Scale and enterprise footprint support continued reinvestment capacity.")
    if not growth_drivers:
        growth_drivers.append("Detailed growth drivers require transcript/news synthesis (currently unavailable).")

    moats: list[str] = []
    if "cloud" in lower_desc:
        moats.append("Cloud platform scale and enterprise integration can create switching-cost advantages.")
    if "search" in lower_desc or "ads" in lower_desc or "advertis" in lower_desc:
        moats.append("Large user and advertiser ecosystems can reinforce network effects.")
    if "ai" in lower_desc:
        moats.append("AI infrastructure and model deployment capabilities may strengthen product differentiation.")
    if industry and not moats:
        moats.append(f"Industry positioning in {industry} may support durable competitive advantages.")
    if yf_info.get("website"):
        moats.append("Brand and distribution reach inferred from global platform presence.")
    if not moats:
        moats.append("Competitive moat assessment requires additional qualitative evidence.")

    key_kpis: list[str] = []
    if mc is not None:
        key_kpis.append(f"Market Cap: {_format_currency(mc)}")
    if rev is not None:
        key_kpis.append(f"Revenue: {_format_currency(rev)}")
    if yf_info.get("pe_trailing") is not None:
        key_kpis.append(f"Trailing P/E: {float(yf_info['pe_trailing']):.1f}x")
    if yf_info.get("pe_forward") is not None:
        key_kpis.append(f"Forward P/E: {float(yf_info['pe_forward']):.1f}x")
    if yf_info.get("52w_high") is not None and yf_info.get("52w_low") is not None:
        key_kpis.append(f"52W range: ${float(yf_info['52w_low']):.2f}–${float(yf_info['52w_high']):.2f}")
    if not key_kpis:
        key_kpis.append("KPI extraction unavailable from current market snapshot.")

    business_risks: list[str] = []
    beta = yf_info.get("beta")
    if isinstance(beta, (int, float)) and beta > 1.2:
        business_risks.append(f"Above-market volatility risk (beta {beta:.2f}).")
    if isinstance(rev_growth, (int, float)) and rev_growth < 0:
        business_risks.append("Negative revenue momentum may pressure valuation multiples.")
    business_risks.append("Qualitative execution risks (competition/regulation/leadership) require transcript-level validation.")

    strengths_parts: list[str] = []
    if mc and mc >= 1e12:
        strengths_parts.append("Very large scale provides capital and distribution advantages")
    if rev and rev >= 1e11:
        strengths_parts.append("high absolute revenue base supports sustained reinvestment")
    if isinstance(rev_growth, (int, float)) and rev_growth > 0:
        strengths_parts.append(f"positive revenue momentum ({rev_growth * 100:+.1f}% YoY)")
    strengths_vs = "; ".join(strengths_parts) if strengths_parts else (
        "Financial scale and market presence appear to be the main relative strengths in available data"
    )

    weaker_parts: list[str] = []
    pe_trailing = yf_info.get("pe_trailing")
    if isinstance(pe_trailing, (int, float)) and pe_trailing > 30:
        weaker_parts.append("valuation is sensitive to execution because trailing multiples are elevated")
    if isinstance(beta, (int, float)) and beta > 1.2:
        weaker_parts.append("share-price volatility is above market average")
    if "other bets" in lower_desc:
        weaker_parts.append("non-core initiatives may dilute near-term margin focus")
    weaker_vs = "; ".join(weaker_parts) if weaker_parts else (
        "No clear structural weakness inferred from the limited fallback dataset"
    )

    ceo_style = (
        "Leadership appears portfolio-oriented, balancing core cash-generating segments with strategic AI and platform investment; "
        "detailed assessment still requires transcript-level management commentary."
    )

    long_term_vision = (
        "Long-term strategy appears centered on scaling AI-enabled products across core platforms, expanding cloud monetization, "
        "and funding selective long-horizon bets from strong cash generation."
    )

    client_types = (
        "Client and end-market segmentation could not be reliably synthesized "
        "because LLM synthesis was unavailable. Based on available data, customers "
        "appear to span enterprise, cloud, consumer, and automotive end markets."
    )

    management_weaknesses = (
        "Specific management weaknesses and governance risks could not be reliably assessed "
        "because LLM synthesis was unavailable. Detailed evaluation requires transcript-level "
        "management commentary and governance analysis."
    )

    investor_takeaway = (
        "A balanced investment takeaway could not be reliably synthesized "
        "because LLM synthesis was unavailable. Key factors to weigh include "
        "valuation multiples, revenue growth momentum, competitive positioning, "
        "and the durability of business moats."
    )

    return {
        "company_profile": {
            "name": yf_info.get("name", ticker),
            "ticker": ticker,
            "sector": sector,
            "industry": industry,
            "country": yf_info.get("country"),
            "website": yf_info.get("website"),
            "employees": yf_info.get("employees"),
            "founded": None,
            "headquarters": yf_info.get("headquarters"),
        },
        "business_description": business_description,
        "revenue_model": revenue_model,
        "business_segments": business_segments,
        "growth_drivers": growth_drivers,
        "moats": moats,
        "key_kpis": key_kpis,
        "business_risks": business_risks,
        "key_financials": {
            "market_cap": mc,
            "market_cap_display": _format_currency(mc),
            "revenue": rev,
            "revenue_display": _format_currency(rev),
            "pe_ratio": yf_info.get("pe_trailing"),
            "pe_forward": yf_info.get("pe_forward"),
            "dividend_yield": yf_info.get("dividend_yield"),
            "beta": beta,
            "52w_high": yf_info.get("52w_high"),
            "52w_low": yf_info.get("52w_low"),
        },
        "recent_developments": [],
        "competitive_position": "LLM synthesis unavailable — using deterministic fallback from market snapshot.",
        "strengths_vs_competitors": strengths_vs,
        "weaker_areas_vs_competitors": weaker_vs,
        "client_types": client_types,
        "management_weaknesses": management_weaknesses,
        "investor_takeaway": investor_takeaway,
        "ceo_leadership_style": ceo_style,
        "long_term_vision": long_term_vision,
        "competitors": [],
        "company_claims": [],
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
