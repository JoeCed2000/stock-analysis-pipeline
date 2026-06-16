#!/usr/bin/env python3
"""Kernel verifier for t_3173af81 — Fix NVDA Net Cash value to 72.1B."""
import json, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
SPEC = BASE / ".ced-agent-kernel" / "specs" / "t_3173af81.json"
spec = json.loads(SPEC.read_text())
checks = spec["checks"]
errors = []

# 1. Files exist
for f in checks["files_exist"]:
    if (BASE / f).exists():
        print(f"✅ {f} exists")
    else:
        errors.append(f"❌ {f} missing")

# 2. Compile
try:
    import py_compile
    py_compile.compile(str(BASE / (checks["compile"]["module"].replace(".", "/") + ".py")), doraise=True)
    print(f"✅ {checks['compile']['module']} compiles")
except Exception as e:
    errors.append(f"❌ Compile failed: {e}")
    print(f"❌ Compile failed: {e}")

# 3. Focused tests
def run_tests(test_files_str, label, timeout=30):
    files = [f.strip() for f in test_files_str.split() if f.strip()]
    result = subprocess.run(
        ["python3", "-m", "pytest", *files, "-q", "--tb=short"],
        capture_output=True, text=True, cwd=BASE, timeout=timeout
    )
    if result.returncode == 0:
        print(f"✅ {label}")
        return True
    else:
        errors.append(f"❌ {label}:\n{result.stdout[-500:]}\n{result.stderr[-500:]}")
        print(f"❌ {label}")
        return False

run_tests(checks["focused_tests"], "focused tests", 30)
run_tests(checks["bundle_tests"], "bundle tests", 60)

if errors:
    print(f"\n❌ {len(errors)} check(s) FAILED:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("\n✅ All checks PASSED")
    sys.exit(0)
