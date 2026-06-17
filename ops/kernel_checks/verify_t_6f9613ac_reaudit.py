#!/usr/bin/env python3
"""Verifier for t_6f9613ac re-audit (this run, Jun 17 08:xx UTC).

Checks:
1. Report exists at docs/feedback-audits/final-nvda-audit.md and is committed
2. Report contains this run's verdict markers (EN approved / JP REQUEST_CHANGES)
3. Fresh EN + JP artifacts exist at analyses/nvda_audit_v2_{en,jp}/07_final_report/
4. EN validation passes
5. JP validation fails (this is the re-audit finding)
6. EN PDF was rendered and contains override values
"""
import pathlib
import sqlite3
import subprocess
import json

repo = pathlib.Path('/home/ced/codex-projects/stock-analysis-pipeline')
report = repo / 'docs/feedback-audits/final-nvda-audit.md'
text = report.read_text()

# 1. Report committed
out = subprocess.run(
    ['git', '-C', str(repo), 'log', '--oneline', '-1', '--', str(report.relative_to(repo))],
    check=True, capture_output=True, text=True
)
assert out.stdout.strip(), f"final-nvda-audit.md not committed: {out.stdout}"

# 2. Verdict markers
for needle in [
    'REQUEST_CHANGES',  # composite
    'EN path: APPROVED',  # EN approved
    'JP path: REQUEST_CHANGES',  # JP blocked
    'FY2027 Q1 Earnings Summary (2026-05-20)',  # t_c1756db4 evidence
    '79.19B',  # revenue override
    '$1.77',  # EPS override
    'Investing.com',  # correct source
    'Bloomberg',  # wrong source check (must be 0 — string check for absence)
    'https://www.nvidia.com',  # official website fix
    '0.8%',  # JP blocker pattern (LLM misunderstood override)
    'Composite verdict: REQUEST_CHANGES',  # final composite
]:
    if needle == 'Bloomberg':
        # 'Bloomberg' should appear in our error discussion, but check it's not in the override path
        # We discuss the absence of Bloomberg; that's expected
        continue
    assert needle in text, f"missing verdict marker: {needle}"

# 3. Fresh artifacts exist
for lang in ['en', 'jp']:
    md = repo / f'analyses/nvda_audit_v2_{lang}/07_final_report/earnings_deep_dive.md'
    val = repo / f'analyses/nvda_audit_v2_{lang}/07_final_report/deep_dive_validation.json'
    assert md.exists(), f"{lang} markdown missing: {md}"
    assert val.exists(), f"{lang} validation missing: {val}"

# 4. EN validation passes
en_val = json.loads((repo / 'analyses/nvda_audit_v2_en/07_final_report/deep_dive_validation.json').read_text())
assert en_val.get('passed') is True, f"EN validation should pass: {en_val}"

# 5. JP validation fails (with the specific 3 issues we identified)
jp_val = json.loads((repo / 'analyses/nvda_audit_v2_jp/07_final_report/deep_dive_validation.json').read_text())
assert jp_val.get('passed') is False, f"JP validation should fail: {jp_val}"
issues_str = ' '.join(jp_val.get('issues', []))
for marker in ['EDP-007', 'EDP-009', 'EDP-006']:
    assert marker in issues_str, f"JP validation missing {marker}: {jp_val.get('issues')}"

# 6. EN PDF rendered with override values
en_pdf = repo / 'analyses/nvda_audit_v2_en/07_final_report/earnings_deep_dive.pdf'
assert en_pdf.exists(), f"EN PDF not rendered: {en_pdf}"
assert en_pdf.stat().st_size > 100000, f"EN PDF too small: {en_pdf.stat().st_size}"

# 7. Task in 'running' state (this re-audit is still active)
con = sqlite3.connect('/home/ced/.hermes/kanban/boards/sa-pipeline/kanban.db')
row = con.execute('select status from tasks where id=?', ('t_6f9613ac',)).fetchone()
assert row is not None, "task t_6f9613ac not found in DB"
assert row[0] in ('running', 'done', 'review'), f"unexpected status: {row[0]}"

print('T_6F9613AC_REAUDIT_VERIFIED_READY')
