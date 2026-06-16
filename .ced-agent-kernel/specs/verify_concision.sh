#!/usr/bin/env bash
# Concision validator verifier — runs the focused concision tests
set -e
cd /home/ced/codex-projects/stock-analysis-pipeline
PYTHONPATH=. backend/.venv/bin/python -m pytest tests/spec_v27_concision.py -q 2>&1 | grep -q "9 passed"
echo "ALL CONCISION TESTS PASSED"
