from backend import transcript_finder
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.schemas import FinancialMetrics


# ---------------------------------------------------------------------------
# Regression suite for NVDA transcript label/URL mismatch (2026-06-09).
#
# Root cause: backend/stockanalysis.py used to set:
#     url = sa_url or stockanalysis_url
#     source = "Seeking Alpha" if sa_url else "Seeking Alpha via StockAnalysis"
# i.e. when an SA article link was found on the StockAnalysis listing page,
# the StockAnalysis-fetched content got relabelled as "Seeking Alpha" and
# the citation URL became the SA article. Downstream, the deep-dive early
# return picked up the SA URL and the filename + PDF header both said
# "Seeking Alpha" while the verbatim content (47K chars) was StockAnalysis.
#
# Fix: stockanalysis.py now ALWAYS labels its own fetch as
# "Seeking Alpha via StockAnalysis" and keeps the SA article URL only in
# a separate `original_sa_url` field for reference. The citation URL is
# the StockAnalysis transcript page (the page actually fetched).
# ---------------------------------------------------------------------------


def test_stockanalysis_fetch_uses_via_label_with_or_without_sa_link(monkeypatch):
    """StockAnalysis fetch must always label as 'via StockAnalysis', regardless
    of whether an SA article link was found on the page. The content came
    from StockAnalysis; the SA link (if any) is a reference, not the source.
    """
    from backend import stockanalysis

    # No SA link on page — old test case (was already correct).
    html_no_link = """
    <html><body>
      <h1>NVDA Q1 2027 Earnings Call Transcript</h1>
      <main>Long transcript text </main>
    </body></html>
    """.replace("Long transcript text ", "Long transcript text " * 150)

    monkeypatch.setattr(stockanalysis, "_fetch_page", lambda url: html_no_link)
    data = stockanalysis.fetch_transcript("https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/")

    assert data is not None
    assert data["source"] == "Seeking Alpha via StockAnalysis"
    assert data["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    assert data["stockanalysis_url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    # No SA link on this page → no SA reference URL.
    assert not data.get("original_sa_url")


def test_stockanalysis_fetch_keeps_sa_url_as_reference_only(monkeypatch):
    """When an SA article link is found on the StockAnalysis page, the SA URL
    must be preserved in `original_sa_url` (reference for clients with SA
    Premium cookies) but MUST NOT be used as the primary citation — the
    content was fetched from StockAnalysis.
    """
    from backend import stockanalysis

    html_with_sa_link = """
    <html><body>
      <h1>NVDA Q1 2027 Earnings Call Transcript</h1>
      <a href="https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript">Original</a>
      <main>Long transcript text </main>
    </body></html>
    """.replace("Long transcript text ", "Long transcript text " * 150)

    monkeypatch.setattr(stockanalysis, "_fetch_page", lambda url: html_with_sa_link)
    data = stockanalysis.fetch_transcript("https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/")

    assert data is not None
    # Source label is the actual provider, NOT plain "Seeking Alpha".
    assert data["source"] == "Seeking Alpha via StockAnalysis"
    # Citation URL is the StockAnalysis page we actually fetched.
    assert data["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    assert data["stockanalysis_url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    # The SA article URL is preserved as a reference, not as the citation.
    assert data["original_sa_url"] == "https://seekingalpha.com/article/4700000-nvidia-q1-2027-earnings-call-transcript"


def test_transcript_finder_labels_stockanalysis_fallback_as_via(monkeypatch):
    """The StockAnalysis fallback in transcript_finder must produce a
    'Seeking Alpha via StockAnalysis' label (per Ced's PDF convention),
    NOT plain 'Seeking Alpha' (which would be a lie about the content
    source) and NOT bare 'StockAnalysis' (which misses the SA lineage
    that users expect to see in client-facing artefacts).
    """
    monkeypatch.setattr("backend.seeking_alpha_access._read_store", lambda: {})
    monkeypatch.setattr(
        "backend.stockanalysis.search_transcripts",
        lambda ticker, limit=3: [{"url": "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/", "id": "568907"}],
    )
    monkeypatch.setattr(
        "backend.stockanalysis.fetch_transcript",
        lambda url: {
            "source": "Seeking Alpha via StockAnalysis",
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
    # Label must be the via-form, not the plain SA label (which would
    # contradict the StockAnalysis URL) and not bare "StockAnalysis"
    # (which loses the SA lineage).
    assert source["source"] == "Seeking Alpha via StockAnalysis"
    assert source["url"] == "https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/"
    # Bare "Seeking Alpha" (without "via") would mean the content came
    # from SA — it did not. The via-form makes this honest.
    assert not source["source"] == "Seeking Alpha"
    assert not source["source"] == "StockAnalysis"


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
