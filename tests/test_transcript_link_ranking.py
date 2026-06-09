"""Tests for SA transcript link ranking — fixes 2026-06-09.

The previous filter (``_is_earnings_call_transcript_link``) rejected any link
containing the words "conference" or "presentation", which wrongly excluded
legitimate conference transcripts like:

  "NVIDIA Corporation (NVDA) Presents at Bank of America 2026 Global
   Technology Conference Transcript"

Ced flagged this on 2026-06-09: the Bank of America conference transcript is a
real transcript (operator Q&A included) and should be accepted. The fix
introduces a tiered ranking so the caller can prefer the canonical quarterly
earnings-call transcript over a more recent conference presentation.
"""

import pytest

from backend.seeking_alpha_access import (
    _is_earnings_call_transcript_link,
    _rank_transcript_link,
)


# --- ACCEPT: legitimate transcripts ---------------------------------------

ACCEPT_CASES = [
    # (label, href, expected_min_score, description)
    (
        "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript",
        "/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript#source",
        100,
        "quarterly earnings call — highest priority",
    ),
    (
        "NVIDIA Corporation (NVDA) Q4 2026 Earnings Call Transcript",
        "/article/4874926-nvidia-corporation-nvda-q4-2026-earnings-call-transcript",
        100,
        "quarterly earnings call (no source anchor)",
    ),
    (
        "NVIDIA Corporation (NVDA) Earnings Call Transcript",
        "/article/4900000-nvda-earnings-call-transcript",
        50,
        "earnings call transcript without quarter tag",
    ),
    (
        "NVIDIA Corporation (NVDA) Shareholder/Analyst Call Transcript",
        "/article/4883301-nvidia-corporation-nvda-shareholder-analyst-call-transcript",
        40,
        "shareholder/analyst call",
    ),
    # Conference transcripts (previously REJECTED — now ACCEPTED)
    (
        "NVIDIA Corporation (NVDA) Presents at Bank of America 2026 Global Technology Conference Transcript",
        "/article/4912081-nvidia-corporation-nvda-presents-at-bank-of-america-2026-global",
        20,
        "BoA conference transcript — was wrongly rejected before fix",
    ),
    (
        "NVIDIA Corporation (NVDA) Presents at TD Cowen's 54th Annual Technology, Media & Telecom Conference Transcript",
        "/article/4909711-nvidia-corporation-nvda-presents-at-td-cowens-54th-annual-techn",
        20,
        "TD Cowen conference transcript",
    ),
    (
        "NVIDIA Corporation (NVDA) Presents at NVIDIA GTC AI Conference 2026 Prepared Remarks Transcript",
        "/article/4882990-nvidia-corporation-nvda-presents-at-nvidia-gtc-ai-conference-20",
        10,
        "GTC prepared remarks transcript (no Q&A)",
    ),
    (
        "NVIDIA Corporation (NVDA) Presents at Second Annual AI Summit Transcript",
        "/article/4865562-nvidia-corporation-nvda-presents-at-second-annual-ai-summit-tra",
        20,
        "AI Summit transcript",
    ),
    # Conference CALL transcript (Q&A at a conference — operator-driven)
    (
        "NVIDIA Corporation (NVDA) Q1 2027 Earnings Conference Call Transcript",
        "/article/4907259-q1-2027-earnings-conference-call-transcript",
        40,
        "earnings CONFERENCE call — has 'conference call' + 'transcript'",
    ),
    (
        "Apple Inc. (AAPL) Q4 2025 Conference Call Transcript",
        "/article/12345-aapl-q4-2025-conference-call-transcript",
        40,
        "quarterly conference call transcript (no 'earnings' word)",
    ),
    (
        "NVIDIA Corporation (NVDA) Citi Global Technology Conference Call Transcript",
        "/article/12346-nvda-citi-tech-conference-call",
        40,
        "conference call transcript at a venue",
    ),
]


# --- REJECT: clearly not transcripts --------------------------------------

REJECT_CASES = [
    (
        "1 Comment",
        "/article/4909711-nvidia-corporation-nvda-presents-at-td-cowens-54th-annual-techn#scroll_comments",
        "comment anchor (not a transcript)",
    ),
    (
        "8 Comments",
        "/article/4874926-nvidia-corporation-nvda-q4-2026-earnings-call-transcript#scroll_comments",
        "comment anchor pointing at a real transcript",
    ),
    (
        "NVIDIA Corporation 2027 Q1 - Results - Earnings Call Presentation",
        "/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation",
        "earnings-call PRESENTATION (slides only, not spoken transcript)",
    ),
    (
        "NVIDIA Corporation (NVDA) Presents at CES 2026 - Slideshow",
        "/article/4859348-nvidia-corporation-nvda-presents-at-ces-2026-slideshow",
        "slideshow (not a transcript)",
    ),
    (
        "44th Annual J.P. Morgan Healthcare Conference",
        "/article/4859043-44th-annual-j-p-morgan-healthcare-conference",
        "conference article without transcript word",
    ),
    (
        "Some news article about NVIDIA",
        "/article/1234567-some-news-article",
        "news article — no transcript signal",
    ),
    (
        "Analyst commentary on NVDA",
        "/article/9999999-analyst-commentary",
        "commentary — not a transcript",
    ),
    (
        "",
        "https://example.com/some/page",
        "non-article URL",
    ),
]


@pytest.mark.parametrize("label,href,min_score,description", ACCEPT_CASES)
def test_transcript_link_accepted_with_score(label, href, min_score, description):
    """Legitimate transcripts are accepted and scored at or above the expected tier."""
    score = _rank_transcript_link(label, href)
    assert score >= min_score, (
        f"FAIL: {description!r}: score={score}, expected >= {min_score}\n"
        f"  label={label!r}\n  href={href!r}"
    )
    assert _is_earnings_call_transcript_link(label, href) is True, (
        f"FAIL: {description!r}: accepted by filter but score={score} is non-positive"
    )


@pytest.mark.parametrize("label,href,description", REJECT_CASES)
def test_transcript_link_rejected(label, href, description):
    """Non-transcripts are rejected with score 0."""
    score = _rank_transcript_link(label, href)
    assert score == 0, (
        f"FAIL: {description!r}: score={score}, expected 0\n"
        f"  label={label!r}\n  href={href!r}"
    )
    assert _is_earnings_call_transcript_link(label, href) is False, (
        f"FAIL: {description!r}: filter accepted but score={score} is non-positive"
    )


def test_quarterly_earnings_call_outranks_conference():
    """The quarterly earnings call must rank ABOVE any conference transcript.

    Reproduces the 2026-06-09 scenario: SA listing for NVDA has both the BoA
    conference transcript (most recent, ranked 20) and the Q1 2027 earnings
    call transcript (ranked 100). The deep-dive analysis must prefer the
    earnings call.
    """
    conference_label = (
        "NVIDIA Corporation (NVDA) Presents at Bank of America 2026 "
        "Global Technology Conference Transcript"
    )
    conference_href = (
        "/article/4912081-nvidia-corporation-nvda-presents-at-bank-of-america-2026-global"
    )
    earnings_label = "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript"
    earnings_href = (
        "/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript"
    )

    conf_score = _rank_transcript_link(conference_label, conference_href)
    earn_score = _rank_transcript_link(earnings_label, earnings_href)

    assert earn_score > conf_score, (
        f"earnings call (score={earn_score}) should outrank "
        f"conference (score={conf_score})"
    )
    assert earn_score >= 100, f"earnings call should score >=100, got {earn_score}"
    assert conf_score >= 20, f"conference should still be accepted (>=20), got {conf_score}"


def test_filter_backward_compatible():
    """``_is_earnings_call_transcript_link`` returns the same booleans as before
    for the cases the previous filter handled — only the conference-rejection
    behavior changed.
    """
    # These were accepted before AND should still be accepted
    assert _is_earnings_call_transcript_link(
        "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript",
        "/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript",
    ) is True
    # These were rejected before AND should still be rejected
    assert _is_earnings_call_transcript_link(
        "NVIDIA Corporation 2027 Q1 - Results - Earnings Call Presentation",
        "/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation",
    ) is False
    assert _is_earnings_call_transcript_link(
        "1 Comment",
        "/article/12345-anything#scroll_comments",
    ) is False
    # This is the NEW behavior — was rejected, now accepted
    assert _is_earnings_call_transcript_link(
        "NVIDIA Corporation (NVDA) Presents at Bank of America 2026 Global Technology Conference Transcript",
        "/article/4912081-nvidia-corporation-nvda-presents-at-bank-of-america-2026-global",
    ) is True, "BoA conference transcript must be accepted after the 2026-06-09 fix"


def test_ranking_prefers_earnings_call_over_older_conference():
    """Even if the earnings call is older in the listing, the ranking must
    prefer it to a more recent conference transcript.
    """
    # More recent conference
    conf_score = _rank_transcript_link(
        "ACME Corp Presents at Recent Conference 2026 Transcript",
        "/article/9999-acme-presents-at-recent-conference-2026-transcript",
    )
    # Older earnings call
    earn_score = _rank_transcript_link(
        "ACME Corp Q4 2025 Earnings Call Transcript",
        "/article/1234-acme-q4-2025-earnings-call-transcript",
    )
    assert earn_score > conf_score


# --- Tests for _primary_source_name (label/content consistency) ------------


def test_primary_source_name_picks_longest_not_first():
    """The primary source label must match the source with the longest text,
    not just the first one with any text.

    Reproduces the 2026-06-09 bug: SA primary path captured 5042 chars (MPW
    paywall preview); StockAnalysis captured 49881 chars (full text).
    _best_transcript correctly picked StockAnalysis for the content, but
    _primary_source_name iterated in list order and returned "Seeking Alpha"
    (the first source with any text) — so the saved dossier's header and
    filename said "Seeking Alpha" while the content was actually from
    StockAnalysis. This test pins the fix.
    """
    from backend.earnings_deep_dive.generator import _primary_source_name

    sources = [
        {
            "source": "Seeking Alpha",
            "url": "https://seekingalpha.com/article/4907259-q1-2027",
            "text": "Skip to content Home page Seeking Alpha - Power to Investors..." * 50,  # 5042
        },
        {
            "source": "Seeking Alpha via StockAnalysis",
            "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027",
            "text": "NVIDIA (NVDA) Q1 2027 Earnings Call Transcript & Audio\n\n" + "Operator: ... " * 5000,  # 49K+
        },
    ]
    name = _primary_source_name(sources)
    assert name == "Seeking Alpha via StockAnalysis", (
        f"FAIL: primary_source should match the longest transcript "
        f"(StockAnalysis, 49K), got {name!r}"
    )


def test_primary_source_name_handles_list_text():
    """Some sources pass text as a list of paragraphs — must still compare lengths."""
    from backend.earnings_deep_dive.generator import _primary_source_name

    sources = [
        {
            "source": "Seeking Alpha",
            "text": ["short", "list"],
        },
        {
            "source": "Seeking Alpha via StockAnalysis",
            "text": ["line " * 200 for _ in range(200)],  # 1000 chars
        },
    ]
    name = _primary_source_name(sources)
    assert name == "Seeking Alpha via StockAnalysis"


def test_primary_source_name_handles_empty_sources():
    """Empty source list returns 'unknown' without crashing."""
    from backend.earnings_deep_dive.generator import _primary_source_name

    assert _primary_source_name([]) == "unknown"


def test_primary_source_name_falls_back_to_title():
    """When 'source' is missing but 'title' is present, use title."""
    from backend.earnings_deep_dive.generator import _primary_source_name

    sources = [
        {"title": "Earnings Call Q1 2027", "text": "Some content here"},
    ]
    name = _primary_source_name(sources)
    assert name == "Earnings Call Q1 2027"


def test_primary_source_name_ignores_empty_text():
    """A source with no usable text must not be picked over one with text."""
    from backend.earnings_deep_dive.generator import _primary_source_name

    sources = [
        {"source": "Empty", "text": ""},
        {"source": "Has Text", "text": "Some real transcript content"},
    ]
    name = _primary_source_name(sources)
    assert name == "Has Text"
