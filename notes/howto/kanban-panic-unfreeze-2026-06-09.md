---
type: note
title: Howto — Dégeler une tâche gelée par un kill-switch Kanban
date: '2026-06-09T00:00:00.000Z'
status: living-doc
projects:
  - projects/sa-pipeline
  - projects/ced-kanban-orchestrator
related_pages:
  - notes/incidents/2026-06-09-sa-pipeline-kill-switch-loop
ingested_via: 'mcp:put_page'
ingested_at: '2026-06-09T06:23:29.057Z'
source_kind: 'mcp:put_page'
tags:
  - howto
  - kanban
  - kill-switch
  - panic-unfreeze
  - runbook
---

# Howto — Dégeler une tâche gelée par un kill-switch Kanban

> **Complémentaire** de `references/kanban-panic-kill-switch.md` (qui explique comment **geler** en urgence). Cette page explique comment **dégeler** une tâche `blocked` avec marqueur `PANIC_FREEZE`, sans recréer le loop gel/dégel observé le 2026-06-09 sur le board sa-pipeline.
>
> **Source canonique sur disque** : `~/.hermes/shared/skills/devops/kanban-healthcheck/references/kanban-panic-unfreeze-2026-06-09.md`. Cette page gbrain en est le résumé searchable.

## 1. Quand dégeler

Une tâche reste en `blocked` + `PANIC_FREEZE` tant qu'un humain (ou un orchestrateur avec approbation explicite) n'a pas décidé que l'incident est résolu.

**3 conditions à vérifier avant toute tentative de dégel** :

1. La cause racine du burn est identifiée et corrigée (ex: scripts en loop, prompts récursifs, deps cassées, DB malformée).
2. Le kill-switch lui-même est désactivé / pause — sinon il re-gèlera la tâche à la milliseconde suivant le dégel.
3. Aucun worker / orchestrateur n'est actuellement en train de muter le board (sinon on reintroduit un race).

## 2. Procédure recommandée (read-then-write, JAMAIS en parallèle)

### Étape 1 — Pause du kill-switch

```bash
# Vérifier l'état du DISABLED file (option ceinture-bretelles)
test -f /home/ced/.hermes/sa-kanban-kill-switch.DISABLED && echo "DISABLED file present" || echo "DISABLED file absent"

# Vérifier l'état du job cron
jq '.jobs[] | select(.id=="8ff32c104208")' /home/ced/.hermes/shared/cron/jobs.json
```

**Note critique** : `hermes cron pause/resume` ne fonctionne PAS pour les jobs `no_agent: true` script-only (bug connu 2026-06-09). Workaround : éditer `jobs.json` directement.

### Étape 2 — Inspection pre-degel (read-only)

```bash
sqlite3 "file:/home/ced/.hermes/kanban/boards/sa-pipeline/kanban.db?mode=ro" \
  "SELECT id, status, substr(result,1,120), claim_lock, worker_pid, updated_at
     FROM tasks WHERE id='t_<id>'"
```

**Critères de go** :

- `worker_pid` mort depuis > 5 min = OK pour dégeler.
- `claim_lock` présent = ne PAS dégeler, le worker est en handoff.
- `result LIKE 'PANIC_FREEZE:%'` confirme l'origine du gel.

### Étape 3 — Dégel (2 options)

**Option A — Remettre en `ready` (re-spawn classique)** :

```bash
sqlite3 /home/ced/.hermes/kanban/boards/sa-pipeline/kanban.db <<SQL
UPDATE tasks
   SET status='ready',
       result = CASE WHEN result LIKE 'PANIC_FREEZE:%'
                     THEN 'UNFROZEN 2026-06-09: <brief reason>'
                     ELSE result END,
       claim_lock = NULL,
       worker_pid = NULL,
       updated_at = datetime('now')
 WHERE id='t_<id>';
SQL
```

**Option B — Remettre en `triage`** : **uniquement** si `auto_decompose` est désactivé sur le board. Sinon le triage re-crée un spawn frais dans la minute et on retombe dans le loop.

### Étape 4 — Vérification post-degel

- `hermes kanban list --board sa-pipeline --status ready` doit montrer la tâche.
- Le prochain tick du codex-lane worker (ou `hermes kanban dispatch`) doit la clamer dans 2-5 min.
- **Si elle re-reçoit `PANIC_FREEZE` au tick suivant** : la cause racine n'est pas résolue. Stop. Investiguer.

## 3. Rollback des patches kill-switch (2026-06-09)

Si un patch structurel a cassé un comportement désiré, voici les artefacts de rollback :

| Composant | Backup | Commande de rollback |
|---|---|---|
| Cron job B (schedule 1m→15m) | `~/.hermes/cron/jobs.json.bak-b-schedule-20260609-080709` | `cp <bak> ~/.hermes/shared/cron/jobs.json` |
| Patch E (no-op freeze_tasks) | `~/.hermes/cron/sa_kanban_kill_switch.py.bak-ce-20260609-081004` | `cp <bak> ~/.hermes/shared/scripts/sa_kanban_kill_switch.py` |
| Pause initiale du kill-switch | `~/.hermes/cron/jobs.json.bak-disable-ks-20260609-080229` | `cp <bak> ~/.hermes/shared/cron/jobs.json` |
| Snapshots DB pre-loop | `~/.hermes/backups/sa-kanban-kill-switch/sa-pipeline-20260609-080215.db` (et 7 autres) | copier vers `kanban.db` si DB live corrompue |

## 4. Pièges connus (post-mortem 2026-06-09)

| # | Piège | Solution |
|---|---|---|
| 1 | `DISABLED file` ≠ job cron désactivé. Le fichier DISABLED rend le script inerte mais le job continue de notifier. | Désactiver aussi dans `jobs.json`. |
| 2 | `hermes cron list` cache les jobs no_agent script-only | Workaround : `jq '.jobs[] | select(.id=="…")'` |
| 3 | `freeze_tasks` n'est pas no-op naturel avant le patch E | Le patch E ajoute un `skip_clause` quand `result LIKE 'PANIC_FREEZE:%'`. |
| 4 | Le kill-switch n'agit que sur `SPAWNABLE` (`ready`, `todo`, `running`, `review`) | Pour dégeler, remettre en `ready` (jamais `triage` sauf si auto_decompose off). |
| 5 | `tb status` peut signaler "dispatcher dead" alors que c'est un cron en train de geler | Croiser avec le log kill-switch avant de conclure. |

## 5. Lié à

- `notes/incidents/2026-06-09-sa-pipeline-kill-switch-loop` — le post-mortem de l'incident qui a motivé ce runbook.
- `projects/sa-pipeline` — la board cible.
- Skill `ced/kanban-forensics` — l'audit read-only qui précède tout dégel.
- Skill `ced/kanban-healthcheck/references/kanban-panic-kill-switch.md` — l'opération inverse (gel).
- Skill `ced/kanban-healthcheck/references/kanban-panic-unfreeze-2026-06-09.md` — version longue sur disque, à consulter en mode offline.
- Skill `ced/cron-job-hardening` — règles no_agent/silent cron.
