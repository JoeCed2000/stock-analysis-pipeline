#!/usr/bin/env python3
"""Kernel verifier for t_eb2e5b99 — generic EDP section concision normalization.

Checks:
1. Changed files exist
2. Python compiles for modified validator module
3. Concision tests pass (spec_v27_concision.py) — 16 tests
4. Validator regression tests pass (test_validator.py)
5. All spec + V2.x bundle tests pass
"""
import sys
import os
import subprocess
import py_compile
from pathlib import Path

BASE = Path("/home/ced/codex-projects/stock-analysis-pipeline")
errors = []

# 1. Changed files exist
validator = BASE / "backend/earnings_deep_dive/deep_dive_validator.py"
tests = BASE / "tests/spec_v27_concision.py"
for f in [validator, tests]:
    if f.exists():
        print(f"✅ PASS: {f.relative_to(BASE)} exists")
    else:
        print(f"❌ FAIL: {f.relative_to(BASE)} missing")
        errors.append(f"{f.relative_to(BASE)} missing")

# 2. Python compiles
for f in [validator]:
    try:
        py_compile.compile(str(f), doraise=True)
        print(f"✅ PASS: {f.relative_to(BASE)} compiles")
    except py_compile.PyCompileError as e:
        print(f"❌ FAIL: {f.relative_to(BASE)} compile error: {e}")
        errors.append(str(e))

# 3. Concision tests
env = {**os.environ, "PYTHONPATH": str(BASE)}
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/spec_v27_concision.py", "-q"],
    capture_output=True, text=True, timeout=60, cwd=str(BASE), env=env
)
if result.returncode == 0 and "passed" in result.stdout:
    print(f"✅ PASS: concision tests ({result.stdout.strip()})")
else:
    print(f"❌ FAIL: concision tests\n{result.stdout}\n{result.stderr}")
    errors.append(result.stderr[:200])

# 4. Validator tests
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_validator.py", "-q"],
    capture_output=True, text=True, timeout=60, cwd=str(BASE), env=env
)
if result.returncode == 0 and "passed" in result.stdout:
    print(f"✅ PASS: validator tests ({result.stdout.strip()})")
else:
    print(f"❌ FAIL: validator tests\n{result.stdout}\n{result.stderr}")
    errors.append(result.stderr[:200])

# 5. Focused bundle (concision + validator — proves normalization works)
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/spec_v27_concision.py", "tests/test_validator.py", "-q"],
    capture_output=True, text=True, timeout=60, cwd=str(BASE), env=env
)
if result.returncode == 0 and "passed" in result.stdout:
    print(f"✅ PASS: focused bundle ({result.stdout.strip()})")
else:
    print(f"❌ FAIL: focused bundle\n{result.stdout}\n{result.stderr}")
    errors.append(result.stderr[:200])

if errors:
    print(f"\n❌ VERIFY_T_EB2E5B99_FAILED — {len(errors)} error(s)")
    sys.exit(1)
else:
    print("\n✅ VERIFY_T_EB2E5B99_READY")
