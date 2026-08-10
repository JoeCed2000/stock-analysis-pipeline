# Stock Analysis Pipeline — Deployment Guide

> Verified against the live system on 2026-08-10. The previous version of this
> file described a Vercel + Render deployment that was never the production
> setup; ignore any older copy.

## Architecture

Production is **self-hosted on Ced's WSL2 box**, exposed through a Cloudflare
Tunnel. There is no external PaaS in the path.

```
www.cedlabusa.net/stock-analysis/   (public)
sa.cedlabusa.net
            │
            ▼
  cloudflared-tunnel.service         systemd --user unit
            │
            ▼
  127.0.0.1:8780                     uvicorn backend.main:app
  stock-pipeline.service             systemd --user unit
            │
            ├── /api/*               FastAPI
            └── everything else      static files from frontend/dist/
```

Both units are **systemd `--user`** units, not system units. `systemctl
is-active stock-pipeline.service` answers `inactive` and is misleading — always
pass `--user`.

## Deploying the frontend

The backend serves `frontend/dist/` straight off disk, so a build **is** the
deploy. No publish step, no CDN invalidation.

```bash
cd frontend && npm run build
```

`npm run build` injects `VITE_API_URL=/stock-analysis/api`; `vite.config.js`
pins `base: '/stock-analysis/'`. Both matter — a plain `vite build` produces a
bundle that 404s in production.

Verify the deploy landed (the served bundle must be byte-identical to `dist/`):

```bash
curl -s https://www.cedlabusa.net/stock-analysis/ | grep -o 'assets/index-[^"]*\.js'
ls frontend/dist/assets/index-*.js
```

## Deploying the backend

Python changes require a restart — uvicorn runs without `--reload` in
production.

```bash
systemctl --user restart stock-pipeline.service
systemctl --user is-active stock-pipeline.service
curl -s localhost:8780/api/health
```

`ExecStart` is `~/.hermes/scripts/launch-stock-backend.sh`, which clears stale
`__pycache__`, exports `PYTHONPATH`, and runs `backend/.venv/bin/python3.12 -m
uvicorn backend.main:app --host 0.0.0.0 --port 8780`. The unit has
`Restart=always`, so never `pkill` the process — it comes straight back.

> `sa-backend.service` was disabled on 2026-06-12 (port conflict crash-loop).
> `stock-pipeline.service` is the canonical unit.

### ⚠️ `/api/health` does not prove what is running

`commit` in the health payload is recomputed per request from the checkout's
git state, so it reports the repo HEAD even when the running process loaded
older code. To know what is actually live, compare the process start time to
the commit time:

```bash
ps -eo pid,lstart,cmd | grep "[u]vicorn backend.main"
git log -1 --format='%h %ad' --date=local
```

If the process predates the commit, the code is **not** live. This is the
"stale runtime" trap recorded in `WIKI.md`.

## Local development

```bash
# Backend (repo root — the app is backend.main, not main)
PYTHONPATH=. .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8780

# Frontend — vite proxies /api to 127.0.0.1:8780, port 5180
cd frontend && npm run dev
```

## Two virtualenvs — not interchangeable by convention

| venv | Used for |
|---|---|
| `.venv/` (repo root) | tests — `.venv/bin/python -m pytest tests/ backend/tests/` (also what `npm run recette` calls) |
| `backend/.venv/` | the production service, via the launcher script |

Both currently carry pytest and uvicorn, so a mistake fails silently rather
than loudly. Keep tests on the root venv.

`pytest-timeout` is **not** installed: `--timeout=` aborts the whole run with
`unrecognized arguments`.

## Secrets

`CED_CONTROL_KEY` lives in the repo-root `.env` (not `backend/.env`) and gates
every protected route via `_require_auth`. It is never embedded in the frontend
bundle — the `#admin` page prompts for it and keeps it in `sessionStorage`.
`_require_auth` performs **no** loopback/host/Origin bypass: the tunnel
terminates on localhost, so any such bypass would make every protected route
public.

Downloads accept `?api_key=` as a fallback because an `<a href>` cannot carry
a header.
