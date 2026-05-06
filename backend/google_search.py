"""Google Custom Search adapter for transcript discovery.

Disabled unless GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID are set.
"""
import logging
import os
from typing import Any, Dict, List

import httpx

from backend.http_client import http

logger = logging.getLogger(__name__)


def search_google(query: str, limit: int = 5) -> List[Dict[str, str]]:
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
    engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()
    if not api_key or not engine_id:
        return []

    try:
        response = http.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": api_key, "cx": engine_id, "q": query, "num": min(limit, 10)},
            timeout=15,
        )
    except httpx.RequestError as exc:
        logger.warning(f"Google transcript search request failed: {exc}")
        return []

    if response.status_code != 200:
        logger.warning(f"Google transcript search returned HTTP {response.status_code}")
        return []

    try:
        payload: Dict[str, Any] = response.json()
    except ValueError:
        return []

    results: List[Dict[str, str]] = []
    for item in payload.get("items", [])[:limit]:
        link = str(item.get("link") or "").strip()
        if not link:
            continue
        results.append(
            {
                "title": str(item.get("title") or "").strip(),
                "url": link,
                "snippet": str(item.get("snippet") or "").strip(),
            }
        )
    return results
