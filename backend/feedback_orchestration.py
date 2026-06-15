"""Feedback orchestration router — pure side-effect-free decision module.

This is Card 2 from the SA feedback orchestration gap spec. It provides three
pure functions with no file IO, no Kanban calls, no network calls:

1. classify_feedback(entry) → Assessment: ACK_ONLY, DIRECT_OPS, COUNCIL_REQUIRED, CLARIFY, REJECT
2. generate_dedupe_key(entry, bucket) → str: stable, deterministic dedupe key
3. generate_routing_metadata(entry, assessment, bucket) → RoutingMetadata: hermes-routing block
"""

import hashlib
import json
import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ==============================================================================
# Assessment types — routing decision for each feedback entry
# ==============================================================================


class Assessment(str, Enum):
    """Routing decision for a single feedback entry.

    ACK_ONLY          — Acknowledge, no Kanban, no council, no action.
    DIRECT_OPS        — Known operational remediation (reanalyze, restart, probe).
    COUNCIL_REQUIRED  — Multi-model deliberation before any action.
    CLARIFY           — Needs more information from the user first.
    REJECT            — Not actionable (empty, ticker-only, spam).
    """

    ACK_ONLY = "ACK_ONLY"
    DIRECT_OPS = "DIRECT_OPS"
    COUNCIL_REQUIRED = "COUNCIL_REQUIRED"
    CLARIFY = "CLARIFY"
    REJECT = "REJECT"


# ==============================================================================
# Routing metadata model — hermes-routing YAML block for Kanban task bodies
# ==============================================================================


class RouteRecommendation(BaseModel):
    """Profile and model recommendation for a Kanban task."""

    assignee_profile: str = "python-builder"
    builder_model: str = "codex-gpt-5.5"
    builder_reasoning: str = "medium"
    reviewer_model: Optional[str] = None
    reviewer_reasoning: Optional[str] = None


class RoutingMetadata(BaseModel):
    """Hermes-routing metadata block for Kanban task bodies (spec §6.2)."""

    atom: int = 1
    diff: int = Field(default=1, ge=0, le=5)
    crit: int = Field(default=0, ge=0, le=5)
    amb: int = Field(default=1, ge=0, le=3)
    ver: int = Field(default=1, ge=0, le=3)
    impact_count: int = 1
    route: RouteRecommendation = Field(default_factory=RouteRecommendation)
    project: str = "stock-analysis-pipeline"
    write_scope: list[str] = Field(default_factory=list)
    read_scope: list[str] = Field(default_factory=list)
    expected_tests: list[str] = Field(default_factory=list)
    risk: str = "low"
    idempotency_key: str = ""


# ==============================================================================
# Classification logic
# ==============================================================================

# Category keywords that trigger specific assessments
_CATEGORY_ACK_ONLY: set[str] = {"har_export_help",}
_CATEGORY_DIRECT_OPS: set[str] = {"pdf_access_issue", "site_availability",}
_CATEGORY_COUNCIL_REQUIRED: set[str] = {"correction_request", "bug_report", "feature_request",}


def _normalized_text(entry: dict[str, Any]) -> str:
    """Return the stripped text of a feedback entry."""
    raw = entry.get("text") or ""
    return raw.strip()


def _has_har_file(entry: dict[str, Any]) -> bool:
    """Check if any attached file has a .har extension."""
    files = entry.get("files") or []
    return any(f.lower().endswith(".har") for f in files)


def _is_ticker_only(text: str) -> bool:
    """Check if text is just a ticker symbol (1-6 uppercase chars, possibly with spaces).

    The original text must be all-uppercase — mixed-case words like "Thanks" are
    not ticker symbols even though their upper() form matches [A-Z]{1,6}.
    """
    stripped = text.strip()
    # Must be entirely uppercase in the original form to be a ticker
    if stripped != stripped.upper():
        return False
    return bool(re.fullmatch(r"[A-Z]{1,6}(/[A-Z]{1,6})?", stripped))


def _is_generic_question(text: str) -> bool:
    """Detect generic 'how do I' / 'help' type questions that need no action."""
    lower = text.lower()
    generic_phrases = [
        "how do i", "how to", "how can i", "what is", "where is",
        "can you tell", "i don't know how", "help me",
    ]
    return any(phrase in lower for phrase in generic_phrases)


def _is_vague_problem_report(text: str) -> bool:
    """Detect vague problem reports that need clarification."""
    lower = text.lower().strip()
    vague_patterns = [
        "not working", "something is", "doesn't work", "does not work",
        "issue", "problem", "broken", "wrong", "error",
    ]
    # Must be short (< 60 chars) AND contain a vague pattern
    if len(text) >= 60:
        return False
    return any(p in lower or lower == p for p in vague_patterns)


def classify_feedback(entry: dict[str, Any]) -> Assessment:
    """Classify a feedback entry into one of five assessment types.

    Pure function — no IO, no side effects. Accepts any dict following the
    feedback_store entry schema: category, text, files, ticker.

    Args:
        entry: A feedback entry dict with at minimum 'category' and 'text' keys.

    Returns:
        Assessment enum value.
    """
    text = _normalized_text(entry)

    # REJECT: empty or whitespace-only text
    if not text:
        return Assessment.REJECT

    # REJECT: ticker-only text (single ticker with no description)
    if _is_ticker_only(text):
        return Assessment.REJECT

    category = (entry.get("category") or "general").strip().lower().replace(" ", "_")

    # Fast path: known categories with fixed assessments
    if category in _CATEGORY_ACK_ONLY:
        return Assessment.ACK_ONLY

    if category in _CATEGORY_DIRECT_OPS:
        return Assessment.DIRECT_OPS

    if category in _CATEGORY_COUNCIL_REQUIRED:
        return Assessment.COUNCIL_REQUIRED

    # har_upload_issue: depends on presence of HAR file
    if category == "har_upload_issue":
        if _has_har_file(entry):
            return Assessment.DIRECT_OPS
        return Assessment.CLARIFY

    # General category: heuristic classification
    if category == "general" or not category:
        ticker = entry.get("ticker")

        # Generic "how do I" questions → ACK_ONLY
        if _is_generic_question(text):
            return Assessment.ACK_ONLY

        # Vague problem report with no ticker → CLARIFY
        if not ticker and _is_vague_problem_report(text):
            return Assessment.CLARIFY

        # Substantive text with ticker → ACK_ONLY
        if ticker:
            return Assessment.ACK_ONLY

        # Substantive text without ticker but long enough to be useful
        if len(text) >= 12:
            return Assessment.ACK_ONLY

        # Very short text (< 12 chars) that doesn't look like a problem → ACK_ONLY
        # "Thanks", "OK", "Great" — gratitude/acknowledgment, not ambiguity
        if not _is_vague_problem_report(text):
            return Assessment.ACK_ONLY

        # Short text, no ticker, no specific category → CLARIFY
        return Assessment.CLARIFY

    # Fallback: unknown category with substantive text → COUNCIL_REQUIRED
    if len(text) >= 20:
        return Assessment.COUNCIL_REQUIRED

    # Unknown category, short text → CLARIFY
    return Assessment.CLARIFY


# ==============================================================================
# Dedupe key generation
# ==============================================================================


def generate_dedupe_key(
    entry: dict[str, Any],
    bucket: str,
) -> str:
    """Generate a stable, deterministic dedupe key for a feedback entry.

    The key incorporates bucket, entry_id, category, normalized text, and files
    list to produce a unique hash. Same inputs always produce the same key.

    Format: sa-fb-<16_hex_chars>

    Args:
        entry: A feedback entry dict (must have 'id', 'category', 'text' keys).
        bucket: The feedback bucket name (e.g., 'NVDA', 'GENERAL').

    Returns:
        Stable dedupe key string.
    """
    payload = {
        "bucket": bucket,
        "entry_id": entry.get("id", ""),
        "category": (entry.get("category") or "general").strip().lower(),
        "text": _normalized_text(entry),
        "files": sorted(entry.get("files") or []),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"sa-fb-{digest}"


# ==============================================================================
# Routing metadata generation
# ==============================================================================


def _build_route_for_assessment(
    assessment: Assessment,
    entry: dict[str, Any],
) -> tuple[RouteRecommendation, int, int, int, int, str]:
    """Determine routing recommendation, scoring, and risk based on assessment.

    Returns:
        (route, diff, crit, amb, ver, risk)
    """
    category = (entry.get("category") or "general").strip().lower()

    if assessment == Assessment.COUNCIL_REQUIRED:
        return (
            RouteRecommendation(
                assignee_profile="architect-spec",
                builder_model="codex-gpt-5.5",
                builder_reasoning="high",
                reviewer_model="minimax-m3",
                reviewer_reasoning="medium",
            ),
            3,   # diff
            4,   # crit
            2,   # amb
            3,   # ver
            "medium",
        )

    if assessment == Assessment.DIRECT_OPS:
        return (
            RouteRecommendation(
                assignee_profile="python-builder",
                builder_model="codex-gpt-5.5",
                builder_reasoning="medium",
            ),
            2,   # diff
            2,   # crit
            1,   # amb
            2,   # ver
            "medium",
        )

    if assessment == Assessment.CLARIFY:
        return (
            RouteRecommendation(
                assignee_profile="python-builder",
                builder_model="codex-gpt-5.5",
                builder_reasoning="low",
            ),
            1,   # diff
            1,   # crit
            3,   # amb
            1,   # ver
            "low",
        )

    if assessment == Assessment.REJECT:
        return (
            RouteRecommendation(
                assignee_profile="python-builder",
                builder_model="codex-gpt-5.5",
                builder_reasoning="low",
            ),
            0,  # diff
            0,  # crit
            0,  # amb
            0,  # ver
            "low",
        )

    # ACK_ONLY
    return (
        RouteRecommendation(
            assignee_profile="python-builder",
            builder_model="codex-gpt-5.5",
            builder_reasoning="low",
        ),
        1,   # diff
        1,   # crit
        1,   # amb
        1,   # ver
        "low",
    )


def _build_write_scope(assessment: Assessment, entry: dict[str, Any]) -> list[str]:
    """Suggest write scope based on assessment type."""
    if assessment == Assessment.COUNCIL_REQUIRED:
        return [
            "docs/feedback-council/<id>.md",
            "backend/feedback_orchestration.py",
        ]
    if assessment == Assessment.DIRECT_OPS:
        category = (entry.get("category") or "").strip().lower()
        if category == "pdf_access_issue":
            return ["backend/feedback_pipeline.py"]
        if category == "site_availability":
            return ["operations/"]
        return ["backend/feedback_orchestration.py"]
    return []


def _build_read_scope(assessment: Assessment, entry: dict[str, Any]) -> list[str]:
    """Suggest read scope based on assessment type."""
    if assessment == Assessment.COUNCIL_REQUIRED:
        return [
            "docs/sa-feedback-orchestration-gap-spec.md",
            "docs/feedback-fusion-council-spec.md",
        ]
    if assessment == Assessment.DIRECT_OPS:
        category = (entry.get("category") or "").strip().lower()
        if category == "pdf_access_issue":
            return [
                "backend/main.py",
                "backend/async_dossier.py",
                "backend/feedback_pipeline.py",
            ]
        return ["backend/feedback_pipeline.py"]
    return []


def _build_expected_tests(assessment: Assessment, entry: dict[str, Any]) -> list[str]:
    """Suggest expected test commands based on assessment type."""
    if assessment == Assessment.COUNCIL_REQUIRED:
        return ["PYTHONPATH=. backend/.venv/bin/pytest tests/test_feedback_orchestration.py -q"]
    if assessment == Assessment.DIRECT_OPS:
        return ["PYTHONPATH=. backend/.venv/bin/pytest tests/test_feedback.py -q"]
    return []


def generate_routing_metadata(
    entry: dict[str, Any],
    assessment: Assessment,
    bucket: str,
) -> RoutingMetadata:
    """Generate complete hermes-routing metadata block for a classified entry.

    Pure function — no IO, no side effects.

    Args:
        entry: A feedback entry dict.
        assessment: The assessment from classify_feedback().
        bucket: The feedback bucket (e.g., 'NVDA', 'GENERAL').

    Returns:
        RoutingMetadata Pydantic model with all routing fields populated.
    """
    route, diff, crit, amb, ver, risk = _build_route_for_assessment(assessment, entry)
    dedupe_key = generate_dedupe_key(entry, bucket)

    return RoutingMetadata(
        diff=diff,
        crit=crit,
        amb=amb,
        ver=ver,
        risk=risk,
        route=route,
        write_scope=_build_write_scope(assessment, entry),
        read_scope=_build_read_scope(assessment, entry),
        expected_tests=_build_expected_tests(assessment, entry),
        idempotency_key=dedupe_key,
    )
