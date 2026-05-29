from backend.pipeline import _best_transcript_source, _transcript_url


def test_transcript_url_canonicalizes_stockanalysis_deep_link():
    source = {
        "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    }

    assert _transcript_url(source, ticker="NVDA") == "https://stockanalysis.com/stocks/nvda/transcripts/"


def test_transcript_url_keeps_non_stockanalysis_links_unchanged():
    source = {"url": "https://seekingalpha.com/article/1234567-foo"}

    assert _transcript_url(source, ticker="NVDA") == "https://seekingalpha.com/article/1234567-foo"


def test_transcript_url_uses_source_path_when_ticker_hint_missing():
    source = {
        "url": "https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/"
    }

    assert _transcript_url(source) == "https://stockanalysis.com/stocks/msft/transcripts/"


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
