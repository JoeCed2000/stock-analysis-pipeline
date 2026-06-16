#!/usr/bin/env python3
"""Kernel verifier for t_ca12f2b1: NVDA EDP validation repair.

Checks:
1. Changed files exist
2. Python compiles for changed source files
3. Focused test suite passes
4. Bundle test suite has no regressions
"""

import subprocess
import sys

BASE = "/home/ced/codex-projects/stock-analysis-pipeline"
CHANGED = [
    "backend/earnings_deep_dive/deep_dive_validator.py",
    "backend/earnings_deep_dive/prompts.py",
    "tests/spec_v27_numeric_consistency.py",
]
COMPILE_FILES = [
    "backend/earnings_deep_dive/deep_dive_validator.py",
]
TEST_CMDS = [
    ([sys.executable, "-m", "pytest", "tests/spec_v27_numeric_consistency.py", "-v", "--tb=short", "-q"], "7 passed"),
    ([sys.executable, "-m", "pytest", "tests/spec_v27_numeric_consistency.py", "tests/spec_v27_concision.py", "tests/spec_v27_forbidden_headings.py", "tests/spec_v27_missing_data_leaks.py", "tests/test_validator.py", "tests/spec_v27_verdict_valuation_dq_segments.py", "tests/spec_v27_period_consistency.py", "tests/spec_v27_metrics_ledger.py", "tests/spec_v27_source_registry.py", "-v", "--tb=short", "-q"], "173 passed"),
]

errors = []

print("═══ Kernel Check: t_ca12f2b1 ═══")
print()

# Check 1: Files exist
print("--- Check 1: Changed files exist ---")
for f in CHANGED:
    p = f"{BASE}/{f}"
    import os
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
        [sys.executable, "-m", "py_compile", f"{BASE}/{f}"],
        capture_output=True, text=True, timeout=10,
        cwd=BASE,
    )
    if result.returncode == 0:
        print(f"  ✅ {f}")
    else:
        print(f"  ❌ {f}: {result.stderr.strip()}")
        errors.append(f)
print()

# Check 3: Test commands
print("--- Check 3: Test commands ---")
for cmd, expected_stdout in TEST_CMDS:
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        cwd=BASE,
        env={**__import__("os").environ, "PYTHONPATH": "."},
    )
    if result.returncode == 0 and expected_stdout in result.stdout:
        print(f"  ✅ {' '.join(cmd[:3])}... → {expected_stdout}")
    else:
        print(f"  ❌ {' '.join(cmd[:3])}...")
        print(f"     exit: {result.returncode}")
        print(f"     stdout: {result.stdout[:200]}")
        print(f"     stderr: {result.stderr[:200]}")
        errors.append(str(cmd))
print()

# Verdict
if errors:
    print(f"═══ BLOCKED: {len(errors)} check(s) failed ═══")
    sys.exit(1)
else:
    print("═══ READY: all checks passed ═══")
    sys.exit(0)
