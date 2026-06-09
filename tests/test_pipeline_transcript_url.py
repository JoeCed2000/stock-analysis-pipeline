from backend.pipeline import _best_transcript_source, _transcript_url


def test_transcript_url_canonicalizes_stockanalysis_deep_link():
    source = {
        "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    }

    assert _transcript_url(source, ticker="NVDA") == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"


def test_transcript_url_keeps_seekingalpha_links():
    source = {"url": "https://seekingalpha.com/article/1234567-foo"}

    assert _transcript_url(source, ticker="NVDA") == "https://seekingalpha.com/article/1234567-foo"


def test_transcript_url_uses_source_path_when_ticker_hint_missing():
    source = {
        "url": "https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/"
    }

    assert _transcript_url(source) == "https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/"


def test_transcript_url_demotes_investor_relations_portal():
    """Investor-relations URLs must never be returned when a better alternative exists."""
    source = {
        "url": "https://investor.nvidia.com/home/default.aspx"
    }
    result = _transcript_url(source, ticker="NVDA")
    assert result is None


def test_transcript_url_does_not_fabricate_listing_for_any_ticker():
    """A generic listing page is not a transcript citation."""
    for ticker in ("AAPL", "GOOGL", "TSLA", "BRK.B"):
        source = {"url": "https://investor.example.com/"}
        assert _transcript_url(source, ticker=ticker) is None


def test_transcript_url_prefers_stockanalysis_in_all_sources():
    """When all_sources is provided, prefer stockanalysis.com over IR portal."""
    primary = {"url": "https://investor.nvidia.com/home/default.aspx"}
    all_srcs = [
        primary,
        {"source": "StockAnalysis", "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"},
    ]
    result = _transcript_url(primary, ticker="NVDA", all_sources=all_srcs)
    assert result is not None
    assert "stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/" in result
    assert "investor.nvidia.com" not in result


def test_transcript_url_rejects_generic_seeking_alpha_listing():
    source = {"url": "https://seekingalpha.com/symbol/NVDA/earnings/transcripts"}

    assert _transcript_url(source, ticker="NVDA") is None


def test_transcript_url_uses_picked_source_url_even_when_higher_priority_url_exists_in_all_sources():
    """The citation URL must match the picked (longest-text) source.

    Regression for 2026-06-09 NVDA bug: the old implementation iterated over
    ALL sources and picked the highest-priority URL (SA article = 500), even
    when the picked source was StockAnalysis (priority 350). The PDF then
    showed "Seeking Alpha" as the header + URL while the verbatim content
    was StockAnalysis. Fix: the picked source's URL wins by default; only
    fall back to scanning all_sources when the picked source has no usable
    URL.
    """
    stockanalysis = {"url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"}
    sa_article = {"url": "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"}
    sources = [stockanalysis, sa_article]

    # StockAnalysis is the picked source → citation is the StockAnalysis URL.
    assert (
        _transcript_url(stockanalysis, ticker="NVDA", all_sources=sources)
        == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    )

    # SA article is the picked source (e.g. SA cookies made the full
    # transcript reachable, picked as longest) → citation is the SA article.
    assert (
        _transcript_url(sa_article, ticker="NVDA", all_sources=sources)
        == "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"
    )


def test_transcript_url_no_source_no_ticker_returns_none():
    assert _transcript_url({}) is None


def test_best_transcript_source_prefers_seeking_alpha_when_both_usable():
    """Priority (SA=400, StockAnalysis=300) wins when content lengths are
    comparable (within 1.2x). Per _best_transcript_source tie-break rule
    added in d29d854: when non-SA content is 1.2x+ longer than SA, prefer
    the longer (avoids paying for SA MPW-truncated previews when
    StockAnalysis has the full transcript).
    """
    stockanalysis_text = "A" * 3000
    seekingalpha_text = "B" * 2900  # comparable length, no 1.2x swing
    sources = [
        {
            "source": "StockAnalysis.com",
            "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/",
            "text": stockanalysis_text,
        },
        {
            "source": "RapidAPI Seeking Alpha",
            "url": "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript",
            "text": seekingalpha_text,
        },
    ]

    best_text, best_source = _best_transcript_source(sources)
    assert best_text == seekingalpha_text
    assert "seekingalpha.com" in best_source["url"]


def test_best_transcript_source_prefers_longer_when_1_2x_clearer():
    """When non-SA source is 1.2x+ longer than SA, prefer the longer one
    to avoid MPW-truncated SA previews. Per Ced rule 2026-06-05:
    fallback transcripts must be reliable full text, not truncated previews.
    """
    stockanalysis_text = "A" * 5000  # clearly longer
    seekingalpha_text = "B" * 2100  # MPW-truncated preview
    sources = [
        {
            "source": "StockAnalysis.com",
            "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/",
            "text": stockanalysis_text,
        },
        {
            "source": "RapidAPI Seeking Alpha",
            "url": "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript",
            "text": seekingalpha_text,
        },
    ]

    best_text, best_source = _best_transcript_source(sources)
    assert best_text == stockanalysis_text
    assert "stockanalysis.com" in best_source["url"]


def test_best_transcript_source_falls_back_to_longest_when_none_usable():
    short_public = "short text"
    longer_public = "longer public snippet"
    sources = [
        {"source": "Public transcript search", "url": "https://example.com/a", "text": short_public},
        {"source": "Public transcript search", "url": "https://example.com/b", "text": longer_public},
    ]

    best_text, best_source = _best_transcript_source(sources)
    assert best_text == longer_public
    assert best_source["url"].endswith("/b")
