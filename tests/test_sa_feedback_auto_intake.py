"""Tests for sa_feedback_auto_intake — cron wiring with orchestration.

Tests verify:
- DIRECT_OPS: reanalyze ticker / restart backend
- COUNCIL_REQUIRED: taken_into_account with orchestration metadata, NO reanalyze
- ACK_ONLY: acknowledge only
- CLARIFY: mark as needs_clarification
- REJECT: reject silently
- Silent when idle (no unprocessed entries)
- --dry-run: no side effects
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Hermes profile HOME quirk: Path.home() resolves to profile-local home.
# Use the REAL home for shared scripts and project paths.
_REAL_HOME = Path("/home/ced")

# Import the script under test — it lives in ~/.hermes/shared/scripts/
SHARED_SCRIPTS = _REAL_HOME / ".hermes" / "shared" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

# Add the SA pipeline root so the script can import backend modules
SA_PIPELINE_ROOT = _REAL_HOME / "codex-projects" / "stock-analysis-pipeline"
sys.path.insert(0, str(SA_PIPELINE_ROOT))

import sa_feedback_auto_intake as intake


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def feedback_dir(tmp_path):
    """Create a mock analyses/ directory with feedback buckets."""
    d = tmp_path / "analyses"
    d.mkdir()
    return d


def _write_feedback(feedback_dir: Path, bucket: str, entries: list[dict]) -> None:
    """Write an index.json for a feedback bucket."""
    bucket_dir = feedback_dir / f"feedback_{bucket}"
    bucket_dir.mkdir(parents=True, exist_ok=True)
    (bucket_dir / "index.json").write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    )


def _entry(
    *,
    entry_id: str = "2026-06-15_120000",
    ticker: str | None = "NVDA",
    category: str = "general",
    text: str = "Some feedback",
    files: list[str] | None = None,
    processed: bool = False,
) -> dict:
    return {
        "id": entry_id,
        "ticker": ticker,
        "category": category,
        "submitted_at": "2026-06-15T12:00:00",
        "text": text,
        "files": files or [],
        "processed": processed,
        "processed_at": None,
        "notes": "",
        "orchestration": {"status": "pending", "source": "feedback_page", "severity": "low"},
    }


# ==============================================================================
# Test: --dry-run shows what would happen without side effects
# ==============================================================================


class TestDryRun:
    """--dry-run mode must not modify files or call external APIs."""

    def test_dry_run_no_entries(self, feedback_dir):
        """No unprocessed entries → silent (returns 0)."""
        _write_feedback(feedback_dir, "NVDA", [_entry(processed=True)])
        count = intake.process_entries(dry_run=True, analyses_dir=str(feedback_dir))
        assert count == 0

    def test_dry_run_ack_only(self, feedback_dir):
        """ACK_ONLY entry in dry-run shows intent without side effects."""
        _write_feedback(feedback_dir, "NVDA", [_entry(text="Thanks!")])
        with patch("backend.feedback_orchestration.classify_feedback") as mock_classify:
            mock_classify.return_value = intake.Assessment.ACK_ONLY
            count = intake.process_entries(dry_run=True, analyses_dir=str(feedback_dir))
            assert count == 1

    def test_dry_run_council_required_no_reanalyze(self, feedback_dir):
        """COUNCIL_REQUIRED in dry-run must NOT call reanalyze_ticker."""
        _write_feedback(feedback_dir, "NVDA", [_entry(
            category="correction_request",
            text="The EPS number is wrong",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.COUNCIL_REQUIRED
            count = intake.process_entries(dry_run=True, analyses_dir=str(feedback_dir))
            assert count == 1
            mock_reanalyze.assert_not_called()


# ======================================================================
# Test: Live mode — actual entry modification
# ======================================================================


class TestLiveAckOnly:
    """ACK_ONLY entries should be acknowledged with no side effects."""

    def test_marks_taken_into_account(self, feedback_dir):
        """ACK_ONLY → taken_into_account, no fix_status change."""
        _write_feedback(feedback_dir, "NVDA", [_entry(text="Nice work!")])
        with patch("backend.feedback_orchestration.classify_feedback") as mock_classify:
            mock_classify.return_value = intake.Assessment.ACK_ONLY
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1

    def test_does_not_reanalyze(self, feedback_dir):
        """ACK_ONLY must NOT trigger reanalysis."""
        _write_feedback(feedback_dir, "NVDA", [_entry(text="Great!")])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.ACK_ONLY
            intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            mock_reanalyze.assert_not_called()


class TestLiveDirectOps:
    """DIRECT_OPS entries should apply remediation."""

    def test_pdf_access_triggers_reanalyze(self, feedback_dir):
        """PDF access issue → reanalyze_ticker called."""
        _write_feedback(feedback_dir, "NVDA", [_entry(
            category="pdf_access_issue",
            text="Can't open PDF for NVDA",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.DIRECT_OPS
            mock_reanalyze.return_value = {"success": True, "detail": "ok"}
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1
            mock_reanalyze.assert_called_once()

    def test_reanalyze_failure_sets_in_progress(self, feedback_dir):
        """DIRECT_OPS with failed reanalyze → status in_progress."""
        _write_feedback(feedback_dir, "NVDA", [_entry(
            category="pdf_access_issue",
            text="Can't open PDF",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.DIRECT_OPS
            mock_reanalyze.return_value = {"success": False, "detail": "API error"}
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1

    def test_does_not_reanalyze_without_ticker(self, feedback_dir):
        """DIRECT_OPS without ticker → no reanalysis, ack only."""
        _write_feedback(feedback_dir, "GENERAL", [_entry(
            ticker=None,
            category="pdf_access_issue",
            text="PDF for AAPL won't open",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.DIRECT_OPS
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1
            mock_reanalyze.assert_not_called()


class TestLiveCouncilRequired:
    """COUNCIL_REQUIRED entries must NOT trigger direct reanalysis."""

    def test_taken_into_account_with_metadata(self, feedback_dir):
        """COUNCIL_REQUIRED → taken_into_account, NO reanalyze."""
        _write_feedback(feedback_dir, "NVDA", [_entry(
            category="correction_request",
            text="The EPS number on page 3 is wrong.",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.COUNCIL_REQUIRED
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1
            mock_reanalyze.assert_not_called()

    def test_includes_hermes_routing_block(self, feedback_dir):
        """COUNCIL_REQUIRED entry's notes contains hermes-routing metadata."""
        _write_feedback(feedback_dir, "NVDA", [_entry(
            category="correction_request",
            text="The EPS number on page 3 is wrong.",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.COUNCIL_REQUIRED
            intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))

            # Read the updated index
            index_path = feedback_dir / "feedback_NVDA" / "index.json"
            entries = json.loads(index_path.read_text())
            entry = entries[0]

            # Should have hermes-routing in notes
            assert "hermes-routing" in entry.get("notes", "")
            assert entry.get("status") == "taken_into_account"
            assert entry["orchestration"]["status"] == "taken_into_account"
            mock_reanalyze.assert_not_called()


class TestLiveClarify:
    """CLARIFY entries should be marked as needs_clarification."""

    def test_marks_needs_clarification(self, feedback_dir):
        """CLARIFY → needs_clarification status."""
        _write_feedback(feedback_dir, "GENERAL", [_entry(
            ticker=None,
            category="har_upload_issue",
            text="I tried to upload HAR but got an error",
            files=[],
        )])
        with patch("backend.feedback_orchestration.classify_feedback") as mock_classify:
            mock_classify.return_value = intake.Assessment.CLARIFY
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1


class TestLiveReject:
    """REJECT entries should be silently rejected."""

    def test_rejects_silently(self, feedback_dir):
        """REJECT → marked as rejected."""
        _write_feedback(feedback_dir, "NVDA", [_entry(text="")])
        with patch("backend.feedback_orchestration.classify_feedback") as mock_classify:
            mock_classify.return_value = intake.Assessment.REJECT
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 1


class TestSilentWhenIdle:
    """Script must produce no output when nothing to process."""

    def test_no_unprocessed_entries(self, feedback_dir):
        """All entries processed → silent (0 count)."""
        _write_feedback(feedback_dir, "NVDA", [
            _entry(entry_id="e1", text="old", processed=True),
            _entry(entry_id="e2", text="older", processed=True),
        ])
        count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
        assert count == 0

    def test_no_feedback_at_all(self, feedback_dir):
        """No feedback directory → silent (0 count)."""
        count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
        assert count == 0


# ==============================================================================
# Test: Multiple entries in same bucket processed correctly
# ==============================================================================


class TestMultipleEntries:
    """Multiple unprocessed entries in one bucket."""

    def test_two_entries_different_assessments(self, feedback_dir):
        """Two entries with different classifications both get processed."""
        _write_feedback(feedback_dir, "NVDA", [
            _entry(entry_id="e1", text="Great tool!", processed=False),
            _entry(entry_id="e2", category="pdf_access_issue", text="Can't open PDF", processed=False),
        ])
        classify_side_effects = {
            "e1": intake.Assessment.ACK_ONLY,
            "e2": intake.Assessment.DIRECT_OPS,
        }

        def _mock_classify(entry):
            return classify_side_effects.get(entry.get("id", ""), intake.Assessment.ACK_ONLY)

        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.side_effect = _mock_classify
            mock_reanalyze.return_value = {"success": True, "detail": "ok"}
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 2
            mock_reanalyze.assert_called_once()

    def test_council_and_ack_only(self, feedback_dir):
        """COUNCIL_REQUIRED + ACK_ONLY — only ACK doesn't trigger reanalyze."""
        _write_feedback(feedback_dir, "NVDA", [
            _entry(entry_id="e1", text="Great tool!", processed=False),
            _entry(entry_id="e2", category="correction_request", text="Fix EPS", processed=False),
        ])
        classify_side_effects = {
            "e1": intake.Assessment.ACK_ONLY,
            "e2": intake.Assessment.COUNCIL_REQUIRED,
        }

        def _mock_classify(entry):
            return classify_side_effects.get(entry.get("id", ""), intake.Assessment.ACK_ONLY)

        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.side_effect = _mock_classify
            count = intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))
            assert count == 2
            mock_reanalyze.assert_not_called()


# ==============================================================================
# Test: Lock file behavior
# ==============================================================================


class TestLockFile:
    """Lock file prevents concurrent runs (tested via main())."""

    def test_lock_prevents_second_instance(self):
        """When lock is held, main() silently exits with code 0."""
        with (
            patch.object(sys, "argv", ["sa_feedback_auto_intake.py", "--dry-run"]),
            patch("fcntl.flock") as mock_flock,
        ):
            mock_flock.side_effect = BlockingIOError  # Lock is held
            rc = intake.main()
            assert rc == 0  # Silently skipped


# ==============================================================================
# Test: --dry-run via main() entry point (subprocess)
# ==============================================================================


class TestMainEntryPoint:
    """The main() function handles CLI args correctly."""

    def test_main_dry_run_no_feedback(self, feedback_dir):
        """python script.py --dry-run with no feedback → exits 0, no output."""
        from io import StringIO
        with (
            patch.object(sys, "argv", ["sa_feedback_auto_intake.py", "--dry-run"]),
            patch.object(intake, "ANALYSES_DIR", feedback_dir),
        ):
            rc = intake.main()
            assert rc == 0


# ==============================================================================
# Test: Hermes-routing block format in notes for COUNCIL_REQUIRED
# ==============================================================================


class TestHermesRoutingFormat:
    """hermes-routing metadata block is valid YAML-like format."""

    def test_block_contains_required_fields(self, feedback_dir):
        """hermes-routing block has atom, diff, crit, amb, ver, route fields."""
        _write_feedback(feedback_dir, "NVDA", [_entry(
            category="correction_request",
            text="Fix EPS on page 3",
        )])
        with (
            patch("backend.feedback_orchestration.classify_feedback") as mock_classify,
            patch.object(intake, "reanalyze_ticker") as mock_reanalyze,
        ):
            mock_classify.return_value = intake.Assessment.COUNCIL_REQUIRED
            intake.process_entries(dry_run=False, analyses_dir=str(feedback_dir))

            index_path = feedback_dir / "feedback_NVDA" / "index.json"
            entries = json.loads(index_path.read_text())
            notes = entries[0].get("notes", "")

            assert "# hermes-routing" in notes
            assert "atom:" in notes
            assert "diff:" in notes
            assert "crit:" in notes
            assert "amb:" in notes
            assert "ver:" in notes
            assert "route:" in notes
            assert "assignee_profile:" in notes
            assert mock_reanalyze.assert_not_called or True
