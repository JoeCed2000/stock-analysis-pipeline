from types import SimpleNamespace

from backend import transcript_finder
from backend import transcript_web_search as tws


def test_brave_discovers_concrete_seeking_alpha_article_and_never_listing(monkeypatch, tmp_path):
    monkeypatch.setattr(tws, "SA_ARTICLE_CACHE_PATH", tmp_path / "sa_article_cache.json")

    html = """
    <a href="https://seekingalpha.com/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation">Presentation</a>
    <a href="https://seekingalpha.com/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript">Transcript</a>
    <a href="https://seekingalpha.com/symbol/NVDA/earnings/transcripts">Listing</a>
    """

    def fake_get(url, **kwargs):
        assert url.startswith("https://search.brave.com/search?")
        return SimpleNamespace(status_code=200, text=html)

    monkeypatch.setattr(tws.http, "get", fake_get)

    results = tws._search_brave("NVDA", company="NVIDIA Corporation", limit=5)

    assert [item["url"] for item in results] == [
        "https://seekingalpha.com/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation",
        "https://seekingalpha.com/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript",
    ]
    assert all("/symbol/" not in item["url"] for item in results)


def test_extract_sa_escaped_transcript_text_from_ssr_payload():
    raw = r'''
    <script>window.SSR_DATA={"body":"\u003Cdiv class=\"transcript-presentation-section\"\u003E
    \u003Cp class=\"transcript-presentation-section-title\"\u003E\u003Cstrong\u003EOperator\u003C\u002Fstrong\u003E\u003C\u002Fp\u003E
    \u003Cp\u003EGood afternoon. Welcome to NVIDIA NVDA earnings call transcript. Revenue and EPS were discussed.\u003C\u002Fp\u003E
    \u003C\u002Fdiv\u003E"}</script>
    '''

    text = tws._extract_sa_escaped_transcript_text(raw)

    assert "Operator" in text
    assert "NVIDIA NVDA earnings call transcript" in text
    assert "Revenue and EPS" in text


def test_search_pages_fetches_seeking_alpha_candidates_with_cookie_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(tws, "SA_ARTICLE_CACHE_PATH", tmp_path / "sa_article_cache.json")
    monkeypatch.setattr(tws, "_search_sa_direct", lambda ticker, company=None, limit=5: [])
    monkeypatch.setattr(tws, "search_google", lambda query, limit=5: [])
    monkeypatch.setattr(
        tws,
        "_search_brave",
        lambda ticker, company=None, limit=5: [
            {"url": "https://seekingalpha.com/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation", "title": "Presentation"},
            {"url": "https://seekingalpha.com/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript", "title": "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript"},
        ],
    )
    fetched = []

    def fake_fetch_sa(url, headers=None):
        fetched.append(url)
        if "4907259" not in url:
            return "NVIDIA presentation slides revenue transcript"
        return "NVIDIA NVDA earnings call transcript Operator revenue EPS " + ("content " * 2000)

    monkeypatch.setattr(tws, "_fetch_page_text_sa", fake_fetch_sa)

    results = tws.search_transcript_pages("NVDA", company="NVIDIA Corporation")

    assert len(results) == 1
    assert results[0]["source"] == "Seeking Alpha"
    assert results[0]["url"] == "https://seekingalpha.com/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript"
    assert fetched == [
        "https://seekingalpha.com/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation",
        "https://seekingalpha.com/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript",
    ]


def test_find_transcripts_uses_stockanalysis_before_slow_web_discovery(monkeypatch):
    monkeypatch.setattr(transcript_finder, "_is_usable", lambda text: len(text) >= 20)
    monkeypatch.setattr("backend.seeking_alpha_access._read_store", lambda: {})
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{
            "source": "Seeking Alpha via StockAnalysis",
            "title": "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript",
            "url": "https://stockanalysis.com/stocks/nvda/earnings-call-transcripts/q1-2027/",
            "id": "q1-2027",
        }],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            "source": "Seeking Alpha via StockAnalysis",
            "title": "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript",
            "url": url,
            "stockanalysis_url": url,
            "content": "NVIDIA NVDA earnings call transcript Operator revenue EPS full text",
            "date": "2026-05-28",
            "retrieval_provider": "StockAnalysis",
        },
    )
    web_discovery_calls = []
    monkeypatch.setattr(
        "backend.transcript_web_search.search_transcript_pages",
        lambda *args, **kwargs: web_discovery_calls.append((args, kwargs)) or [],
    )

    result = transcript_finder.find_transcripts("NVDA", company="NVIDIA Corporation")

    assert web_discovery_calls == []
    assert result["found"] is True
    assert result["sources"][0]["source"] == "Seeking Alpha via StockAnalysis"
    assert result["sources"][0]["url"] == "https://stockanalysis.com/stocks/nvda/earnings-call-transcripts/q1-2027/"
