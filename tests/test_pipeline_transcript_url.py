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


def test_transcript_url_prefers_true_seeking_alpha_article_over_stockanalysis():
    stockanalysis = {"url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"}
    sources = [
        stockanalysis,
        {"url": "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"},
    ]

    assert _transcript_url(stockanalysis, ticker="NVDA", all_sources=sources) == "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"


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
