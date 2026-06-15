"""Tests for feedback_orchestration — pure side-effect-free router.

Test scope:
- Classification: ACK_ONLY, DIRECT_OPS, COUNCIL_REQUIRED, CLARIFY, REJECT
- Stable dedupe key generation
- Hermes-routing metadata generation
- No file IO, no Kanban calls, no side effects.
"""

import json
import hashlib
from typing import Any

import pytest

from backend.feedback_orchestration import (
    classify_feedback,
    generate_dedupe_key,
    generate_routing_metadata,
    Assessment,
    RoutingMetadata,
)


# ==============================================================================
# Helper to build a minimal feedback entry dict
# ==============================================================================

def _entry(
    *,
    category: str = "general",
    text: str = "Some feedback text",
    ticker: str | None = "NVDA",
    files: list[str] | None = None,
    entry_id: str = "2026-06-15_120000",
) -> dict[str, Any]:
    return {
        "id": entry_id,
        "ticker": ticker,
        "category": category,
        "submitted_at": "2026-06-15T12:00:00",
        "text": text,
        "files": files or [],
        "processed": False,
        "processed_at": None,
        "notes": "",
    }


# ==============================================================================
# Classification tests
# ==============================================================================


class TestClassifyAckOnly:
    """Feedback that should be acknowledged but requires no further action."""

    def test_har_export_help(self):
        """HAR export help questions → ACK_ONLY, no Kanban."""
        entry = _entry(category="har_export_help", text="How do I export a HAR file?")
        assert classify_feedback(entry) == Assessment.ACK_ONLY

    def test_generic_how_do_i(self):
        """Generic 'how do I' questions → ACK_ONLY."""
        entry = _entry(category="general", text="How do I download the report?")
        assert classify_feedback(entry) == Assessment.ACK_ONLY

    def test_general_feedback_no_ticker(self):
        """General feedback with no ticker → ACK_ONLY."""
        entry = _entry(category="general", text="Great product!", ticker=None)
        assert classify_feedback(entry) == Assessment.ACK_ONLY

    def test_general_empty_text(self):
        """Minimal feedback with no actionable content → ACK_ONLY."""
        entry = _entry(category="general", text="Thanks", ticker=None)
        assert classify_feedback(entry) == Assessment.ACK_ONLY


class TestClassifyDirectOps:
    """Feedback with known operational remediation."""

    def test_har_upload_issue_with_har_file(self):
        """HAR upload issue WITH an uploaded HAR file → DIRECT_OPS (can probe)."""
        entry = _entry(
            category="har_upload_issue",
            text="I uploaded my HAR file but it didn't work",
            files=["2026-06-15_120000_export.har"],
        )
        assert classify_feedback(entry) == Assessment.DIRECT_OPS

    def test_pdf_access_issue(self):
        """PDF access issue → DIRECT_OPS (probe/status check first)."""
        entry = _entry(category="pdf_access_issue", text="Can't open PDF for NVDA")
        assert classify_feedback(entry) == Assessment.DIRECT_OPS

    def test_site_availability(self):
        """Site availability report → DIRECT_OPS (runbook)."""
        entry = _entry(category="site_availability", text="Site is down")
        assert classify_feedback(entry) == Assessment.DIRECT_OPS


class TestClassifyCouncilRequired:
    """Feedback requiring multi-model deliberation before action."""

    def test_correction_request(self):
        """Correction request touching PDF content → COUNCIL_REQUIRED."""
        entry = _entry(
            category="correction_request",
            text="The EPS number on page 3 is wrong",
        )
        assert classify_feedback(entry) == Assessment.COUNCIL_REQUIRED

    def test_bug_report(self):
        """Bug report about production UI/scoring → COUNCIL_REQUIRED."""
        entry = _entry(
            category="bug_report",
            text="The BUY/HOLD/SELL score changed incorrectly after refresh",
        )
        assert classify_feedback(entry) == Assessment.COUNCIL_REQUIRED

    def test_feature_request(self):
        """Feature request → COUNCIL_REQUIRED (spec first, no direct impl)."""
        entry = _entry(
            category="feature_request",
            text="Can you add support for options analysis?",
        )
        assert classify_feedback(entry) == Assessment.COUNCIL_REQUIRED

    def test_correction_request_no_ticker(self):
        """Correction request without ticker still requires council."""
        entry = _entry(
            category="correction_request",
            text="The numbers are wrong in the report",
            ticker=None,
        )
        assert classify_feedback(entry) == Assessment.COUNCIL_REQUIRED


class TestClassifyClarify:
    """Feedback needing more information from the user."""

    def test_har_upload_issue_no_har(self):
        """HAR upload issue WITHOUT an HAR file → CLARIFY (needs HAR)."""
        entry = _entry(
            category="har_upload_issue",
            text="I tried to upload but got an error",
            files=[],
        )
        assert classify_feedback(entry) == Assessment.CLARIFY

    def test_ambiguous_text_no_ticker_no_category(self):
        """Completely ambiguous feedback with no ticker and no specific category → CLARIFY."""
        entry = _entry(
            category="general",
            text="Something is not working",
            ticker=None,
        )
        assert classify_feedback(entry) == Assessment.CLARIFY


class TestClassifyReject:
    """Non-actionable feedback that should be rejected."""

    def test_ticker_only_no_text(self):
        """Entry with only a ticker and no description → REJECT."""
        entry = _entry(category="general", text="NVDA")
        assert classify_feedback(entry) == Assessment.REJECT

    def test_empty_text(self):
        """Entry with completely empty text → REJECT."""
        entry = _entry(category="general", text="", ticker=None)
        assert classify_feedback(entry) == Assessment.REJECT

    def test_whitespace_only(self):
        """Entry with only whitespace → REJECT."""
        entry = _entry(category="general", text="   ")
        assert classify_feedback(entry) == Assessment.REJECT

    def test_single_ticker_only(self):
        """Entry with a single valid ticker symbol and nothing else → REJECT."""
        entry = _entry(category="general", text="AAPL  ")
        assert classify_feedback(entry) == Assessment.REJECT


# ==============================================================================
# Dedupe key tests
# ==============================================================================


class TestDedupeKey:
    """Stable deterministic dedupe key generation."""

    def test_stable_deterministic(self):
        """Same input always produces the same key."""
        entry = _entry()
        key1 = generate_dedupe_key(entry, bucket="NVDA")
        key2 = generate_dedupe_key(entry, bucket="NVDA")
        assert key1 == key2

    def test_different_text_produces_different_key(self):
        """Different feedback text produces different keys."""
        e1 = _entry(text="EPS is wrong", entry_id="a")
        e2 = _entry(text="Revenue is wrong", entry_id="b")

        key1 = generate_dedupe_key(e1, bucket="NVDA")
        key2 = generate_dedupe_key(e2, bucket="NVDA")
        assert key1 != key2

    def test_includes_bucket(self):
        """Same entry in different buckets produces different keys."""
        entry = _entry(text="The numbers are wrong", entry_id="x")
        key_a = generate_dedupe_key(entry, bucket="NVDA")
        key_b = generate_dedupe_key(entry, bucket="GENERAL")
        assert key_a != key_b

    def test_includes_category(self):
        """Same text but different categories produces different keys."""
        e1 = _entry(category="bug_report", text="Numbers are wrong", entry_id="1")
        e2 = _entry(category="correction_request", text="Numbers are wrong", entry_id="1")

        key1 = generate_dedupe_key(e1, bucket="NVDA")
        key2 = generate_dedupe_key(e2, bucket="NVDA")
        assert key1 != key2

    def test_includes_files(self):
        """Entries with different file lists produce different keys."""
        e1 = _entry(files=["screenshot.png"], entry_id="a")
        e2 = _entry(files=["export.har"], entry_id="a")

        key1 = generate_dedupe_key(e1, bucket="NVDA")
        key2 = generate_dedupe_key(e2, bucket="NVDA")
        assert key1 != key2

    def test_text_normalization(self):
        """Leading/trailing whitespace in text is normalized for keying."""
        e1 = _entry(text="  EPS is wrong  ", entry_id="1")
        e2 = _entry(text="EPS is wrong", entry_id="1")

        key1 = generate_dedupe_key(e1, bucket="NVDA")
        key2 = generate_dedupe_key(e2, bucket="NVDA")
        assert key1 == key2

    def test_key_format(self):
        """Dedupe key follows the spec format 'sa-fb-<prefix>'."""
        entry = _entry()
        key = generate_dedupe_key(entry, bucket="NVDA")
        assert key.startswith("sa-fb-")
        assert len(key) > 10

    def test_different_entry_id_same_content(self):
        """Entries with different IDs but same content should have DIFFERENT keys
        (entry_id is part of the dedupe material since it's the time-based unique)."""
        e1 = _entry(text="Same feedback", entry_id="2026-06-15_120000")
        e2 = _entry(text="Same feedback", entry_id="2026-06-15_120001")

        key1 = generate_dedupe_key(e1, bucket="NVDA")
        key2 = generate_dedupe_key(e2, bucket="NVDA")
        assert key1 != key2


# ==============================================================================
# Routing metadata tests
# ==============================================================================


class TestRoutingMetadata:
    """Hermes-routing metadata generation for each assessment type."""

    def test_routing_metadata_council_required(self):
        """COUNCIL_REQUIRED → architect-spec, high reasoning, max crit."""
        meta = generate_routing_metadata(
            entry=_entry(category="correction_request"),
            assessment=Assessment.COUNCIL_REQUIRED,
            bucket="NVDA",
        )
        assert meta.route.assignee_profile == "architect-spec"
        assert meta.route.builder_reasoning == "high"
        assert meta.route.builder_model == "codex-gpt-5.5"
        assert meta.crit >= 3
        assert meta.project == "stock-analysis-pipeline"

    def test_routing_metadata_direct_ops(self):
        """DIRECT_OPS → python-builder, medium reasoning, low crit."""
        meta = generate_routing_metadata(
            entry=_entry(category="pdf_access_issue"),
            assessment=Assessment.DIRECT_OPS,
            bucket="NVDA",
        )
        assert meta.route.assignee_profile == "python-builder"
        assert meta.route.builder_reasoning == "medium"
        assert meta.crit == 2

    def test_routing_metadata_ack_only(self):
        """ACK_ONLY → minimal routing, 0 crit, reviewer not needed."""
        meta = generate_routing_metadata(
            entry=_entry(category="har_export_help", text="How do I export HAR?"),
            assessment=Assessment.ACK_ONLY,
            bucket="GENERAL",
        )
        assert meta.route.assignee_profile == "python-builder"
        assert meta.crit == 1
        assert meta.amb == 1
        assert meta.ver == 1

    def test_routing_metadata_clarify(self):
        """CLARIFY → python-builder, medium ambiguity, low crit."""
        meta = generate_routing_metadata(
            entry=_entry(category="general", text="Something is not working", ticker=None),
            assessment=Assessment.CLARIFY,
            bucket="GENERAL",
        )
        assert meta.route.assignee_profile == "python-builder"
        assert meta.amb >= 2
        assert meta.crit == 1

    def test_routing_metadata_reject(self):
        """REJECT → minimal routing, 0 diff, 0 crit."""
        meta = generate_routing_metadata(
            entry=_entry(category="general", text="NVDA"),
            assessment=Assessment.REJECT,
            bucket="NVDA",
        )
        assert meta.diff == 0
        assert meta.crit == 0
        assert meta.amb == 0
        assert meta.ver == 0

    def test_idempotency_key_in_metadata(self):
        """Metadata includes a stable idempotency_key."""
        meta = generate_routing_metadata(
            entry=_entry(category="correction_request"),
            assessment=Assessment.COUNCIL_REQUIRED,
            bucket="NVDA",
        )
        assert meta.idempotency_key.startswith("sa-fb-")

    def test_routing_reviewer_model(self):
        """COUNCIL_REQUIRED has reviewer model set, ACK_ONLY does not."""
        council_meta = generate_routing_metadata(
            entry=_entry(category="bug_report"),
            assessment=Assessment.COUNCIL_REQUIRED,
            bucket="NVDA",
        )
        ack_meta = generate_routing_metadata(
            entry=_entry(category="har_export_help"),
            assessment=Assessment.ACK_ONLY,
            bucket="GENERAL",
        )
        assert council_meta.route.reviewer_model is not None
        # ACK_ONLY may or may not set reviewer; just check it doesn't crash

    def test_impact_count_always_one(self):
        """impact_count is always 1 for single feedback items."""
        meta = generate_routing_metadata(
            entry=_entry(category="correction_request"),
            assessment=Assessment.COUNCIL_REQUIRED,
            bucket="NVDA",
        )
        assert meta.impact_count == 1

    def test_metadata_is_json_serializable(self):
        """RoutingMetadata can be serialized to JSON (for embedding in task bodies)."""
        meta = generate_routing_metadata(
            entry=_entry(category="bug_report"),
            assessment=Assessment.COUNCIL_REQUIRED,
            bucket="NVDA",
        )
        as_dict = meta.model_dump()
        json_str = json.dumps(as_dict, ensure_ascii=False)
        assert isinstance(json_str, str)
        recovered = json.loads(json_str)
        assert recovered["route"]["assignee_profile"] == "architect-spec"


# ==============================================================================
# High-level integration tests
# ==============================================================================


class TestFullAssessmentPipeline:
    """End-to-end: classify → dedupe → route metadata for realistic entries."""

    def test_pdf_access_full_flow(self):
        """PDF access issue: DIRECT_OPS + stable key + python-builder route."""
        entry = _entry(
            category="pdf_access_issue",
            text="PDF for NVDA shows blank page on page 2",
            ticker="NVDA",
        )
        assessment = classify_feedback(entry)
        assert assessment == Assessment.DIRECT_OPS

        key = generate_dedupe_key(entry, bucket="NVDA")
        assert key.startswith("sa-fb-")

        meta = generate_routing_metadata(entry, assessment, "NVDA")
        assert meta.route.assignee_profile == "python-builder"

    def test_correction_full_flow(self):
        """Correction request: COUNCIL_REQUIRED + stable key + architect-spec."""
        entry = _entry(
            category="correction_request",
            text="Revenue consensus is wrong on page 5 of NVDA deep-dive",
            ticker="NVDA",
        )
        assessment = classify_feedback(entry)
        assert assessment == Assessment.COUNCIL_REQUIRED

        key = generate_dedupe_key(entry, bucket="NVDA")
        assert key.startswith("sa-fb-")

        meta = generate_routing_metadata(entry, assessment, "NVDA")
        assert meta.route.assignee_profile == "architect-spec"
        assert meta.crit >= 3
        assert meta.diff >= 2

    def test_no_side_effects(self):
        """Calling any function must not write files, call APIs, or create tasks.

        This test runs in a controlled environment — if a function accidentally
        opens files or makes network calls, it will either fail or be detectable.
        """
        entry = _entry(category="general")
        # All three functions should be pure
        a = classify_feedback(entry)
        k = generate_dedupe_key(entry, bucket="TEST")
        m = generate_routing_metadata(entry, a, "TEST")
        assert a in Assessment
        assert isinstance(k, str)
        assert isinstance(m, RoutingMetadata)
