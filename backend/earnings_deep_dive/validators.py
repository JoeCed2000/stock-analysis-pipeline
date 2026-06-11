"""Deterministic validators for Kimi earnings deep-dive sections."""
import re
from collections import Counter


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", re.MULTILINE)
_EN_ALLOWED_TEMPLATE_CJK_RE = re.compile(
    r"投資家向け(?:解釈|の本質理解)?|"
    r"機関投資家|"
    r"一言まとめ|総合評価|説明・分析|全体構造|今後のチェックポイント|"
    r"補足データ|計算ベース|指標ごとの解説|注意点|本質理解|"
    r"ハイライト|良かった点|ローライト|懸念点|投資視点の一言|"
    r"セグメント別の解説・分析|地域別の重要ポイント|"
    r"来期ガイダンス|一言でいうと|分析|中期|来期以降|"
    r"ただし注意点|リスク|超重要|かなり重要"
)

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


def collapse_repetition_loop(markdown: str) -> tuple[str, bool]:
    """Salvage output caught in a repetition loop by truncating at the loop.

    LLM repetition loops are trailing: the model produces valid content, then
    repeats a line/block until the token budget runs out. Truncate right
    before the first line whose normalized form reaches its 4th occurrence
    (the detect_repetition_loop threshold) and drop everything after it.

    Returns (text, True) when a truncation was applied; the caller must
    re-validate the truncated section before accepting it.
    """
    if not markdown:
        return markdown, False
    lines = markdown.splitlines()
    counts: Counter = Counter()
    for idx, line in enumerate(lines):
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized:
            continue
        counts[normalized] += 1
        if counts[normalized] > 3:
            return "\n".join(lines[:idx]).rstrip(), True
    return markdown, False


def check_table_presence(markdown: str) -> bool:
    """Return True when markdown contains a basic pipe table."""
    if not markdown:
        return False
    return "|" in markdown and _TABLE_SEPARATOR_RE.search(markdown) is not None


def is_bilingual(markdown: str, language: str) -> bool:
    """Reject output that appears to mix Japanese/CJK and English prose."""
    if not markdown:
        return False

    normalized = language.lower()
    checked_markdown = markdown
    cjk_chars = _CJK_RE.findall(checked_markdown)
    has_cjk = bool(cjk_chars)
    latin_words = [
        word
        for word in _LATIN_WORD_RE.findall(checked_markdown)
        if word.upper() not in _LATIN_ALLOWLIST
    ]

    if normalized == "en":
        return has_cjk

    if normalized in {"jp"}:
        if not has_cjk and len(latin_words) >= 12:
            return True
        latin_chars = sum(len(word) for word in latin_words)
        return has_cjk and len(latin_words) > 80 and latin_chars > (len(cjk_chars) * 2)

    return False
