"""Tests for the feedback endpoints.

POST /api/feedback accepts:
- ticker-specific feedback (legacy behavior)
- general product feedback without a ticker (new dedicated page flow)
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app

TEST_KEY = "test-feedback-key"


@pytest.fixture(autouse=True)
def api_key_setup(monkeypatch):
    """Set up test API key to bypass auth."""
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setattr("backend.main._API_KEY", TEST_KEY)


@pytest.fixture
def client():
    return TestClient(app)


class TestFeedbackEndpoint:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        """Redirect feedback storage to a temp directory."""
        self.feedback_root = tmp_path / "analyses"
        monkeypatch.setattr("backend.feedback_store.ANALYSES_DIR", self.feedback_root)

    def _submit(self, client, ticker=None, text="", files=None):
        data = {}
        if ticker is not None:
            data["ticker"] = ticker
        if text:
            data["text"] = text
        headers = {"X-API-Key": TEST_KEY}
        return client.post("/api/feedback", data=data, files=files or {}, headers=headers)

    def test_general_feedback_without_ticker(self, client):
        resp = self._submit(client, text="The feedback page is easier to use")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["ticker"] is None
        assert body["bucket"] == "GENERAL"

    def test_general_feedback_stored_under_general_bucket(self, client):
        self._submit(client, text="General UX feedback")
        fb_dir = self.feedback_root / "feedback_GENERAL"
        assert fb_dir.exists()
        index = fb_dir / "index.json"
        assert index.exists()
        entries = json.loads(index.read_text())
        assert entries[0]["ticker"] is None
        assert entries[0]["text"] == "General UX feedback"

    def test_feedback_stored_on_disk_for_ticker(self, client):
        self._submit(client, ticker="NVDA", text="Test feedback")
        fb_dir = self.feedback_root / "feedback_NVDA"
        assert fb_dir.exists()
        assert fb_dir.is_dir()
        assert (fb_dir / "index.json").exists()

    def test_invalid_ticker_rejected(self, client):
        resp = self._submit(client, ticker="123!", text="Bad ticker")
        assert resp.status_code == 422

    def test_blank_ticker_saved_as_general_feedback(self, client):
        resp = self._submit(client, ticker="", text="No ticker on purpose")
        assert resp.status_code == 200
        assert resp.json()["bucket"] == "GENERAL"

    def test_ticker_uppercased(self, client):
        self._submit(client, ticker="aapl", text="feedback")
        fb_dir = self.feedback_root / "feedback_AAPL"
        assert fb_dir.exists()

    def test_feedback_has_timestamp(self, client):
        self._submit(client, ticker="MSFT", text="timestamp test")
        entries = json.loads((self.feedback_root / "feedback_MSFT" / "index.json").read_text())
        assert len(entries) >= 1
        assert "submitted_at" in entries[-1]

    def test_feedback_requires_text_or_file(self, client):
        resp = self._submit(client)
        assert resp.status_code == 422

    def test_feedback_list_endpoint_reads_same_store(self, client):
        self._submit(client, text="General feedback visible to user")
        self._submit(client, ticker="MSFT", text="Ticker feedback visible to user")
        resp = client.get("/api/feedback", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 2
        texts = [entry["text"] for entry in payload["entries"]]
        assert "General feedback visible to user" in texts
        assert "Ticker feedback visible to user" in texts

    def test_admin_feedback_endpoint_reads_same_store(self, client):
        self._submit(client, ticker="MSFT", text="Admin sees this")
        resp = client.get("/api/admin/feedback", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) >= 1
        assert entries[0]["ticker"] == "MSFT"
        assert entries[0]["text"] == "Admin sees this"

    def test_ticker_specific_feedback_endpoint_still_works(self, client):
        self._submit(client, ticker="GOOGL", text="Ticker-only history")
        resp = client.get("/api/feedback/GOOGL", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["ticker"] == "GOOGL"
        assert payload["entries"][0]["text"] == "Ticker-only history"

    def test_multiple_entries_stacked(self, client):
        for i in range(3):
            self._submit(client, ticker="GOOGL", text=f"Feedback #{i}")
        index = json.loads((self.feedback_root / "feedback_GOOGL" / "index.json").read_text())
        assert len(index) == 3

    def test_feedback_with_file(self, client):
        resp = self._submit(
            client,
            ticker="AAPL",
            text="Screenshot",
            files={"files": ("shot.png", b"fake png", "image/png")},
        )
        assert resp.status_code == 200

    def test_feedback_file_download_endpoint_serves_saved_attachment(self, client):
        self._submit(
            client,
            ticker="AAPL",
            text="Screenshot",
            files={"files": ("shot.png", b"fake png", "image/png")},
        )
        entries = json.loads((self.feedback_root / "feedback_AAPL" / "index.json").read_text())
        file_name = entries[0]["files"][0]

        resp = client.get(f"/api/feedback-file/AAPL/{file_name}", headers={"X-API-Key": TEST_KEY})

        assert resp.status_code == 200
        assert resp.content == b"fake png"

    def test_feedback_file_download_missing_returns_404(self, client):
        resp = client.get("/api/feedback-file/AAPL/missing.pdf", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 404
