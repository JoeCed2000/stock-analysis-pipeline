from backend import transcript_finder


LONG = "Revenue and EPS improved. " * 120


def _disable_sa_cookies(monkeypatch):
    monkeypatch.setattr("backend.seeking_alpha_access._read_store", lambda: {})


def _disable_stockanalysis(monkeypatch):
    monkeypatch.setattr("backend.stockanalysis.search_transcripts", lambda ticker, limit=3: [])
    monkeypatch.setattr("backend.stockanalysis.fetch_transcript", lambda url: None)


def test_find_transcripts_uses_stockanalysis_as_first_cookie_fallback(monkeypatch):
    _disable_sa_cookies(monkeypatch)
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{"id": "568907", "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"}],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            "source": "StockAnalysis",
            "title": "NVDA Q1 2027 Earnings Call Transcript",
            "url": url,
            "stockanalysis_url": url,
            "content": LONG,
            "date": "2026-05-28",
            "retrieval_provider": "StockAnalysis",
        },
    )
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", lambda ticker: None)

    result = transcript_finder.find_transcripts("NVDA")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "StockAnalysis"
    assert result["sources"][0]["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    assert "Seeking Alpha via StockAnalysis" not in result["sources"][0]["source"]


def test_find_transcripts_preserves_original_seeking_alpha_url_from_stockanalysis(monkeypatch):
    _disable_sa_cookies(monkeypatch)
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{"id": "568907", "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"}],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            "source": "Seeking Alpha",
            "title": "NVDA Q1 2027 Earnings Call Transcript",
            "url": "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript",
            "stockanalysis_url": url,
            "content": LONG,
            "date": "2026-05-28",
            "retrieval_provider": "StockAnalysis",
        },
    )

    result = transcript_finder.find_transcripts("NVDA")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "Seeking Alpha"
    assert result["sources"][0]["url"] == "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"
    assert result["sources"][0]["stockanalysis_url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"


def test_find_transcripts_falls_back_to_alpha_vantage_when_stockanalysis_empty(monkeypatch):
    _disable_sa_cookies(monkeypatch)
    _disable_stockanalysis(monkeypatch)
    monkeypatch.setattr(
        "backend.alpha_vantage.fetch_transcript",
        lambda ticker: {"content": LONG, "quarter": "2026Q3", "date": "2026-04-25"},
    )
    monkeypatch.setattr("backend.seeking_alpha.search_transcript_web", lambda ticker: [])

    result = transcript_finder.find_transcripts("MSFT")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "Alpha Vantage API"
    assert result["sources"][0]["text"] == LONG


def test_find_transcripts_falls_back_to_fool_when_structured_sources_fail(monkeypatch):
    _disable_sa_cookies(monkeypatch)
    _disable_stockanalysis(monkeypatch)
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", lambda ticker: None)
    monkeypatch.setattr(
        "backend.sources.motleyfool.get_transcript",
        lambda ticker: {
            "url": "https://www.fool.com/earnings/call-transcripts/amd/",
            "text": LONG,
            "date": "2026-04-30",
        },
    )

    result = transcript_finder.find_transcripts("AMD")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "The Motley Fool"
    assert result["sources"][0]["text"] == LONG
    assert result["sources"][0]["quarter"] == ""


def test_find_transcripts_falls_back_to_public_search(monkeypatch):
    _disable_sa_cookies(monkeypatch)
    _disable_stockanalysis(monkeypatch)
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", lambda ticker: None)
    monkeypatch.setattr("backend.sources.motleyfool.get_transcript", lambda ticker: None)
    monkeypatch.setattr(
        "backend.seeking_alpha.search_transcript_web",
        lambda ticker: [
            {
                "source": "Public transcript search",
                "title": "MSFT Earnings Call Transcript",
                "url": "https://example.com/msft-transcript",
                "text": LONG,
                "quarter": "FY2026 Q1",
                "date": "2025-10-29",
            }
        ],
    )
    monkeypatch.setattr(
        "backend.transcript_web_search.search_transcript_pages",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("web discovery should not run when public search succeeds")),
    )

    result = transcript_finder.find_transcripts("MSFT", company="Microsoft Corporation")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "Public transcript search"
    assert result["sources"][0]["url"] == "https://example.com/msft-transcript"
