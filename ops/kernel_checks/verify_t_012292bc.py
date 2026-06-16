#!/usr/bin/env python3
"""Kernel verifier for t_012292bc: verdict_multiple_recommendations false positive fix.

Root cause: RECOMMENDATION_RE with re.IGNORECASE matched lowercase "hold"/"sell"
in English prose ("margins hold firm", "sell-side", "sell-off").

Fix: made RECOMMENDATION_RE case-sensitive so only uppercase BUY/HOLD/SELL
are detected as recommendations.

Checks:
1. Changed files exist
2. Python compiles for changed source files
3. Focused verdict test suite passes (20 tests incl. regression)
4. Regression test specifically verifies "margins hold firm" no longer false-positive
5. Full V2.x bundle has no regressions
"""

import subprocess
import sys
import os
import re

BASE = "/home/ced/codex-projects/stock-analysis-pipeline"
PYTHON = BASE + "/.venv/bin/python3"
CHANGED = [
    "backend/earnings_deep_dive/pre_render_validator.py",
    "tests/spec_v27_verdict_valuation_dq_segments.py",
]
COMPILE_FILES = [
    "backend/earnings_deep_dive/pre_render_validator.py",
]
VERDICT_TEST_FILE = "tests/spec_v27_verdict_valuation_dq_segments.py"
BUNDLE_FILES = "tests/spec_v27_verdict_valuation_dq_segments.py tests/spec_v27_numeric_consistency.py tests/spec_v27_concision.py tests/spec_v27_forbidden_headings.py tests/spec_v27_missing_data_leaks.py tests/test_validator.py tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py tests/spec_v27_source_registry.py tests/spec_v27_fcf_margin_presence.py tests/spec_v27_net_debt_presence.py tests/spec_v27_source_display_policy.py tests/spec_v27_source_display_renderer.py"

errors = []

print("═══ Kernel Check: t_012292bc ═══")
print()

# Check 1: Files exist
print("--- Check 1: Changed files exist ---")
for f in CHANGED:
    p = f"{BASE}/{f}"
    if os.path.exists(p):
        print(f"  ✅ {f}")
    else:
        print(f"  ❌ {f} — MISSING")
        errors.append(f)
print()

# Check 2: Python compile
print("--- Check 2: Python compile ---")
for f in COMPILE_FILES:
    result = subprocess.run(
        [PYTHON, "-m", "py_compile", f"{BASE}/{f}"],
        capture_output=True, text=True, timeout=10,
        cwd=BASE,
    )
    if result.returncode == 0:
        print(f"  ✅ {f}")
    else:
        print(f"  ❌ {f}: {result.stderr.strip()}")
        errors.append(f)
print()

# Check 3: Verdict test suite (20 tests, incl. regression)
print("--- Check 3: Verdict test suite ---")
cmd = [PYTHON, "-m", "pytest", VERDICT_TEST_FILE, "-v", "--tb=short", "-q"]
result = subprocess.run(
    cmd, capture_output=True, text=True, timeout=120,
    cwd=BASE,
    env={**os.environ, "PYTHONPATH": "."},
)
expected = "passed"
if result.returncode == 0 and expected in result.stdout:
    # Extract test count
    count_m = re.search(r'(\d+) passed', result.stdout)
    count = count_m.group(1) if count_m else "?"
    print(f"  ✅ {count} passed (includes test_verdict_prose_hold_verb_not_false_positive)")
else:
    print(f"  ❌ Verdict tests")
    print(f"     exit: {result.returncode}")
    print(f"     stdout: {result.stdout[:300]}")
    print(f"     stderr: {result.stderr[:300]}")
    errors.append("verdict-tests")
print()

# Check 4: Regression test exists and passes
print("--- Check 4: Regression test ---")
cmd = [PYTHON, "-m", "pytest", VERDICT_TEST_FILE + "::TestVerdict::test_verdict_prose_hold_verb_not_false_positive", "-v", "--tb=short", "-q"]
result = subprocess.run(
    cmd, capture_output=True, text=True, timeout=30,
    cwd=BASE,
    env={**os.environ, "PYTHONPATH": "."},
)
if result.returncode == 0:
    # Exit code 0 means test passed (with -q, stdout shows "." not "PASSED")
    print("  ✅ test_verdict_prose_hold_verb_not_false_positive PASSED (exit 0)")
else:
    print(f"  ❌ Regression test failed or missing")
    print(f"     stdout: {result.stdout[:200]}")
    print(f"     stderr: {result.stderr[:200]}")
    errors.append("regression-test")
print()

# Check 5: Full V2.x bundle
print("--- Check 5: Full V2.x bundle ---")
cmd = [PYTHON, "-m", "pytest"] + BUNDLE_FILES.split() + ["-q"]
result = subprocess.run(
    cmd, capture_output=True, text=True, timeout=180,
    cwd=BASE,
    env={**os.environ, "PYTHONPATH": "."},
)
if result.returncode == 0:
    count_m = re.search(r'(\d+) passed', result.stdout)
    count = count_m.group(1) if count_m else "?"
    print(f"  ✅ {count} passed in bundle (0 regressions)")
else:
    print(f"  ❌ Bundle tests")
    print(f"     exit: {result.returncode}")
    print(f"     stdout: {result.stdout[:200]}")
    print(f"     stderr: {result.stderr[:200]}")
    errors.append("bundle-tests")
print()

# Verdict
if errors:
    print(f"═══ BLOCKED: {len(errors)} check(s) failed ═══")
    for e in errors:
        print(f"  ❌ {e}")
    sys.exit(1)
else:
    print("═══ READY: all checks passed ═══")
    sys.exit(0)
