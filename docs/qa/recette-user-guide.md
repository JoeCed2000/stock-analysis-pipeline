# SA Recette User Guide

## Lancer la recette

```bash
cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline

# Recette rapide (~1-2 min, sans analyse longue)
.venv/bin/pytest tests_e2e/ -v -k "not analysis_completes and not download_dossier"

# Recette complète (~5-10 min, inclut analyse NVDA + download ZIP)
.venv/bin/pytest tests_e2e/ -v

# Avec rapport HTML
.venv/bin/pytest tests_e2e/ -v --html=e2e/reports/latest/report.html --self-contained-html

# Avec capture des échecs
.venv/bin/pytest tests_e2e/ -v --screenshot only-on-failure --tracing retain-on-failure

# Test unique
.venv/bin/pytest tests_e2e/ -v -k "test_p0_home_loads"
```

## Structure

```
docs/qa/
  functional-map.md      — Cartographie des fonctionnalités
  uat-test-strategy.md   — Stratégie de test
  recette-user-guide.md  — Ce fichier

tests_e2e/
  conftest.py            — Config pytest + Playwright
  test_sa_recette.py     — 14 tests (P0 + P1 + états)

e2e/reports/latest/
  summary.md             — Rapport auto après chaque run
  report.html            — Rapport HTML Playwright
  screenshots/           — Captures des échecs
```

## Prérequis

```bash
# Une seule fois
.venv/bin/pip install playwright pytest pytest-playwright
.venv/bin/playwright install chromium

# Le serveur doit tourner
source COMMANDS.sh && sa-restart
```

## Interpréter les résultats

- **PASS** : tous les tests verts
- **PARTIAL** : certains tests échouent, bugs documentés
- **FAIL** : échecs critiques non résolus

## Ajouter un test

1. Identifier le parcours dans `docs/qa/functional-map.md`
2. Ajouter le test dans `tests_e2e/test_sa_recette.py`
3. Suivre le pattern : nom en `test_pX_description`, assertions `expect()`, pas de `sleep()`
4. Relancer la recette
