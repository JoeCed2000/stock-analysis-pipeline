#!/usr/bin/env python3
"""Kernel verifier for t_feee864b — NVDA revenue estimate override.

Checks:
1. consensus_overrides.json has NVDA FY2027 Q1 with revenue_estimate 79.19B
2. pipeline.py calls apply_consensus_overrides for NVDA
3. Hotfix acceptance tests pass (override priority, surprise calc, ticker isolation)
4. V2.x bundle passes (0 regressions)
5. EPS & Revenue prompt carries the consensus provider name
6. Revenue estimate is never fabricated from actuals
"""
import json, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
PASS, FAIL = 0, 0

def check(label, ok):
    global PASS, FAIL
    if ok:
        print(f"  ✅ {label}")
        PASS += 1
    else:
        print(f"  ❌ {label}")
        FAIL += 1

def run(cmd, expected_in_stdout=None):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
        if expected_in_stdout and expected_in_stdout not in r.stdout:
            ok = False
        return ok, r.stdout
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"

# 1. Override data exists
ov_path = BASE / "backend" / "config" / "consensus_overrides.json"
try:
    ov = json.loads(ov_path.read_text())
    nvda_q1 = ov.get("NVDA", {}).get("FY2027 Q1", {})
    check("Override data: NVDA FY2027 Q1 has revenue_estimate=79.19B",
          nvda_q1.get("revenue_estimate") == 79_190_000_000)
    check("Override data: source='Investing.com (analyst consensus)'",
          "Investing.com" in nvda_q1.get("source", ""))
    check("Override data: eps_estimate=1.77",
          nvda_q1.get("eps_estimate") == 1.77)
except Exception as e:
    check(f"Override data file readable: {e}", False)

# 2. pipeline.py calls apply_consensus_overrides
pipeline = (BASE / "backend" / "pipeline.py").read_text()
check("Pipeline calls apply_consensus_overrides",
      "apply_consensus_overrides(ticker_for_segments, fin_data)" in pipeline)

# 3. Hotfix acceptance tests
ok, out = run(
    f"cd {BASE} && PYTHONPATH=backend backend/.venv/bin/python -m pytest tests/test_hotfix_acceptance.py -q",
    expected_in_stdout="14 passed"
)
check("Hotfix acceptance: 14 tests pass", ok)

# 4. V2.x bundle
ok, out = run(
    f"cd {BASE} && PYTHONPATH=backend backend/.venv/bin/python -m pytest tests/spec_v27_*.py tests/test_hotfix_acceptance.py tests/test_earnings_deep_dive_prompts.py tests/test_quarterly_comparison.py -q",
    expected_in_stdout="559 passed"
)
check("V2.x bundle: 559 tests pass, 0 regressions", ok)

# 5. Prompt carries consensus provider
ok, out = run(
    f"cd {BASE} && PYTHONPATH=backend backend/.venv/bin/python -m pytest tests/test_earnings_deep_dive_prompts.py::test_eps_revenue_prompt_carries_consensus_provider -v",
    expected_in_stdout="PASSED"
)
check("Prompt carries consensus provider name", ok)

# 6. No fabrication guard
ok, out = run(
    f"cd {BASE} && PYTHONPATH=backend backend/.venv/bin/python -m pytest tests/test_quarterly_comparison.py::test_revenue_estimate_is_never_fabricated_from_actuals -v",
    expected_in_stdout="PASSED"
)
check("Revenue estimate never fabricated from actuals", ok)

print(f"\n{'='*40}")
print(f"VERIFY_T_FEEE864B: {PASS}/{PASS+FAIL} checks passed")
if FAIL:
    print(f"WARNING: {FAIL} check(s) failed — do not mark READY")
    sys.exit(1)
print("READY")
sys.exit(0)
