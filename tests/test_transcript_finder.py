from backend import transcript_finder


LONG = "Revenue and EPS improved. " * 120


def _disable_sa_cookies(monkeypatch):
    monkeypatch.setattr("backend.seeking_alpha_access._read_store", lambda: {})


def _disable_stockanalysis(monkeypatch):
    monkeypatch.setattr("backend.stockanalysis.search_transcripts", lambda ticker, limit=3: [])
    monkeypatch.setattr("backend.stockanalysis.fetch_transcript", lambda url: None)


def test_find_transcripts_uses_stockanalysis_as_first_cookie_fallback(monkeypatch):
    """When SA cookies are not configured, the StockAnalysis fallback must
    produce a 'Seeking Alpha via StockAnalysis' label — NOT plain
    'StockAnalysis' (which loses the SA lineage the client expects to see
    in PDFs and the dossier header) and NOT plain 'Seeking Alpha' (which
    would lie about the content source). The URL stays on StockAnalysis
    because the content was fetched from there.
    """
    _disable_sa_cookies(monkeypatch)
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{"id": "568907", "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"}],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            # stockanalysis.fetch_transcript now always returns the via-label
            # regardless of whether an SA link was found on the page.
            "source": "Seeking Alpha via StockAnalysis",
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
    assert result["sources"][0]["source"] == "Seeking Alpha via StockAnalysis"
    assert result["sources"][0]["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    # Negative checks: must NOT be the bare labels.
    assert result["sources"][0]["source"] != "Seeking Alpha"
    assert result["sources"][0]["source"] != "StockAnalysis"


def test_find_transcripts_preserves_original_sa_url_as_reference_only(monkeypatch):
    """Regression for 2026-06-09 NVDA bug.

    When stockanalysis.fetch_transcript finds an SA article link on the
    StockAnalysis page, the SA URL is preserved as `original_sa_url`
    (reference for clients with SA Premium cookies in their browser) — NOT
    used as the primary citation. The citation URL stays on StockAnalysis
    because that is the page we actually fetched the verbatim content from.
    """
    _disable_sa_cookies(monkeypatch)
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{"id": "568907", "url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"}],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            "source": "Seeking Alpha via StockAnalysis",
            "title": "NVDA Q1 2027 Earnings Call Transcript",
            "url": url,  # StockAnalysis URL — the page we actually fetched
            "stockanalysis_url": url,
            # The SA article URL is preserved as a reference, not as the citation.
            "original_sa_url": "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript",
            "content": LONG,
            "date": "2026-05-28",
            "retrieval_provider": "StockAnalysis",
        },
    )

    result = transcript_finder.find_transcripts("NVDA")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "Seeking Alpha via StockAnalysis"
    # Citation URL is the StockAnalysis page we actually fetched.
    assert result["sources"][0]["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    assert result["sources"][0]["stockanalysis_url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    # SA URL is preserved as a reference for clients with SA Premium cookies.
    assert result["sources"][0]["original_sa_url"] == "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"


def test_find_transcripts_reuses_recent_cache_before_slow_web_discovery(monkeypatch):
    _disable_sa_cookies(monkeypatch)
    stockanalysis_calls = []
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: stockanalysis_calls.append(ticker) or [],
    )
    monkeypatch.setattr("backend.stockanalysis.fetch_transcript", lambda url: None)
    cached = {
        "source": "Seeking Alpha via StockAnalysis",
        "type": "earnings_transcript",
        "title": "AAPL Q2 2026 Earnings Call Transcript",
        "url": "https://stockanalysis.com/stocks/aapl/transcripts/548666-q2-2026/",
        "text": LONG,
        "text_length": len(LONG),
        "date": "2026-04-30",
        "id": "548666",
        "retrieval_provider": "StockAnalysis",
    }
    monkeypatch.setattr(
        transcript_finder,
        "_load_recent_cached_transcript",
        lambda ticker: cached,
        raising=False,
    )
    web_calls = []
    monkeypatch.setattr(
        "backend.transcript_web_search.search_transcript_pages",
        lambda *args, **kwargs: web_calls.append((args, kwargs)) or [],
    )

    result = transcript_finder.find_transcripts("AAPL", company="Apple Inc")

    assert result["found"] is True
    assert result["sources"][0]["url"] == cached["url"]
    assert web_calls == []
    assert stockanalysis_calls == []


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
