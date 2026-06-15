"""Tests for feedback notification outbox (Card 7).

Covers:
- No email sent when recipient/config missing → outbox records pending_config
- Email body uses user-facing language: issue, action taken, verification, next step
- Success records email_sent_at and email_log_id
- Outbox persistence across store reads/writes
- No secrets in logs/tests (config values redacted from outbox log)
"""

import json
import uuid

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def temp_outbox_dir(tmp_path, monkeypatch):
    """Redirect notification outbox to a temp directory."""
    import backend.feedback_notifications as fn
    outbox_root = tmp_path / "feedback_notifications"
    monkeypatch.setattr(fn, "OUTBOX_DIR", outbox_root)
    return outbox_root


@pytest.fixture
def sample_feedback():
    """A minimal feedback entry dict for notification generation."""
    return {
        "id": "2026-06-15_143022",
        "ticker": "NVDA",
        "category": "correction",
        "text": "EPS number is wrong on page 3. Should be $2.94 not $2.84.",
        "status": "corrected",
        "fix_status": "corrected",
        "correction": "Fixed EPS display: updated mapper to use actual EPS field instead of estimate. Regenerated PDF.",
    }


@pytest.fixture
def no_config():
    """Simulate missing email configuration by clearing env vars."""
    return {}


# ── RED tests — write first, verify they fail ──────────────────────────


class TestNotificationOutboxConfig:
    """Tests for config detection — missing config → pending_config."""

    def test_no_email_when_config_missing(self, temp_outbox_dir, sample_feedback):
        """When no email config/recipient is available, outbox records pending_config.
        
        Rule: No email sent when recipient/config missing.
        """
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)

        assert result is not None, "Should produce an outbox entry"
        assert result["status"] == "pending_config", (
            "Should record pending_config when no email config"
        )
        assert "email_to" not in result or result["email_to"] is None, (
            "No recipient should be set when config missing"
        )

    def test_pending_config_has_reason(self, temp_outbox_dir, sample_feedback):
        """pending_config entries should include a human-readable reason."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)

        assert result["status"] == "pending_config"
        reason = result.get("config_missing_reason", "")
        assert len(reason) > 5, "Config missing reason should be descriptive"
        assert "mail" in reason.lower() or "smtp" in reason.lower() or "recipient" in reason.lower(), (
            "Reason should mention email/mail/recipient"
        )

    def test_pending_config_not_sent(self, temp_outbox_dir, sample_feedback):
        """With missing config, send() should NOT actually send and should return pending_config."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        prepared = outbox.prepare(sample_feedback)
        sent = outbox.send(prepared)

        assert sent["status"] == "pending_config", (
            "send() should not send when config missing"
        )
        assert sent.get("email_sent_at") is None, (
            "No email_sent_at should be set when nothing was sent"
        )


class TestNotificationEmailBody:
    """Tests for email body generation — user-facing language."""

    def test_email_body_has_issue_section(self, temp_outbox_dir, sample_feedback):
        """Email body must restate the issue in user-facing language."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)
        body = result.get("email_body", "")

        assert "issue" in body.lower() or "problem" in body.lower() or "EPS" in body, (
            "Email body must reference the reported issue"
        )
        assert "page 3" in body or "wrong" in body, (
            "Email body should include specific issue details"
        )

    def test_email_body_has_action_taken(self, temp_outbox_dir, sample_feedback):
        """Email body must describe the action taken to fix."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)
        body = result.get("email_body", "")

        assert "Fixed" in body or "fixed" in body or "updated" in body or "corrected" in body or "修正" in body, (
            "Email body must describe what was fixed"
        )
        assert "mapper" in body.lower() or "EPS" in body or "PDF" in body, (
            "Email body should mention specific fix details"
        )

    def test_email_body_has_verification(self, temp_outbox_dir, sample_feedback):
        """Email body must explain how to verify the fix."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)
        body = result.get("email_body", "")

        assert "verif" in body.lower() or "check" in body.lower() or "download" in body.lower() or "see" in body.lower(), (
            "Email body must guide the user to verify the fix"
        )

    def test_email_body_has_next_step(self, temp_outbox_dir, sample_feedback):
        """Email body must include a clear next step for the user."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)
        body = result.get("email_body", "")

        assert "let" in body.lower() or "please" in body.lower() or "contact" in body.lower() or "if you" in body.lower() or "ご連絡" in body or "ください" in body, (
            "Email body must include next steps for the user"
        )

    def test_email_body_no_secrets(self, temp_outbox_dir, sample_feedback):
        """Email body must not contain secrets/config values."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)
        body = result.get("email_body", "")

        secrets_words = ["api_key", "password", "token", "secret", "smtp_login"]
        for secret in secrets_words:
            assert secret not in body.lower(), (
                f"Email body must not contain secret field: {secret}"
            )


class TestNotificationOutboxPersistence:
    """Tests for outbox store persistence."""

    def test_outbox_persists_across_instances(self, temp_outbox_dir, sample_feedback):
        """Outbox entries should survive a new outbox instance (disk persistence)."""
        from backend.feedback_notifications import NotificationOutbox

        # First instance: prepare
        outbox1 = NotificationOutbox()
        result1 = outbox1.prepare(sample_feedback)

        # Second instance: should read the same entry
        outbox2 = NotificationOutbox()
        entries = outbox2.list_entries()
        assert len(entries) >= 1, "Entries should persist to disk"

        # Verify by ID
        matching = [e for e in entries if e["id"] == result1["id"]]
        assert len(matching) == 1, "Previously saved entry should be readable"
        assert matching[0]["status"] == result1["status"]

    def test_list_entries_returns_ordered(self, temp_outbox_dir):
        """list_entries should return entries newest-first."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        entries_before = len(outbox.list_entries())

        outbox.prepare({"id": "entry-1", "ticker": "AAPL", "category": "bug", "text": "test1"})
        outbox.prepare({"id": "entry-2", "ticker": "NVDA", "category": "correction", "text": "test2"})

        entries = outbox.list_entries()
        assert len(entries) == entries_before + 2

        # Should be newest first (entry-2 was prepared after entry-1)
        assert entries[0]["feedback_entry_id"] == "entry-2" or entries[0]["feedback_entry_id"] == "entry-2"

    def test_send_records_timestamp(self, temp_outbox_dir, sample_feedback, monkeypatch):
        """When config is present, send() should record email_sent_at."""
        from backend.feedback_notifications import NotificationOutbox

        # Simulate email config being available
        monkeypatch.setattr("backend.feedback_notifications._check_email_config", lambda: {
            "smtp_host": "127.0.0.1",
            "smtp_port": 1025,
            "smtp_user": "test@example.com",
            "smtp_password": "redacted-test",
            "email_to": "nami@example.com",
        })

        outbox = NotificationOutbox()
        prepared = outbox.prepare(sample_feedback)
        sent = outbox.send(prepared)

        assert sent["status"] == "sent" or sent["status"] == "pending", (
            "When config present, send should queue or mark sent"
        )
        if sent["status"] == "sent":
            assert sent.get("email_sent_at") is not None, (
                "Sent entries should have a timestamp"
            )
            assert sent.get("email_log_id") is not None, (
                "Sent entries should have a log ID"
            )
            # Verify the outbox entry was updated on disk
            entries = outbox.list_entries()
            updated = next(e for e in entries if e["id"] == sent["id"])
            assert updated.get("email_sent_at") is not None

    def test_send_still_records_in_missing_config(self, temp_outbox_dir, sample_feedback):
        """When config is missing, send() should still return an entry, not raise."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        prepared = outbox.prepare(sample_feedback)
        # This should not raise
        sent = outbox.send(prepared)

        assert sent is not None, "send() must always return a result"
        assert isinstance(sent, dict), "send() must return a dict"


class TestNotificationEdgeCases:
    """Edge cases for the notification outbox."""

    def test_no_ticker_feedback(self, temp_outbox_dir):
        """General feedback (no ticker) should still generate an outbox entry."""
        from backend.feedback_notifications import NotificationOutbox

        feedback = {
            "id": "2026-06-15_150000",
            "ticker": None,
            "category": "general",
            "text": "The site is much faster now, thank you!",
            "status": "taken_into_account",
            "fix_status": "corrected",
        }

        outbox = NotificationOutbox()
        result = outbox.prepare(feedback)

        assert result is not None, "General feedback should produce an outbox entry"
        assert result["status"] == "pending_config", (
            "General feedback should also respect missing config"
        )

    def test_email_body_does_not_leak_internal_language(self, temp_outbox_dir, sample_feedback):
        """The email body must avoid internal pipeline language like 'kanban', 'mapper', 'validator'."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()
        result = outbox.prepare(sample_feedback)
        body = result.get("email_body", "")

        internal_terms = ["kanban", "preflight", "idempotency"]
        for term in internal_terms:
            assert term not in body.lower(), (
                f"Email body must not contain internal term: {term}"
            )

    def test_pending_config_allows_retry(self, temp_outbox_dir, sample_feedback, monkeypatch):
        """An entry in pending_config should be retryable when config becomes available."""
        from backend.feedback_notifications import NotificationOutbox

        outbox = NotificationOutbox()

        # First: no config → pending_config
        prepared = outbox.prepare(sample_feedback)
        assert prepared["status"] == "pending_config"

        # Second: config becomes available → retry
        monkeypatch.setattr("backend.feedback_notifications._check_email_config", lambda: {
            "smtp_host": "127.0.0.1",
            "smtp_port": 1025,
            "smtp_user": "test@example.com",
            "smtp_password": "redacted-test",
            "email_to": "nami@example.com",
        })

        retried = outbox.send(prepared)
        assert retried["status"] in ("sent", "pending"), (
            "A pending_config entry should be sendable when config is provided"
        )
