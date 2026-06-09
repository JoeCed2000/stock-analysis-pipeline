# Transcript Source Label/URL Mismatch — Root Cause Fix (2026-06-05)

## Symptôme observé

Analyse NVDA du 09/06/2026 (exemple concret) :
- `analyses/2026-06-09_062806_NVDA_NVIDIA_Corp/04_transcripts_and_management/transcript_sources_NVDA.json` :
  - `source = "StockAnalysis"` ✅
  - `url = https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/` ✅
- `analyses/2026-06-09_062806_NVDA_NVIDIA_Corp/07_final_report/earnings_deep_dive_meta.json` :
  - `transcript.source = "Seeking Alpha"` ❌ (label inventé)
  - `transcript.url = https://stockanalysis.com/stocks/nvda/transcripts/568907-q1-2027/` (URL réelle)
- PDF rendu → **lien cliquable "Seeking Alpha" → atterrit sur stockanalysis.com** (incohérence auditable)

## Root cause architecturale

Le fix précédent (`ab37b86 fix: match source label to actual fetch method`) avait corrigé
`backend/transcript_finder.py` ligne 182-187 (mapping URL → label dans le module de fetch),
mais **3 autres endroits** continuaient de hardcoder `"stockanalysis.com": "Seeking Alpha"`
dans des domain_maps utilisés au moment du rendu PDF :

1. `backend/stockanalysis.py:87` — search_transcripts() retourne `source: "Seeking Alpha"`
2. `backend/stockanalysis.py:166` — fetch_transcript() retourne `source: "Seeking Alpha" if sa_url else "StockAnalysis"` (le `sa_url` était rarement truthy)
3. `backend/earnings_deep_dive/generator.py:503-504` — domain_map dans `_build_transcript_response`
4. `backend/earnings_deep_dive/mapper.py:2551-2552` — DOMAIN_NAMES dans `_build_pdf_sources`

Conséquence : même quand `transcript_finder.py` retournait `source="StockAnalysis"` dans le
`transcript_sources_NVDA.json` brut, le mapper / generator re-mappait l'URL et écrasait
le label avec `"Seeking Alpha"`.

De plus, `requirements.txt` ne déclarait pas `patchright`, ce qui en cas de réinstall
fresh du venv aurait fait crasher silencieusement le bloc SA direct (try/except).

## Fix appliqué (commit en cours)

5 fichiers patchés, 17/17 tests passent :

| Fichier | Changement |
|---------|------------|
| `backend/stockanalysis.py` | search/fetch retournent `"Seeking Alpha via StockAnalysis"` au lieu de `"Seeking Alpha"` |
| `backend/earnings_deep_dive/generator.py` | `domain_map["stockanalysis.com"]` → `"Seeking Alpha via StockAnalysis"` |
| `backend/earnings_deep_dive/mapper.py` | `DOMAIN_NAMES["stockanalysis.com"]` → `"Seeking Alpha via StockAnalysis"` |
| `requirements.txt` | Ajout `patchright>=1.60.0` |
| `tests/test_pipeline_transcript_url.py` | Fix test pré-existant (2100/2600 vs nouveau 1.2x tie-break) |
| `tests/test_transcript_source_label.py` | Nouveau fichier : 5 tests régression |

## Règle Ced appliquée (source of truth)

> SA cookies/auth → "Seeking Alpha"
> SA direct via web search → "Seeking Alpha" (si URL = `/article/...`)
> StockAnalysis.com fallback → **"Seeking Alpha via StockAnalysis"**

Le label DOIT matcher l'URL réelle cliquable. L'audit trail du PDF doit permettre à
Nami/Ced de cliquer sur la source et d'atterrir sur la bonne page.

## Pourquoi "via StockAnalysis" et pas juste "StockAnalysis" ?

Cohérence historique : depuis mai 2026, on référence les transcripts comme « Seeking Alpha
content » (Nami les lit sur SA mentalement, même si techniquement on les fetch via
StockAnalysis). Le suffixe "via StockAnalysis" est la RFC 3986 bis du « fetched from X
which republishes Y ». Permet à l'analyste de :
1. Savoir que c'est une transcript SA (substantive content)
2. Savoir qu'on a fallback sur StockAnalysis (delivery channel)
3. Cliquer sur le bon lien (URL = stockanalysis.com)

## Tests de non-régression

```bash
cd /home/ced/codex-projects/stock-analysis-pipeline
backend/.venv/bin/python -m pytest tests/test_pipeline_transcript_url.py tests/test_transcript_source_label.py -v
# 17 passed in 3.36s
```

Couvrent :
- ✅ Aucun `domain_map` ne peut plus mapper `stockanalysis.com → "Seeking Alpha"` (test grep)
- ✅ `requirements.txt` contient `patchright`
- ✅ `stockanalysis.search_transcripts()` retourne `source: "Seeking Alpha via StockAnalysis"`
- ✅ `stockanalysis.fetch_transcript()` retourne le bon label
- ✅ Tie-break `_best_transcript_source` : SA gagne sur comparable, StockAnalysis gagne sur 1.2x+

## Vérification end-to-end (à confirmer en browser)

1. Lancer analyse NVDA : `POST /api/analyze/async {"ticker":"NVDA","force_refresh":true}`
2. Attendre fin du job (`/api/analyze/job/{job_id}`)
3. Ouvrir PDF : `analyses/.../07_final_report/earnings_deep_dive.pdf`
4. Section "Sources" → le lien "Transcript" doit être cliquable, atterrir sur stockanalysis.com
5. Le label doit dire **"Seeking Alpha via StockAnalysis"** (pas "Seeking Alpha")

## Scope de la note

Couvre UNIQUEMENT le mismatch label/URL. Ne traite pas :
- Paywall SA vs full text — déjà géré via fallback StockAnalysis (MPW paywalled ~4K chars vs StockAnalysis 50K+)
- L'URL SA dans le PDF doit pointer vers un article concret (`/article/...`) — déjà géré par `_transcript_url`

## Dépendances opérationnelles (hors git, à recréer après rebuild WSL)

Le path SA direct via Patchright **fonctionne** (cf. e2e MSFT + NVDA plus bas). MAIS il dépend
de 2 éléments qui ne sont PAS dans le repo (`.env` gitignored, symlinks en `~/.cache/`) :

### 1. `.env` à la racine du projet
```
PLAYWRIGHT_BROWSERS_PATH=/home/ced/.hermes/profiles/codex-first/home/.cache/ms-playwright
```
Sans cette ligne, `p.chromium.launch()` cherche dans `/home/ced/.cache/ms-playwright` (le défaut
Patchright) et lève `Executable doesn't exist at /home/ced/.cache/ms-playwright/chromium-1223/...`.

### 2. Symlinks (le cache Patchright vit dans le profile home, pas le user home)
```bash
mkdir -p /home/ced/.cache/ms-playwright
ln -s /home/ced/.hermes/profiles/codex-first/home/.cache/ms-playwright/chromium-1223 \
      /home/ced/.cache/ms-playwright/chromium-1223
ln -s /home/ced/.hermes/profiles/codex-first/home/.cache/ms-playwright/chromium_headless_shell-1223 \
      /home/ced/.cache/ms-playwright/chromium_headless_shell-1223
```

### Pourquoi les deux ?
- `PLAYWRIGHT_BROWSERS_PATH` dans `.env` → `load_dotenv()` au démarrage de uvicorn → `os.environ`
  est setté → Patchright cherche au bon endroit pour le code Python.
- Les symlinks → belt-and-suspenders pour les sous-processus que Patchright fork (le binaire
  `chrome-linux64/chrome` lit parfois des chemins absolus hardcodés sur `~/.cache/ms-playwright/`).

### Vérification après rebuild
```bash
# 1. Le binaire résoud
test -f /home/ced/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome && echo OK
# 2. .env chargé
grep -q PLAYWRIGHT_BROWSERS_PATH /home/ced/codex-projects/stock-analysis-pipeline/.env && echo OK
# 3. Test e2e (60-90s, voir Codex Spark timeout pitfall)
curl -sX POST http://127.0.0.1:8780/api/analyze/async \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"MSFT","force_refresh":true}'
# Puis poll /api/analyze/job/{job_id} jusqu'à status=done
# Vérifier analyses/<date>_<time>_MSFT/04_transcripts_and_management/transcript_MSFT_*.txt
```

## Comportement actuel du SA primary path (juin 2026)

- Cookies valides (24 cookies + UA Chrome/136, fichier `.state/seeking_alpha_access.json` du 06/06)
- Patchright lance chromium sans PerimeterX (33 article links visibles)
- MAIS : pour NVDA/MSFT en ce moment, les articles SA visibles sont des **conferences** (Bank of
  America, TD Cowen), pas des earnings calls. Le filtre `_is_earnings_call_transcript_link` rejette
  correctement → fallback StockAnalysis s'active → label = "Seeking Alpha via StockAnalysis".
- Quand SA republiera un earnings call (typiquement 1-2 jours après la date du call), le path SA
  direct reprendra la priorité et le label sera "Seeking Alpha" + URL seekingalpha.com.

## Vérification e2e réalisée (2026-06-09)

| Ticker | Dossier | Transcript size | Source | URL | Match |
|---|---|---|---|---|---|
| MSFT | `2026-06-09_155257_MSFT_Microsoft_Corp` | 61243 bytes / 2463 lignes | `Seeking Alpha via StockAnalysis` | `stockanalysis.com/stocks/msft/transcripts/...` | ✅ |
| NVDA | `2026-06-09_143455_NVDA_NVIDIA_Corp` | 50202 bytes / 2475 lignes | `Seeking Alpha via StockAnalysis` | `stockanalysis.com/stocks/nvda/transcripts/...` | ✅ |
