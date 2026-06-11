import json
import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.seeking_alpha_access import _is_earnings_call_transcript_link

TEST_KEY = "test-seeking-alpha-key"


@pytest.fixture(autouse=True)
def api_key_setup(monkeypatch):
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setattr("backend.main._API_KEY", TEST_KEY)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def remote_client():
    """Simulate production traffic so auth bypass for loopback/testclient does not apply."""
    return TestClient(app, client=("203.0.113.10", 50000))


class TestSeekingAlphaAccessAdmin:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.state_dir = tmp_path / ".state"
        monkeypatch.setattr("backend.seeking_alpha_access.STATE_DIR", self.state_dir)

    def test_status_reports_not_configured_by_default(self, client):
        resp = client.get("/api/admin/seeking-alpha/access", headers={"X-API-Key": TEST_KEY})

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["configured"] is False
        assert payload["cookie_count"] == 0
        assert "cookie_header" not in payload

    def test_feedback_mode_status_is_public_for_remote_browser(self, remote_client):
        resp = remote_client.get("/api/admin/seeking-alpha/access")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["configured"] is False
        assert "cookie_header" not in payload

    def test_feedback_mode_save_is_public_but_clear_stays_protected(self, remote_client):
        save_resp = remote_client.post(
            "/api/admin/seeking-alpha/access",
            json={"cookie_header": "sessionid=abc123; xsrf=token456"},
        )

        assert save_resp.status_code == 200
        saved = save_resp.json()
        assert saved["configured"] is True
        assert saved["cookie_count"] == 2
        assert "cookie_header" not in saved
        assert (self.state_dir / "seeking_alpha_access.json").exists()

        clear_resp = remote_client.delete("/api/admin/seeking-alpha/access")
        assert clear_resp.status_code == 403
        assert (self.state_dir / "seeking_alpha_access.json").exists()

    def test_feedback_mode_probe_is_public_for_remote_browser(self, remote_client, monkeypatch):
        async def fake_probe(ticker=None):
            from backend.seeking_alpha_access import _read_store
            store = _read_store()
            assert store["cookie_header"] == "sessionid=abc123; xsrf=token456"
            return {"ok": True, "authenticated": True, "status_code": 200, "ticker": (ticker or "").upper()}

        monkeypatch.setattr("backend.seeking_alpha_access.probe_access_async", fake_probe)
        remote_client.post(
            "/api/admin/seeking-alpha/access",
            json={"cookie_header": "sessionid=abc123; xsrf=token456"},
        )

        resp = remote_client.post("/api/admin/seeking-alpha/test", json={"ticker": "nvda"})

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is True
        assert payload["ticker"] == "NVDA"

    def test_save_then_clear_roundtrip(self, client):
        save_resp = client.post(
            "/api/admin/seeking-alpha/access",
            json={"cookie_header": "sessionid=abc123; xsrf=token456"},
            headers={"X-API-Key": TEST_KEY},
        )
        assert save_resp.status_code == 200
        saved = save_resp.json()
        assert saved["configured"] is True
        assert saved["cookie_count"] == 2
        assert "cookie_header" not in saved

        store_path = self.state_dir / "seeking_alpha_access.json"
        assert store_path.exists()
        store = json.loads(store_path.read_text())
        assert store["cookie_header"] == "sessionid=abc123; xsrf=token456"
        if os.name == "posix":
            assert oct(store_path.stat().st_mode & 0o777) == "0o600"

        clear_resp = client.delete("/api/admin/seeking-alpha/access", headers={"X-API-Key": TEST_KEY})
        assert clear_resp.status_code == 200
        cleared = clear_resp.json()
        assert cleared["configured"] is False
        assert not store_path.exists()

    def test_status_flags_analytics_only_cookie_header(self, client):
        save_resp = client.post(
            "/api/admin/seeking-alpha/access",
            json={"cookie_header": "__hssc=1; _ga=GA1.1.1; _hjSession_65666=abc"},
            headers={"X-API-Key": TEST_KEY},
        )

        assert save_resp.status_code == 200
        diagnostics = save_resp.json()["cookie_diagnostics"]
        assert diagnostics["quality"] == "analytics_only_or_incomplete"
        assert diagnostics["has_auth_cookie"] is False
        assert diagnostics["has_antibot_cookie"] is False

    def test_probe_reports_missing_auth_or_antibot_before_network(self, client):
        client.post(
            "/api/admin/seeking-alpha/access",
            json={"cookie_header": "__hssc=1; _ga=GA1.1.1; _hjSession_65666=abc"},
            headers={"X-API-Key": TEST_KEY},
        )

        resp = client.post(
            "/api/admin/seeking-alpha/test",
            json={"ticker": "nvda"},
            headers={"X-API-Key": TEST_KEY},
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is False
        assert payload["authenticated"] is False
        assert payload["reason"] == "missing_auth_or_antibot_cookies"
        assert payload["cookie_diagnostics"]["quality"] == "analytics_only_or_incomplete"

    def test_probe_uses_saved_cookies(self, client, monkeypatch):
        async def fake_probe(ticker=None):
            from backend.seeking_alpha_access import _read_store
            store = _read_store()
            assert store["cookie_header"] == "sessionid=abc123; xsrf=token456"
            return {
                "ok": True,
                "authenticated": True,
                "status_code": 200,
                "ticker": (ticker or "").upper(),
                "url": f"https://seekingalpha.com/symbol/{(ticker or '').upper()}/earnings/transcripts",
            }

        monkeypatch.setattr("backend.seeking_alpha_access.probe_access_async", fake_probe)

        client.post(
            "/api/admin/seeking-alpha/access",
            json={"cookie_header": "sessionid=abc123; xsrf=token456"},
            headers={"X-API-Key": TEST_KEY},
        )
        resp = client.post(
            "/api/admin/seeking-alpha/test",
            json={"ticker": "nvda"},
            headers={"X-API-Key": TEST_KEY},
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ok"] is True
        assert payload["authenticated"] is True
        assert payload["status_code"] == 200
        assert payload["ticker"] == "NVDA"
        assert payload["url"].endswith("/symbol/NVDA/earnings/transcripts")

    @pytest.mark.asyncio
    async def test_probe_handles_playwright_negative_result_without_keyerror(self, monkeypatch):
        """A Playwright PRO-cookie failure must be returned as a clean diagnosis.

        Regression: _probe_with_playwright() can return negative outcomes such as
        mpw_locked_even_with_playwright without an authenticated key. The outer
        probe must not collapse that into request_error "'authenticated'".
        """
        from backend import seeking_alpha_access as saa

        store = {
            "cookie_header": "ever_pro=1; has_paid_subscription=true; sapu=abc; _px3=anti",
            "cookies_parsed": [
                {"name": "ever_pro", "value": "1", "domain": ".seekingalpha.com", "path": "/"},
                {"name": "has_paid_subscription", "value": "true", "domain": ".seekingalpha.com", "path": "/"},
                {"name": "sapu", "value": "abc", "domain": ".seekingalpha.com", "path": "/"},
                {"name": "_px3", "value": "anti", "domain": ".seekingalpha.com", "path": "/"},
            ],
        }
        saa._write_store(store)

        monkeypatch.setattr(
            saa,
            "_probe_with_playwright",
            lambda listing_url, cookie_store: {
                "ok": False,
                "reason": "mpw_locked_even_with_playwright",
                "text_length": 1200,
                "url": "https://seekingalpha.com/article/123-test-transcript",
                "phase": "playwright_transcript",
            },
        )

        result = await saa.probe_access_async("nvda")

        assert result["ok"] is False
        assert result["authenticated"] is False
        assert result["reachable"] is True
        assert result["reason"] == "mpw_locked_even_with_playwright"
        assert result["probe_method"] == "transcript_deep_probe"
        assert "error" not in result

    def test_probe_link_filter_ranks_earnings_call_above_conference_transcript(self):
        """Transcript links must be classified and ranked, not binary-rejected.

        Ced rule 2026-06-09: 'Presents at Bank of America ... Conference
        Transcript' is VALID earnings content (prepared remarks + Q&A at an
        industry event) and must be accepted as a fallback, NOT rejected.
        The ranking system prefers Q1 2027 Earnings Call (rank 100) over
        such conference transcripts (rank 20), but both are usable.

        The only hard rejections are non-transcript artefacts: slides-only
        'Earnings Call Presentation', slideshows, news, commentary, and
        comment anchors.
        """
        from backend.seeking_alpha_access import (
            _RANK_CONFERENCE_TRANSCRIPT,
            _RANK_EARNINGS_CALL,
            _is_earnings_call_transcript_link,
            _rank_transcript_link,
        )

        # Conference transcript with Q&A → ACCEPT, rank 20.
        assert _is_earnings_call_transcript_link(
            "NVIDIA Corporation (NVDA) Presents at Bank of America 2026 Global Technology Conference Transcript",
            "/article/4912081-nvidia-corporation-nvda-presents-at-bank-of-america-2026-global-technology-conference",
        )
        assert (
            _rank_transcript_link(
                "NVIDIA Corporation (NVDA) Presents at Bank of America 2026 Global Technology Conference Transcript",
                "/article/4912081-nvidia-corporation-nvda-presents-at-bank-of-america-2026-global-technology-conference",
            )
            == _RANK_CONFERENCE_TRANSCRIPT
        )

        # Slides-only 'Earnings Call Presentation' → still REJECTED
        # (no spoken transcript content).
        assert not _is_earnings_call_transcript_link(
            "NVIDIA Corporation 2027 Q1 - Results - Earnings Call Presentation",
            "/article/4907285-nvidia-corporation-2027-q1-results-earnings-call-presentation",
        )

        # Q1 2027 Earnings Call Transcript → ACCEPT, rank 100 (top).
        assert _is_earnings_call_transcript_link(
            "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript",
            "/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript",
        )
        assert (
            _rank_transcript_link(
                "NVIDIA Corporation (NVDA) Q1 2027 Earnings Call Transcript",
                "/article/4907259-nvidia-corporation-nvda-q1-2027-earnings-call-transcript",
            )
            == _RANK_EARNINGS_CALL
        )

        # Ranking invariant: earnings call (100) > conference (20), so the
        # pipeline's _best_transcript_source / transcript_ranking picks the
        # Q1 2027 Earnings Call over the conference transcript when both
        # are present on the SA listing.
        assert _RANK_EARNINGS_CALL > _RANK_CONFERENCE_TRANSCRIPT


class TestCompanyOverviewDownload:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.analysis_dir = tmp_path / "2026-05-28_120000_AAPL_Apple_Inc"
        self.sources_dir = self.analysis_dir / "01_official_company_sources"
        self.sources_dir.mkdir(parents=True)
        monkeypatch.setattr("backend.main._find_analysis_dirs", lambda ticker: [self.analysis_dir])

    def test_download_serves_current_investor_profile_pdf_when_present(self, client, monkeypatch):
        current_pdf = self.sources_dir / "AAPL_company_overview_investor_profile_2026-05-28.pdf"
        legacy_pdf = self.sources_dir / "company_profile_AAPL.pdf"
        current_pdf.write_bytes(b"%PDF-current")
        legacy_pdf.write_bytes(b"%PDF-legacy")
        monkeypatch.setattr("backend.main._company_overview_pdf_quality_failure", lambda path: None)

        resp = client.get("/api/company-overview/AAPL/download")

        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/pdf")
        content_disposition = resp.headers.get("content-disposition", "")
        assert "inline" in content_disposition
        assert "AAPL_company_overview_investor_profile_2026-05-28.pdf" in content_disposition
        assert resp.content.startswith(b"%PDF-current")

    def test_download_legacy_only_does_not_serve_thin_client_pdf(self, client):
        legacy_pdf = self.sources_dir / "company_profile_AAPL.pdf"
        legacy_pdf.write_bytes(b"%PDF-legacy-only")

        resp = client.get("/api/company-overview/AAPL/download?format=pdf")

        assert resp.status_code == 404
        payload = resp.json()
        assert payload["detail"] == "No company overview artifact found for AAPL"

    def test_download_tiny_current_pdf_is_blocked_as_not_client_ready(self, client):
        tiny_pdf = self.sources_dir / "AAPL_company_overview_investor_profile_2026-05-28.pdf"
        tiny_pdf.write_bytes(b"%PDF-tiny")

        resp = client.get("/api/company-overview/AAPL/download?format=pdf")

        assert resp.status_code == 422
        payload = resp.json()["detail"]
        assert payload["status"] == "company_overview_pdf_blocked"
        assert payload["retryable"] is True
        assert payload["rejected_pdfs"][0]["reason"].startswith("too_small:")

    def test_download_no_artifact_returns_explicit_actionable_404(self, client):
        resp = client.get("/api/company-overview/AAPL/download")

        assert resp.status_code == 404
        assert resp.headers.get("content-type", "").startswith("application/json")
        payload = resp.json()
        assert payload["detail"] == "No company overview artifact found for AAPL"

    def test_invalid_format_rejected(self, client):
        resp = client.get("/api/company-overview/AAPL/download?format=exe")

        assert resp.status_code == 400
