---
type: project
title: sa-pipeline (Nami) — Stock Analysis Pipeline
date: '2026-06-09T00:00:00.000Z'
status: active
code_path: /home/ced/codex-projects/stock-analysis-pipeline
kanban_board: sa-pipeline
related_pages:
  - notes/incidents/2026-06-09-sa-pipeline-kill-switch-loop
  - notes/howto/kanban-panic-unfreeze-2026-06-09
ingested_via: 'mcp:put_page'
ingested_at: '2026-06-09T06:24:40.852Z'
source_kind: 'mcp:put_page'
tags:
  - nami
  - pdf-reports
  - project
  - sa-pipeline
  - stock-analysis
---

# sa-pipeline (Nami) — Stock Analysis Pipeline

> Alias projet : **Nami** (cf. profile user 2026-06-04).

## Vue d'ensemble

Pipeline Python qui génère des rapports PDF d'analyse financière sur actions US. Tourne sur le board Kanban `sa-pipeline` avec plusieurs workers dédiés :

- `python-builder` — exécution Python réelle (fetch data → compute → render PDF)
- `reviewer-qa` — QA et relecture des PDFs
- `pdf-report-auditor` — audit spécifique des défauts PDF

## Localisation

- Code : `/home/ced/codex-projects/stock-analysis-pipeline/`
- DB Kanban : `~/.hermes/kanban/boards/sa-pipeline/kanban.db`
- Workspace tasks : `~/.hermes/kanban/boards/sa-pipeline/workspaces/`

## Profil user dominant

`minimax-m3` (default), mais la board spawn des sub-profiles (`codex-first`, `pdf-report-auditor`, `reviewer-qa`).

## Risques connus

- **Token-burn loops** : la board a un kill-switch dédié (`sa_kanban_kill_switch.py`, job cron `8ff32c104208`) suite à un incident de 2026-06-09.
- **DB malformée** : référencée par `kanban-healthcheck/references/db-header-recovery.md`.
- **Auto-decompose + triage** : piège, voir `kanban-healthcheck/references/auto-decompose-triage-token-burn-2026-06-02.md`.

## Incidents liés

- `notes/incidents/2026-06-09-sa-pipeline-kill-switch-loop` — kill-switch self-blooping loop, résolu.

## Runbooks

- `notes/howto/kanban-panic-unfreeze-2026-06-09` — dégeler une tâche gelée par le kill-switch.
- Skill `ced/kanban-forensics` — audit read-only d'incident Kanban.
- Skill `ced/kanban-healthcheck/references/kanban-panic-kill-switch.md` — gel d'urgence.
