# Stock Analysis Pipeline — Deployment Guide

## Architecture
- **Frontend:** React + Vite → Vercel (free)
- **Backend:** FastAPI → Render (free, 750h/month)

## 1. Deploy Backend to Render

### Option A: One-click (render.yaml)
1. Fork/push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your repo — Render detects `render.yaml` automatically
4. Set environment variables:
   - `ALPHA_VANTAGE_API_KEY` — from https://alphavantage.co (free, 25 req/day)
   - `FINNHUB_API_KEY` — from https://finnhub.io (free tier)
5. Deploy — note the URL (e.g. `https://stock-analysis-api.onrender.com`)

### Option B: Manual
1. Render → New Web Service
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `cd backend && PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Set env vars as above

**⚠️ Render free tier sleeps after 15 min of inactivity. First request wakes it (~30s cold start).**

## 2. Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) → Import Project
2. Set root directory to `frontend/`
3. Framework preset: Vite (auto-detected)
4. Set environment variable:
   - `VITE_API_URL` = `https://stock-analysis-api.onrender.com/api` (your Render URL)
5. Deploy — note the URL (e.g. `https://stock-analysis.vercel.app`)

### Manual (Vercel CLI)
```bash
cd frontend
npx vercel --prod \
  -e VITE_API_URL=https://stock-analysis-api.onrender.com/api
```

## 3. Local Development
```bash
# Backend
cd backend && PYTHONPATH=.. uvicorn main:app --host 0.0.0.0 --port 8780

# Frontend (auto-proxies /api to localhost:8780)
cd frontend && npm run dev -- --host 0.0.0.0 --port 5180
```

## Limitations (Free Tier)
- Alpha Vantage: 25 API calls/day (transcripts)
- Finnhub: 60 API calls/min (financial data)
- Render: 750h/month, sleeps after 15min idle
- Vercel: 100 GB bandwidth/month
