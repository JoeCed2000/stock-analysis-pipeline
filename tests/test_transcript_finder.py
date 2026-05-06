from backend import transcript_finder


def test_find_transcripts_uses_rapidapi_as_primary(monkeypatch):
    def fake_search_sa_transcripts(ticker):
        assert ticker == "NVDA"
        return [{"id": "sa-1", "title": "NVDA Q1 2026 Earnings Call", "date": "2026-02-20", "quarter": "2026Q1"}]

    def fake_fetch_sa_transcript(transcript_id):
        assert transcript_id == "sa-1"
        return {
            "id": "sa-1",
            "title": "NVDA Q1 2026 Earnings Call",
            "date": "2026-02-20",
            "quarter": "2026Q1",
            "url": "https://seekingalpha.com/article/sa-1",
            "content": "Revenue accelerated. " * 20,
        }

    def fail_lower_source(*args, **kwargs):
        raise AssertionError("lower-priority source should not be called")

    monkeypatch.setattr("backend.rapidapi_sa.search_sa_transcripts", fake_search_sa_transcripts)
    monkeypatch.setattr("backend.rapidapi_sa.fetch_sa_transcript", fake_fetch_sa_transcript)
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", fail_lower_source)
    monkeypatch.setattr("backend.seeking_alpha.search_transcript_web", fail_lower_source)

    result = transcript_finder.find_transcripts("NVDA")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "RapidAPI Seeking Alpha"
    assert result["sources"][0]["text"] == "Revenue accelerated. " * 20
    assert result["sources"][0]["text_length"] == len("Revenue accelerated. " * 20)
    assert result["sources"][0]["quarter"] == "2026Q1"


def test_find_transcripts_falls_back_to_alpha_vantage_when_rapidapi_empty(monkeypatch):
    def fake_av(ticker):
        assert ticker == "MSFT"
        return {
            "content": "Cloud revenue and EPS improved. " * 20,
            "quarter": "2026Q3",
            "date": "2026-04-25",
        }

    def fail_fool(*args, **kwargs):
        raise AssertionError("Fool.com should not be called when Alpha Vantage succeeds")

    monkeypatch.setattr("backend.rapidapi_sa.search_sa_transcripts", lambda ticker: [])
    monkeypatch.setattr("backend.rapidapi_sa.fetch_sa_transcript", fail_fool)
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", fake_av)
    monkeypatch.setattr("backend.seeking_alpha.search_transcript_web", fail_fool)

    result = transcript_finder.find_transcripts("MSFT")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "Alpha Vantage API"
    assert result["sources"][0]["text"] == "Cloud revenue and EPS improved. " * 20


def test_find_transcripts_falls_back_to_fool_when_structured_sources_fail(monkeypatch):
    def raise_unavailable(*args, **kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr("backend.rapidapi_sa.search_sa_transcripts", raise_unavailable)
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", raise_unavailable)
    monkeypatch.setattr(
        "backend.seeking_alpha.search_transcript_web",
        lambda ticker: [
            {
                "source": "The Motley Fool",
                "title": "AMD Earnings Call Transcript",
                "url": "https://www.fool.com/earnings/call-transcripts/amd/",
                "text": "Data center demand improved. " * 20,
                "free": True,
            }
        ],
    )

    result = transcript_finder.find_transcripts("AMD")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "The Motley Fool"
    assert result["sources"][0]["text"] == "Data center demand improved. " * 20
    assert result["sources"][0]["quarter"] == ""


def test_find_transcripts_falls_back_to_google_discovered_web_source(monkeypatch):
    def empty(*args, **kwargs):
        return []

    def none(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.rapidapi_sa.search_sa_transcripts", empty)
    monkeypatch.setattr("backend.alpha_vantage.fetch_transcript", none)
    monkeypatch.setattr("backend.sources.motleyfool.get_transcript", none)
    monkeypatch.setattr(
        "backend.transcript_web_search.search_transcript_pages",
        lambda ticker, company=None, limit=5: [
            {
                "source": "Google Search Transcript",
                "title": "Microsoft FY26 Q1 Earnings Call Transcript",
                "url": "https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q1",
                "text": "Revenue was $77.7 billion and EPS was $4.13. " * 20,
                "quarter": "FY2026 Q1",
                "date": "2025-10-29",
                "text_length": len("Revenue was $77.7 billion and EPS was $4.13. " * 20),
            }
        ],
    )

    result = transcript_finder.find_transcripts("MSFT", company="Microsoft Corporation")

    assert result["found"] is True
    assert result["sources"][0]["source"] == "Google Search Transcript"
    assert "EPS was $4.13" in result["sources"][0]["text"]
    assert result["sources"][0]["quarter"] == "FY2026 Q1"
