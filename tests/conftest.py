"""Shared pytest configuration for the stock-analysis-pipeline suite."""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSES_DIR = PROJECT_ROOT / "analyses"


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
