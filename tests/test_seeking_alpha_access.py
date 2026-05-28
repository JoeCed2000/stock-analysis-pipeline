import json
import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app

TEST_KEY = "test-seeking-alpha-key"


@pytest.fixture(autouse=True)
def api_key_setup(monkeypatch):
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setattr("backend.main._API_KEY", TEST_KEY)


@pytest.fixture
def client():
    return TestClient(app)


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

    def test_probe_uses_saved_cookies(self, client, monkeypatch):
        captured = {}

        class FakeResponse:
            status_code = 200
            text = "<html>transcript list</html>"
            url = "https://seekingalpha.com/symbol/NVDA/earnings/transcripts"

        def fake_get(url, headers=None, timeout=None, follow_redirects=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            return FakeResponse()

        monkeypatch.setattr("backend.seeking_alpha_access.http.get", fake_get)

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
        assert captured["url"].endswith("/symbol/NVDA/earnings/transcripts")
        assert captured["headers"]["Cookie"] == "sessionid=abc123; xsrf=token456"


class TestCompanyOverviewDownload:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.analysis_dir = tmp_path / "2026-05-28_120000_AAPL_Apple_Inc"
        self.sources_dir = self.analysis_dir / "01_official_company_sources"
        self.sources_dir.mkdir(parents=True)
        monkeypatch.setattr("backend.main._find_analysis_dirs", lambda ticker: [self.analysis_dir])

    def test_download_prefers_pdf_when_available(self, client):
        pdf_path = self.sources_dir / "company_profile_AAPL.pdf"
        pdf_path.write_bytes(b"%PDF-test")

        resp = client.get("/api/company-overview/AAPL/download")

        assert resp.status_code == 200
        assert resp.content == b"%PDF-test"
        assert "company_profile_AAPL.pdf" in resp.headers.get("content-disposition", "")

    def test_download_auto_falls_back_to_json(self, client):
        json_path = self.sources_dir / "company_overview_AAPL.json"
        json_path.write_text('{"ticker":"AAPL"}', encoding="utf-8")

        resp = client.get("/api/company-overview/AAPL/download")

        assert resp.status_code == 200
        assert resp.json()["ticker"] == "AAPL"

    def test_invalid_format_rejected(self, client):
        resp = client.get("/api/company-overview/AAPL/download?format=exe")

        assert resp.status_code == 400
