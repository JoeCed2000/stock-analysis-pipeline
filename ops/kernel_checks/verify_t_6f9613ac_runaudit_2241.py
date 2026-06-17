#!/usr/bin/env python3
"""Verifier for t_6f9613ac re-audit (run 2241, Jun 17 08:25+ UTC).

Reaffirms the run 2240 verdict for the third consecutive run.
Checks:
1. Report exists and contains the run-2241 §1.2 marker
2. HEAD advanced since 4e0d4ac (the run-2240 kernel proof) by exactly 1 commit
3. That 1 commit is the audit doc, not backend/frontend code
4. Backend /api/health still reports commit 4e0d4ac or 0ade5f2
5. JP validation still fails (3 issues: EDP-007/009/006)
6. JP markdown still has 3 numbered items (①②③) AND the 0.8% bug
7. No v3 analysis directories created
"""
import pathlib
import subprocess
import json

repo = pathlib.Path('/home/ced/codex-projects/stock-analysis-pipeline')
report = repo / 'docs/feedback-audits/final-nvda-audit.md'
text = report.read_text()

# 1. §1.2 marker present
assert '## 1.2. Re-dispatch verification' in text, "§1.2 marker missing"
assert 'run 2241' in text, "run 2241 reference missing"

# 2. Report committed
out = subprocess.run(
    ['git', '-C', str(repo), 'log', '--oneline', '-1', '--', str(report.relative_to(repo))],
    check=True, capture_output=True, text=True
)
assert '0ade5f2' in out.stdout or 'no-op' in out.stdout, f"audit doc not committed cleanly: {out.stdout}"

# 3. HEAD advanced by exactly 1 commit since 4e0d4ac
out = subprocess.run(
    ['git', '-C', str(repo), 'log', '4e0d4ac..HEAD', '--oneline'],
    check=True, capture_output=True, text=True
)
lines = [l for l in out.stdout.strip().split('\n') if l]
assert len(lines) == 1, f"expected 1 commit since 4e0d4ac, got {len(lines)}: {lines}"
assert 'no-op re-dispatch' in lines[0], f"unexpected commit: {lines[0]}"

# 4. No backend/frontend changes
out = subprocess.run(
    ['git', '-C', str(repo), 'log', '4e0d4ac..HEAD', '--oneline', '--', 'backend/', 'frontend/'],
    check=True, capture_output=True, text=True
)
assert out.stdout.strip() == '', f"backend/frontend changed in run 2241: {out.stdout}"

# 5. Backend health still at 4e0d4ac or 0ade5f2
out = subprocess.run(
    ['curl', '-s', '--max-time', '5', 'http://127.0.0.1:8780/api/health'],
    check=True, capture_output=True, text=True
)
h = json.loads(out.stdout)
assert h.get('commit') in ('4e0d4ac', '0ade5f2'), f"backend commit changed unexpectedly: {h.get('commit')}"

# 6. JP validation still fails
jp_val = json.loads((repo / 'analyses/nvda_audit_v2_jp/07_final_report/deep_dive_validation.json').read_text())
assert jp_val.get('passed') is False, f"JP validation should still fail: {jp_val}"
issues_str = ' '.join(jp_val.get('issues', []))
for marker in ['EDP-007', 'EDP-009', 'EDP-006']:
    assert marker in issues_str, f"JP validation missing {marker}: {jp_val.get('issues')}"

# 7. JP markdown still has 3 numbered items AND 0.8%
jp_md = (repo / 'analyses/nvda_audit_v2_jp/07_final_report/earnings_deep_dive.md').read_text()
for marker in ['①', '②', '③']:
    assert marker in jp_md, f"JP markdown missing numbered item {marker}"
assert '0.8%' in jp_md, "JP markdown 0.8% bug gone?"

# 8. No v3 directories
assert not (repo / 'analyses/nvda_audit_v3_en').exists(), "v3_en directory created unexpectedly"
assert not (repo / 'analyses/nvda_audit_v3_jp').exists(), "v3_jp directory created unexpectedly"

print('T_6F9613AC_RUNAUDIT_2241_VERIFIED_READY')
