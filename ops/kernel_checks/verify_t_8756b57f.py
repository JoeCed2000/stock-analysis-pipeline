#!/usr/bin/env python3
"""Deterministic verifier for t_8756b57f — Quality row removed from Peer Benchmark."""

import os
import subprocess
import sys

BASE_DIR = "/home/ced/codex-projects/stock-analysis-pipeline"
os.chdir(BASE_DIR)

# Set up environment for test execution
ENV = os.environ.copy()
ENV["PYTHONPATH"] = f"{BASE_DIR}/backend"
PYTHON = f"{BASE_DIR}/backend/.venv/bin/python"

errors = []

def run(cmd, check_out=None, expected_exit=0, use_venv=False, timeout=120):
    full_cmd = cmd
    result = subprocess.run(
        full_cmd, cwd=BASE_DIR, capture_output=True, text=True,
        shell=True, timeout=timeout, env=ENV
    )
    if result.returncode != expected_exit:
        errors.append(f"Command exited {result.returncode} (expected {expected_exit}): {cmd[:120]}")
        stderr = result.stderr.strip()[:300]
        stdout = result.stdout.strip()[:200]
        if stderr:
            errors.append(f"  stderr: {stderr}")
        if stdout:
            errors.append(f"  stdout: {stdout}")
        return False
    if check_out and check_out not in result.stdout:
        errors.append(f"Pattern '{check_out}' not in stdout for: {cmd[:120]}")
        errors.append(f"  stdout: {result.stdout.strip()[:300]}")
        return False
    return True

# Check 1: Quality tuple is absent from pdf_renderer.py (grep returns 1 = no match)
run("grep 'translate(\"Quality\", lang), pb.relative_quality_label' backend/earnings_deep_dive/pdf_renderer.py",
    expected_exit=1)

# Check 2: Valuation and Growth tuples still present
run("grep 'translate(\"Valuation\", lang), pb.relative_valuation_label' backend/earnings_deep_dive/pdf_renderer.py",
    expected_exit=0)
run("grep 'translate(\"Growth\", lang), pb.relative_growth_label' backend/earnings_deep_dive/pdf_renderer.py",
    expected_exit=0)

# Check 3: Py_compile pdf_renderer.py
result = subprocess.run(["python3", "-m", "py_compile", "backend/earnings_deep_dive/pdf_renderer.py"],
                        cwd=BASE_DIR, capture_output=True, text=True, env=ENV)
if result.returncode != 0:
    errors.append(f"py_compile pdf_renderer.py failed: {result.stderr.strip()[:500]}")

# Check 4: Py_compile test file
result = subprocess.run(["python3", "-m", "py_compile", "tests/spec_v27_pdf_renderer.py"],
                        cwd=BASE_DIR, capture_output=True, text=True, env=ENV)
if result.returncode != 0:
    errors.append(f"py_compile spec_v27_pdf_renderer.py failed: {result.stderr.strip()[:500]}")

# Check 5: New Quality regression test exists
run("grep 'test_quality_row_suppressed_when_all_dimensions_present' tests/spec_v27_pdf_renderer.py",
    expected_exit=0)

# Check 6: Focused tests pass (37 tests)
run(f"{PYTHON} -m pytest tests/spec_v27_pdf_renderer.py -q",
    check_out="37 passed", use_venv=True)

# Check 7: Bundle tests pass (102 tests)
run(f"{PYTHON} -m pytest tests/spec_v27_pdf_renderer.py tests/test_v27_peer_benchmark.py tests/spec_v27_report_model.py tests/test_earnings_deep_dive.py -q",
    check_out="102 passed", use_venv=True)

if errors:
    print("VERIFY_T_8756B57F_FAILED", flush=True)
    for e in errors:
        print(f"  ❌ {e}", flush=True)
    sys.exit(1)
else:
    print("VERIFY_T_8756B57F_READY", flush=True)
    sys.exit(0)
