# Stock Analysis Pipeline — Claude Code Reference

> Facts below re-verified against the tree on 2026-08-10.

## Quick Start
- **Repo**: `/home/ced/codex-projects/stock-analysis-pipeline/`
- **Backend**: FastAPI on port 8780, `backend.main:app`
- **Frontend**: React/Vite, built to `frontend/dist/`, served by the backend
- **Branch**: `kanban/spec-fonctionnelle-sa`
- **Prod**: self-hosted, Cloudflare Tunnel → see `DEPLOY.md`

## Commands
```bash
cd /home/ced/codex-projects/stock-analysis-pipeline

# Tests — root .venv, NOT backend/.venv
.venv/bin/python -m pytest tests/ backend/tests/ -q     # full run, ~33 min
.venv/bin/python -m pytest tests/spec_v27_*.py -q       # pre-render validator
# NOTE: pytest-timeout is not installed — passing --timeout= aborts the run.

# Run backend locally
PYTHONPATH=. .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8780

# Frontend: build IS the deploy (backend serves dist/ off disk)
cd frontend && npm run build     # injects VITE_API_URL + base=/stock-analysis/
node src/components/*.test.cjs   # static guard tests, one file each

# Restart prod backend (systemd --user unit, Restart=always — never pkill)
systemctl --user restart stock-pipeline.service
curl -s localhost:8780/api/health
```

## Architecture
```
backend/
├── main.py                  # FastAPI app, all routes, _require_auth
├── pipeline.py              # Analysis pipeline (EN + JP)
├── orchestrator.py          # Parallel multi-ticker runs
├── async_dossier.py         # Dossier phase state machine (incl. PDF_BLOCKED)
├── transcript_finder.py     # Transcript sourcing + 24h same-day cache
├── seeking_alpha_access.py  # Cookie/HAR management
├── company_overview.py      # Company Overview synthesis
├── feedback_store.py        # Client feedback (analyses/feedback_<BUCKET>/)
├── storage_paths.py         # Canonical analyses root (SA_ANALYSES_DIR)
└── earnings_deep_dive/
    ├── prompts.py           # LLM prompts
    ├── markdown.py          # Post-processing
    ├── mapper.py            # Data → report model
    ├── pre_render_validator.py, validators.py, deep_dive_validator.py
    └── pdf_renderer.py      # PDF generation

frontend/src/
├── App.jsx                  # Hash routing: #admin, #feedback, 404
├── api.js                   # Shared URL/fetch helpers
└── components/
    ├── AnalysisCard.jsx     # Main analysis view
    ├── ChatWidget.jsx       # Nami chat (mounted globally by App)
    ├── FeedbackPage.jsx     # Public #feedback — submit only, no history
    ├── AdminPage.jsx        # #admin — feedback viewer, needs admin key
    └── *.test.cjs           # Static source guards, run with plain node

tests/
├── conftest.py              # autouse: neutralizes the transcript disk cache
├── spec_v27_*.py            # Validator rule tests
└── test_*.py                # API / PDF / contract tests
```

## Key Conventions
- Backend `.env` is in **project root**, not `backend/`
- Post-process markdown before PDF rendering
- Validator: errors = data integrity, warnings = content quality
- Transcript order: SA cookies → StockAnalysis → web discovery (slow, last)
- Chat widget: session-scoped, ticker-based, "I" not "we"
- Codex skip is controlled by `SA_COMPANY_OVERVIEW_SKIP_CODEX` (default
  `false`). `SA_SKIP_CODEX` survives only in a comment — **no code reads it**.

## Navigation Tools Available
- **CodeGraph**: `.codegraph/` is indexed here — `codegraph_explore` returns
  linked symbols' source in one call instead of a grep+Read loop
- **Serena**: symbol-level edits
- **Wiki**: `/home/ced/codex-projects/docs/llm-wiki/projects/stock-analysis-pipeline.md`
- **GBrain**: `gbrain query "stock analysis"` — semantic search

## Pitfalls
1. `post_process_markdown()` cleans .md files but PDF renderer uses raw sections — apply cleanup in pipeline.py BEFORE `build_earnings_deep_dive_report()`
2. `asyncio.run()` cannot be called from a running event loop — use `await`
3. yfinance normalizes keys to snake_case — raw Yahoo data in `_raw_info`
4. Patch tool fails on backslash-heavy Python (prompts.py) — use a heredoc script
5. Frontend build must be verified via browser, not just curl
6. **`/api/health` lies about `commit`** — it re-reads git per request, so it
   reports HEAD even when uvicorn is running older code. Compare the process
   start time to the commit date instead (`DEPLOY.md`).
7. **Two venvs**: `.venv/` (tests) and `backend/.venv/` (the prod service).
   Both carry pytest and uvicorn, so mixing them fails silently.
8. `_require_auth` has **no** loopback/host/Origin bypass — the tunnel
   terminates on localhost, so any bypass would make every protected route
   public. The static bundle never embeds `CED_CONTROL_KEY`; `#admin` prompts
   for it and keeps it in `sessionStorage`.
9. Tests must not read the live `analyses/` root. The transcript 24h cache did,
   which made results depend on whether an analysis had run that day —
   `tests/conftest.py` neutralizes it by default.
