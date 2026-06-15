"""Tests for the feedback endpoints.

POST /api/feedback accepts:
- ticker-specific feedback (legacy behavior)
- general product feedback without a ticker (new dedicated page flow)
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.feedback_store import _decorate_entry, _normalize_feedback_bucket

TEST_KEY = "test-feedback-key"


@pytest.fixture(autouse=True)
def api_key_setup(monkeypatch):
    """Set up test API key to bypass auth."""
    monkeypatch.setenv("CED_CONTROL_KEY", TEST_KEY)
    monkeypatch.setattr("backend.main._API_KEY", TEST_KEY)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def remote_client():
    """Simulate production traffic so auth bypass for loopback/testclient does not apply."""
    return TestClient(app, client=("203.0.113.10", 50000))


class TestFeedbackEndpoint:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        """Redirect feedback storage to a temp directory."""
        self.feedback_root = tmp_path / "analyses"
        monkeypatch.setattr("backend.feedback_store.ANALYSES_DIR", self.feedback_root)

    def _submit(self, client, ticker=None, category=None, text="", files=None):
        data = {}
        if ticker is not None:
            data["ticker"] = ticker
        if category is not None:
            data["category"] = category
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

    def test_feedback_category_is_persisted(self, client):
        resp = self._submit(client, ticker="NVDA", category="data_quality", text="Need better TTM consistency")
        assert resp.status_code == 200
        body = resp.json()
        assert body["category"] == "data_quality"

        entries = json.loads((self.feedback_root / "feedback_NVDA" / "index.json").read_text())
        assert entries[-1]["category"] == "data_quality"

    def test_general_feedback_stored_under_general_bucket(self, client):
        self._submit(client, text="General UX feedback")
        fb_dir = self.feedback_root / "feedback_GENERAL"
        assert fb_dir.exists()
        index = fb_dir / "index.json"
        assert index.exists()
        entries = json.loads(index.read_text())
        assert entries[0]["ticker"] is None
        assert entries[0]["text"] == "General UX feedback"

    def test_blank_ticker_is_inferred_from_known_analysis_ticker_in_text(self, client):
        analysis_dir = self.feedback_root / "2026-06-08_050625_NVDA_NVIDIA_Corp" / "07_final_report"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "earnings_deep_dive.pdf").write_bytes(b"%PDF-1.4 fake nvda pdf")

        resp = self._submit(
            client,
            text="I checked NVDA now, but I still cannot retrieve PDF or access to the data on the site.",
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ticker"] == "NVDA"
        assert body["bucket"] == "NVDA"
        entries = json.loads((self.feedback_root / "feedback_NVDA" / "index.json").read_text())
        assert entries[0]["ticker"] == "NVDA"
        assert entries[0]["files"][0].endswith("_deep_dive_NVDA.pdf")
        assert not (self.feedback_root / "feedback_GENERAL" / "index.json").exists()

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

    def test_feedback_user_page_list_is_public_for_remote_browser(self, client, remote_client):
        self._submit(client, text="General feedback visible on production page")

        resp = remote_client.get("/api/feedback")

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["total"] == 1
        assert payload["entries"][0]["text"] == "General feedback visible on production page"

    def test_feedback_user_page_submit_is_public_for_remote_browser(self, remote_client):
        resp = remote_client.post("/api/feedback", data={"text": "Remote browser can submit feedback"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        entries = json.loads((self.feedback_root / "feedback_GENERAL" / "index.json").read_text())
        assert entries[0]["text"] == "Remote browser can submit feedback"

    def test_feedback_page_direct_url_redirects_to_hash_route(self, client):
        resp = client.get("/feedback", follow_redirects=False)
        assert resp.status_code in {307, 308}
        assert resp.headers["location"] == "/#feedback"

    def test_admin_page_direct_url_redirects_to_hash_route(self, client):
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code in {307, 308}
        assert resp.headers["location"] == "/#admin"

    def test_admin_feedback_remains_protected_for_remote_browser(self, remote_client):
        resp = remote_client.get("/api/admin/feedback")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Invalid API key"

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
        assert resp.headers["x-content-type-options"] == "nosniff"

    def test_feedback_upload_rejects_active_content_extensions(self, client):
        resp = self._submit(
            client,
            text="HTML should not be accepted as a public feedback attachment",
            files={"files": ("proof.html", b"<script>alert(1)</script>", "text/html")},
        )

        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]
        assert not (self.feedback_root / "feedback_GENERAL" / "index.json").exists()

    def test_feedback_upload_rejects_oversized_attachment(self, client, monkeypatch):
        monkeypatch.setattr("backend.feedback_store.MAX_FEEDBACK_UPLOAD_BYTES", 4)

        resp = self._submit(
            client,
            text="Attachment is too large",
            files={"files": ("shot.png", b"12345", "image/png")},
        )

        assert resp.status_code == 400
        assert "too large" in resp.json()["detail"]
        assert not (self.feedback_root / "feedback_GENERAL" / "index.json").exists()

    def test_feedback_upload_sanitizes_path_like_filenames(self, client):
        resp = self._submit(
            client,
            text="Path-like filename should be flattened",
            files={"files": ("../evil screenshot.png", b"fake png", "image/png")},
        )

        assert resp.status_code == 200
        entries = json.loads((self.feedback_root / "feedback_GENERAL" / "index.json").read_text())
        saved_name = entries[0]["files"][0]
        assert ".." not in saved_name
        assert "/" not in saved_name
        assert saved_name.endswith("evil_screenshot.png")
        assert (self.feedback_root / "feedback_GENERAL" / saved_name).exists()

    def test_feedback_file_download_rejects_unindexed_bucket_file(self, client):
        self._submit(client, ticker="AAPL", text="Creates index")
        index_path = self.feedback_root / "feedback_AAPL" / "index.json"
        assert index_path.exists()

        resp = client.get("/api/feedback-file/AAPL/index.json", headers={"X-API-Key": TEST_KEY})

        assert resp.status_code == 404

    def test_feedback_file_download_missing_returns_404(self, client):
        resp = client.get("/api/feedback-file/AAPL/missing.pdf", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 404


class TestFeedbackLifecycleMetadata:
    """Tests for feedback orchestration lifecycle metadata (Card 1)."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path, monkeypatch):
        self.feedback_root = tmp_path / "analyses"
        monkeypatch.setattr("backend.feedback_store.ANALYSES_DIR", self.feedback_root)
        from backend.feedback_store import save_feedback
        self.save_feedback = save_feedback

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def _submit(self, client, ticker=None, text=""):
        data = {}
        if ticker is not None:
            data["ticker"] = ticker
        if text:
            data["text"] = text
        headers = {"X-API-Key": TEST_KEY}
        return client.post("/api/feedback", data=data, headers=headers)

    # ── Raw entry tests (disk-level) ──────────────────────────────────

    def test_new_entries_have_orchestration_defaults(self, client):
        """New feedback entries must include an orchestration field with defaults."""
        self._submit(client, ticker="NVDA", text="test orchestration defaults")
        bucket = "NVDA"
        entries = json.loads((self.feedback_root / f"feedback_{bucket}" / "index.json").read_text())
        entry = entries[-1]

        assert "orchestration" in entry, "New entries must have orchestration field"
        orch = entry["orchestration"]
        assert isinstance(orch, dict), "orchestration must be a dict"
        assert orch.get("status") == "pending", "New entries must start with orchestration.status=pending"

    def test_orchestration_defaults_include_source(self, client):
        """Orchestration must include a source field on new entries."""
        self._submit(client, ticker="NVDA", text="check source field")
        bucket = "NVDA"
        entry = json.loads((self.feedback_root / f"feedback_{bucket}" / "index.json").read_text())[-1]
        orch = entry["orchestration"]
        assert "source" in orch, "orchestration must include a source field"
        assert orch["source"] == "feedback_page", "Default source should be feedback_page"

    def test_orchestration_defaults_include_severity(self, client):
        """Orchestration must include a default severity."""
        self._submit(client, ticker="NVDA", text="check severity")
        bucket = "NVDA"
        entry = json.loads((self.feedback_root / f"feedback_{bucket}" / "index.json").read_text())[-1]
        orch = entry["orchestration"]
        assert "severity" in orch, "orchestration must include a severity field"
        assert orch["severity"] == "low", "Default severity should be low"

    # ── Decoration tests ──────────────────────────────────────────────

    def test_decorate_entry_shows_pending_status_from_raw_entry(self):
        """A raw entry with processed=False should decorate as status=pending."""
        raw = {"id": "test-1", "processed": False}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "pending"

    def test_decorate_entry_shows_taken_into_account_for_orchestration_in_progress(self):
        """When orchestration.status=in_progress, decorated status should reflect it."""
        raw = {
            "id": "test-2",
            "orchestration": {"status": "in_progress"},
            "processed": False,  # orchestration overrides raw processed
        }
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "in_progress"

    def test_decorate_entry_shows_blocked_from_orchestration(self):
        """orchestration.status=blocked should decorate as status=blocked."""
        raw = {"id": "test-3", "orchestration": {"status": "blocked"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "blocked"

    def test_decorate_entry_shows_corrected_from_orchestration(self):
        """orchestration.status=corrected should decorate as status=corrected."""
        raw = {"id": "test-4", "orchestration": {"status": "corrected"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "corrected"

    def test_decorate_entry_shows_closed_from_orchestration(self):
        """orchestration.status=closed should decorate as status=closed."""
        raw = {"id": "test-5", "orchestration": {"status": "closed"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "closed"

    def test_decorate_entry_shows_rejected_from_orchestration(self):
        """orchestration.status=rejected should decorate as status=rejected."""
        raw = {"id": "test-6", "orchestration": {"status": "rejected"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "rejected"

    def test_decorate_entry_shows_not_reproducible(self):
        """orchestration.status=not_reproducible should decorate as status=not_reproducible."""
        raw = {"id": "test-7", "orchestration": {"status": "not_reproducible"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "not_reproducible"

    # ── Backward compatibility tests ─────────────────────────────────

    def test_decorate_entry_backward_compat_no_orchestration(self):
        """Entry without orchestration should still get status from processed."""
        raw = {"id": "test-8", "processed": False}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["status"] == "pending"

        raw2 = {"id": "test-9", "processed": True}
        decorated2 = _decorate_entry(raw2, "NVDA")
        assert decorated2["status"] == "taken_into_account"

    def test_decorate_entry_backward_compat_fix_status(self):
        """fix_status should still work alongside orchestration."""
        raw = {
            "id": "test-10",
            "processed": True,
            "fix_status": "in_progress",
        }
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["fix_status"] == "in_progress"

    def test_decorate_entry_derives_fix_status_from_orchestration(self):
        """When no fix_status but orchestration present, fix_status should be derived."""
        raw = {"id": "test-11", "orchestration": {"status": "corrected"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert "fix_status" in decorated, "fix_status should be present for backward compatibility"
        assert decorated["fix_status"] == "corrected"

    def test_decorate_entry_derives_fix_status_blocked(self):
        """orchestration.status=blocked → fix_status=in_progress (still being worked on)."""
        raw = {"id": "test-12", "orchestration": {"status": "blocked"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["fix_status"] == "in_progress"

    def test_decorate_entry_derives_fix_status_rejected(self):
        """orchestration.status=rejected → fix_status=None (no fix applied)."""
        raw = {"id": "test-13", "orchestration": {"status": "rejected"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated.get("fix_status") is None or decorated.get("fix_status") == ""

    def test_decorate_entry_derives_processed_from_orchestration(self):
        """processed should be True when orchestration status is not pending."""
        raw = {"id": "test-14", "orchestration": {"status": "corrected"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["processed"] is True

    def test_decorate_entry_processed_false_for_pending_orchestration(self):
        """processed should be False when orchestration.status is still pending."""
        raw = {"id": "test-15", "orchestration": {"status": "pending"}}
        decorated = _decorate_entry(raw, "NVDA")
        assert decorated["processed"] is False

    # ── Endpoint shape tests ─────────────────────────────────────────

    def test_feedback_list_exposes_orchestration_status_safely(self, client):
        """The public /api/feedback endpoint should expose orchestration.status safely."""
        self._submit(client, ticker="NVDA", text="Lifecycle check")
        resp = client.get("/api/feedback", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        decorated = next(e for e in entries if e["text"] == "Lifecycle check")
        assert "status" in decorated
        assert decorated["status"] == "pending"

    def test_admin_feedback_exposes_orchestration_metadata(self, client):
        """The admin endpoint should expose orchestration metadata."""
        self._submit(client, ticker="NVDA", text="Admin lifecycle check")
        resp = client.get("/api/admin/feedback", headers={"X-API-Key": TEST_KEY})
        assert resp.status_code == 200
        entries = resp.json()
        decorated = next(e for e in entries if e["text"] == "Admin lifecycle check")
        assert "status" in decorated
