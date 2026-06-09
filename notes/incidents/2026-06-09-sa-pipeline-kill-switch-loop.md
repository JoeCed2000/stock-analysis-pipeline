---
type: note
title: Incident sa-pipeline — Kill-Switch self-bloating loop (2026-06-09)
date: '2026-06-09T00:00:00.000Z'
status: resolved
projects:
  - projects/sa-pipeline
  - projects/ced-kanban-orchestrator
severity: medium
duration_min: 90
related_pages:
  - notes/howto/kanban-panic-unfreeze-2026-06-09
ingested_via: 'mcp:put_page'
ingested_at: '2026-06-09T06:23:15.684Z'
source_kind: 'mcp:put_page'
tags:
  - cron
  - incident
  - kanban
  - kill-switch
  - sa-pipeline
  - self-bloating
  - token-burn
---

# Incident sa-pipeline — Kill-Switch self-bloating loop (2026-06-09)

## 1. TL;DR

Le job cron `8ff32c104208` (kill-switch `sa_kanban_kill_switch.py`) et la codex-lane du board `sa-pipeline` entraient dans une **boucle gel/dégel toutes les ~64s** sur la tâche `t_b3d9a3bc` ("Triage PDF access bug feedback"). Chaque tick du kill-switch :

1. (re-)gelait la tâche en `status=blocked` + appendait une ligne `PANIC_FREEZE: …` à son `result`,
2. sauvegardait un clone 4 MB de `kanban.db` dans `~/.hermes/backups/sa-kanban-kill-switch/`,
3. émettait une notification Telegram.

La codex-lane re-clâmait et re-promouvait la tâche en `ready` ~53s plus tard, le kill-switch la re-gelait 53s après, et ainsi de suite. **Résultat** : 60+ notifs Telegram/heure, `result` passé de 0 → 76+ lignes de `PANIC_FREEZE`, et 552 MB de backups DB (139 fichiers × 4 MB).

## 2. Timeline (UTC)

| Heure UTC | Événement |
|---|---|
| 04:40 | Création de la tâche `t_b3d9a3bc` "Triage PDF access bug feedback" |
| 04:40–07:30 | Codex-lane claim+promote / kill-switch freeze, ~64s de cycle |
| 06:48 | Le compteur `repeat.completed` du job cron atteint 4715 |
| ~06:50 | **tb status** rapporte le dispatcher dead 57 min (faux positif — c'était le kill-switch qui gelait tout) |
| 07:10 | **Lecture seule forensics** démarrée (DB `mode=ro`, `sqlite3.connect(uri=True)`) |
| 07:25 | Identification du loop (cross-référencé 65 events `promoted` ↔ 64 ticks kill-switch) |
| 07:48 | Rapport forensique livré à l'utilisateur, 7 options A-G proposées |
| 07:49 | **Action immédiate** : désactivation du job cron `8ff32c104208` dans `~/.hermes/shared/cron/jobs.json` (enabled=false, state=paused). **Stop net du spam Telegram.** |
| 08:07 | **Fix B** : schedule 1m → 15m |
| 08:10 | **Fix E** : patch no-op `freeze_tasks` (skip_clause si result déjà marqué) |
| 08:11 | **Fix D** : cleanup 131 backups obsolètes, 520 MB libérés |
| 08:11 | **Fix F** : doc `kanban-panic-unfreeze-2026-06-09.md` créée |
| 08:13 | Vérification post-fix intégrale : tous les patches actifs, t_b3d9a3bc repassée en `ready` (codex lane a re-spawn naturellement), aucun worker_pid vivant. |

## 3. Diagnostic forensique

### 3.1 Pattern topologique

```
                 ┌──────────────────────────────────┐
                 │                                  │
                 ▼                                  │
   codex-lane worker                                 │
   ┌──────────────────┐                              │
   │ claim t_b3d9a3bc │                              │
   │ status=ready     │                              │
   │ work in progress │                              │
   │ promote (t+0)    │─────────┐                    │
   │ status=ready     │         │                    │
   └──────────────────┘         │                    │
                                ▼                    │
                  kill-switch (every 1m)             │
                  ┌──────────────────────┐            │
                  │ freeze_tasks:        │            │
                  │   status = blocked   │            │
                  │   append PANIC_FREEZE│            │
                  │   backup DB (4 MB)   │            │
                  │   notify Telegram    │            │
                  └──────────────────────┘            │
                                │                    │
                                │ (53s plus tard)    │
                                └────────────────────┘
```

### 3.2 Évidence SQLite (lecture seule)

- 65 events `promoted` sur `t_b3d9a3bc` entre 04:40 et 07:48 UTC.
- 64 ticks kill-switch dans le même intervalle, gap de **−53s** constant (kill-switch 53s APRÈS chaque promote).
- Tous les ticks récents : `process_count=0`, `killed_pids=[]`. **Aucun worker n'a jamais dépassé le stade "claim".**
- Le `result` de `t_b3d9a3bc` contenait 76+ occurrences de `PANIC_FREEZE:` à 07:48 UTC.

### 3.3 Cause racine

**Le script `freeze_tasks` n'était pas idempotent.** Le `result` était appendé à chaque tick même quand la tâche venait d'être re-gelée, et aucun mécanisme n'empêchait la codex-lane de re-clâmer la tâche. C'est un **self-reinforcing loop** par mutations successives, pas un crash-loop.

**Cause secondaire** : `hermes cron pause/resume` ne fonctionne PAS pour les jobs `no_agent: true` script-only. Cause présumée : filtrage CLI sur un champ LLM-spécifique. Workaround obligatoire : édition directe de `~/.hermes/shared/cron/jobs.json`.

## 4. Fixes appliqués

| ID | Fix | Fichier | Effet |
|---|---|---|---|
| (urgent) | Kill-switch désactivé (job cron) | `~/.hermes/shared/cron/jobs.json` | Stop net du spam Telegram |
| B | Schedule `every 1m` → `every 15m` | `~/.hermes/shared/cron/jobs.json` (job 8ff32c104208) | Quand on réactivera, le pire cas passe de 60 ticks/h à 4 ticks/h |
| E | `freeze_tasks` no-op sur tâches déjà gelées | `~/.hermes/shared/scripts/sa_kanban_kill_switch.py` | Stoppe le self-bloating, économise les backups DB |
| D | Cleanup 131 backups obsolètes (520 MB libérés) | `~/.hermes/backups/sa-kanban-kill-switch/` | De 552 MB à 32 MB. 8 fichiers gardés : 5 datés (1/jour) + 3 nommés `before-archive-*` |
| F | Procédure de dégel documentée | `~/.hermes/shared/skills/devops/kanban-healthcheck/references/kanban-panic-unfreeze-2026-06-09.md` | Couvre le gap exact qu'on a rencontré |

### 4.1 Code du patch E (freeze_tasks)

```python
def freeze_tasks(con: sqlite3.Connection) -> int:
    cols = table_columns(con, "tasks")
    # E (anti self-bloating, 2026-06-09): if a task is already frozen by a prior
    # kill-switch tick, do NOT re-append the PANIC_FREEZE line.
    frozen_marker = "PANIC_FREEZE:"
    placeholders = ",".join("?" for _ in sorted(SPAWNABLE))
    skip_clause = ""
    if "result" in cols:
        skip_clause = f" AND NOT (status='{FREEZE_STATUS}' AND result LIKE '{frozen_marker}%')"
    assignments = [f"status='{FREEZE_STATUS}'"]
    if "result" in cols:
        assignments.append(
            f"result=CASE WHEN result LIKE '{frozen_marker}%' THEN result "
            f"ELSE COALESCE(result || '\n', '') || 'PANIC_FREEZE: frozen by SA kill-switch; manual review required before retry' END"
        )
    # ... (unchanged)
    q = "UPDATE tasks SET {} WHERE status IN ({}){}".format(
        ", ".join(assignments), placeholders, skip_clause
    )
```

Le test in-vitro sur clone de la DB confirme : le 2e freeze sur une tâche `ready` (après un reset simulant une re-promote) ne fait plus croître le `result`.

## 5. Décisions NON prises (et pourquoi)

| Option | Pas appliqué | Raison |
|---|---|---|
| C. `FREEZE_STATUS` 'blocked' → 'triage' | ✅ Conservé `blocked` | Le commentaire L36 du script dit explicitement "never triage: auto-decompose may re-spawn triaged tasks". Choix conscient des devs originaux, je ne contredis pas sans comprendre la cause racine. |
| A. Touch `DISABLED` file | ✅ Pas appliqué | Redondant avec la désactivation du job cron. À ajouter en ceinture-bretelles si on veut. |
| Patch du bug CLI `hermes cron pause` | ✅ Out of scope | Le CLI est buggé pour les jobs `no_agent`. C'est un bug hermes-cli, pas un bug kill-switch. À ouvrir comme ticket séparé. |

## 6. Rollback (si les patches cassent un comportement voulu)

| Composant | Fichier de backup | Commande de rollback |
|---|---|---|
| Cron job 8ff32c104208 (B) | `~/.hermes/cron/jobs.json.bak-b-schedule-20260609-080709` | `cp <bak> ~/.hermes/shared/cron/jobs.json` + restart scheduler |
| Patch E sur `sa_kanban_kill_switch.py` | `~/.hermes/cron/sa_kanban_kill_switch.py.bak-ce-20260609-081004` | `cp <bak> ~/.hermes/shared/scripts/sa_kanban_kill_switch.py` |
| Backup du `jobs.json` avant pause KS | `~/.hermes/cron/jobs.json.bak-disable-ks-20260609-080229` | `cp <bak> ~/.hermes/shared/cron/jobs.json` |
| Snapshots DB pre-loop | `~/.hermes/backups/sa-kanban-kill-switch/sa-pipeline-20260609-080215.db` (et 7 autres) | copier vers `kanban.db` si DB live corrompue |

## 7. Pièges découverts (à propager)

1. **DISABLED file ≠ job cron désactivé.** Le fichier DISABLED rend le script inerte, mais le job cron `no_agent` continue de tourner et d'envoyer des notifs. Pour stopper les notifs : éditer `jobs.json` directement.
2. **`hermes cron list` cache les jobs no_agent script-only.** Cause présumée : filtrage CLI sur champ LLM-spécifique. Workaround : `jq '.jobs[] | select(.id=="8ff32c104208")' ~/.hermes/shared/cron/jobs.json`.
3. **`freeze_tasks` n'est pas un no-op naturel** par défaut — d'où le besoin du patch E.
4. **Le kill-switch ne gèle que les statuts `SPAWNABLE`** (`ready`, `todo`, `running`, `review`). Une tâche en `triage` ou `blocked` est ignorée.
5. **`tb status` peut signaler un "dispatcher dead"** alors que c'est un job cron en train de tout geler. Toujours croiser avec le log du kill-switch avant de conclure.

## 8. Commandes de vérification

```bash
# Vérifier que le kill-switch est bien off
jq '.jobs[] | select(.id=="8ff32c104208")' ~/.hermes/shared/cron/jobs.json

# Vérifier que le patch E est en place
grep -c "frozen_marker\|skip_clause" ~/.hermes/shared/scripts/sa_kanban_kill_switch.py
# attendu: ≥ 2

# Vérifier la doc de dégel
ls -l ~/.hermes/shared/skills/devops/kanban-healthcheck/references/kanban-panic-unfreeze-2026-06-09.md

# Vérifier le cleanup disque
du -sh ~/.hermes/backups/sa-kanban-kill-switch/
# attendu: ~32 MB (était 552 MB)

# Vérifier l'état de t_b3d9a3bc
sqlite3 "file:/home/ced/.hermes/kanban/boards/sa-pipeline/kanban.db?mode=ro" \
  "SELECT id, status, claim_lock, worker_pid FROM tasks WHERE id='t_b3d9a3bc'"
```

## 9. Lié à

- `notes/howto/kanban-panic-unfreeze-2026-06-09` — procédure de dégel (page sœur).
- `projects/sa-pipeline` — la board touchée.
- Skill `ced/kanban-forensics` (chargée pour cet audit).
- Skill `ced/kanban-healthcheck/references/kanban-panic-kill-switch.md` — doc parente, explique le gel.
- Skill `ced/kanban-healthcheck/references/kanban-panic-unfreeze-2026-06-09.md` — le dégel (cette page la résume).
- Skill `ced/cron-job-hardening` — règles no_agent/silent cron.
