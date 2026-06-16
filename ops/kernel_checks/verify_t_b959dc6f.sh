#!/bin/bash
set -euo pipefail

echo "=== Verifying t_b959dc6f: EPS Revenue numbered-item limit ==="

# 1. Python compiles
python3 -m py_compile backend/earnings_deep_dive/deep_dive_validator.py
echo "PASS: deep_dive_validator.py compiles"

# 2. Focused concision tests pass (including the new regression test)
python3 -m pytest tests/spec_v27_concision.py -q
echo "PASS: concision tests"

# 3. Bundle tests pass
python3 -m pytest \
  tests/spec_v27_concision.py \
  tests/spec_v27_numeric_consistency.py \
  tests/spec_v27_forbidden_headings.py \
  tests/spec_v27_missing_data_leaks.py \
  tests/spec_v27_verdict_valuation_dq_segments.py \
  tests/spec_v27_period_consistency.py \
  tests/spec_v27_metrics_ledger.py \
  tests/spec_v27_source_registry.py \
  tests/spec_v27_fcf_margin_presence.py \
  tests/spec_v27_net_debt_presence.py \
  tests/spec_v27_source_display_policy.py \
  tests/spec_v27_source_display_renderer.py \
  -q
echo "PASS: bundle tests"

echo "=== ALL CHECKS PASSED ==="
