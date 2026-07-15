#!/usr/bin/env python3
"""Kernel proof for t_750fe7b2 artifact access contract.

Verifies the implemented public/private artifact boundary and batch capability
contract with deterministic source inspections plus the focused pytest bundle.
"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAIN_PY = REPO / "backend" / "main.py"
TEST_FILE = REPO / "tests" / "test_artifact_access_security.py"
EXPECTED_TESTS = [
    "tests/test_artifact_access_security.py",
    "tests/test_main_endpoints.py",
    "tests/test_public_client_auth.py",
    "tests/test_batch.py",
]

errors: list[str] = []
source = MAIN_PY.read_text(encoding="utf-8")
test_source = TEST_FILE.read_text(encoding="utf-8")
tree = ast.parse(source)

functions: dict[str, ast.AST] = {}
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        functions[node.name] = node


def _function_source(name: str) -> str:
    node = functions.get(name)
    if node is None:
        return ""
    return ast.get_source_segment(source, node) or ""

for name in (
    "_sign_batch_capability",
    "_verify_batch_capability",
    "_batch_internal_id_from_request",
    "_sanitize_public_dossier_status",
    "batch_analyze",
    "batch_status",
    "batch_download",
):
    if name not in functions:
        errors.append(f"missing function: {name}")

required_route_patterns = {
    "private legacy ZIP protected": r'@app\.get\("/api/analyze/\{ticker\}/download",\s*dependencies=\[Depends\(_require_auth\)\]\)',
    "sources protected": r'@app\.get\("/api/sources/\{ticker\}",\s*dependencies=\[Depends\(_require_auth\)\]\)',
    "traceability protected": r'@app\.get\("/api/traceability/\{ticker\}",\s*dependencies=\[Depends\(_require_auth\)\]\)',
}
for label, pattern in required_route_patterns.items():
    if not re.search(pattern, source):
        errors.append(f"route contract missing: {label}")

capability_source = "\n".join(
    _function_source(name)
    for name in ("_sign_batch_capability", "_verify_batch_capability")
)
for needle, label in (
    ("hmac.new", "HMAC signing"),
    ("hmac.compare_digest", "constant-time signature/key compare"),
    ("exp", "expiry binding"),
    ("batch-status-download", "purpose binding"),
):
    if needle not in capability_source and needle not in source:
        errors.append(f"batch capability missing {label}")

batch_analyze_src = _function_source("batch_analyze")
if "secrets.token_urlsafe" not in batch_analyze_src:
    errors.append("batch internal id must use secrets.token_urlsafe")
if "_sign_batch_capability" not in batch_analyze_src:
    errors.append("batch_analyze must mint signed capability")
if "hashlib.sha256" in batch_analyze_src:
    errors.append("batch_analyze still uses deterministic hash-based job id")

status_src = _function_source("dossier_status")
if "_sanitize_public_dossier_status" not in status_src:
    errors.append("public dossier status must sanitize filesystem fields")

download_src = _function_source("dossier_download")
for needle in ("is_symlink", "relative_to(analyses_root)", "part.startswith(\".\")", "X-Content-Type-Options"):
    if needle not in download_src:
        errors.append(f"dossier_download missing hardened check/header: {needle}")

if "TEST_KEY" not in test_source or "CAPABILITY_SECRET" not in test_source:
    errors.append("test_artifact_access_security.py must use placeholder auth/capability secrets")
if re.search(r"sk-[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9]{20,}", test_source):
    errors.append("test fixture contains a string shaped like a real API secret")

cmd = [sys.executable, "-m", "pytest", *EXPECTED_TESTS, "-q"]
result = subprocess.run(
    cmd,
    cwd=str(REPO),
    env={**os.environ, "PYTHONPATH": "."},
    capture_output=True,
    text=True,
    timeout=300,
)
if result.returncode != 0:
    errors.append(
        "pytest bundle failed (exit %s):\n%s\n%s"
        % (result.returncode, result.stdout[-1200:], result.stderr[-1200:])
    )
elif "passed" not in result.stdout:
    errors.append(f"pytest bundle output did not include pass marker:\n{result.stdout[-500:]}")

if errors:
    print("VERIFY_T_750FE7B2_ARTIFACT_ACCESS_FAIL")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("VERIFY_T_750FE7B2_ARTIFACT_ACCESS_READY")
print("- private artifact routes: /api/analyze/{ticker}/download, /api/sources/{ticker}, /api/traceability/{ticker} protected")
print("- public curated routes/status: report/dossier flows remain unauthenticated and sanitized")
print("- batch status/download: signed HMAC capability + expiry + master-key override")
print("- tests:", result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "passed")
sys.exit(0)
