# AGENTS.md — Stock Analysis Pipeline

## 0. Double-Porte : Wiki & CodeGraph — NON NÉGOCIABLE

Avant toute tâche, recherche ou modification de code, tu dois obligatoirement traverser la **Double-Porte** pour économiser les tokens, respecter l'architecture et éliminer le gâchis d'exploration.

### 🚪 Porte 1 (Haut Niveau) : Le Wiki d'abord
Consulter la mémoire consolidée du projet avant de chercher ou coder. Interdit de redécouvrir ce qui est déjà documenté.
1. **Consulter la page du projet** dans `Codex/docs/llm-wiki/projects/stock-analysis-pipeline.md`.
2. Comprendre l'architecture en 30 secondes, les invariants métier, les contrats de confiance et les playbooks de non-régression ("Quand modifier X, lancer Y").
3. **Tout agent (Hermes, Codex, OpenClaw, ChatGPT, worker Kanban) doit lire le wiki en premier.**

### 🚪 Porte 2 (Bas Niveau) : Exploration rapide du code
Une fois orienté par le Wiki, privilégie les outils rapides et déterministes pour explorer le code :

1. **`tb rg "<pattern>"`** — ripgrep instantané (remplace `grep -r`). Plus rapide que `search_files`.
2. **`tb find "<glob>"`** — trouver des fichiers par motif.
3. **`tb cat <path>`** — lire un fichier rapidement (alternative légère à `read_file`).
4. **`search_files`** — recherche Hermes avec regex et filtrage par glob.
5. **`codegraph <project>`** — génère un graphe de dépendances (HTML/CSV) pour visualiser l'architecture du projet. Utile avant un refactor ou pour comprendre les dépendances entre modules.

**Règle :** ne pas enchaîner les `read_file` sur des fichiers entiers. Utiliser `tb section` pour lire une portion ciblée, `tb rg` pour trouver un symbole, et `codegraph` pour la vue d'ensemble architecturale.

---

## 1. Sécurité — NON NÉGOCIABLE
- Secrets dans .env uniquement. .env dans .gitignore AVANT premier commit.
- Pas de sudo, pas de droits admin, pas de registre Windows.
- Endpoint externe → prévenir avant curl/API.
- Sandbox : travailler uniquement dans `stock-analysis-pipeline/`.

## 2. Qualité — NON NÉGOCIABLE
- TDD : pas de code sans test échouant d'abord. RED → GREEN → REFACTOR.
- Backup avant modif de config : `cp fichier fichier.bak`.
- Pas de replace_all=true sur du code.
- Commit atomique à chaque feature qui marche.

## 3. Git — NON NÉGOCIABLE
- `git diff --staged --stat` avant chaque commit.
- Jamais `git add -A` sans vérifier le staging.
- Pas de commit de logs, .env, node_modules, analyses/, ou binaires.

## 4. Validation — NON NÉGOCIABLE
- Fichiers créés → `stat` ou `ls -la`
- Endpoints → `curl` et vérifier le status code
- Frontend → `browser_navigate` + `browser_console`
- Tests → lancés et passés

## 5. Stack
- Backend: Python 3.11+ FastAPI, yfinance, finnhub-python
- Frontend: React + Vite
- Tests: pytest, pytest-asyncio

## 6. Règle anti-invention
Toute donnée financière doit être sourcée. Si une donnée manque → "DONNÉE NON DISPONIBLE".
Les conclusions doivent être auditables à partir du dossier de sources.
