# Carte technique performance du projet

## Etat du depot au debut de l'audit

Audit lance depuis `C:\Users\cedon\Documents\Codex\stock-analysis-pipeline`.

Le workspace est deja sale avant cette mission. Les zones modifiees/non suivies incluent notamment :

- PDF/deep-dive : `backend/earnings_deep_dive/*`, `scripts/generate_sample_earnings_pdf.py`, `scripts/validate_pdf_against_model.py`, `tests/test_*earnings*`, `reports/generated/*`.
- Frontend/deploiement : `frontend/.env.production`, `frontend/vite.config.js`, `frontend/dist-tailscale/`.
- Scripts de diagnostic temporaires : `_check_*.py`, `_cron_run*.py`, `_diag_render.py`, `_extract_log.py`, `scripts/tmp_emoji_font_probe.py`.

Cette mission performance ne doit pas confondre ses changements avec ces travaux deja presents.

## Stack

- Backend : Python, FastAPI, Pydantic v2, yfinance, Finnhub, httpx, ReportLab, WeasyPrint, OpenAI/Codex/Kimi selon providers.
- Frontend : React 18 + Vite.
- Tests : pytest.
- Stockage local : fichiers JSON/MD/PDF/XLSX sous `analyses/`, `batches/`, `reports/`, cache JSON sous `backend/.cache`, SQLite de logs sous `backend/logs/searches.db`.
- Base de donnees applicative : pas de DB metier centrale identifiee ; usage SQLite limite aux logs de recherche/admin.

## Modules backend principaux

| Zone | Responsabilite | Sensibilite performance |
|---|---|---|
| `backend/main.py` | API FastAPI, validation ticker/ISIN, batch, download ZIP, traduction, conversion PDF a la volee, endpoints admin | Demarrage/import, endpoints synchrones longs, scans `rglob`, ZIP en memoire, traduction et PDF dans le chemin utilisateur |
| `backend/orchestrator.py` | Analyse multi-ticker via `ThreadPoolExecutor` | Parallele par ticker limite a 4 workers, timeout tres long, annulation non cooperative |
| `backend/pipeline.py` | Pipeline complet ticker : donnees, SEC, management analysis, scoring, dossier, PDF, Excel, deep-dive | Chemin critique principal ; melange collecte reseau, I/O, rendu, LLM, fichiers |
| `backend/sources_collector.py` | Collecte Yahoo/Finnhub/TwelveData/EODHD/SEC/EDGAR, cache JSON | Appels reseau sequentiels, retries bloquants, cache fichier, yfinance lourd |
| `backend/transcript_finder.py` | Recherche transcripts via RapidAPI Seeking Alpha, Alpha Vantage, Motley Fool, public search, DuckDuckGo, Google | Fallbacks sequentiels ; potentiel fort de latence reseau ; ecriture JSON |
| `backend/earnings_deep_dive/*` | Schema, prompts, generation IA, mapping, rendu PDF ReportLab, validation | Imports lourds, rendu PDF, validation, parsing schema |
| `backend/async_dossier.py` | Statut dossier et generation background legacy | Threads daemon non persistants, scan disque, duplication partielle avec `pipeline.py` |
| `backend/pdf_generator.py` | Conversion Markdown/TXT vers PDF generique | Appels multiples depuis API/download/pipeline |
| `frontend/src/*` | UI analyse, batch, cartes, download, polling status | Polling regulier, timeout client tres long, download gate cote UI |

## Flux principaux

### Analyse immediate

1. `POST /api/analyze` dans `backend/main.py`.
2. Normalisation ticker/ISIN.
3. `asyncio.to_thread(run_analysis_parallel, tickers)`.
4. `backend/orchestrator.py` lance `analyze_ticker_fast` en pool de threads.
5. `backend/pipeline.py` collecte donnees, extrait SEC, appelle Codex/Kimi, score, ecrit dossier, genere PDF/Excel/deep-dive.
6. Reponse JSON allegee pour le frontend.

Observation : le nom `analyze_ticker_fast` est trompeur. Le code genere maintenant beaucoup d'artefacts synchrones apres le scoring.

### Download dossier

1. `GET /api/dossier/{ticker}/download`.
2. Verifie le statut via `async_dossier.get_dossier_status`.
3. Si pas pret, relance `analyze_ticker`.
4. Si langue `jp`, copie le dossier en temp et traduit plusieurs fichiers.
5. Convertit MD/TXT en PDF a la volee.
6. Scanne le dossier et construit un ZIP en memoire.

Observation : le download peut declencher analyse, traduction, conversion PDF et compression ZIP dans une seule requete HTTP.

### Batch

1. `POST /api/batch/analyze` cree un job disque.
2. `GET /api/batch/{job_id}/status` declenche le traitement si le job est pending.
3. Le status endpoint attend `run_analysis_parallel`.

Observation : le polling status peut devenir un endpoint de travail long et bloquant cote requete.

### Deep-dive earnings

1. `pipeline._add_earnings_deep_dive_if_transcript`.
2. `transcript_finder.find_transcripts`.
3. Metrics depuis yfinance/EDGAR.
4. `generate_deep_dive`.
5. `build_earnings_deep_dive_report`.
6. `render_earnings_deep_dive_pdf`.
7. Validation deep-dive.

Observation : recherche transcript, generation IA, mapping et rendu sont dans le chemin de generation dossier.

## Caches existants

- `_ticker_cache` en memoire dans `main.py` pour validation ticker, TTL 30 minutes.
- `backend/.cache/{TICKER}.json`, TTL 1h, versionne.
- `backend/.cache/{TICKER}_yf.json`, TTL 10 minutes, alimente par cron.
- `_batch_jobs` en memoire + persistance JSON sous `batches/`.
- `_dossier_registry` en memoire dans `async_dossier.py`, toujours revalide par scan disque.
- Pas de cache explicite pour resolution CIK SEC, imports PDF/fonts, conversion MD vers PDF, resultat de traduction, ni transcript source par ticker au-dela des fichiers ecrits.

## Zones sensibles performance identifiees

- Demarrage/import backend : import de `backend.main` mesure a 10,769 s.
- Imports PDF/deep-dive : `cProfile` montre 1,75 s d'import dans un script PDF de 2,1 s.
- Chemin `analyze_ticker_fast` : collecte reseau, SEC, Codex/Kimi, PDF, Excel et deep-dive synchrones.
- Download dossier : traduction, conversion PDF et ZIP dans la requete utilisateur.
- Transcript finder : plusieurs providers/fallbacks potentiellement sequentiels.
- Scans `rglob` sur `analyses/` : 741 fichiers et 45 dossiers d'analyse locaux au moment de la mesure.
- Tests integration : un groupe a depasse 184 s et a ete tue par timeout.

