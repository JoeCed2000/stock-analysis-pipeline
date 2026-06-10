# Stock Analysis Pipeline — Claude Code Reference

## Quick Start
- **Repo**: `/home/ced/codex-projects/stock-analysis-pipeline/`
- **Backend**: FastAPI on port 8780
- **Frontend**: React/Vite, served from `dist/`
- **Branch**: `kanban/spec-fonctionnelle-sa`
- **Last commit**: `48a05a5` (June 9)

## Commands
```bash
cd /home/ced/codex-projects/stock-analysis-pipeline
source backend/.venv/bin/activate

# Run backend
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8780

# Run tests
pytest tests/ -x -q
pytest tests/spec_v27_*.py -q    # Pre-render validator tests
pytest tests/test_api_compatibility.py -q

# Build frontend
cd frontend && npm run build

# Check production
curl https://sa.cedlabusa.net/api/health
```

## Architecture
```
backend/
├── main.py              # FastAPI app
├── pipeline.py          # Analysis pipeline (EN + JP)
├── prompts.py           # LLM prompts
├── markdown.py          # Post-processing
├── validator.py         # Pre-render validation
├── renderer.py          # PDF generation
├── transcript_finder.py # Seeking Alpha access
├── seeking_alpha_access.py # Cookie/HAR management
└── feedback_store.py    # Client feedback

frontend/
├── src/components/      # React components
│   ├── AnalysisCard.jsx  # Main analysis view
│   ├── ChatWidget.jsx    # Nami chat
│   └── Feedback.jsx      # Client feedback
└── dist/                # Built assets

tests/
├── spec_v27_*.py        # Validator rule tests
├── test_api_*.py         # API tests
└── test_earnings_*.py    # PDF template tests
```

## Key Conventions (from WIKI.md + AGENTS.md)
- **SA_SKIP_CODEX=true** by default — skip Codex Spark for speed
- Backend `.env` is in **project root**, not `backend/`
- Post-process markdown before PDF rendering
- Validator: errors = data integrity, warnings = content quality
- Transcript source: SA via cookies → StockAnalysis fallback
- Chat widget: session-scoped, ticker-based, "I" not "we"

## Navigation Tools Available
- **CodeGraph**: `gbrain code_callers`, `code_callees`, `code_def` — structural analysis
- **Serena**: Symbol-level edits (if MCP is configured)
- **Wiki**: `/home/ced/codex-projects/docs/llm-wiki/projects/stock-analysis-pipeline.md`
- **GBrain**: `gbrain query "stock analysis"` — semantic search

## Pitfalls
1. `post_process_markdown()` cleans .md files but PDF renderer uses raw sections — apply cleanup in pipeline.py BEFORE build_earnings_deep_dive_report()
2. `asyncio.run()` cannot be called from a running event loop — use `await`
3. yfinance normalizes keys to snake_case — raw Yahoo data in `_raw_info`
4. Patch tool fails on backslash-heavy Python (prompts.py) — use heredoc Python script instead
5. Frontend build must be verified via browser, not just curl
