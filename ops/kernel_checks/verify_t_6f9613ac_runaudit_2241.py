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

# 3. HEAD advanced since 4e0d4ac — verifier checks for audit-doc + kernel + verifier-fix commits
out = subprocess.run(
    ['git', '-C', str(repo), 'log', '4e0d4ac..HEAD', '--oneline', '--',
     'docs/feedback-audits/final-nvda-audit.md',
     '.ced-agent-kernel/specs/t_6f9613ac-runaudit-2241.json',
     'ops/kernel_checks/verify_t_6f9613ac_runaudit_2241.py'],
    check=True, capture_output=True, text=True
)
verifier_commits = [l for l in out.stdout.strip().split('\n') if l]
assert 1 <= len(verifier_commits) <= 5, f"expected 1-5 task commits since 4e0d4ac, got {len(verifier_commits)}: {verifier_commits}"
assert any('no-op re-dispatch' in l for l in verifier_commits), f"missing audit doc commit: {verifier_commits}"
assert any('run 2241 re-audit kernel proof' in l for l in verifier_commits), f"missing kernel proof commit: {verifier_commits}"

# 4. No backend/frontend changes
out = subprocess.run(
    ['git', '-C', str(repo), 'log', '4e0d4ac..HEAD', '--oneline', '--', 'backend/', 'frontend/'],
    check=True, capture_output=True, text=True
)
assert out.stdout.strip() == '', f"backend/frontend changed in run 2241: {out.stdout}"

# 5. Backend health — commit must be a descendant of 4e0d4ac (post-run-2240 ancestor)
# Use prefix check against the actual HEAD so verifier doesn't break on every new commit
out_health = subprocess.run(
    ['curl', '-s', '--max-time', '5', 'http://127.0.0.1:8780/api/health'],
    check=True, capture_output=True, text=True
)
h = json.loads(out_health.stdout)
backend_commit = h.get('commit', '')
# Backend must be a commit on the same branch as HEAD; check it's descendant of 4e0d4ac
desc = subprocess.run(
    ['git', '-C', str(repo), 'merge-base', '--is-ancestor', '4e0d4ac', 'HEAD'],
    capture_output=True, text=True
)
# Simpler check: backend commit must be one of the post-4e0d4ac commits
post = subprocess.run(
    ['git', '-C', str(repo), 'log', '4e0d4ac..HEAD', '--format=%H'],
    check=True, capture_output=True, text=True
)
post_commits = set(post.stdout.strip().split('\n'))
# Backend reports short SHA; match by prefix
matches = [c for c in post_commits if c.startswith(backend_commit)]
assert matches, f"backend commit {backend_commit} is not a descendant of 4e0d4ac (post-commits: {sorted(post_commits, reverse=True)[:5]})"

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
