"""Tests for backend/url_validator.py — BL-SA-003."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.url_validator import (
    _check_one_url,
    _extract_urls_from_pdf,
    _extract_urls_from_report,
    _extract_urls_from_text,
    UrlCheck,
    ValidationReport,
    validate_pdf_urls_sync,
    validate_report_urls_sync,
)


class FakeSource:
    def __init__(self, url="", label=""):
        self.url = url
        self.label = label


class FakeClaimSource:
    def __init__(self, source_id="S1", source_url="", source_name="", grounding="direct_metric", section=""):
        self.source_id = source_id
        self.source_url = source_url
        self.source_name = source_name
        self.grounding = grounding
        self.section = section


class FakeReport:
    def __init__(self):
        self.ticker = "TEST"
        self.sources = []
        self.earnings_audio_url = None
        self.official_website = None
        self.claim_sources = []


class TestExtractUrls:
    def test_empty_report(self):
        r = FakeReport()
        urls = _extract_urls_from_report(r)
        assert urls == []

    def test_sources(self):
        r = FakeReport()
        r.sources = [
            FakeSource("https://www.sec.gov/edgar", "SEC EDGAR"),
            FakeSource("https://finnhub.io/api", "Finnhub"),
        ]
        urls = _extract_urls_from_report(r)
        assert len(urls) == 2
        assert urls[0] == ("https://www.sec.gov/edgar", "SEC EDGAR")

    def test_audio_url(self):
        r = FakeReport()
        r.earnings_audio_url = "https://edge.media-server.com/call"
        urls = _extract_urls_from_report(r)
        assert urls == [("https://edge.media-server.com/call", "Earnings Call Audio")]

    def test_official_website(self):
        r = FakeReport()
        r.official_website = "https://www.nvidia.com"
        urls = _extract_urls_from_report(r)
        assert urls == [("https://www.nvidia.com", "Official Website")]

    def test_claim_sources(self):
        r = FakeReport()
        r.claim_sources = [
            FakeClaimSource(source_id="S1", source_url="https://sec.gov/doc1"),
            FakeClaimSource(source_id="S2", source_url="https://sec.gov/doc2"),
        ]
        urls = _extract_urls_from_report(r)
        assert len(urls) == 2
        assert urls[0] == ("https://sec.gov/doc1", "ClaimSource[S1]")

    def test_dedup(self):
        r = FakeReport()
        r.sources = [FakeSource("https://sec.gov/x", "SEC")]
        r.official_website = "https://sec.gov/x"  # same URL
        urls = _extract_urls_from_report(r)
        assert len(urls) == 1  # deduplicated

    def test_skip_empty_urls(self):
        r = FakeReport()
        r.sources = [FakeSource("", "Empty")]
        urls = _extract_urls_from_report(r)
        assert urls == []


class TestExtractPdfUrls:
    def test_extract_urls_from_visible_pdf_text_and_annotations(self, tmp_path):
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "links.pdf"
        c = canvas.Canvas(str(pdf_path))
        c.drawString(72, 720, "Visible source: https://visible.example.com/path?x=1.")
        c.drawString(72, 700, "Clickable source")
        c.linkURL("https://click.example.com/report", (72, 696, 220, 714), relative=0)
        c.save()

        urls = _extract_urls_from_pdf(pdf_path)

        assert ("https://click.example.com/report", "PDF link annotation p1") in urls
        assert ("https://visible.example.com/path?x=1", "PDF visible text p1") in urls
        assert len({url for url, _ in urls}) == len(urls)

    def test_extract_urls_from_text_cleans_html_and_trailing_punctuation(self):
        urls = _extract_urls_from_text(
            "Sources: https://example.com/report?x=1&amp;y=2, and https://example.com/other).",
            "PDF visible text p1",
        )

        assert urls == [
            ("https://example.com/report?x=1&y=2", "PDF visible text p1"),
            ("https://example.com/other", "PDF visible text p1"),
        ]

    def test_validate_pdf_urls_sync_checks_extracted_pdf_urls(self, tmp_path):
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "validate.pdf"
        c = canvas.Canvas(str(pdf_path))
        c.drawString(72, 720, "https://validated.example.com/source")
        c.save()

        async def fake_check(url, label, timeout=8.0):
            return UrlCheck(url=url, label=label, alive=True, status_code=200)

        with patch("backend.url_validator._check_one_url", side_effect=fake_check) as mock_check:
            result = validate_pdf_urls_sync(pdf_path, ticker="PDF")

        assert result.ticker == "PDF"
        assert result.total_urls == 1
        assert result.alive == 1
        assert result.dead == 0
        assert result.checks[0].url == "https://validated.example.com/source"
        mock_check.assert_called_once()


class TestValidationReport:
    def test_healthy_when_no_dead(self):
        r = ValidationReport(total_urls=5, alive=5, dead=0)
        assert r.healthy is True

    def test_unhealthy_when_dead(self):
        r = ValidationReport(total_urls=5, alive=4, dead=1)
        assert r.healthy is False

    def test_dead_urls_filter(self):
        r = ValidationReport(
            total_urls=3, alive=1, dead=2,
            checks=[
                UrlCheck(url="https://ok.com", alive=True, status_code=200),
                UrlCheck(url="https://dead.com", alive=False, error="timeout"),
                UrlCheck(url="https://also-dead.com", alive=False, status_code=404),
            ],
        )
        assert len(r.dead_urls) == 2
        assert r.dead_urls[0].url == "https://dead.com"


class TestCheckOneUrl:
    @pytest.mark.asyncio
    async def test_restricted_status_is_reachable_not_dead(self):
        class FakeResponse:
            status_code = 403
            has_redirect_location = False
            headers = {}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method, url):
                return FakeResponse()

        with patch("httpx.AsyncClient", FakeAsyncClient):
            check = await _check_one_url("https://seekingalpha.com/symbol/NVDA/earnings/transcripts", "SA")

        assert check.status_code == 403
        assert check.alive is True
        assert check.error == "restricted but reachable: 403"

    @pytest.mark.asyncio
    async def test_known_antibot_5xx_is_reachable_not_dead(self):
        class FakeResponse:
            status_code = 503
            has_redirect_location = False
            headers = {}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method, url):
                return FakeResponse()

        with patch("httpx.AsyncClient", FakeAsyncClient):
            check = await _check_one_url("https://finance.yahoo.com/quote/GOOGL", "Yahoo")

        assert check.status_code == 503
        assert check.alive is True
        assert check.error == "transient anti-bot response: 503"

    @pytest.mark.asyncio
    async def test_404_remains_dead(self):
        class FakeResponse:
            status_code = 404
            has_redirect_location = False
            headers = {}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method, url):
                return FakeResponse()

        with patch("httpx.AsyncClient", FakeAsyncClient):
            check = await _check_one_url("https://example.com/missing", "Missing")

        assert check.status_code == 404
        assert check.alive is False


class TestSyncValidation:
    @patch("backend.url_validator.asyncio.get_running_loop", side_effect=RuntimeError)
    @patch("backend.url_validator.validate_report_urls")
    def test_sync_wrapper_creates_new_loop(self, mock_validate, mock_loop):
        mock_validate.return_value = ValidationReport(total_urls=0)
        r = FakeReport()
        result = validate_report_urls_sync(r, ticker="TEST")
        assert isinstance(result, ValidationReport)
        mock_validate.assert_called_once()


class TestRendererWiring:
    def test_pdf_renderer_validates_final_pdf_artifact(self):
        import inspect
        from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf

        source = inspect.getsource(render_earnings_deep_dive_pdf)

        assert "validate_pdf_urls_sync" in source
        assert "validate_pdf_urls_sync(output" in source
        assert "validate_report_urls_sync(report" not in source
