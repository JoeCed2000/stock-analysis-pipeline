# AGENTS.md — Stock Analysis Pipeline

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
