#!/usr/bin/env bash
set -euo pipefail
cd /home/ced/codex-projects/stock-analysis-pipeline
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/spec_v27_numeric_consistency.py tests/spec_v27_concision.py tests/spec_v27_forbidden_headings.py tests/spec_v27_missing_data_leaks.py tests/test_validator.py tests/spec_v27_verdict_valuation_dq_segments.py tests/spec_v27_period_consistency.py tests/spec_v27_metrics_ledger.py tests/spec_v27_source_registry.py -q -o addopts=
PYTHONPATH=. backend/.venv/bin/python -m py_compile backend/earnings_deep_dive/deep_dive_validator.py
printf 'EDP006_NUMERIC_CONSISTENCY_READY\n'
