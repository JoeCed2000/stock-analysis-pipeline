# ADR-001 — Choix de la stack et architecture SA

| Métadonnée | Valeur |
|---|---|
| Statut | Accepté |
| Date | 2026-05-18 |
| Décideurs | Ced + Hermes |
| Domaine | Architecture |

## 1. Contexte

Stock Analysis Pipeline collecte, analyse et restitue des données financières pour un investisseur particulier. Le besoin est un pipeline fiable avec sortie PDF professionnelle, accessible via navigateur.

## 2. Décisions

### 2.1 Backend Python/FastAPI vs Java Spring Boot

**Choix : Python + FastAPI**

| Option | Avantages | Inconvénients |
|---|---|---|
| Python FastAPI | Écosystème data (yfinance, pandas, ReportLab, edgartools), async natif, itératif | Performance moindre, typage faible |
| Java Spring Boot | Typé, robuste production | Verbosité, écosystème data financière moins riche |

**Justification :** Pipeline data-intensive — les bindings Python pour yfinance, Finnhub, EDGAR et ReportLab sont plus matures. La performance n'est pas critique (1 ticker à la fois, batch ≤ 10).

### 2.2 Frontend React/Vite vs HTMX

**Choix : React + Vite**

| Option | Avantages | Inconvénients |
|---|---|---|
| React + Vite | UX riche (téléchargements, états), écosystème | Build step, dépendances |
| HTMX | Simple, pas de build | Limité pour interactions complexes multi-états |

**Justification :** L'interface gère téléchargements de fichiers, barres de progression multi-étapes, et états asynchrones (job polling). HTMX serait trop limitant.

### 2.3 PDF via ReportLab vs fpdf2

**Choix : ReportLab**

ReportLab offre contrôle précis du layout (tables, callout boxes, headers/footers, templates multi-pages). fpdf2 manque de support tableaux complexes et layout multi-colonnes. Le modele.pdf de référence utilise un layout ReportLab.

### 2.4 Cloudflare Tunnel vs Render/Vercel

**Choix : WSL local + Cloudflare Tunnel named**

| Option | Avantages | Inconvénients |
|---|---|---|
| Local + CF Tunnel | Latence nulle, pas de cold start, gratuit | Dépend WSL, pas de scaling |
| Render free tier | Pas de gestion infra | Cold start 30s après 15min sleep |
| Vercel (frontend only) | CDN rapide | Backend toujours nécessaire |

**Justification :** Usage personnel — la latence nulle et l'absence de cold start priment sur le scaling.

## 3. Conséquences

**Positives :**
- Stack unifiée Python backend
- Frontend React riche pour l'UX
- PDF pro-grade avec ReportLab
- Latence minimale (WSL + CF)

**Négatives :**
- Dépendance WSL (pas de containerisation)
- Cache-busting nécessaire (frontend buildé)
- Tunnel CF = point de défaillance unique (mitigé par auto-recovery)
- Pas de scaling horizontal (usage personnel OK)

## 4. Alternatives rejetées

| Option | Raison |
|---|---|
| Java Spring Boot | Écosystème data financière insuffisant |
| HTMX frontend | UX limitée (téléchargements, états) |
| fpdf2 | Contrôle layout insuffisant |
| Render.com | Cold start 30s (free tier) |
| Quick tunnel | Pas de domaine stable |
