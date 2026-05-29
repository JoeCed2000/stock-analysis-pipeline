from backend.pipeline import _best_transcript_source, _transcript_url


def test_transcript_url_canonicalizes_stockanalysis_deep_link():
    source = {
        "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    }

    assert _transcript_url(source, ticker="NVDA") == "https://stockanalysis.com/stocks/nvda/transcripts/"


def test_transcript_url_keeps_seekingalpha_links():
    source = {"url": "https://seekingalpha.com/article/1234567-foo"}

    assert _transcript_url(source, ticker="NVDA") == "https://seekingalpha.com/article/1234567-foo"


def test_transcript_url_uses_source_path_when_ticker_hint_missing():
    source = {
        "url": "https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/"
    }

    assert _transcript_url(source) == "https://stockanalysis.com/stocks/msft/transcripts/"


def test_transcript_url_demotes_investor_relations_portal():
    """Investor-relations URLs must never be returned when a better alternative exists."""
    source = {
        "url": "https://investor.nvidia.com/home/default.aspx"
    }
    # Without all_sources, and with ticker known, fall back to stockanalysis.com
    result = _transcript_url(source, ticker="NVDA")
    assert "stockanalysis.com" in result
    assert "investor.nvidia.com" not in result


def test_transcript_url_falls_back_to_stockanalysis_for_any_ticker():
    """Any ticker should get a stockanalysis.com listing URL as fallback."""
    for ticker in ("AAPL", "GOOGL", "TSLA", "BRK.B"):
        source = {"url": "https://investor.example.com/"}
        result = _transcript_url(source, ticker=ticker)
        assert f"stocks/{ticker.strip().lower()}" in result.lower()


def test_transcript_url_prefers_stockanalysis_in_all_sources():
    """When all_sources is provided, prefer stockanalysis.com over IR portal."""
    primary = {"url": "https://investor.nvidia.com/home/default.aspx"}
    all_srcs = [
        primary,
        {"source": "Public search", "url": "https://stockanalysis.com/stocks/nvda/transcripts/"},
    ]
    result = _transcript_url(primary, ticker="NVDA", all_sources=all_srcs)
    assert "stockanalysis.com/stocks/nvda/transcripts/" in result
    assert "investor.nvidia.com" not in result


def test_transcript_url_no_source_no_ticker_returns_none():
    assert _transcript_url({}) is None


def test_best_transcript_source_prefers_seeking_alpha_when_both_usable():
    stockanalysis_text = "A" * 2600
    seekingalpha_text = "B" * 2100
    sources = [
        {
            "source": "StockAnalysis.com",
            "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/",
            "text": stockanalysis_text,
        },
        {
            "source": "RapidAPI Seeking Alpha",
            "url": "https://seekingalpha.com/symbol/NVDA/earnings/transcripts",
            "text": seekingalpha_text,
        },
    ]

    best_text, best_source = _best_transcript_source(sources)
    assert best_text == seekingalpha_text
    assert "seekingalpha.com" in best_source["url"]


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
