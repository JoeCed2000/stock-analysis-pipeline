# Cross-Model Audit — Case Study: stock-analysis-pipeline (2026-05-05)

## Contexte

Audit de sécurité et qualité complet du projet `stock-analysis-pipeline` (FastAPI + React/Vite, ~8,000 lignes, déployé Render + Vercel).

## Méthode

1. **Hermes (DeepSeek V4 Pro)** : audit solo → 18 findings P0-P3
2. **Codex (GPT-5.5)** via `codex-second-opinion` : challenge de l'audit Hermes

## Résultats comparés

### Findings identifiés par les deux modèles (confirmés)
- CORS `allow_origins=["*"]`
- Debug endpoint `/api/debug/yf-cache` non protégé
- `_ticker_exists()` toujours True (validation désactivée)
- `_score_management_realtime` hardcode du français
- `run_analysis_parallel` = stub non fonctionnel
- `_batch_jobs` dict en mémoire volatile
- Duplication `analyze_ticker` / `analyze_ticker_fast`
- `getConvictionLevel()` JA cassé

### Hermes a trouvé, Codex a confirmé
- `os.environ.setdefault()` → Codex a rétrogradé de P0 à P2 (comportement voulu sur Render)
- `DONNÉE NON DISPONIBLE` en français → Codex a noté qu'AGENTS.md l'exige
- `GEMINI_API` hardcodé → Codex a noté que c'est du code mort (P3, pas P2)

### Codex a trouvé, Hermes avait complètement raté (P0)

| # | Bug | Sévérité | Description |
|---|-----|----------|-------------|
| 1 | Exposition publique massive | 🔴 P0 | 6 endpoints servent les dossiers/sources/reports sans auth : `/api/report`, `/api/sources`, `/api/traceability`, `/api/analyses`, `/api/analyze/{t}/download`, `/api/dossier/{t}/download` |
| 2 | Mutation destructive GET | 🔴 P0 | `GET /dossier/{t}/download?lang=ja` écrase les fichiers originaux via `translate_file()` — un téléchargement JA corrompt le dossier pour les téléchargements EN |
| 3 | Triple bug justesse financière | 🔴 P0 | (a) TwelveData `percent_change` (variation prix) → `revenue_yoy_growth` (croissance CA), (b) EUR conversion `amount_usd * rate` au lieu de `/ rate`, (c) `guidance_official` Finnhub pas converti en décimal |
| 4 | Fast-path sans traçabilité | 🟠 P1 | `analyze_ticker_fast` définit `sources_manifest_path` mais ne génère jamais le fichier |

## Analyse

**Pattern :** Hermes (DeepSeek) a excellé sur les patterns de surface visibles dans le code (CORS, duplication, i18n, debug). Codex (GPT-5.5) a trouvé les problèmes structurels nécessitant de raisonner sur le comportement global du système (flux de données, side effects, intégrité, exposition).

**Implication :** Un audit single-model est structurellement incomplet. Chaque modèle a des angles morts différents. La combinaison des deux couvre un spectre plus large.

## Leçon

> **Ne jamais reviewer avec le même modèle que le codeur. Le second modèle ne confirme pas — il challenge et trouve ce que le premier a raté.**
