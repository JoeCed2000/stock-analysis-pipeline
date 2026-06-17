#!/usr/bin/env python3
"""Kernel verifier: t_0ad38717 — EPS/Revenue CRITICAL OVERRIDE before DATA CONTRACT.

Usage:
    python3 ops/kernel_checks/verify_t_0ad38717.py
    kverify .ced-agent-kernel/specs/t_0ad38717-eps-revenue-override-seam.json --base-dir /home/ced/codex-projects/stock-analysis-pipeline
"""

import ast
import os
import subprocess
import sys
import json

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPTS_PY = os.path.join(BASE, "backend", "earnings_deep_dive", "prompts.py")
SPEC_TEST = os.path.join(BASE, "tests", "spec_nvda_eps_revenue_override_seam.py")
WIKI_MD = os.path.join(BASE, "WIKI.md")

PASS = "✅"
FAIL = "❌"

results = []


def check(label, ok, detail=""):
    icon = PASS if ok else FAIL
    msg = f"{icon} {label}"
    if detail:
        msg += f" — {detail}"
    results.append(msg)
    return ok


def main():
    # 1. prompts.py compiles
    try:
        with open(PROMPTS_PY) as f:
            ast.parse(f.read())
        check("prompts.py compiles", True)
    except SyntaxError as e:
        check("prompts.py compiles", False, str(e))

    # 2. Regression spec file exists
    check("Regression spec file exists", os.path.isfile(SPEC_TEST))

    # 3. CRITICAL OVERRIDE comes before DATA CONTRACT in prompt
    try:
        sys.path.insert(0, BASE)
        from backend.earnings_deep_dive.generator import _section_metrics
        from backend.earnings_deep_dive.prompts import build_prompt

        metrics = {
            "eps_estimate": 1.77, "eps_actual": 0.89,
            "revenue_estimate": 79190000000, "revenue_actual": 81600000000,
            "consensus_provider": "Investing.com (analyst consensus)",
            "revenue_yoy": 0.398, "eps_yoy": -0.395,
        }
        section_metrics = _section_metrics("EPS & Revenue", metrics)
        prompt = build_prompt(
            "EPS & Revenue", "en", "NVDA", "NVIDIA Corp", "FY2027 Q1",
            section_metrics, "Revenue beat expectations.",
        )
        override_idx = prompt.index("CRITICAL OVERRIDE")
        contract_idx = prompt.index("DATA CONTRACT")
        ok = override_idx < contract_idx
        check("Override before DATA CONTRACT (EN)", ok,
              f"override={override_idx}, contract={contract_idx}")
    except Exception as e:
        check("Override before DATA CONTRACT (EN)", False, str(e))

    # 4. Override before DATA CONTRACT in JP too
    try:
        section_metrics = _section_metrics("EPS & Revenue", dict(metrics))
        prompt_jp = build_prompt(
            "EPS & Revenue", "jp", "NVDA", "NVIDIA Corp", "FY2027 Q1",
            section_metrics, "Revenue beat expectations.",
        )
        override_idx = prompt_jp.index("CRITICAL OVERRIDE")
        contract_idx = prompt_jp.index("DATA CONTRACT")
        ok = override_idx < contract_idx
        check("Override before DATA CONTRACT (JP)", ok,
              f"override={override_idx}, contract={contract_idx}")
    except Exception as e:
        check("Override before DATA CONTRACT (JP)", False, str(e))

    # 5. Regression tests pass
    try:
        env = {**os.environ, "PYTHONPATH": BASE}
        r = subprocess.run(
            [sys.executable, "-m", "pytest", SPEC_TEST, "-q"],
            capture_output=True, text=True, timeout=60, env=env,
        )
        ok = r.returncode == 0
        last_line = [l for l in r.stdout.strip().split("\n") if l][-1] if r.stdout else ""
        check("Regression tests pass", ok, last_line)
    except subprocess.TimeoutExpired:
        check("Regression tests pass", False, "timeout")

    # 6. Existing prompt tests pass (no regressions)
    try:
        env = {**os.environ, "PYTHONPATH": BASE}
        r = subprocess.run(
            [sys.executable, "-m", "pytest",
             os.path.join(BASE, "tests", "test_earnings_deep_dive_prompts.py"),
             "-q"],
            capture_output=True, text=True, timeout=60, env=env,
        )
        ok = r.returncode == 0
        last_line = [l for l in r.stdout.strip().split("\n") if l][-1] if r.stdout else ""
        check("Existing prompt tests pass", ok, last_line)
    except subprocess.TimeoutExpired:
        check("Existing prompt tests pass", False, "timeout")

    # 7. Spec + nvda bundle tests pass
    try:
        env = {**os.environ, "PYTHONPATH": BASE}
        import glob
        test_files = (
            glob.glob(os.path.join(BASE, "tests", "spec_v27_*.py"))
            + glob.glob(os.path.join(BASE, "tests", "spec_nvda_*.py"))
            + [os.path.join(BASE, "tests", "test_earnings_deep_dive_prompts.py")]
        )
        r = subprocess.run(
            [sys.executable, "-m", "pytest"] + test_files + ["-q"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        ok = r.returncode == 0
        last_line = [l for l in r.stdout.strip().split("\n") if l][-1] if r.stdout else ""
        check("Bundle tests pass (547+ tests)", ok, last_line)
    except subprocess.TimeoutExpired:
        check("Bundle tests pass (547+ tests)", False, "timeout")

    # 8. WIKI has entry
    try:
        with open(WIKI_MD) as f:
            wiki = f.read()
        check("WIKI.md has t_0ad38717 entry", "t_0ad38717" in wiki)
    except FileNotFoundError:
        check("WIKI.md has t_0ad38717 entry", False, "WIKI.md not found")

    # Summary
    passed = sum(1 for r in results if r.startswith(PASS))
    total = len(results)
    status = "VERIFY_T_0AD38717_READY" if passed == total else "VERIFY_T_0AD38717_PARTIAL"
    print(f"\n## Kernel Verify: t_0ad38717 ({passed}/{total})")
    print(f"Status: {status}")
    print()
    for r in results:
        print(r)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
