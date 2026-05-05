"""RapidAPI Seeking Alpha transcript adapter."""
import html
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from backend.http_client import http

logger = logging.getLogger(__name__)

DEFAULT_HOST = "seeking-alpha.p.rapidapi.com"
LIST_ENDPOINT = "gettranscripts/v2/list"
DETAIL_ENDPOINT = "gettranscripts/v2/get-details"


def get_api_key() -> str:
    """Return the configured RapidAPI key, or an empty string when disabled."""
    return os.getenv("RAPIDAPI_KEY", "").strip()


def get_host() -> str:
    """Return the RapidAPI Seeking Alpha host.

    APIDojo's public RapidAPI host is used by default. The host is configurable
    because RapidAPI providers can publish compatible Seeking Alpha feeds under
    different host names.
    """
    return os.getenv("RAPIDAPI_SEEKING_ALPHA_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST


def search_sa_transcripts(ticker: str) -> List[Dict[str, str]]:
    """
    Return available Seeking Alpha transcripts for a ticker via RapidAPI.

    Output format:
        [{id, title, date, quarter, url}]
    """
    data = _rapidapi_get(
        LIST_ENDPOINT,
        {
            "symbol": ticker.upper(),
            "size": 10,
            "number": 1,
        },
    )
    if not data:
        return []

    transcripts = []
    for item in _extract_items(data):
        record = _flatten_record(item)
        transcript_id = _coerce_str(_first(record, "id", "transcriptId", "transcript_id", "articleId"))
        if not transcript_id:
            continue
        transcripts.append(
            {
                "id": transcript_id,
                "title": _coerce_str(_first(record, "title", "name", "headline")),
                "date": _normalize_date(_first(record, "date", "publishOn", "publishedOn", "published_at")),
                "quarter": _coerce_str(_first(record, "quarter", "fiscalQuarter", "period")),
                "url": _normalize_url(_first(record, "url", "link"), transcript_id),
            }
        )

    return transcripts


def fetch_sa_transcript(transcript_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full transcript text and metadata from RapidAPI Seeking Alpha.

    Output format:
        {id, title, date, quarter, url, content, source}
    """
    data = _rapidapi_get(DETAIL_ENDPOINT, {"id": transcript_id})
    if not data:
        return None

    record = _flatten_record(_extract_record(data))
    content = _extract_text(record)
    if not content:
        logger.info(f"RapidAPI Seeking Alpha transcript {transcript_id} has no text")
        return None

    return {
        "id": _coerce_str(_first(record, "id")) or str(transcript_id),
        "title": _coerce_str(_first(record, "title", "name", "headline")),
        "date": _normalize_date(_first(record, "date", "publishOn", "publishedOn", "published_at")),
        "quarter": _coerce_str(_first(record, "quarter", "fiscalQuarter", "period")),
        "url": _normalize_url(_first(record, "url", "link"), str(transcript_id)),
        "content": content,
        "source": "rapidapi_seeking_alpha",
    }


def _rapidapi_get(endpoint: str, params: Dict[str, Any]) -> Optional[Any]:
    api_key = get_api_key()
    if not api_key:
        return None

    host = get_host()
    url = f"https://{host}/{endpoint}"
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": host,
    }

    try:
        response = http.get(url, params=params, headers=headers, timeout=15)
    except httpx.RequestError as exc:
        logger.warning(f"RapidAPI Seeking Alpha request failed for {endpoint}: {exc}")
        return None

    if response.status_code != 200:
        logger.warning(
            f"RapidAPI Seeking Alpha {endpoint} returned HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )
        return None

    try:
        return response.json()
    except ValueError as exc:
        logger.warning(f"RapidAPI Seeking Alpha {endpoint} returned invalid JSON: {exc}")
        return None


def _extract_items(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("data", "transcripts", "items", "results", "response", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested

    if _first(payload, "id", "transcriptId", "transcript_id", "articleId"):
        return [payload]
    return []


def _extract_record(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list):
        return payload[0] if payload and isinstance(payload[0], dict) else {}
    if not isinstance(payload, dict):
        return {}

    for key in ("data", "transcript", "article", "result", "response"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]

    return payload


def _flatten_record(record: Any) -> Dict[str, Any]:
    if not isinstance(record, dict):
        return {}

    flattened = dict(record)
    attributes = record.get("attributes")
    if isinstance(attributes, dict):
        flattened.update(attributes)
    meta = record.get("meta")
    if isinstance(meta, dict):
        for key, value in meta.items():
            flattened.setdefault(key, value)
    return flattened


def _extract_text(record: Dict[str, Any]) -> str:
    for key in ("content", "transcript", "text", "body", "fullText", "article"):
        text = _text_from_value(record.get(key))
        if text:
            return text
    return ""


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                speaker = _coerce_str(_first(item, "speaker", "speakerName", "name", "title"))
                text = _text_from_value(_first(item, "content", "text", "body"))
                if text and speaker:
                    parts.append(f"{speaker}: {text}")
                elif text:
                    parts.append(text)
            else:
                text = _text_from_value(item)
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        for key in ("content", "transcript", "text", "body", "fullText"):
            text = _text_from_value(value.get(key))
            if text:
                return text
    return ""


def _clean_text(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _normalize_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""

    text = str(value).strip()
    if not text:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    return text


def _normalize_url(value: Any, transcript_id: str) -> str:
    url = _coerce_str(value)
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return f"https://seekingalpha.com{url}"
    return f"https://seekingalpha.com/article/{transcript_id}"


def _first(record: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return ""


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
