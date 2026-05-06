# API Wrapper Integration Pattern

Pattern for integrating an external Python tool/library into an existing FastAPI + React project.

## Use Case

You have an existing tool (CLI, Python library, ML model) and want to expose it
as an API consumed by your web frontend and/or mobile app. The tool may be slow
(5-10 min per call) so async processing with caching is essential.

## Real Example (hedge-fund-local → AlphaRadar)

- **Tool**: hedge-fund-local (22 AI investor agents analyzing stocks, LangChain/LangGraph)
- **Consumer**: AlphaRadar Web (FastAPI + React)
- **Result**: "AI Verdict" column in asset table with BUY🟢/SELL🔴/HOLD🟡 badges
- **Mobile**: Same API reached via Tailscale VPN

## Architecture

```
External Tool (Python lib)
    │
    ▼
API Wrapper (FastAPI, new port)
  ├─ POST /api/analyze → runs tool, returns structured result
  ├─ GET /api/health → health check
  └─ In-memory cache (TTL-based)
    │
    ▼
Main Backend (FastAPI)
  ├─ GET /api/verdict/{id} → calls wrapper, caches result
  └─ POST /api/verdict/batch → queues multiple analyses
    │
    ▼
Frontend (React)
  ├─ "Analyze" button per item → triggers API call
  ├─ Verdict badge (color-coded) + confidence %
  └─ Score adjustment: base_score × (1 + api_result.score_impact)
```

## Implementation Checklist

- [ ] **API Wrapper** (`api_server.py`):
  - [ ] FastAPI on dedicated port (7875 in example)
  - [ ] POST endpoint wrapping the tool's main function
  - [ ] Response model (Pydantic) with verdict, confidence, score_impact
  - [ ] In-memory cache: dict with TTL (3600s recommended)
  - [ ] Health endpoint for reachability check
  - [ ] `.env.example` for required API keys

- [ ] **Main Backend Integration** (`routes/new_route.py`):
  - [ ] New router with GET `/api/verdict/{id}` endpoint
  - [ ] Health check before calling wrapper (graceful degradation)
  - [ ] Cache on the backend side too (belt-and-suspenders)
  - [ ] Long timeout (600s) for slow tools
  - [ ] Register router in `main.py`

- [ ] **Frontend Integration**:
  - [ ] New state for verdicts: `{id: {verdict, confidence, score_impact}}`
  - [ ] "Analyze" button per item → `handleAnalyze(id)` function
  - [ ] Verdict badge component (emoji + text + tooltip with details)
  - [ ] Loading state while analysis runs
  - [ ] Score display: original + AI-adjusted with delta

- [ ] **Score Impact** (if applicable):
  - [ ] Modify scoring function: `score × (1 + score_impact)` clamped [0, 100]
  - [ ] Score impact formula: `direction × confidence × max_adjustment`
    - BUY → positive, SELL → negative, HOLD → 0
    - max_adjustment = 0.20 (±20%)

- [ ] **Mobile Access** (if needed):
  - [ ] Tailscale VPN (free, encrypted, no port forwarding)
  - [ ] Both devices on same tailnet
  - [ ] Mobile calls `http://<tailscale-ip>:<port>/api/...`

## Pitfalls

- **NTFS + WSL**: `poetry install` / `pip install` can be very slow. Use venv in WSL native path if possible. Timeout generously.
- **LangChain imports**: 10-15s on NTFS. Don't import in health checks — keep those lightweight.
- **22+ agents = 5-10 min**: Cache aggressively. Don't block the UI. Show loading state.
- **API key exhaustion**: 22 agents × 1 LLM call each = 22 API calls per analysis. Budget accordingly.
- **Port conflicts**: Choose a dedicated port far from existing services. Document it.
