"""Shared pytest configuration for the stock-analysis-pipeline suite."""
import shutil
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSES_DIR = PROJECT_ROOT / "analyses"


@pytest.fixture(autouse=True)
def _no_real_transcript_cache(monkeypatch):
    """Stop find_transcripts() from reading real dossiers off disk.

    _load_recent_cached_transcript() globs the live analyses/ root for any
    transcript persisted in the last 24h. In a test that means a real NVDA
    run silently outranks the monkeypatched stockanalysis source, so results
    depend on whether someone ran an analysis today. Default it to "no cache";
    tests that exercise the cache re-patch it themselves (same function-scoped
    monkeypatch, so their setattr wins).

    analyses/ itself is deliberately NOT redirected: DeepDiveRequest validates
    output_dir against that exact root, so deep-dive tests must write there.
    """
    monkeypatch.setattr(
        "backend.transcript_finder._load_recent_cached_transcript",
        lambda ticker, max_age_seconds=24 * 3600: None,
        raising=False,
    )


def pytest_sessionfinish(session, exitstatus):
    """Remove test residue from analyses/.

    Several deep-dive tests must write under analyses/ because
    DeepDiveRequest validates output_dir against that root; they use
    tempfile.mkdtemp(dir=analyses) which leaves tmp* directories behind
    (141 had accumulated by 2026-06-12). Only the unambiguous tmp* pattern
    is removed — real dossiers are named <date>_<TICKER>_<Company>.
    """
    if not ANALYSES_DIR.is_dir():
        return
    for entry in ANALYSES_DIR.glob("tmp*"):
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
