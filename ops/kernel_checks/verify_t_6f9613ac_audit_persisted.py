#!/usr/bin/env python3
import pathlib, sqlite3, subprocess
repo=pathlib.Path('/home/ced/codex-projects/stock-analysis-pipeline')
report=repo/'docs/feedback-audits/final-nvda-audit.md'
text=report.read_text()
for needle in ['REQUEST_CHANGES','EPS & Revenue','79.19B','Official Website: Not disclosed','not client-approvable']:
    assert needle in text, f'missing {needle}'
con=sqlite3.connect('/home/ced/.hermes/kanban/boards/sa-pipeline/kanban.db')
row=con.execute('select status,result from tasks where id=?',('t_6f9613ac',)).fetchone()
assert row and row[0]=='blocked', row
assert row[1] and 'REQUEST_CHANGES' in row[1] and 'final-nvda-audit.md' in row[1], row
subprocess.run(['git','-C',str(repo),'log','--oneline','-1','--',str(report.relative_to(repo))], check=True, capture_output=True, text=True)
print('T_6F9613AC_AUDIT_PERSISTED_READY')
