"""Deterministic validators for Kimi earnings deep-dive sections."""
import re
from collections import Counter


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", re.MULTILINE)

_LATIN_ALLOWLIST = {
    "EPS",
    "CEO",
    "CFO",
    "GAAP",
    "NON",
    "EBIT",
    "EBITDA",
    "FCF",
    "ROIC",
    "ROE",
    "CAPEX",
    "USD",
    "JPY",
}


def validate_section_heading(markdown: str, expected_heading: str) -> bool:
    """Return True when the section contains the exact expected H2 heading."""
    if not markdown:
        return False
    pattern = rf"(?m)^\s*##\s+{re.escape(expected_heading)}\s*$"
    return re.search(pattern, markdown.strip()) is not None


def detect_repetition_loop(markdown: str) -> bool:
    """Detect Kimi repetition bugs: more than 3 identical non-empty lines."""
    if not markdown:
        return False
    lines = [re.sub(r"\s+", " ", line).strip() for line in markdown.splitlines()]
    meaningful = [line for line in lines if line]
    counts = Counter(meaningful)
    return any(count > 3 for count in counts.values())


def check_table_presence(markdown: str) -> bool:
    """Return True when markdown contains a basic pipe table."""
    if not markdown:
        return False
    return "|" in markdown and _TABLE_SEPARATOR_RE.search(markdown) is not None


def is_bilingual(markdown: str, language: str) -> bool:
    """Reject output that appears to mix Japanese/CJK and English prose."""
    if not markdown:
        return False

    has_cjk = _CJK_RE.search(markdown) is not None
    latin_words = [
        word
        for word in _LATIN_WORD_RE.findall(markdown)
        if word.upper() not in _LATIN_ALLOWLIST
    ]

    if language == "en":
        return has_cjk

    if language == "jp":
        if not has_cjk and len(latin_words) >= 12:
            return True
        return has_cjk and len(latin_words) > 25

    return has_cjk and len(latin_words) > 0
