"""Extract segment/revenue/backlog data from SEC XBRL filings via edgartools.

Free, unlimited, GAAP-compliant. Works for all US-listed companies.

Requirements: pip install edgartools
Note: MUST unset HTTPS_PROXY/HTTP_PROXY before importing edgar.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

EDGAR_IDENTITY = "Ced Control Center (ced.chatillon@gmail.com)"

_DISAGGREGATION_STATEMENTS = (
    "DisaggregationOfRevenue",
    "RevenueFromContractWithCustomerTextBlock",
    "RevenueRecognition",
)

_STOP_REVENUE_BLOCK_RE = re.compile(
    r"^(?:cost|gross|operating|research|selling|general|interest|income before|net income)",
    re.IGNORECASE,
)

_GENERIC_ROW_RE = re.compile(
    r"^(?:revenue|revenues|net revenue|net revenues|net sales|sales|total|"
    r"reportable segments?|segment|market|platform|"
    r"geographic|geographical|country|region|by product|by category|by segment)$",
    re.IGNORECASE,
)


def _clean_proxy_env():
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        os.environ.pop(key, None)


def _ensure_identity():
    _clean_proxy_env()
    from edgar import set_identity
    set_identity(EDGAR_IDENTITY)


def _extract_numbers(text: str) -> List[int]:
    """Extract all integer numbers from text (after removing $ and commas)."""
    nums = re.findall(r"(?<![\w.])\(?[\d,]+(?:\.\d+)?\)?", text.replace("$", ""))
    return [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]


def _clean_label(label: Any) -> str:
    text = re.sub(r"\s+", " ", str(label or "")).strip()
    text = text.replace("(in millions)", "").replace("$ in millions", "")
    text = text.replace(":", "").replace("(1)", "").replace("(2)", "")
    return re.sub(r"\s+", " ", text).strip(" -")


def _looks_like_total(label: str) -> bool:
    lowered = label.lower()
    return "total" in lowered and ("revenue" in lowered or "sales" in lowered)


def _is_candidate_label(label: str) -> bool:
    if not label or len(label) > 80:
        return False
    if any(ch.isdigit() for ch in label):
        return False
    lowered = label.lower()
    if _GENERIC_ROW_RE.match(label):
        return False
    if any(token in lowered for token in (
        "expense", "cost of", "gross margin", "operating income",
        "geographic", "country", "region",
        "united states", "china", "taiwan", "japan", "korea",
        "europe", "asia", "america", "international",
        "obligation", "retain", "beginning", "operating segment",
        "all other", "inventory", "retained",
    )):
        return False
    return True


def _numeric_value(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "")
    try:
        parsed = int(float(text))
    except ValueError:
        return None
    return -parsed if negative else parsed


def _row_amounts(row: Any) -> List[int]:
    amounts: List[int] = []
    for cell in getattr(row, "cells", []) or []:
        value = _numeric_value(getattr(cell, "value", None))
        if value is not None:
            amounts.append(value)
    return amounts


def _append_segment(segments: List[Dict[str, Any]], name: str, values: List[int], source: str) -> None:
    if not values:
        return
    canonical = _clean_label(name)
    if not _is_candidate_label(canonical):
        return
    if any(existing["name"].lower() == canonical.lower() for existing in segments):
        return
    segment: Dict[str, Any] = {
        "name": canonical,
        "revenue_quarterly": values[0],
        "source": source,
    }
    if len(values) > 1:
        segment["revenue_q_prior_year"] = values[1]
    segments.append(segment)


def _parse_disaggregation_rendered(rendered: Any) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    segments: List[Dict[str, Any]] = []
    total_revenue: Optional[int] = None

    for row in getattr(rendered, "rows", []) or []:
        label = _clean_label(getattr(row, "label", ""))
        amounts = _row_amounts(row)
        if not amounts:
            continue
        if _looks_like_total(label):
            total_revenue = amounts[0]
            continue
        _append_segment(segments, label, amounts, "SEC XBRL DisaggregationOfRevenue")

    return segments, total_revenue


def _parse_income_statement_rendered(rendered: Any) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    rows = list(getattr(rendered, "rows", []) or [])
    segments: List[Dict[str, Any]] = []
    total_revenue: Optional[int] = None
    in_revenue_block = False
    revenue_level: Optional[int] = None

    for row in rows:
        label = _clean_label(getattr(row, "label", ""))
        lowered = label.lower()
        level = int(getattr(row, "level", 0) or 0)
        amounts = _row_amounts(row)

        if amounts and ("revenue" in lowered or "sales" in lowered) and not total_revenue:
            total_revenue = amounts[0]

        is_revenue_heading = lowered in {
            "revenue",
            "revenues",
            "net revenue",
            "net revenues",
            "net sales",
            "sales",
        }
        if is_revenue_heading:
            in_revenue_block = True
            revenue_level = level
            continue

        if in_revenue_block and revenue_level is not None:
            if level <= revenue_level and _STOP_REVENUE_BLOCK_RE.search(label):
                in_revenue_block = False
                revenue_level = None
                continue
            if level <= revenue_level and amounts and not _is_candidate_label(label):
                continue
            if level > revenue_level and amounts:
                _append_segment(segments, label, amounts, "SEC XBRL IncomeStatement")
                continue

        if amounts and getattr(row, "is_dimension", False) and _is_candidate_label(label):
            _append_segment(segments, label, amounts, "SEC XBRL IncomeStatement")

    return segments, total_revenue


def _scale_text_amount(value: int, rendered_text: str) -> int:
    if value <= 0:
        return value
    if value < 1_000_000 and re.search(r"\bin millions\b|\$m|millions", rendered_text, re.IGNORECASE):
        return value * 1_000_000
    if value < 1_000_000 and re.search(r"\bin billions\b|\$b|billions", rendered_text, re.IGNORECASE):
        return value * 1_000_000_000
    return value


def _parse_text_rendered(rendered_text: str, source: str) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    segments: List[Dict[str, Any]] = []
    total_revenue: Optional[int] = None
    lines = rendered_text.splitlines()

    for line in lines:
        cleaned = re.sub(r"[│┃║|]", " ", line)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            continue
        numbers = _extract_numbers(cleaned)
        if not numbers:
            continue
        label = re.split(r"\(?\$?\s*[\d,]+", cleaned, maxsplit=1)[0].strip()
        label = _clean_label(label)
        if _looks_like_total(label):
            total_revenue = _scale_text_amount(numbers[0], rendered_text)
            continue
        values = [_scale_text_amount(value, rendered_text) for value in numbers[:2]]
        _append_segment(segments, label, values, source)

    if segments:
        return segments, total_revenue

    for index, line in enumerate(lines):
        label = _clean_label(line)
        if not _is_candidate_label(label):
            continue
        lookahead = " ".join(lines[index + 1:index + 4])
        values = [_scale_text_amount(value, rendered_text) for value in _extract_numbers(lookahead)[:2]]
        _append_segment(segments, label, values, source)

    return segments, total_revenue


def _merge_segments(primary: List[Dict[str, Any]], fallback: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = list(primary)
    seen = {item["name"].lower() for item in merged if item.get("name")}
    for item in fallback:
        name = str(item.get("name") or "").strip()
        if name and name.lower() not in seen:
            merged.append(item)
            seen.add(name.lower())
    return merged


def _render_xbrl_statement(xbrl: Any, statement: str) -> Optional[Any]:
    try:
        return xbrl.render_statement(statement, include_dimensions=True)
    except TypeError:
        try:
            return xbrl.render_statement(statement)
        except Exception as exc:
            logger.debug("Unable to render %s: %s", statement, exc)
            return None
    except Exception as exc:
        logger.debug("Unable to render %s: %s", statement, exc)
        return None


def extract_segment_revenue(ticker: str) -> Dict[str, Any]:
    """Extract product segment revenue from latest 10-K XBRL.

    Returns:
        {
            "source": "SEC XBRL 10-Q",
            "filing_date": "2026-05-01",
            "total_revenue_quarterly": 111184000000,
            "product_segments": [
                {"name": "iPhone", "revenue_quarterly": 56994000000},
                ...
            ],
            "deferred_revenue_total": 14700000000,
            "deferred_revenue_1yr_pct": 64,
        }
    """
    _ensure_identity()
    from edgar import Company

    company = Company(ticker.upper())
    filing = company.get_filings(form="10-K").latest(1)
    xbrl = filing.xbrl()
    result: Dict[str, Any] = {
        "source": "SEC XBRL 10-K (edgartools)",
        "filing_date": str(filing.filing_date),
        "product_segments": [],
    }

    segments: List[Dict[str, Any]] = []
    total_q: Optional[int] = None
    rendered_for_deferred = ""

    for statement_name in _DISAGGREGATION_STATEMENTS:
        rendered = _render_xbrl_statement(xbrl, statement_name)
        if not rendered:
            continue
        rendered_for_deferred = str(rendered)
        parsed_segments, parsed_total = _parse_disaggregation_rendered(rendered)
        if not parsed_segments:
            parsed_segments, parsed_total = _parse_text_rendered(
                rendered_for_deferred,
                "SEC XBRL DisaggregationOfRevenue",
            )
        segments = _merge_segments(segments, parsed_segments)
        total_q = total_q or parsed_total
        if segments:
            break

    if not segments:
        rendered = _render_xbrl_statement(xbrl, "IncomeStatement")
        if rendered:
            rendered_for_deferred = str(rendered)
            segments, total_q = _parse_income_statement_rendered(rendered)
            if not segments:
                segments, total_q = _parse_text_rendered(
                    rendered_for_deferred,
                    "SEC XBRL IncomeStatement",
                )

    if not segments:
        logger.warning(f"[{ticker}] No segment revenue rows found")

    result["product_segments"] = segments
    if total_q:
        result["total_revenue_quarterly"] = total_q

    # ── Deferred revenue ──
    deferred_match = re.search(
        r"total deferred revenue of \$?([\d.]+)\s*billion",
        rendered_for_deferred, re.IGNORECASE
    )
    if deferred_match:
        result["deferred_revenue_total"] = int(
            float(deferred_match.group(1)) * 1_000_000_000
        )
    timing_pct = re.findall(r"(\d+)%\s*(?:of total deferred revenue)", rendered_for_deferred)
    if timing_pct:
        result["deferred_revenue_1yr_pct"] = int(timing_pct[0]) if timing_pct else None

    return result


# ── Quick test ──
if __name__ == "__main__":
    import json
    data = extract_segment_revenue("AAPL")
    print(json.dumps(data, indent=2, default=str))
