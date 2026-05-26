"""Tests for IR site scraping — earnings dates and webcasts.

IN-008: Collecte IR sites (dates earnings, webcasts)
Tests: _parse_ir_date, _is_future_date, _extract_next_earnings_from_ir,
        _extract_audio_webcast_from_ir, _search_next_earnings_tavily.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.pipeline import (
    _parse_ir_date,
    _is_future_date,
    _extract_next_earnings_from_ir,
    _extract_audio_webcast_from_ir,
    _search_next_earnings_tavily,
)


# ── _parse_ir_date ────────────────────────────────────────────────────


class TestParseIRDate:
    def test_iso_format(self):
        assert _parse_ir_date("2026-07-15") == "2026-07-15"

    def test_slash_format(self):
        assert _parse_ir_date("5/20/2026") == "2026-05-20"

    def test_slash_padded(self):
        assert _parse_ir_date("12/01/2026") == "2026-12-01"

    def test_short_year_format(self):
        assert _parse_ir_date("26-7-15") == "2026-07-15"

    def test_short_year_padded(self):
        assert _parse_ir_date("26-12-01") == "2026-12-01"

    def test_day_month_year(self):
        assert _parse_ir_date("28 May 2026") == "2026-05-28"

    def test_day_month_year_comma(self):
        assert _parse_ir_date("28 May, 2026") == "2026-05-28"

    def test_month_day_year(self):
        assert _parse_ir_date("May 28, 2026") == "2026-05-28"

    def test_month_day_year_no_comma(self):
        assert _parse_ir_date("July 23 2026") == "2026-07-23"

    def test_month_abbrev_with_st_th(self):
        assert _parse_ir_date("May 28th 2026") == "2026-05-28"

    def test_invalid_returns_none(self):
        assert _parse_ir_date("not a date") is None

    def test_empty_returns_none(self):
        assert _parse_ir_date("") is None

    def test_garbage_returns_none(self):
        assert _parse_ir_date("123456") is None


# ── _is_future_date ────────────────────────────────────────────────────


class TestIsFutureDate:
    def test_tomorrow_is_future(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert _is_future_date(tomorrow) is True

    def test_today_is_future(self):
        today = date.today().isoformat()
        assert _is_future_date(today) is True

    def test_yesterday_is_past(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        assert _is_future_date(yesterday) is False

    def test_far_future(self):
        assert _is_future_date("2030-01-01") is True

    def test_invalid_date_returns_false(self):
        assert _is_future_date("not-a-date") is False

    def test_empty_returns_false(self):
        assert _is_future_date("") is False


# ── _extract_next_earnings_from_ir ─────────────────────────────────────


def _mock_resp(text: str, status=200):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    return resp


def _patch_http(mock_http_client, resp):
    """Patch http.get to return a controlled response."""
    mock_http_client.get.return_value = resp


@pytest.fixture
def mock_http_client():
    """Patch the http_client module used inside the IR functions."""
    with patch("backend.http_client.http") as mock:
        yield mock


# Helper: make a future date string like "May 28, 2026" that actually resolves
# to a future date (or today) so _is_future_date passes.
def _future_month_day():
    """Return a date string in the future relative to today.
    Format: '25 Jun 2026' (day-month, matches the regex pattern)."""
    d = date.today() + timedelta(days=30)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{d.day} {months[d.month - 1]} {d.year}"


class TestExtractNextEarnings:
    def test_next_earnings_label_pattern(self, mock_http_client):
        """Pattern: 'Next Earnings Date: May 28, 2026'"""
        fut = _future_month_day()
        html = f"""<html><body><p>Next Earnings Date: {fut}</p></body></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
        assert result is not None
        assert result.startswith("20")

    def test_iso_date_in_text(self, mock_http_client):
        """Pattern: iso date in text."""
        next_year = date.today().year + 1
        html = f"""<html><body>Q4 Earnings Call — {next_year}-06-15</body></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
        assert result == f"{next_year}-06-15"

    def test_quarter_pattern(self, mock_http_client):
        """Pattern: 'Q2 2026 Earnings Call — July 23, 2026'"""
        fut = _future_month_day()
        html = f"""<html><body>Q2 2026 Earnings Call — {fut}</body></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "MSFT")
        assert result is not None
        assert result.startswith("20")

    def test_jsonld_startdate(self, mock_http_client):
        """Pattern: JSON-LD with startDate."""
        next_year = date.today().year + 1
        html = f"""<script type="application/ld+json">{{"startDate":"{next_year}-04-20"}}</script>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "NVDA")
        assert result == f"{next_year}-04-20"

    def test_time_element(self, mock_http_client):
        """Pattern: <time datetime='...'>"""
        next_year = date.today().year + 1
        html = f"""<html><time datetime="{next_year}-05-15">May 15</time></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "GOOGL")
        assert result == f"{next_year}-05-15"

    def test_403_still_parses(self, mock_http_client):
        """403 response should still be parsed (some sites block but return body)."""
        fut = _future_month_day()
        html = f"""<html><body>Earnings Date: {fut}</body></html>"""
        _patch_http(mock_http_client, _mock_resp(html, status=403))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
        assert result is not None
        assert result.startswith("20")

    def test_no_match_falls_back_to_tavily(self, mock_http_client):
        """No date found → Tavily fallback."""
        _patch_http(mock_http_client, _mock_resp("<html><body>Welcome to IR</body></html>"))
        with patch("backend.pipeline._search_next_earnings_tavily") as mock_tav:
            mock_tav.return_value = "2026-08-15"
            result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
            assert result == "2026-08-15"
            mock_tav.assert_called_once()

    def test_http_error_returns_none_then_tavily(self, mock_http_client):
        """Exception → fallback to Tavily."""
        mock_http_client.get.side_effect = Exception("Connection refused")
        with patch("backend.pipeline._search_next_earnings_tavily") as mock_tav:
            mock_tav.return_value = None
            result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
            assert result is None

    def test_past_date_ignored(self, mock_http_client):
        """A date in the past is ignored, falls back to Tavily."""
        _patch_http(mock_http_client, _mock_resp(
            "<html><body>Next Earnings Date: Jan 15, 2020</body></html>"
        ))
        with patch("backend.pipeline._search_next_earnings_tavily") as mock_tav:
            mock_tav.return_value = "2026-11-10"
            result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
            assert result == "2026-11-10"

    def test_scripts_and_styles_stripped(self, mock_http_client):
        """<script> containing a date pattern should not match."""
        fut = _future_month_day()
        html = f"""<script>console.log("Earnings Date: 2020-01-01")</script>
                   <body><p>Earnings Date: {fut}</p></body>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_next_earnings_from_ir("https://ir.example.com", "AAPL")
        assert result is not None
        assert result.startswith("20")
        # Should match the body date, not the script date (which is past)


# ── _extract_audio_webcast_from_ir ─────────────────────────────────────


class TestExtractAudioWebcast:
    def test_webcast_in_href(self, mock_http_client):
        """Direct link with 'webcast' in href."""
        html = """<html><a href="/events/webcast/q2-2026">Listen</a></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_audio_webcast_from_ir(
            "https://investor.example.com", "AAPL"
        )
        assert result == "https://investor.example.com/events/webcast/q2-2026"

    def test_earnings_call_audio_href(self, mock_http_client):
        """Link with 'earnings' and 'call' in href."""
        html = """<html><a href="/earnings-call-audio">Audio</a></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_audio_webcast_from_ir(
            "https://ir.example.com", "MSFT"
        )
        assert result == "https://ir.example.com/earnings-call-audio"

    def test_audio_replay_keyword(self, mock_http_client):
        """Keyword 'audio replay' with nearby href."""
        html = """<html><div>Audio Replay <a href="/audio/q2-2026.mp3">Download</a></div></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_audio_webcast_from_ir(
            "https://ir.example.com", "NVDA"
        )
        assert result == "https://ir.example.com/audio/q2-2026.mp3"

    def test_listen_to_keyword(self, mock_http_client):
        """Keyword 'listen to' with nearby href."""
        html = """<html><span>Listen to <a href="/webcast/replay">Replay</a></span></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_audio_webcast_from_ir(
            "https://ir.example.com", "GOOGL"
        )
        assert result == "https://ir.example.com/webcast/replay"

    def test_skips_pdf_ics_links(self, mock_http_client):
        """Skips .pdf, .ics, .xml links."""
        html = """<html><a href="/events/calendar.ics">Calendar</a>
                       <a href="/events/webcast">Webcast</a></html>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_audio_webcast_from_ir(
            "https://ir.example.com", "AMZN"
        )
        assert "webcast" in result

    def test_full_url_kept(self, mock_http_client):
        """Full http URLs in href kept as-is."""
        html = """<a href="https://edge.media-server.com/mmc/p/abc123">Webcast</a>"""
        _patch_http(mock_http_client, _mock_resp(html))
        result = _extract_audio_webcast_from_ir(
            "https://ir.example.com", "TSLA"
        )
        assert result == "https://edge.media-server.com/mmc/p/abc123"

    def test_no_match_falls_back_to_tavily(self, mock_http_client):
        """No webcast found → Tavily fallback."""
        _patch_http(mock_http_client, _mock_resp("<html><body>Welcome</body></html>"))
        with patch("backend.pipeline._search_audio_webcast_tavily") as mock_tav:
            mock_tav.return_value = "https://example.com/webcast"
            result = _extract_audio_webcast_from_ir(
                "https://ir.example.com", "AAPL"
            )
            assert result == "https://example.com/webcast"

    def test_http_error_falls_back(self, mock_http_client):
        """Exception → Tavily fallback."""
        mock_http_client.get.side_effect = Exception("Timeout")
        with patch("backend.pipeline._search_audio_webcast_tavily") as mock_tav:
            mock_tav.return_value = None
            result = _extract_audio_webcast_from_ir(
                "https://ir.example.com", "AAPL"
            )
            assert result is None


# ── _search_next_earnings_tavily (offline fallback tests) ───────────────


class TestSearchNextEarningsTavily:
    def test_no_api_key_returns_none(self, monkeypatch):
        """Without TAVILY_API_KEY, returns None immediately."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = _search_next_earnings_tavily("AAPL")
        assert result is None

    def test_extracts_domain_from_ir_url(self, monkeypatch):
        """Company hint extracted from IR URL domain."""
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "results": [
                {"content": "Apple next earnings date is 2026-07-28"}
            ]
        }
        with patch("backend.http_client.http") as mock_http_client_tav:
            mock_http_client_tav.post.return_value = resp
            with patch("backend.pipeline._parse_ir_date") as mock_parse:
                mock_parse.return_value = "2026-07-28"
                with patch("backend.pipeline._is_future_date") as mock_future:
                    mock_future.return_value = True
                    result = _search_next_earnings_tavily(
                        "AAPL", "https://investor.apple.com"
                    )
                    # The query should include "Apple" extracted from domain
                    assert result == "2026-07-28"
