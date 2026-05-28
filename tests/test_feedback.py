"""IN-007: Tests for the existing /api/feedback endpoint.

POST /api/feedback — FormData (ticker, text, files) — stored per-ticker via feedback_store.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app

# Bypass auth — set API key and pass it as header
TEST_KEY = "test-feedback-key"


@pytest.fixture(autouse=True)
def api_key_setup(monkeypatch):
    """Set up test API key to bypass auth."""
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    # Also patch the module-level _API_KEY cache so the guard sees it
    monkeypatch.setattr("backend.main._API_KEY", TEST_KEY)


@pytest.fixture
def client():
    return TestClient(app)


class TestFeedbackEndpoint:
    """Test the existing FormData-based feedback endpoint in main.py."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        """Redirect feedback storage to a temp directory."""
        self.tmp = tmp_path
        self.feedback_root = tmp_path / "analyses"
        monkeypatch.setattr(
            "backend.feedback_store.ANALYSES_DIR",
            self.feedback_root,
        )

    def _submit(self, client, ticker="AAPL", text=""):
        """Submit feedback via FormData with auth header."""
        data = {"ticker": ticker}
        if text:
            data["text"] = text
        headers = {"X-API-Key": TEST_KEY}
        return client.post("/api/feedback", data=data, headers=headers)

    def test_up_feedback(self, client):
        resp = self._submit(client, text="👍")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_detailed_feedback(self, client):
        resp = self._submit(client, text="Market cap seems off by ~10%")
        assert resp.status_code == 200

    def test_feedback_stored_on_disk(self, client):
        self._submit(client, ticker="NVDA", text="Test feedback")
        fb_dir = self.feedback_root / "feedback_NVDA"
        assert fb_dir.exists()
        assert fb_dir.is_dir()
        index = fb_dir / "index.json"
        assert index.exists()

    def test_invalid_ticker_rejected(self, client):
        resp = self._submit(client, ticker="123!")
        assert resp.status_code == 422

    def test_empty_ticker_rejected(self, client):
        resp = self._submit(client, ticker="")
        assert resp.status_code == 422

    def test_ticker_uppercased(self, client):
        self._submit(client, ticker="aapl", text="feedback")
        fb_dir = self.feedback_root / "feedback_AAPL"
        assert fb_dir.exists()

    def test_feedback_has_timestamp(self, client):
        self._submit(client, ticker="MSFT", text="timestamp test")
        fb_dir = self.feedback_root / "feedback_MSFT"
        index_file = fb_dir / "index.json"
        entries = json.loads(index_file.read_text())
        assert len(entries) >= 1
        assert "submitted_at" in entries[-1]

    def test_admin_feedback_endpoint_reads_same_store(self, client):
        self._submit(client, ticker="MSFT", text="Admin sees this")
        resp = client.get("/api/admin/feedback", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) >= 1
        assert entries[0]["ticker"] == "MSFT"
        assert entries[0]["text"] == "Admin sees this"

    def test_multiple_entries_stacked(self, client):
        for i in range(3):
            self._submit(client, ticker="GOOGL", text=f"Feedback #{i}")
        fb_dir = self.feedback_root / "feedback_GOOGL"
        index = json.loads((fb_dir / "index.json").read_text())
        assert len(index) == 3

    def test_feedback_with_file(self, client):
        headers = {"X-API-Key": TEST_KEY}
        resp = client.post(
            "/api/feedback",
            data={"ticker": "AAPL", "text": "Screenshot"},
            files={"files": ("shot.png", b"fake png", "image/png")},
            headers=headers,
        )
        assert resp.status_code == 200
