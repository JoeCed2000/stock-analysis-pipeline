from backend.pipeline import _transcript_url


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
