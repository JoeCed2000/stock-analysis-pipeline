"""Tests for backend/url_validator.py — BL-SA-003."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.url_validator import (
    _extract_urls_from_report,
    UrlCheck,
    ValidationReport,
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


class TestSyncValidation:
    @patch("backend.url_validator.asyncio.get_running_loop", side_effect=RuntimeError)
    @patch("backend.url_validator.validate_report_urls")
    def test_sync_wrapper_creates_new_loop(self, mock_validate, mock_loop):
        mock_validate.return_value = ValidationReport(total_urls=0)
        r = FakeReport()
        result = validate_report_urls_sync(r, ticker="TEST")
        assert isinstance(result, ValidationReport)
        mock_validate.assert_called_once()
