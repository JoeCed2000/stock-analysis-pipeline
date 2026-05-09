# Prompt ChatGPT — Revue de parité PDF Earnings Deep-Dive vs Spécification Nami

## Contexte
Je développe un pipeline automatisé d'analyse financière (Python/FastAPI) qui génère des PDF "Earnings Deep-Dive" pour des actions US. Le modèle cible est un template Nami (startup finance Tokyo).
Tu es mon reviewer externe. Ta mission : comparer le PDF généré contre le JSON de spécification extrait du PDF modèle Nami.

## Fichiers fournis
1. **`modele_expected_chatgpt.json`** — Extraction du PDF modèle Nami (la spec canonique). Structure : `verification_report` + `original_extracted_json` contenant ~10 sections avec tableaux, analyses, métriques.
2. **`generated_pdf_extracted.json`** — Extraction texte du PDF généré par mon pipeline pour AAPL (5 pages, 10 sections).
3. **`earnings_deep_dive.pdf`** — Le PDF généré (pour inspection visuelle : polices, couleurs, alignement, emojis, tofu □).

## Règles absolues
- **Toute valeur doit être sourcée** (yfinance, Finnhub, SEC). Pas d'invention.
- **Zéro "DATA NOT AVAILABLE"** — cette phrase exacte est interdite.
- **Zéro "?" dans les cellules de tableaux** — toute cellule doit contenir une valeur réelle ou "Not available" (minuscule, anglais).
- **Zéro artefact markdown** (::, >>, ^^, !!, **, []) dans le PDF final.
- **Zéro tofu □** — tous les caractères doivent render correctement (emojis via police Symbola).
- **Zéro fuite de prompts LLM** dans le PDF final.
- **Toutes les 10 sections obligatoires** doivent être présentes.
- **Langue de surface** : anglais uniquement (pas de japonais, pas de français).

## Sections obligatoires (dans l'ordre)
1. 📊 EPS & Revenue — Tableau : Metric, Estimate, Actual, vs Estimate, YoY Change, Source
2. 🌟 ⚠️ Highlights & Lowlights — Tableau : Type, Number, Point, Evidence, Investor implication, Severity
3. 🧠 Operating Metrics — Tableau dédié
4. 💵 Cash Flow — Tableau dédié
5. 🏦 Capital Efficiency — Tableau : Metric, Value, YoY, vs Industry, Assessment
6. 🧩 Segments — Tableau segments d'activité
7. 📈 Forward P/E — Analyse + verdict
8. 📦 Backlog — Tableau backlog
9. 🔭 Guidance — Tableau guidance
10. 🎯 Verdict / Overall Assessment — Note sur 10 + BUY/HOLD/SELL + conviction + risques

## Questions pour ta review

### 1. Parité structurelle (champ par champ, chiffre par chiffre)
Compare chaque section, chaque tableau, chaque métrique. Mets en gras tout ce qui diverge.

Format :
```
✅ PRESENT — "EPS & Revenue" — complet, 2 rows
❌ MANQUANT — "Capital Efficiency" colonne "vs Industry" absente
⚠️ DIVERGE — "Verdict" : spec attend "Severity: High/Medium/Low", généré a "Impact: Élevé"
```

### 2. Qualité des données
- Les chiffres EPS, Revenue, marges, FCF, PE, ROE, backlog, guidance sont-ils réalistes pour AAPL Q1 2026 ?
- Y a-t-il des incohérences entre sections (ex: EPS différent entre Highlights et EPS & Revenue) ?
- Les sources sont-elles traçables ?

### 3. Qualité visuelle (inspecte le PDF)
- Polices : propres, pas de mix bizarre ?
- Couleurs : cohérentes avec un rapport financier professionnel ?
- Emojis : rendus correctement (monochromes, pas de tofu) ?
- Alignement : tableaux alignés, pas de débordement ?
- Le PDF est-il "présentable à un analyste financier" ?

### 4. Synthèse
- Note globale sur 10
- Top 3 problèmes à corriger en priorité
- Le pipeline est-il "production-ready" ou encore "beta" ?
