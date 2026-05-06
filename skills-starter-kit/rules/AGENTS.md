# AGENTS.md — Contrat commun Hermes / Codex / agents

## Rôle

Ce fichier est lu automatiquement par Codex CLI (zero token cost).
Il définit les règles non négociables de sécurité, sandbox, Git et validation.

## 1. Sécurité — NON NÉGOCIABLE

- **Secrets** : jamais en ligne de commande, scripts (.sh, .bat, .ps1), ou fichiers commités.
- **.env + .gitignore** AVANT le premier commit. Toute fuite → `git filter-branch` + `gc --prune=now` + régénération immédiate.
- **Sandbox** : travailler uniquement dans le dossier projet. Pas de modif globale (Python, CUDA, npm global, Docker, PATH).
- **Pas de `sudo`**, pas de droit admin, pas de registre Windows.
- **Endpoint externe** (curl vers API cloud) → prévenir avant de lancer.

## 2. Qualité — NON NÉGOCIABLE

- **TDD** : pas de code sans test échouant d'abord. RED → GREEN → REFACTOR.
- **Backup** avant toute modif de config : `cp fichier.yaml fichier.yaml.bak`.
- **Pas de `replace_all=true`** sur du code — corrompt les fichiers.
- **Commit atomique** à chaque feature qui marche. Message descriptif.

## 3. Git — NON NÉGOCIABLE

- Avant commit : `git diff --staged --stat` obligatoire.
- Jamais `git add -A` sans vérifier le staging.
- Pas de commit de logs, .env, node_modules, ou fichiers binaires non voulus.
- Push si remote configuré. Le .git est la seule assurance contre les catastrophes.

## 4. Validation — NON NÉGOCIABLE

Une tâche n'est pas terminée sans preuve :
- Fichiers créés → `stat` ou `ls -la`
- Endpoints → `curl` et vérifier le status code
- Frontend → `browser_navigate` + `browser_console` (pas juste curl 200)
- Tests → lancés et passés, pas juste "ça devrait marcher"

## 5. Actions interdites

- Modifier des fichiers hors du projet
- Modifier la configuration globale de la machine
- Installer des paquets globalement (pip, npm, apt)
- Supprimer des fichiers hors projet
- Utiliser `ffplay`/`aplay`/sortie audio sans permission explicite
- Annoncer un succès sans vérification réelle

## 6. Comportement attendu

- Travailler depuis la racine du projet (`TARGET_PROJECT`)
- Préférer les outils et caches locaux au projet
- Logger les commandes importantes
- Donner un compte rendu honnête si une vérification n'a pas pu être faite
- Distinguer : `confirmé` / `hypothèse` / `non vérifié` / `échec`

## 7. Format de rapport final

1. Résumé des changements
2. Fichiers modifiés / créés
3. Commandes exécutées et résultats
4. Tests lancés
5. Points non vérifiés
6. Risques restants
