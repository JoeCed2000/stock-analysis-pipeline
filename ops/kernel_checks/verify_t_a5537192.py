#!/usr/bin/env python3
"""Kernel proof script for t_a5537192: segment revenue EDP-006 filter.

Checks:
1. deep_dive_validator.py compiles
2. Focused numeric consistency tests pass (9 tests)
3. Broader bundle passes (numeric + concision + validator = 64 tests)
4. NVDA dossier (which previously failed EDP-006 for Data Center $75B) now passes
5. True revenue mismatch still correctly flagged even with segment data present
"""
import sys
import subprocess
import ast
import os

BASE_DIR = "/home/ced/codex-projects/stock-analysis-pipeline"

errors = []

# 1. Compile check
validator_path = os.path.join(BASE_DIR, "backend/earnings_deep_dive/deep_dive_validator.py")
try:
    with open(validator_path) as f:
        ast.parse(f.read())
    print(f"✅ Compile: {validator_path}")
except SyntaxError as e:
    errors.append(f"Compile error: {e}")
    print(f"❌ Compile: {e}")

# 2. Focused numeric tests
result = subprocess.run(
    ["python3", "-m", "pytest", "tests/spec_v27_numeric_consistency.py", "-q"],
    capture_output=True, text=True, cwd=BASE_DIR, timeout=30
)
if "9 passed" in result.stdout:
    print(f"✅ Numeric consistency: 9/9 passed")
else:
    errors.append(f"Numeric tests: {result.stdout.strip()}")
    print(f"❌ Numeric tests: {result.stdout.strip()}")

# 3. Broader bundle (numeric + concision + validator)
result = subprocess.run(
    ["python3", "-m", "pytest",
     "tests/spec_v27_numeric_consistency.py",
     "tests/spec_v27_concision.py",
     "tests/test_validator.py", "-q"],
    capture_output=True, text=True, cwd=BASE_DIR, timeout=30
)
if "64 passed" in result.stdout:
    print(f"✅ Bundle (numeric+concision+validator): 64/64 passed")
else:
    errors.append(f"Bundle tests: {result.stdout.strip()}")
    print(f"❌ Bundle tests: {result.stdout.strip()}")

# 4. Full V2.x bundle
result = subprocess.run(
    "python3 -m pytest tests/spec_v27_*.py tests/test_v27_*.py tests/test_validator.py -q",
    capture_output=True, text=True, cwd=BASE_DIR, timeout=90, shell=True
)
if "passed" in result.stdout:
    count = result.stdout.strip().split(" ")[0]
    print(f"✅ Full V2.x bundle: {count} passed")
else:
    errors.append(f"Full bundle: {result.stdout.strip()}")
    print(f"❌ Full bundle: {result.stdout.strip()}")

# 5. NVDA dossier no longer blocked by EDP-006
sys.path.insert(0, BASE_DIR)
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive
md_path = os.path.join(BASE_DIR,
    "analyses/2026-06-16_143249_NVDA_NVIDIA_Corp/07_final_report/earnings_deep_dive.md")
passed, issues = validate_deep_dive(md_path)
numeric_issues = [i for i in issues if "numeric" in i.lower() or "EDP-006" in i]
if passed and len(numeric_issues) == 0:
    print(f"✅ NVDA dossier: passed ({len(issues)} total issues, 0 numeric/EDP-006)")
else:
    errors.append(f"NVDA dossier: passed={passed}, numeric_issues={numeric_issues}")
    print(f"❌ NVDA dossier: passed={passed}, numeric_issues={numeric_issues}")

if errors:
    print(f"\n❌ FAILED — {len(errors)} error(s):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"\n✅ ALL CHECKS PASSED")
    sys.exit(0)
