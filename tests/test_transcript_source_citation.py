from backend import transcript_finder
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.schemas import FinancialMetrics


def test_stockanalysis_fetch_result_uses_stockanalysis_when_no_original_sa_url(monkeypatch):
    from backend import stockanalysis

    html = """
    <html><body>
      <h1>NVDA Q1 2027 Earnings Call Transcript</h1>
      <main>Long transcript text </main>
    </body></html>
    """.replace("Long transcript text ", "Long transcript text " * 150)

    monkeypatch.setattr(stockanalysis, "_fetch_page", lambda url: html)

    data = stockanalysis.fetch_transcript("https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/")

    assert data is not None
    assert data["source"] == "StockAnalysis"
    assert data["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    assert data["stockanalysis_url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"


def test_stockanalysis_fetch_result_prefers_original_sa_article_url(monkeypatch):
    from backend import stockanalysis

    html = """
    <html><body>
      <h1>NVDA Q1 2027 Earnings Call Transcript</h1>
      <a href="https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript">Original</a>
      <main>Long transcript text </main>
    </body></html>
    """.replace("Long transcript text ", "Long transcript text " * 150)

    monkeypatch.setattr(stockanalysis, "_fetch_page", lambda url: html)

    data = stockanalysis.fetch_transcript("https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/")

    assert data is not None
    assert data["source"] == "Seeking Alpha"
    assert data["url"] == "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"
    assert data["stockanalysis_url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"


def test_transcript_finder_does_not_label_stockanalysis_fallback_as_seeking_alpha(monkeypatch):
    monkeypatch.setattr("backend.seeking_alpha_access._read_store", lambda: {})
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{"url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/", "id": "568907"}],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            "source": "StockAnalysis",
            "title": "NVDA Q1 2027 Earnings Call Transcript",
            "url": url,
            "stockanalysis_url": url,
            "content": "Revenue accelerated. " * 120,
            "date": "2026-05-28",
            "retrieval_provider": "StockAnalysis",
        },
    )

    result = transcript_finder.find_transcripts("NVDA")

    assert result["found"] is True
    source = result["sources"][0]
    assert source["source"] == "StockAnalysis"
    assert source["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    assert "Seeking Alpha via StockAnalysis" not in source["source"]


def test_mapper_does_not_add_generic_seeking_alpha_listing_candidate():
    report = build_earnings_deep_dive_report(
        ticker="NVDA",
        company="NVIDIA Corporation",
        quarter="FY2027 Q1",
        language="en",
        metrics=FinancialMetrics(transcript_source="StockAnalysis"),
        transcript_url="https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/",
    )

    text = report.model_dump_json()

    assert "Transcript - StockAnalysis" in text
    assert "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/" in text
    assert "Seeking Alpha via StockAnalysis" not in text
    assert "https://seekingalpha.com/symbol/NVDA/earnings/transcripts" not in text
