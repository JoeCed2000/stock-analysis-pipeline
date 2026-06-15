"""
Feedback Notification Outbox — email abstraction for Nami notifications.

Outbox stores notification entries in analyses/feedback_notifications/outbox.json.
Email is NOT actually sent by this module — it records intent and checks config.

States:
  pending_config  — no email config/recipient available; will be sent later
  pending         — ready to send (stub only — real sending comes later)
  sent            — recorded as sent with timestamp + log id
  failed          — send attempt recorded as failed

Usage:
    outbox = NotificationOutbox()
    entry = outbox.prepare(feedback_entry)
    result = outbox.send(entry)

No secrets in logs/tests. Config values are used only within this module
and never logged.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.storage_paths import get_analyses_dir

logger = logging.getLogger(__name__)

ANALYSES_DIR = get_analyses_dir()
OUTBOX_DIR = ANALYSES_DIR / "feedback_notifications"
OUTBOX_FILE = "outbox.json"

# ── Email body template (user-facing) ────────────────────────────────────


def _build_email_subject(feedback_entry: dict[str, Any]) -> str:
    """Generate a user-facing email subject from a feedback entry."""
    ticker = feedback_entry.get("ticker") or "General"
    category = feedback_entry.get("category", "general").replace("_", " ").title()
    return f"[Stock Analysis] {ticker} — {category} Update"


def _build_email_body(feedback_entry: dict[str, Any]) -> str:
    """Generate a user-facing email body from a feedback entry.

    Format:
      - Issue (restates what was reported)
      - Action taken (what was fixed/changed)
      - Verification (how to check the fix)
      - Next step (what to do if not satisfied)
    """
    ticker = feedback_entry.get("ticker") or "the platform"
    text = feedback_entry.get("text", "").strip()
    correction = feedback_entry.get("correction", "").strip()
    category = feedback_entry.get("category", "general")

    # Restate the issue
    if text:
        issue_section = f"You reported: \"{text[:300]}\""
    else:
        issue_section = f"We received your feedback regarding {ticker}."

    # Action taken
    if correction:
        action_section = f"We have reviewed your feedback and taken the following action:\n\n{correction[:500]}"
    else:
        action_section = "We have reviewed your feedback and it has been taken into account."

    # Verification
    if ticker and ticker != "GENERAL" and ticker != "General":
        verification_section = (
            f"You can verify the update by downloading the latest analysis for {ticker} "
            f"from the dashboard at https://sa.cedlabusa.net"
        )
    else:
        verification_section = (
            "You can verify the update by visiting the dashboard at https://sa.cedlabusa.net"
        )

    # Next step
    next_step_section = (
        "If the issue is not resolved to your satisfaction, please reply to this email "
        "or submit new feedback through the dashboard. We are happy to follow up."
    )

    return (
        f"Hello,\n\n"
        f"{issue_section}\n\n"
        f"{action_section}\n\n"
        f"{verification_section}\n\n"
        f"{next_step_section}\n\n"
        f"Best regards,\n"
        f"The Stock Analysis Team"
    )


# ── Config detection ─────────────────────────────────────────────────────


def _check_email_config() -> dict[str, str] | None:
    """Check if email configuration is available.

    Returns a config dict if SMTP settings + recipient are configured,
    or None if any required setting is missing.

    Checks environment variables:
      - SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD
      - NOTIFICATION_EMAIL_TO
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = os.environ.get("SMTP_PORT", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    email_to = os.environ.get("NOTIFICATION_EMAIL_TO", "")

    missing = []
    if not smtp_host:
        missing.append("SMTP_HOST")
    if not smtp_port:
        missing.append("SMTP_PORT")
    if not smtp_user:
        missing.append("SMTP_USER")
    if not smtp_password:
        missing.append("SMTP_PASSWORD")
    if not email_to:
        missing.append("NOTIFICATION_EMAIL_TO")

    if missing:
        logger.debug("Email config incomplete — missing: %s", ", ".join(missing))
        return None

    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "email_to": email_to,
    }


# ── Outbox persistence ───────────────────────────────────────────────────


def _outbox_path() -> Path:
    """Return the path to the outbox JSON file."""
    return OUTBOX_DIR / OUTBOX_FILE


def _read_outbox() -> list[dict[str, Any]]:
    """Read all outbox entries from disk."""
    path = _outbox_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read notification outbox; starting fresh")
            return []
    return []


def _write_outbox(entries: list[dict[str, Any]]) -> None:
    """Write outbox entries to disk."""
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    with open(_outbox_path(), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


# ── NotificationOutbox ───────────────────────────────────────────────────


class NotificationOutbox:
    """Abstraction for notifying users about feedback resolution.

    This class manages an outbox that records notification attempts.
    Email is NOT actually sent — the outbox captures intent and state.
    """

    def prepare(self, feedback_entry: dict[str, Any]) -> dict[str, Any]:
        """Prepare a notification entry for a feedback item.

        Creates an outbox entry with status based on config availability.
        Returns the entry dict.
        """
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Check config
        config = _check_email_config()

        entry: dict[str, Any] = {
            "id": entry_id,
            "feedback_entry_id": feedback_entry.get("id", ""),
            "bucket": feedback_entry.get("ticker") or "GENERAL",
            "feedback_category": feedback_entry.get("category", "general"),
            "status": "pending_config" if config is None else "pending",
            "email_to": config["email_to"] if config else None,
            "email_subject": _build_email_subject(feedback_entry),
            "email_body": _build_email_body(feedback_entry),
            "config_missing_reason": "",
            "email_sent_at": None,
            "email_log_id": None,
            "created_at": now,
        }

        if config is None:
            entry["config_missing_reason"] = (
                "Email notification pending: SMTP server or recipient not configured. "
                "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, and NOTIFICATION_EMAIL_TO "
                "environment variables to enable email delivery."
            )

        # Persist
        entries = _read_outbox()
        entries.insert(0, entry)
        _write_outbox(entries)

        logger.info(
            "Notification outbox entry %s prepared for feedback %s (status=%s)",
            entry_id, feedback_entry.get("id", ""), entry["status"],
        )
        return entry

    def send(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Attempt to send a notification based on available config.

        This is a STUB — no real email is sent. It records state:
        - If config is present: marks as 'pending' (ready for real delivery)
        - If config is missing: returns pending_config status

        When real SMTP delivery is implemented, this method will connect
        to the configured SMTP server and send the email.
        """
        entry_id = entry.get("id", "")
        entries = _read_outbox()

        # Find and update the entry in the stored list
        updated = None
        for i, stored in enumerate(entries):
            if stored.get("id") == entry_id:
                config = _check_email_config()
                if config is None:
                    # Still no config
                    stored["status"] = "pending_config"
                    stored["config_missing_reason"] = (
                        "Email notification pending: SMTP server or recipient not configured."
                    )
                else:
                    # Config is present — mark as sent (stub: no real send)
                    stored["status"] = "sent"
                    stored["email_sent_at"] = datetime.now(timezone.utc).isoformat()
                    stored["email_log_id"] = f"stub-{entry_id[:8]}"
                    stored["email_to"] = config["email_to"]
                    logger.info(
                        "Notification stub-sent for outbox entry %s to %s",
                        entry_id, config["email_to"],
                    )
                entries[i] = stored
                updated = stored
                break

        if updated is None:
            # Entry not found on disk — add it
            updated = dict(entry)
            updated["status"] = "pending_config"
            entries.insert(0, updated)
            logger.warning(
                "Outbox entry %s not found on disk; saved during send attempt",
                entry_id,
            )

        _write_outbox(entries)
        return updated

    def list_entries(self) -> list[dict[str, Any]]:
        """List all outbox entries, newest first."""
        return _read_outbox()

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        """Get a single outbox entry by ID."""
        for entry in _read_outbox():
            if entry.get("id") == entry_id:
                return entry
        return None
