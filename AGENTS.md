# AGENTS.md — Stock Analysis Pipeline

## 0. Double-Porte : Wiki & CodeGraph — NON NÉGOCIABLE

Avant toute tâche, recherche ou modification de code, tu dois obligatoirement traverser la **Double-Porte** pour économiser les tokens, respecter l'architecture et éliminer le gâchis d'exploration.

### 🚪 Porte 1 (Haut Niveau) : Le Wiki d'abord
Consulter la mémoire consolidée du projet avant de chercher ou coder. Interdit de redécouvrir ce qui est déjà documenté.
1. **Consulter la page du projet** dans `Codex/docs/llm-wiki/projects/stock-analysis-pipeline.md`.
2. Comprendre l'architecture en 30 secondes, les invariants métier, les contrats de confiance et les playbooks de non-régression ("Quand modifier X, lancer Y").
3. **Tout agent (Hermes, Codex, OpenClaw, ChatGPT, worker Kanban) doit lire le wiki en premier.**

### 🚪 Porte 2 (Bas Niveau) : CodeGraph d'abord
Une fois orienté par le Wiki, interdit d'utiliser des boucles de commandes `grep`, `rg` ou `find` aveugles pour explorer les symboles et dépendances syntaxiques. Tu devez interroger le graphe de connaissance local via les outils MCP de **CodeGraph** :
- **Trouver un symbole ou sa définition :** `codegraph_search` (retourne le type, l'emplacement et la signature en un seul appel, plus rapide et précis que grep).
- **Tracer les dépendances de fonctions :** `codegraph_callers` (qui appelle cette fonction ?) et `codegraph_callees` (qu'est-ce que cette fonction appelle ?).
- **Analyse d'impact avant modif :** `codegraph_impact` (qu'est-ce qui va casser si je modifie ce fichier ?).
- **Obtenir le contexte d'une tâche :** `codegraph_context "<tâche>"` (analyse l'AST et te sort le code source exact des points d'entrée et symboles connectés en 500ms).
- **Règle d'or de lecture :** Utilise `codegraph_explore` pour lire le code de plusieurs symboles liés d'un coup, plutôt que d'enchaîner des `read_file` répétés qui saturent la fenêtre de contexte.

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
