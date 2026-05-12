# Spécification Fonctionnelle — Stock Analysis Pipeline

**Version :** 1.1  
**Date :** 2026-05-12  
**Nature :** Document de référence — spécification testable et auditable  
**Prédécesseur :** Architecture Plan v1 (docs/plans/architecture-plan.md, 2026-05-04)  
**Confidentiel —** 2026-05-12

---

## 1. Résumé

Stock Analysis Pipeline est une application web d'analyse financière automatisée produisant des rapports d'investissement action par action. Elle exécute un pipeline en 9 étapes par ticker — collecte de données financières, analyse des discours de direction, évaluation des risques, scoring quantitatif sur 40 points, et génération de rapports — avec traçabilité complète des sources. L'interface React affiche des fiches de décision (BUY / HOLD / SELL) et permet le téléchargement de dossiers de sources vérifiables au format ZIP, ainsi que des rapports d'analyse approfondie (earnings deep-dive) bilingues (EN/JP) au format PDF.

---

## 2. Problématique

L'investisseur particulier ou le gérant indépendant fait face à trois problèmes structurels :

1. **Asymétrie d'information** — Les analyses sell-side et les rapports de courtage sont orientés, tardifs, ou inaccessibles sans abonnement coûteux (Bloomberg, FactSet).
2. **Charge cognitive** — Croiser manuellement les données financières (Yahoo Finance), les rapports réglementaires (SEC EDGAR), les transcripts de conférences téléphoniques (Seeking Alpha), et les actualités de marché est ingérable pour plus de quelques tickers.
3. **Absence de traçabilité** — Une recommandation d'achat sans source vérifiable est inopposable. Sans dossier de sources, impossible d'auditer une décision d'investissement.

---

## 3. Proposition de valeur

Stock Analysis Pipeline résout ces problèmes en automatisant la chaîne complète — de la donnée brute à la décision tracée :

- **Pipeline automatisé** — 9 étapes exécutées séquentiellement par ticker, parallélisables.
- **Scoring objectif** — 8 critères pondérés produisant un score /40 et un verdict BUY / HOLD / SELL, reproductible.
- **Dossier de sources** — Chaque chiffre cité dans un rapport est relié à un document source horodaté et haché (SHA-256), stocké localement. Audit complet possible.
- **Deep-dive earnings** — Analyse qualitative des appels résultats avec contexte concurrentiel, valorisation, et résumé bilingue (anglais/japonais).
- **Zéro coût externe** — Utilise exclusivement des APIs publiques et gratuites (Yahoo Finance, SEC EDGAR, Finnhub free tier).

---

## 4. Périmètre et définitions

### 4.1 Acteurs

| Acteur | Rôle |
|--------|------|
| **Utilisateur principal** | Saisit des tickers, lit les rapports, télécharge les dossiers de sources |
| **Auditeur de sécurité** | Vérifie la traçabilité des affirmations via le dossier de sources |
| **Partie prenante externe** | Lit les rapports PDF produits (version investisseur) |

### 4.2 Dans le périmètre

- Analyse unitaire et par lot (batch) de tickers actions (US, Europe via suffixes .PA, .AS, etc.)
- 9 étapes de pipeline : identification → chiffres financiers → segments → discours management → risques officiels → valorisation → scoring → décision → sortie
- Scoring sur 8 critères (/40) avec verdict BUY / HOLD / SELL
- Dossier de sources complet (6 répertoires + manifest JSON + matrice de traçabilité CSV)
- Rapport earnings deep-dive (10 sections, bilingue EN/JP, PDF)
- Conversion automatique de tous les fichiers texte en PDF dans le dossier de sortie
- Recherche et récupération des transcripts de conférences téléphoniques
- Profil société et documents 8-K téléchargeables
- API REST documentée (21 endpoints)
- Interface React responsive (single-page app)
- Rate limiting et gate d'authentification admin

### 4.3 Hors périmètre

- Analyse technique (chartisme, indicateurs)
- Backtesting de portefeuille
- Données temps réel (streaming)
- Gestion de portefeuille
- Exécution d'ordres
- Indices, ETF, obligations, cryptomonnaies
- Comptes utilisateurs et authentification (sauf admin gate)

### 4.4 Définitions

| Terme | Définition |
|-------|-----------|
| **Ticker** | Symbole boursier (ex: AAPL, MC.PA). Format : 1-5 lettres majuscules, suffixe optionnel à 1-2 lettres. |
| **ISIN** | International Securities Identification Number — 12 caractères alphanumériques. Accepté en entrée et résolu vers un ticker. |
| **Pipeline** | Séquence des 9 étapes d'analyse exécutées par ticker. |
| **Deep-dive** | Analyse qualitative approfondie d'un appel résultats trimestriel (10 sections). |
| **Dossier de sources** | Arborescence de fichiers organisée en 7 répertoires contenant tous les documents sources, extractions, et le rapport final. |
| **Manifest** | Fichier JSON listant toutes les sources utilisées avec métadonnées (URL, date, fiabilité). |
| **Matrice de traçabilité** | Fichier CSV liant chaque affirmation du rapport à son document source. |
| **Scoring** | Notation quantitative sur 8 critères (0-5 chacun, total /40). |

---

## 5. Architecture fonctionnelle

### 5.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────┐
│  Frontend React + Vite (SPA)                    │
│  - Saisie tickers (individuel ou batch)         │
│  - Dashboard : cartes par ticker                │
│  - Rapports complets avec sources               │
│  - Téléchargement ZIP + PDF                     │
└──────────────────┬──────────────────────────────┘
                   │ HTTP (REST JSON)
┌──────────────────▼──────────────────────────────┐
│  FastAPI Backend                                │
│  - Orchestrateur d'analyse                      │
│  - Générateur de rapports                       │
│  - Convertisseur PDF                            │
│  - Rate limiter + Admin gate                    │
└──────────────────┬──────────────────────────────┘
                   │ APIs externes
     ┌─────────────┼─────────────┬──────────────┐
     ▼             ▼             ▼              ▼
  Yahoo        Finnhub       SEC EDGAR     Seeking Alpha
  Finance      (gratuit)     (public)      (transcripts)
```

### 5.2 Pipeline en 9 étapes

Chaque ticker est analysé en exécutant séquentiellement les 9 étapes ci-dessous. Les résultats intermédiaires sont stockés dans un répertoire horodaté sous `analyses/`.

| # | Étape | Sources | Livrable |
|---|-------|---------|----------|
| 1 | **Identification** | yfinance | Ticker validé, nom société, secteur, capitalisation, prix natif et EUR |
| 2 | **Chiffres financiers** | yfinance + Finnhub | CA, croissance YoY, marges brutes/opérationnelles, RN, FCF, dette nette, guidance |
| 3 | **Segments** | Finnhub + site entreprise | Segment principal, %CA, croissance segmentaire, dépendance excessive |
| 4 | **Discours management** | SEC EDGAR (dernier 10-K/10-Q) | Ton général, confiance, promesses concrètes, signaux défensifs |
| 5 | **Risques officiels** | SEC EDGAR (Risk Factors) | Concentration, cyclicité, supply chain, régulation — sévérité haute/moyenne/basse |
| 6 | **Valorisation** | yfinance | PE courant, PE forward, PEG, croissance attendue, marge de sécurité |
| 7 | **Scoring** | Calculé (données étapes 1-6) | 8 critères × 5 points = /40 |
| 8 | **Décision** | Règles de scoring | Verdict BUY / HOLD / SELL + niveau de conviction + phrase clé |
| 9 | **Sortie** | Généré | report.md + sources_manifest.json + claim_traceability_matrix.csv + PDFs |

### 5.3 Structure du dossier de sortie

```
analyses/{YYYY-MM-DD}_{TICKER}_{NOM}/
├── 01_official_company_sources/    # Site officiel, communiqués
├── 02_sec_or_regulatory_filings/   # 10-K, 10-Q, 8-K en PDF
├── 03_financial_data_sources/      # Données YF, Finnhub (JSON/XLSX)
├── 04_transcripts_and_management/  # Transcripts earnings calls
├── 05_market_and_context/          # Actualités, contexte marché
├── 06_extracted_data/
│   ├── extracted_financials.json
│   ├── extracted_risks.json
│   ├── extracted_management_quotes.json
│   ├── sources_manifest.json
│   └── claim_traceability_matrix.csv
├── 07_final_report/                # report.md + PDFs
│   └── earnings_deep_dive.pdf
├── en/                             # Miroir en anglais
│   └── 07_final_report/
└── jp/                             # Miroir en japonais
    └── 07_final_report/
```

---

## 6. Sources de données

### 6.1 Providers

| Provider | Type | Gratuit ? | Utilisé pour | Limites |
|----------|------|-----------|-------------|---------|
| **Yahoo Finance** (yfinance) | API non officielle | Oui | Cours, financiers, valorisation, segments, identification | Rate limit implicite, pas de SLA |
| **Finnhub** | API REST | Oui (60 req/min gratuit) | Profil société, actualités, segments | Free tier limité |
| **SEC EDGAR** | API publique | Oui | Filings 10-K, 10-Q, 8-K, risk factors | Données US uniquement |
| **Seeking Alpha** | Web scraping | Oui | Transcripts d'earnings calls | Accès non garanti, fallback nécessaire |
| **Site officiel entreprise** | HTTP | Oui | Profil, communiqués | Structure variable par société |
| **Recherche web** (fallback) | DuckDuckGo/Google | Oui | Transcripts non trouvés sur SA | Qualité variable |

### 6.2 Règles de sourcing

- **BR-SRC-01 :** Toute donnée financière doit être rattachée à un document source horodaté.
- **BR-SRC-02 :** Si une donnée est indisponible, le rapport doit indiquer « Not available » (jamais de donnée inventée).
- **BR-SRC-03 :** Chaque source est identifiée par un hash SHA-256 de son contenu pour vérification d'intégrité.
- **BR-SRC-04 :** Les données de marché (cours) sont horodatées à la seconde près et périment après 24h.

---

## 7. Modèle de scoring

### 7.1 Critères

Le scoring évalue chaque ticker sur 8 critères, chacun noté de 0 à 5 :

| # | Critère | Pondération | Ce qui est mesuré |
|---|---------|------------|-------------------|
| 1 | **Croissance** (growth) | /5 | Croissance du CA YoY, tendance sur 3 ans |
| 2 | **Rentabilité** (profitability) | /5 | Marge brute, marge opérationnelle, RN positif |
| 3 | **Solidité financière** (financial_strength) | /5 | Ratio d'endettement, FCF, couverture des intérêts |
| 4 | **Avantage concurrentiel** (moat) | /5 | Part de marché, barrières à l'entrée, pricing power |
| 5 | **Qualité du management** (management) | /5 | Ton, transparence, track record, guidance |
| 6 | **Risque de valorisation** (valuation_risk) | /5 | PE vs historique, PEG, marge de sécurité |
| 7 | **Risque géopolitique** (geopolitical_risk) | /5 | Exposition Chine, régulation, sanctions |
| 8 | **Momentum business** (business_momentum) | /5 | Catalyseurs court-terme, innovations, contrats |

### 7.2 Verdict

| Score total | Décision |
|-------------|----------|
| ≥ 32 | **BUY** |
| 26 – 31 | **HOLD / BUY ON PULLBACK** |
| 18 – 25 | **HOLD fragile** |
| ≤ 17 | **SELL or AVOID** |

### 7.3 Règles de scoring

- **BR-SCO-01 :** Le verdict est calculé automatiquement à partir du score total. Aucune intervention manuelle.
- **BR-SCO-02 :** Chaque critère doit être justifié par au moins une donnée tracée dans le sources_manifest.json.
- **BR-SCO-03 :** Le niveau de conviction (« Élevée », « Modérée », « Spéculative ») est déterminé par la complétude des données disponibles.

---

## 8. Interface utilisateur

### 8.1 Composants React

| Composant | Rôle |
|-----------|------|
| **TickerInput** | Saisie de tickers (champ texte, séparateur virgule), validation format, bouton « Analyser » |
| **AnalysisCard** | Carte par ticker : score /40, verdict coloré (vert BUY, orange HOLD, rouge SELL), KPIs (PE, marge, croissance) |
| **ReportView** | Rapport complet avec toutes les sections du pipeline, liens vers sources |
| **SourcesView** | Manifest des sources (tableau triable) |
| **BatchUpload** | Upload de fichier CSV/texte de tickers pour analyse par lot |
| **DeepDivePanel** | Interface de déclenchement et visualisation du deep-dive earnings |
| **DossierDownload** | Téléchargement ZIP du dossier de sources complet |
| **AdminPage** | Interface d'administration protégée (statistiques, cache, jobs) |
| **LanguageSelector** | Sélecteur de langue pour les rapports (EN / JP) |
| **StatusIndicator** | Indicateur de progression pour les analyses longues (polling) |

### 8.2 Parcours utilisateur principal

1. L'utilisateur saisit un ou plusieurs tickers (ex: « NVDA, MSFT, ASML »).
2. Il clique sur « Analyser ».
3. Le backend lance l'analyse (job asynchrone), retourne un `job_id`.
4. Le frontend affiche des indicateurs de progression via polling.
5. Une fois l'analyse terminée, les AnalysisCards apparaissent avec le score et le verdict.
6. L'utilisateur peut :
   - Cliquer sur une carte pour voir le rapport complet.
   - Télécharger le dossier de sources (ZIP).
   - Lancer un deep-dive earnings.
   - Télécharger le rapport deep-dive en PDF.

### 8.3 Règles d'interface

- **BR-UI-01 :** Le verdict doit être immédiatement visible (couleur + score).
- **BR-UI-02 :** Les données « Not available » sont affichées en grisé, jamais omises.
- **BR-UI-03 :** Les sources sont cliquables et ouvrent le document original dans un nouvel onglet.
- **BR-UI-04 :** L'interface est responsive (desktop prioritaire, mobile acceptable).

---

## 9. API REST

### 9.1 Liste des endpoints

| Méthode | Path | Rôle |
|---------|------|------|
| GET | `/api/health` | Healthcheck |
| POST | `/api/analyze` | Analyse unitaire (synchrone) |
| POST | `/api/analyze/async` | Analyse unitaire (asynchrone) |
| GET | `/api/analyze/job/{job_id}` | Statut d'un job asynchrone |
| GET | `/api/analyze/{ticker}/download` | Téléchargement ZIP du dossier |
| POST | `/api/batch/upload` | Upload fichier CSV de tickers |
| POST | `/api/batch/analyze` | Analyse batch (plusieurs tickers) |
| GET | `/api/batch/{job_id}/status` | Statut job batch |
| GET | `/api/batch/{job_id}/download` | Téléchargement ZIP batch |
| GET | `/api/report/{ticker}` | Rapport complet (JSON) |
| GET | `/api/report/{ticker}/pdf` | Rapport deep-dive PDF |
| GET | `/api/sources/{ticker}` | Manifest des sources (JSON) |
| GET | `/api/traceability/{ticker}` | Matrice de traçabilité (JSON) |
| GET | `/api/earnings/quarters/{ticker}` | Liste des trimestres avec transcripts |
| POST | `/api/earnings/deep-dive` | Génération deep-dive earnings |
| GET | `/api/dossier/{ticker}/status` | Statut de génération du dossier |
| GET | `/api/dossier/{ticker}/download` | Téléchargement ZIP du dossier |
| POST | `/api/dossier/{ticker}/upload` | Upload de documents complémentaires |
| GET | `/api/debug/yf-cache/{ticker}` | État du cache Yahoo Finance (debug) |
| GET | `/api/debug/sources` | Sources disponibles par ticker (debug) |
| GET | `/api/admin/*` | Endpoints d'administration (protégés par ADMIN_SECRET) |

### 9.2 Règles API

- **BR-API-01 :** Content-Type par défaut : `application/json`.
- **BR-API-02 :** Les erreurs sont retournées au format `{"detail": "message"}` avec le code HTTP approprié.
- **BR-API-03 :** Rate limiting : 30 req/min sur `/api/analyze`, 120 req/min sur les autres endpoints (par IP).
- **BR-API-04 :** Les endpoints d'administration (`/api/admin/*`) requièrent le header `X-Admin-Secret` ou le paramètre `admin_secret` correspondant à la variable `ADMIN_SECRET`.
- **BR-API-05 :** Timeout par défaut : 600s pour les endpoints synchrones, pas de timeout pour les endpoints asynchrones (polling).

### 9.3 Contrats de données

#### TickerRequest (POST /api/analyze)
```json
{
  "tickers": ["NVDA", "MSFT"],
  "deep_dive": false
}
```

#### AnalysisResult (réponse)
```json
{
  "ticker": "NVDA",
  "company_name": "NVIDIA Corporation",
  "price_native": 950.50,
  "price_eur": 875.30,
  "currency": "USD",
  "market_cap": 2350000000000,
  "sector": "Technology",
  "financials": { "revenue_quarterly": 26044000000, "revenue_yoy_growth": 262.0, "gross_margin": 78.4, "operating_margin": 65.0, "net_income": 14881000000, "free_cash_flow": 14500000000, "net_debt": -10000000000 },
  "scoring": { "growth": 5, "profitability": 5, "financial_strength": 4, "moat": 5, "management": 4, "valuation_risk": 3, "geopolitical_risk": 3, "business_momentum": 5 },
  "decision": "BUY",
  "conviction": "Élevée"
}
```

---

## 10. Modules complémentaires

### 10.1 Earnings Deep-Dive

Analyse qualitative approfondie d'un appel résultats trimestriel, structurée en 10 sections :

1. 📊 **EPS & Revenue Summary** — Tableau Estimation vs Réel vs Écart vs YoY
2. 🌟 **Highlights & Lowlights** — Points positifs (numérotés, chiffrés) et points de vigilance (sévérité)
3. 🧠 **Operating Metrics** — Tableau revenus, marges, OpEx, résultat net
4. 💰 **Cash Flow** — OCF, CapEx, FCF avec analyse de soutenabilité
5. 🎯 **Capital Efficiency** — ROE, ROTCE, ROA, ROIC
6. 🧩 **Segments** — Par produit et zone géographique
7. 📈 **Forward P/E** — Contexte secteur, historique 5 ans
8. 📦 **Backlog Quality** — Conditionnel, si applicable
9. 🔮 **Guidance** — Projections T+1 avec analyse QoQ
10. 🏆 **Verdict** — Forces/Faiblesses/Opportunités/Risques, thèse d'investissement

Chaque section inclut une question en anglais et japonais, une réponse structurée, et un résumé en une ligne (一言まとめ). Les rapports sont générés en PDF bilingue (EN + JP).

### 10.2 Profil société

Génération automatique d'un profil société incluant : description, secteur, site web, page relations investisseurs, logo. Intégré en étape préalable du pipeline.

### 10.3 Conversion PDF universelle

Tout fichier `.md` ou `.txt` dans le dossier de sortie est automatiquement converti en PDF via le renderer générique fpdf2, sauf exclusion explicite (README.md, earnings_deep_dive.md déjà traité).

---

## 11. Exigences non fonctionnelles

### 11.1 Performance

- **NFR-PERF-01 :** L'analyse unitaire (1 ticker, sans deep-dive) doit s'exécuter en moins de 60 secondes.
- **NFR-PERF-02 :** L'analyse batch (5 tickers, sans deep-dive) doit s'exécuter en moins de 5 minutes.
- **NFR-PERF-03 :** La génération deep-dive (1 ticker, bilingue) doit s'exécuter en moins de 3 minutes.
- **NFR-PERF-04 :** Le cache Yahoo Finance a une TTL de 30 minutes pour les données de marché.

### 11.2 Disponibilité

- **NFR-DISP-01 :** L'application est conçue pour un déploiement local (WSL/Windows) avec exposition via tunnel (Cloudflare/ngrok).
- **NFR-DISP-02 :** Aucune dépendance à un service cloud payant. Toutes les APIs externes ont un fallback.

### 11.3 Sécurité

- **NFR-SEC-01 :** Tous les secrets (clés API, tokens) sont stockés dans `.env`, hors versionnement Git.
- **NFR-SEC-02 :** CORS est restreint aux origines autorisées (localhost, tunnel de production).
- **NFR-SEC-03 :** Rate limiting par IP prévient les abus sur les endpoints coûteux.
- **NFR-SEC-04 :** Les endpoints d'administration sont protégés par secret partagé (`ADMIN_SECRET`).

### 11.4 Maintenabilité

- **NFR-MAINT-01 :** Le code est structuré en modules indépendants (pipeline, scoring, sources, rendering).
- **NFR-MAINT-02 :** Les tests (pytest) couvrent a minima le pipeline, le scoring, et les modèles.
- **NFR-MAINT-03 :** Les commits sont atomiques avec messages descriptifs.

---

## 12. Parties prenantes

| Rôle | Responsabilité | Contact |
|------|---------------|---------|
| **Utilisateur principal** | Définition des besoins, validation des rapports, utilisation quotidienne | — |
| **Auditeur de sécurité** | Vérification de la traçabilité, audit des sources | — |
| **Partie prenante externe** | Lecture des rapports PDF, décision d'investissement | — |
| **Mainteneur technique** | Développement, déploiement, maintenance | — |

---

## 13. Registre des risques

| ID | Risque | Probabilité | Impact | Mitigation |
|----|--------|------------|--------|-----------|
| **R01** | API Yahoo Finance devient inaccessible (rate limit, blocage) | Moyenne | Élevé | Fallback Finnhub + cache local persistant |
| **R02** | SEC EDGAR change son API ou impose des quotas | Faible | Élevé | Fallback via Finnhub filings |
| **R03** | Transcript Seeking Alpha non disponible (paywall) | Moyenne | Moyen | Fallback recherche web + site officiel |
| **R04** | Coût tokens LLM élevé pour deep-dive (si fournisseur externe) | Moyenne | Moyen | Utilisation prioritaire de Codex/GPT-5.5 inclus dans abonnement existant |
| **R05** | Données financières erronées ou périmées (cache stale) | Moyenne | Élevé | TTL cache 30min, horodatage, hash SHA-256 |
| **R06** | Hallucination LLM dans les rapports (données inventées) | Moyenne | Critique | Règle anti-invention, traçabilité SHA-256, « Not available » explicite |
| **R07** | Corruption du cache disque (NTFS/WSL) | Faible | Moyen | Hash SHA-256 vérifiable, purge cache simple |
| **R08** | Tunnel Cloudflare/ngrok instable (coupure réseau) | Faible | Faible | Fonctionne en local sans tunnel ; fallback ngrok si Cloudflare down |

---

## 14. Observabilité et audit

### 14.1 Logging

- **OBS-LOG-01 :** Logging structuré avec rotation horaire (fichiers dans `backend/logs/`).
- **OBS-LOG-02 :** Chaque étape du pipeline émet un log au niveau INFO avec le ticker et la durée.
- **OBS-LOG-03 :** Les erreurs sont loggées avec traceback complet. Pas de `except: pass` silencieux.
- **OBS-LOG-04 :** L'endpoint `/api/health` retourne l'état du service et des APIs externes.

### 14.2 Métriques

- **OBS-MET-01 :** Nombre de tickers analysés par session.
- **OBS-MET-02 :** Taux de succès/échec par étape du pipeline.
- **OBS-MET-03 :** Temps d'exécution moyen par ticker.
- **OBS-MET-04 :** Taux de complétude des données (ratio champs renseignés).

### 14.3 Traçabilité

- **OBS-TRC-01 :** Chaque rapport inclut un `sources_manifest.json` listant toutes les sources utilisées.
- **OBS-TRC-02 :** Chaque affirmation chiffrée est liée à un document source via `claim_traceability_matrix.csv`.
- **OBS-TRC-03 :** Les documents sources sont hachés (SHA-256) pour détecter toute altération.
- **OBS-TRC-04 :** L'endpoint `/api/traceability/{ticker}` expose la matrice complète en JSON.

---

## 15. Politique de confidentialité

Ce pipeline utilise des fournisseurs LLM externes pour la génération de rapports (deep-dive earnings, analyse qualitative). Les règles suivantes s'appliquent :

- **PR-01 :** Aucune donnée personnelle utilisateur n'est transmise aux LLM. Seuls les tickers (identifiants publics) et les données financières publiques sont envoyés.
- **PR-02 :** Les clés API des fournisseurs LLM sont stockées exclusivement dans `.env`, hors versionnement.
- **PR-03 :** Les rapports générés sont stockés localement dans `analyses/`. Aucune donnée n'est exfiltrée vers un serveur tiers.
- **PR-04 :** Les transcripts d'earnings calls sont des documents publics (SEC EDGAR, Seeking Alpha). Leur traitement par LLM ne constitue pas une fuite de données.
- **PR-05 :** Le cache local (`.cache/`) contient des données financières publiques. Il peut être purgé sans perte de données utilisateur.
- **PR-06 :** Aucun cookie, tracker, ou mécanisme de profilage n'est présent dans l'interface web.
- **PR-07 :** Le tunnel Cloudflare/ngrok est utilisé uniquement pour l'accès distant. Aucune donnée n'est stockée sur les serveurs de tunnel.

---

## 16. Rétention et restauration

### 16.1 Rétention

- **RET-01 :** Les analyses sont conservées indéfiniment dans `analyses/` tant que l'espace disque le permet.
- **RET-02 :** Le cache Yahoo Finance (`.cache/`) a une TTL de 30 minutes. Les entrées expirées peuvent être supprimées manuellement.
- **RET-03 :** Les jobs batch persistés (`batches/`) survivent aux redémarrages du service.

### 16.2 Restauration

| Scénario de panne | Procédure de restauration |
|-------------------|--------------------------|
| **Cache corrompu** | `rm -rf backend/.cache/*` — le cache se reconstruit automatiquement |
| **Analyse interrompue** | Relancer l'analyse — le répertoire horodaté est écrasé |
| **Job batch perdu (redémarrage)** | Le job est rechargé depuis `batches/{job_id}.json` |
| **Fichier .env corrompu** | Restaurer depuis `.env.example` et re-renseigner les clés API |
| **Dossier de sources incomplet** | Relancer l'analyse — toutes les sources sont re-téléchargées |
| **Déploiement tunnel cassé** | Redémarrer le tunnel (Cloudflare : `cloudflared tunnel run`, ngrok : `ngrok http 8780`) |

---

## 17. Glossaire

| Terme | Définition |
|-------|-----------|
| **10-K** | Rapport annuel déposé auprès de la SEC (États-Unis) |
| **10-Q** | Rapport trimestriel déposé auprès de la SEC |
| **8-K** | Déclaration d'événement significatif auprès de la SEC |
| **BUY / HOLD / SELL** | Verdict d'investissement : acheter / conserver / vendre |
| **CapEx** | Capital Expenditures — dépenses d'investissement |
| **Cloudflare Tunnel** | Service de tunneling TCP pour exposer un service local via un domaine |
| **Deep-dive** | Analyse qualitative approfondie d'un appel résultats |
| **EBITDA** | Earnings Before Interest, Taxes, Depreciation, and Amortization |
| **EDGAR** | Electronic Data Gathering, Analysis, and Retrieval — base de données publique de la SEC |
| **EPS** | Earnings Per Share — bénéfice par action |
| **FCF** | Free Cash Flow — flux de trésorerie disponible |
| **Finnhub** | Fournisseur de données financières (API REST, free tier 60 req/min) |
| **ISIN** | International Securities Identification Number |
| **Manifest** | Fichier JSON listant les sources utilisées avec métadonnées |
| **ngrok** | Service de tunneling TCP pour exposer un service local |
| **OCF** | Operating Cash Flow — flux de trésorerie d'exploitation |
| **PEG** | Price/Earnings to Growth — ratio PE divisé par la croissance attendue |
| **Pipeline** | Séquence des 9 étapes d'analyse |
| **ROE** | Return on Equity — rendement des capitaux propres |
| **ROIC** | Return on Invested Capital — rendement du capital investi |
| **SEC** | Securities and Exchange Commission — régulateur financier américain |
| **Seeking Alpha** | Plateforme de contenu financier incluant les transcripts d'earnings calls |
| **Ticker** | Symbole boursier identifiant une action |
| **Tunnel** | Connexion réseau exposant un service local sur internet |
| **一言まとめ (hitokoto matome)** | Résumé en une phrase, obligatoire à la fin de chaque section du deep-dive |
| **yfinance** | Bibliothèque Python non officielle pour accéder aux données Yahoo Finance |

---

*Fin du document — Version 1.1 — 2026-05-12*
