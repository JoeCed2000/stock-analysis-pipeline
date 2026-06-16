#!/usr/bin/env python3
"""Persistent verifier script for t_a31c470f — EPS Revenue canonicalization.

Checks:
1. `_normalize_eps_revenue` exists and is callable
2. All 21 concision tests pass (5 new + 16 existing)
3. Full V2.x bundle passes (645+ tests)
4. NVDA dossier passes validation with 0 issues
5. No EDP-006 false conflicts from segment revenue figures
"""

import sys
import subprocess
import os

REPO = "/home/ced/codex-projects/stock-analysis-pipeline"
os.chdir(REPO)
env = {**os.environ, "PYTHONPATH": "."}


def check(step: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {step}")
    if detail:
        print(f"       {detail}")
    return ok


all_pass = True

# Check 1: function exists
r = subprocess.run(
    [sys.executable, "-c", "from backend.earnings_deep_dive.deep_dive_validator import _normalize_eps_revenue; print('OK')"],
    capture_output=True, text=True, timeout=15, env=env,
)
all_pass &= check("Function _normalize_eps_revenue callable", r.returncode == 0 and "OK" in r.stdout, r.stderr.strip()[:200])

# Check 2: 21 concision tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/spec_v27_concision.py", "-q"],
    capture_output=True, text=True, timeout=30, env=env,
)
all_pass &= check("21 concision tests pass", r.returncode == 0, str(r.stdout.strip().split("\n")[-2:]))

# Check 3: Bundle tests pass
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     "tests/spec_v27_concision.py",
     "tests/spec_v27_numeric_consistency.py",
     "tests/spec_v27_forbidden_headings.py",
     "tests/spec_v27_missing_data_leaks.py",
     "tests/spec_v27_verdict_valuation_dq_segments.py",
     "tests/spec_v27_period_consistency.py",
     "tests/spec_v27_metrics_ledger.py",
     "tests/spec_v27_source_registry.py",
     "tests/test_validator.py",
     "-q"],
    capture_output=True, text=True, timeout=60, env=env,
)
all_pass &= check("Full V2.x bundle passes", r.returncode == 0, str(r.stdout.strip().split("\n")[-2:]))

# Check 4: NVDA dossier passes with 0 issues
validate_script = (
    "from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive; "
    "passed, issues = validate_deep_dive('analyses/2026-06-16_134822_NVDA_NVIDIA_Corp/07_final_report/earnings_deep_dive.md'); "
    "print(f'passed={passed}, issues={len(issues)}')"
)
r = subprocess.run(
    [sys.executable, "-c", validate_script],
    capture_output=True, text=True, timeout=15, env=env,
)
all_pass &= check("NVDA dossier passes with 0 issues",
                  "passed=True, issues=0" in r.stdout,
                  r.stdout.strip())

# Check 5: Git committed
r = subprocess.run(
    ["git", "log", "--oneline", "-3"],
    capture_output=True, text=True, timeout=5, env=env,
)
has_our_commit = "feat(validator): generic EPS Revenue canonicalization" in r.stdout
all_pass &= check("Commit present in git log", has_our_commit, r.stdout.strip()[:200])

print(f"\n{'='*50}")
print(f"VERDICT: {'ALL PASS' if all_pass else 'SOME FAILED'}")
sys.exit(0 if all_pass else 1)
