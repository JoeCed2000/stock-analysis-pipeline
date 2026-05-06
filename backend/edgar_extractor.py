"""Extract segment/revenue/backlog data from SEC XBRL filings via edgartools.

Free, unlimited, GAAP-compliant. Works for all US-listed companies.

Requirements: pip install edgartools
Note: MUST unset HTTPS_PROXY/HTTP_PROXY before importing edgar.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EDGAR_IDENTITY = "Ced Control Center (ced.chatillon@gmail.com)"

# Segment name markers to detect in rendered tables
_SEGMENT_MARKERS = [
    ("iphone", "iPhone"),
    ("mac", "Mac"),
    ("ipad", "iPad"),
    ("wearables, home", "Wearables, Home and Accessories"),
    ("services", "Services"),
    ("total net sales", None),  # None = use original text, handled specially
]


def _clean_proxy_env():
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        os.environ.pop(key, None)


def _ensure_identity():
    from edgar import set_identity
    _clean_proxy_env()
    set_identity(EDGAR_IDENTITY)


def _extract_numbers(text: str) -> List[int]:
    """Extract all integer numbers from text (after removing $ and commas)."""
    nums = re.findall(r"[\d,]+", text.replace("$", ""))
    return [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]


def _find_segment_boundaries(lines: List[str]) -> List[Tuple[str, int, int]]:
    """Find segment name lines and their number range.

    Returns list of (name, start_line, end_line) where start_line=name line,
    end_line=next segment name line (or end of table).
    """
    boundaries = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "$" in stripped or len(stripped) > 50:
            continue  # Number lines or prose — skip
        for marker, canonical in _SEGMENT_MARKERS:
            if marker in stripped.lower():
                name = canonical if canonical else stripped.replace("®", "").strip()
                boundaries.append((name, i))
                break
    return boundaries


def extract_segment_revenue(ticker: str) -> Dict[str, Any]:
    """Extract product segment revenue from latest 10-Q XBRL.

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
    filing = company.get_filings(form="10-Q").latest(1)
    xbrl = filing.xbrl()
    rendered = str(xbrl.render_statement("DisaggregationOfRevenue"))

    result: Dict[str, Any] = {
        "source": "SEC XBRL 10-Q (edgartools)",
        "filing_date": str(filing.filing_date),
        "product_segments": [],
    }

    if not rendered or "No statement" in rendered:
        return result

    lines = rendered.split("\n")
    boundaries = _find_segment_boundaries(lines)

    if not boundaries:
        logger.warning(f"[{ticker}] No segment boundaries found")
        return result

    segments = []
    total_q = total_6m = None

    for idx, (name, start) in enumerate(boundaries):
        # End is next boundary start, or end of rendered area (~15 lines after Total)
        end = boundaries[idx + 1][1] if idx + 1 < len(boundaries) else start + 5

        # Extract ALL numbers from the lines between this segment and the next
        all_nums = []
        for i in range(start + 1, min(end + 3, len(lines))):
            all_nums.extend(_extract_numbers(lines[i]))
        # Filter down to just the first 4 numbers (Q, Q_prior, 6M, 6M_prior)
        all_nums = all_nums[:4]

        if not all_nums:
            continue

        # Apple XBRL order: [Q_rev, Q_prior, 6M_rev, 6M_prior]
        q_rev = all_nums[0] if len(all_nums) > 0 else None
        q_prior = all_nums[1] if len(all_nums) > 1 else None

        if "total" in name.lower():
            total_q = q_rev * 1_000_000 if q_rev else None
            total_6m = all_nums[2] * 1_000_000 if len(all_nums) > 2 and all_nums[2] else None
        else:
            segments.append({
                "name": name,
                "revenue_quarterly": q_rev * 1_000_000 if q_rev else None,
                "revenue_q_prior_year": q_prior * 1_000_000 if q_prior else None,
            })

    result["product_segments"] = segments
    if total_q:
        result["total_revenue_quarterly"] = total_q
    if total_6m:
        result["total_revenue_6m"] = total_6m

    # ── Deferred revenue ──
    deferred_match = re.search(
        r"total deferred revenue of \$?([\d.]+)\s*billion",
        rendered, re.IGNORECASE
    )
    if deferred_match:
        result["deferred_revenue_total"] = int(
            float(deferred_match.group(1)) * 1_000_000_000
        )
    timing_pct = re.findall(r"(\d+)%\s*(?:of total deferred revenue)", rendered)
    if timing_pct:
        result["deferred_revenue_1yr_pct"] = int(timing_pct[0]) if timing_pct else None

    return result


# ── Quick test ──
if __name__ == "__main__":
    import json
    data = extract_segment_revenue("AAPL")
    print(json.dumps(data, indent=2, default=str))
