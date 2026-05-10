# Audit pdf.pdf vs modele.pdf — Rapport complet

**Date :** 2026-05-10  
**Audité par :** Hermes (DeepSeek V4 Pro) + inspection visuelle  
**Fichiers :**
- Référence : `docs/specs/modele.pdf` (14 pages, 421 KB)
- Généré : `pdf.pdf` (11 pages, 217 KB)
- Entreprise cible du PDF généré : NVIDIA Corporation (NVDA), Q2 2026

---

## 1. Résumé exécutif

### Verdict global
**Le PDF généré n'est PAS proche du modèle attendu.** Il existe des écarts structurels, linguistiques, et surtout des **contradictions de données critiques** qui rendent le rapport trompeur pour un investisseur.

### Bloquants principaux
1. 🔴 **Contradictions de données** : EPS ($1.76 vs $1.62), Net Income ($43.0B vs $120.1B), Revenue ($68.1B vs $215.94B) — mélange trimestriel/annuel
2. 🔴 **Sources inexistantes** : "Company filing / Calculated" utilisé 35 fois sans aucun lien vers un filing réel
3. 🔴 **Documents manquants** : Press Release N/A, Earning Call Presentation N/A — sans recherche de fallback
4. 🔴 **Pas de sortie japonaise** — le modèle exige un rapport bilingue EN+JP, le PDF généré est 100% anglais
5. 🔴 **Segments : chiffres annuels mélangés avec trimestriels** — Data Center $193.7B dans un rapport trimestriel de $68.1B

### Top 5 priorités
| Priorité | Problème | Impact |
|----------|----------|--------|
| P0 | Quarter mismatch EPS : table montre -37.6% miss basé sur une estimation du mauvais trimestre | Rend le rapport **trompeur** |
| P0 | Mélange annual/quarterly dans Operating Metrics et Segments | Rend les chiffres **incompréhensibles** |
| P0 | Press Release + Presentation = N/A sans fallback | Perte de 2/3 des sources de données |
| P1 | "Company filing / Calculated" partout — zéro traçabilité | Rend le rapport **inauditable** |
| P1 | Sortie 100% anglaise — le modèle est bilingue EN+JP | Ne correspond pas au format Nami-san |

---

## 2. Score de parité global

| Dimension | Score | Commentaire |
|-----------|-------|-------------|
| Structure /20 | **12** | La plupart des sections existent mais 3 sont gravement affaiblies |
| Couverture données /20 | **8** | Contradictions majeures, segments sans géographie, documents manquants |
| Traçabilité sources /20 | **5** | "Company filing / Calculated" 35 fois, 0 lien SEC/EDGAR, 0 timestamp |
| Similarité visuelle /20 | **10** | Structure de rapport OK mais pas d'emojis Unicode, pas de japonais, densité différente |
| Style analytique /20 | **9** | "For Nami-san" présent mais ton clinique, pas d'interprétation profonde |
| **TOTAL** | **44/100** | ⚠️ Insuffisant — nécessite refonte majeure avant utilisation |

---

## 3. Tableau gap section par section

| Section attendue (modele.pdf) | Statut dans pdf.pdf | Gaps principaux | Sévérité | Correctif requis |
|------|------|------|------|------|
| **Earnings Documents** | ⚠️ Présent mais incomplet | Press Release N/A, Earning Call Presentation N/A, URL IR pointe vers Phoenix IR (plateforme standard, légitime) mais lien spécifique NVIDIA cassé (404), Marketbeat au lieu d'une source transcript officielle | **S4** | Ajouter fallback : chercher sur le site corporate si lien Phoenix IR cassé + SEC EDGAR ; présenter NOT_FOUND avec sources cherchées |
| **EPS & Revenue** | 🔴 Présent mais contradictoire | Table montre EPS=$1.76, est=$2.82 → miss -37.6% ; texte dit EPS=$1.62, est=$1.54 → beat +5.2%. **Deux valeurs EPS différentes dans la même section.** | **S5** | Aligner le trimestre : utiliser les données du BON trimestre (Q4 FY2026) ; ne PAS afficher une comparaison basée sur un mauvais trimestre |
| **Highlights & Lowlights** | ⚠️ Présent mais faible | 3 highlights, 2 lowlights (vs 6+5 dans le modèle). Lowlight #1 cite le EPS miss de -37.6% qui est basé sur un mauvais trimestre. Emojis absents de l'extraction texte. | **S4** | Générer plus de points. Utiliser les vrais données du bon trimestre. Corriger le rendu emoji. |
| **Operating Metrics** | 🔴 Présent mais chiffres incohérents | Table : Net income=$43.0B. Texte : "net income ($120.07B)". Revenue=$215.94B mentionné dans le texte mais $68.1B dans la table. Mélange trimestriel/annuel. | **S5** | Utiliser UNIQUEMENT des données trimestrielles. Vérifier que le total segments ≤ revenue. Normaliser annual/quarterly. |
| **Cash Flow** | ✅ Présent et cohérent | OCF=$36.2B, CapEx=$1.3B, FCF=$34.9B. Cohérent en interne. | **S2** | Ajouter comparaison inter-entreprises comme le modèle (Apple vs NVIDIA vs Amazon vs Google) |
| **Capital Efficiency** | ⚠️ Présent mais sources faibles | ROE=27.3%, ROIC=25.9%, ROTCE=32.3%. Mais "computed from supplied metrics" sans montrer le calcul. Pas de Buybacks/Dividends dans le modèle. | **S3** | Ajouter les formules de calcul. Vérifier cohérence Net Income utilisé ($43.0B ? $120.1B ?) |
| **Segments** | 🔴 Présent mais chiffres ANNUELS + pas de géographie | Data Center=$193.7B sur un rapport trimestriel de $68.1B total. Compute=$162.4B. Aucun breakdown géographique (5 régions dans le modèle). | **S4** | Utiliser données TRIMESTRIELLES. Ajouter breakdown géographique (US, Europe, China, Japan, APAC). |
| **Forward P/E** | ✅ Présent et bien structuré | Forward P/E=19.07x. Bonne analyse, comparaison secteur, PEG. Section la mieux réussie. | **S1** | — |
| **Backlog** | ⚠️ N/A faible | "N/A — company does not report backlog". Le modèle (Sandisk) montre comment analyser même sans chiffre officiel (hyperscaler capex, supply chain). Pour NVIDIA, le carnet de commandes implicite est ÉNORME. | **S3** | Analyser les engagements hyperscaler, les prépaiements clients, le ratio commandes/livraisons — même sans chiffre officiel |
| **Guidance** | ⚠️ Présent mais incomplet | Plusieurs champs "Not disclosed" ou "Not available". Revenue guidance $78.8B mais confusion Q1 2027 vs Q2 2026. | **S3** | Séparer clairement guidance officielle vs consensus analystes. Marquer les champs absents comme "Not disclosed by company" (pas juste "Not available"). |
| **Verdict** | ⚠️ Score 4/5 → BUY mais contradictions | Score 4/5 malgré les contradictions internes. "EPS $1.76 — EPS did not beat consensus" contredit le texte qui dit beat. Pas de sources listées. | **S4** | Le verdict doit refléter les DONNÉES RÉELLES. Si contradiction → la signaler, pas la masquer. Ajouter section Sources. |
| **Sources** | ❌ ABSENT | Aucune section Sources dans le PDF généré. Le modèle liste les URLs et types de documents en fin de rapport. | **S3** | Ajouter une section "Sources" listant chaque URL, date d'accès, type de document |

---

## 4. Audit document-source

| Document requis | Comportement attendu (modèle) | Réel dans pdf.pdf | Problème | Correctif |
|------|------|------|------|------|
| **Earnings Call Transcript** | Chercher sur site officiel IR + sources gratuites ; donner URL réelle | Marketbeat (agrégateur) : `marketbeat.com/stocks/NASDAQ/NVDA/earnings/` | Marketbeat n'est PAS la source du transcript. C'est un agrégateur qui scrape. Le vrai transcript vient de Motley Fool, Seeking Alpha, ou NVIDIA IR. | Chercher le transcript réel sur `investor.nvidia.com` → Events → Earnings. Si payant, utiliser SEC 8-K comme fallback. |
| **Earnings Call Presentation** | Téléchargeable depuis l'IR officiel ou Seeking Alpha. Si indisponible → NOT_FOUND avec sources cherchées. | **N/A** | Aucune recherche documentée. NVIDIA publie des slides decks à chaque earnings. | Chercher sur `investor.nvidia.com/financial-info/quarterly-results/`. Le PDF de présentation est presque toujours disponible. |
| **Press Release** | Doit être trouvé sur le site IR officiel. Source primaire. | **N/A** | Aucune recherche documentée. Le communiqué de presse est la source #1 des données financières. | Chercher sur `investor.nvidia.com/news-events/news/`. Si non trouvé → NOT_FOUND avec URLs cherchées. |
| **Official IR URL** | URL trouvée via la plateforme standard Phoenix IR (phx.corporate-ir.net), utilisée par des milliers de sociétés cotées | `phx.corporate-ir.net/phoenix.zhtml?c=116466&p=irol-IRHome` | L'URL est sur la BONNE plateforme (Phoenix IR = standard), mais retourne 404 pour NVIDIA spécifiquement — l'entreprise a probablement migré son IR vers `investor.nvidia.com`. Le pipeline doit vérifier que l'URL résout (suivre les redirects) et, si 404, chercher le domaine IR actuel. | Vérifier la résolution de l'URL : suivre redirects → si 404, chercher sur le site corporate officiel (nvidia.com → investor.nvidia.com). La plateforme Phoenix IR reste la source légitime pour les tickers qui l'utilisent. |

---

## 5. Problèmes de données financières

| Métrique / Section | Problème | Évidence dans pdf.pdf | Pourquoi c'est grave | Correctif |
|------|------|------|------|------|
| **EPS** | Deux valeurs différentes dans la même section | Table : EPS=$1.76, est=$2.82, miss -37.6%. Texte : "transcript confirms Q4 2026 actual EPS was $1.62, beating the $1.54 estimate" | L'investisseur lit -37.6% miss puis "beat by $0.08" → **incompréhensible** | Aligner TOUS les chiffres sur le même trimestre (Q4 FY2026). EPS réel NVDA Q4 FY2026 = ~$0.89 GAAP ou ~$1.62 non-GAAP selon la période. |
| **Revenue** | Mélange trimestriel/annuel | Table : $68.1B. Texte : "$215.94B". Data Center : $193.7B. | $193.7B de Data Center dans un rapport de $68.1B total → **incohérence flagrante** | Normaliser : soit tout en trimestriel, soit tout en annualisé avec mention claire. |
| **Net Income** | Deux valeurs incompatibles | Table Operating Metrics : $43.0B. Texte : "net income ($120.07B)" | Impossible de savoir quel chiffre est correct | Utiliser UN SEUL net income (trimestriel). Vrai NVDA Q4 FY2026 net income ≈ $22.1B GAAP. |
| **Segments total** | Total segments dépasse le revenue total | Data Center $193.7B + Gaming $16.0B + ProViz $3.2B + Other $4.3B = $217.2B > $68.1B | Les segments utilisent des chiffres ANNUELS dans un rapport trimestriel | Extraire segments trimestriels depuis le 10-Q. |
| **EPS estimate $2.82** | Basé sur le MAUVAIS trimestre | Le texte l'admet : "The estimate appears to be for a different quarter (possibly Q1 2027)" | Malgré l'admission, le tableau présente cette comparaison comme le résultat principal → **trompeur** | Ne pas afficher de comparaison basée sur un mauvais trimestre. Si mismatch → le signaler EN TÊTE, pas en footnote. |
| **One-line summary** | Filler sans valeur | "Not applicable for NVIDIA Corporation" (page Backlog) | Zéro valeur ajoutée. Le modèle n'a pas de "one-line summary" | Supprimer. Remplacer par une analyse réelle ou marquer comme NOT_FOUND avec justification. |
| **Guidance EPS $2.82** | Confusion guidance vs consensus | Guidance table montre EPS=$2.82 comme "Guidance" mais c'est le CONSENSUS, pas la guidance officielle de NVIDIA | L'investisseur croit que NVIDIA a guidé $2.82 | Séparer clairement : "Company guidance" vs "Analyst consensus". NVIDIA donne rarement un guidance EPS précis. |

---

## 6. Problèmes visuels et de formatage

| Page | Problème | Sévérité | Recommandation |
|------|------|------|------|
| **Toutes les tables** | 🔴 **Chevauchement de texte systémique** — les colonnes ont des largeurs fixes insuffisantes. Les valeurs longues (ex: -37.6%, Company filing / Calculated, commentaires) débordent dans la colonne suivante. Confirmé sur : EPS/Revenue, Highlights, Operating Metrics, Cash Flow, Capital Efficiency, Segments, Forward P/E, Guidance, Verdict. | **S5** | Le renderer PDF doit calculer les largeurs de colonnes dynamiquement basées sur le contenu, wrapper le texte dans les cellules, ou réduire la taille de police. |
| Page 1 | URL IR pointe vers Phoenix IR (plateforme standard) mais retourne 404 pour NVIDIA | S2 | Vérifier la résolution → suivre redirects → si 404, chercher le domaine IR actuel |
| Page 1 | Table Earnings Documents : 2 lignes N/A sur 4 | S4 | Remplacer N/A par NOT_FOUND avec URLs cherchées |
| Page 2 | Table EPS/Revenue : colonne "vs Estimate" trompeuse (-37.6%) + texte overflow dans Source | S5 | Corriger l'alignement de trimestre + largeurs de colonnes dynamiques |
| Page 3 | Section Highlights : séparateur `\u0000` avant "Lowlights" + overflow texte | S3 | Vérifier l'encodage des séparateurs + colonnes dynamiques |
| Page 7 | Segments : watermark artefact "Comptabilityfiting" superposé au tableau | S3 | Bug distinct du renderer — origine à investiguer |
| Page 8 | Forward P/E : texte colonne Reference wrappe et coupe, overflow dans Interpretation | S3 | Colonnes dynamiques |
| Page 9 | Backlog : 4 lignes pour dire "N/A" — gaspillage d'espace | S2 | Compresser ou remplacer par analyse indirecte |
| Page 11 | Verdict : overflow Evidence → Risk, texte tronqué | S4 | Colonnes dynamiques |
| Page 11 | Pas de section Sources, pas de date, pas de signature | S3 | Ajouter footer avec date de génération, sources, avertissement |
| Toutes | Pas de rendu emoji Unicode dans l'extraction texte | S3 | Emojis rendus comme images PNG — utiliser NotoColorEmoji Unicode natif |
| Toutes | Absence de texte japonais | ~~S4~~ Annulé — la langue est choisie par l'utilisateur (EN ou JP), le pipeline génère deux versions séparées. Le pdf.pdf audité est la version EN. | Aucun correctif nécessaire — ce n'est pas un bug. |
| Toutes | Pas de séparation "Question → Tableau → Explication → Nami-san → Takeaway" | S3 | Structurer comme le modèle |

---

## 7. Langue et style

### Écart constaté
Le PDF généré est **100% en anglais**. Le modèle (`modele.pdf`) est **bilingue** :
- Questions posées en anglais ET en japonais
- Réponses et analyses en **japonais**
- Commentaires "Nami-san" intégrés dans le flux japonais
- Emojis (🌟⚠️📊🧠🎯🔥) utilisés comme marqueurs visuels
- Flèches (👉) pour les takeaways
- Ton conversationnel adapté à une investisseuse japonaise ("Namiさん向け解釈")

### Ce que le PDF généré fait
- Tags "→ For Nami-san:" présents (21 occurrences) mais en anglais
- Zero japonais
- Emojis absents de l'extraction texte (rendus comme images ou absents)
- Ton plus "analyste financier anglo-saxon" que "conseiller d'investissement japonais"
- Pas de takeaway structuré avec 👉 comme dans le modèle

### Impact
Le PDF généré ne correspond **pas du tout** au format "Nami-san" attendu. Il ressemble à un rapport d'analyste standard en anglais, pas à un rapport d'investissement japonais personnalisé.

---

## 8. Traçabilité des sources

### Problèmes identifiés

| Source | Occurrences | Problème |
|------|------|------|
| **"Company filing / Calculated"** | 35 (chaque cellule de tableau) | Aucun lien vers un filing spécifique. Aucun nom de formulaire (10-Q, 10-K, 8-K). Aucune date. Aucun numéro de page. |
| **Marketbeat** | 1 (page 1) | Agrégateur, pas source primaire. Le vrai transcript vient d'ailleurs. |
| **URL IR obsolète** | 1 (page 1) | `phx.corporate-ir.net` n'est plus utilisé par NVIDIA. |
| **Aucune source SEC EDGAR** | 0 | Le 10-Q/10-K est la source la plus fiable — jamais cité. |
| **Aucune source yfinance** | 0 (mentionné en page 11 mais pas dans les tableaux) | Les données viennent probablement de yfinance mais ce n'est pas documenté. |
| **Aucun timestamp** | 0 | Impossible de savoir QUAND les données ont été extraites. |

### Règle violée
Le principe `AGENTS.md §6` exige : "Toute donnée financière doit être sourcée. Les conclusions doivent être auditables à partir du dossier de sources."

Avec "Company filing / Calculated" comme seule source, **rien n'est auditable**.

---

## 9. Hypothèses de cause racine

Basé sur les patterns observés, voici les causes techniques probables :

| # | Cause probable | Évidence | Confiance |
|------|------|------|------|
| 1 | **Mélange annual/quarterly dans l'extraction yfinance** | Revenue $215.94B (annuel) vs $68.1B (trimestriel), Segments $193.7B (annuel). Fonction `get_stock_data()` ou `get_yahoo_data()` ne normalise pas la période. | Élevée |
| 2 | **Prompt LLM mal contraint** | Le LLM a généré des explications avec des chiffres différents de la table (net income $120.1B vs $43.0B). Manque de guardrails pour forcer la cohérence. | Élevée |
| 3 | **Lien Phoenix IR cassé pour ce ticker spécifique** | Press Release + Presentation N/A. Le pipeline trouve correctement `phx.corporate-ir.net` (plateforme IR standard), mais ce lien précis retourne 404 — NVIDIA a migré ailleurs. Le fallback ne cherche pas le nouveau domaine. | Élevée |
| 4 | **Template mapping ne force pas le japonais** | Le template pour le deep-dive PDF est probablement configuré en anglais. Le modèle montre une sortie JP obligatoire. | Moyenne |
| 5 | **Renderer PDF : largeurs de colonnes fixes** | Texte overflow dans toutes les tables (EPS, OpMetrics, CashFlow, CapEfficiency, Segments, Fwd PE, Guidance, Verdict). Le renderer n'ajuste pas les largeurs au contenu. | Élevée |
| 6 | **Pas de validation post-génération** | Les contradictions (EPS $1.76 vs $1.62, Net Income $43.0B vs $120.1B) auraient dû être détectées par un validateur automatique. | Élevée |
| 7 | **EPS estimate fetching bug** | L'estimate $2.82 vient d'un consensus Q1 2027 au lieu de Q4 2026. La fonction `get_stock_data()` récupère le forward estimate au lieu de l'estimate du quarter courant. | Élevée |
| 8 | **Schéma de source non implémenté** | "Company filing / Calculated" est un placeholder jamais remplacé par des vraies sources. Le code qui devrait injecter les URLs SEC/IR n'est pas appelé. | Élevée |

---

## 10. Recommandations d'implémentation (plan priorisé)

### 🔴 P0 — Doit être corrigé avant TOUTE nouvelle génération de PDF

1. **Normaliser annual/quarterly** — Ajouter un paramètre `period='quarterly'` dans `get_stock_data()` et `get_yahoo_data()`. Vérifier que TOUS les chiffres (revenue, segments, net income) sont sur la même période.
2. **Corriger l'extraction EPS estimate** — L'estimate doit correspondre au quarter du rapport, pas au forward consensus. Ajouter validation : si `estimate > actual * 1.5` → probablement mauvais trimestre → flagger.
3. **Réparer la recherche Press Release + Presentation** — Coder un fallback : (1) `investor.nvidia.com/quarterly-results/` → (2) SEC EDGAR 8-K → (3) marquer NOT_FOUND avec URLs cherchées.
4. **Remplacer "Company filing / Calculated"** — Injecter les vraies sources : nom du formulaire SEC, URL EDGAR, date d'accès, page/tableau.
5. **Corriger les largeurs de colonnes des tables PDF** — Calcul dynamique basé sur le contenu le plus long de chaque colonne, ou text wrapping dans les cellules.

### 🟡 P1 — Important, corriger avant livraison à Nami

5. **Sortie bilingue obligatoire** — Si `lang=ja` → chaque section doit avoir le texte en japonais. Le modèle montre le format exact.
6. **Validation post-génération** — Ajouter un validateur qui détecte :
   - Deux valeurs EPS différentes dans le même document
   - Total segments > revenue
   - Net income contradictoire entre table et texte
7. **Vérifier la résolution de l'URL IR** — Le pipeline trouve correctement `phx.corporate-ir.net` (plateforme Phoenix IR standard). Mais il doit suivre les redirects et, si 404, chercher le domaine IR actuel (ex: nvidia.com → investor.nvidia.com).
8. **Corriger le rendu emoji** — Utiliser NotoColorEmoji.ttf via PIL pour le rendu inline, comme documenté dans les refs du skill.

### 🟢 P2 — Polish

9. **Ajouter breakdown géographique** aux segments (Americas, Europe, China, Japan, APAC).
10. **Ajouter comparaison inter-entreprises** dans Cash Flow (NVIDIA vs autres AI players).
11. **Remplacer "One-line summary"** par une analyse réelle ou supprimer.
12. **Ajouter section Sources** en fin de document avec URLs, dates d'accès, types de documents.
13. **Structurer chaque section** comme le modèle : Question → Table → Explication → Nami-san → Takeaway.

---

## 11. Critères d'acceptation pour le prochain PDF généré

Le prochain PDF sera accepté SI ET SEULEMENT SI :

### Données
- [ ] Tous les chiffres sont sur la MÊME période (trimestrielle)
- [ ] EPS : une seule valeur, cohérente dans tout le document
- [ ] Revenue : cohérent entre table, texte, et segments
- [ ] Net Income : cohérent entre Operating Metrics et Capital Efficiency
- [ ] Total segments ≤ revenue total (à 1% près)
- [ ] EPS estimate correspond au bon trimestre

### Sources
- [ ] Chaque chiffre a une source traçable (URL EDGAR, nom du filing, date, page)
- [ ] Press Release trouvé OU marqué NOT_FOUND avec 3+ URLs cherchées
- [ ] Earning Call Presentation trouvé OU marqué NOT_FOUND avec justification
- [ ] URL IR officielle à jour
- [ ] Transcript : URL de la vraie source (pas juste un agrégateur)

### Contenu
- [ ] Toutes les sections du modèle sont présentes (12 sections)
- [ ] Sortie en japonais si `lang=ja`
- [ ] Emojis rendus correctement en Unicode
- [ ] Pas de "one-line summary" filler
- [ ] Pas de "Not available" sans justification
- [ ] Section Sources en fin de document

### Qualité
- [ ] Aucune contradiction interne (EPS, Revenue, Net Income)
- [ ] Aucun mélange annual/quarterly non documenté
- [ ] Score verdict cohérent avec les données présentées
- [ ] Guidance officielle vs consensus analystes clairement séparés
- [ ] Breakdown géographique présent dans les segments

### Style
- [ ] Format "Nami-san" : explications accessibles, takeaways actionnables
- [ ] Structure Question → Tableau → Explication → Interprétation → Takeaway
- [ ] Emojis comme marqueurs visuels (🌟⚠️📊🧠🎯)
- [ ] Flèches (👉) pour les conclusions
- [ ] Pas de jargon excessif sans explication

---

## Annexe A — Occurrences patterns dans pdf.pdf

| Pattern | Occurrences |
|------|------|
| "Company filing" | 35 |
| "Calculated" | 30 |
| "Nami-san" / "For Nami-san" | 21 |
| "Not available" | 7 |
| "N/A" | 6 |
| "Not disclosed" | 4 |
| "one-line summary" | 3 |
| Emojis Unicode (🌟⚠️📊🧠🎯👉) | 0 (extraction texte) |

## Annexe B — Valeurs EPS contradictoires détectées

| Valeur | Contexte | Page |
|------|------|------|
| $1.76 | Table EPS/Revenue — "Actual" | 2 |
| $1.62 | Texte — "transcript confirms Q4 2026 actual EPS was $1.62" | 2 |
| $2.82 | Table EPS/Revenue — "Estimate" | 2 |
| $1.54 | Texte — "beating the $1.54 estimate" | 2 |
| $11.29 | Forward P/E — "annualized to $11.29" | 8 |
| $4.90 | Forward P/E — "Trailing EPS of $4.90" | 8 |
| $6.00 | Verdict — "FY2027 EPS estimates ($6.00-$7.29)" | 11 |

## Annexe C — Valeurs Revenue contradictoires

| Valeur | Contexte | Problème |
|------|------|------|
| $68.1B / $68.13B | Table Operating Metrics, EPS/Revenue | Trimestriel |
| $215.94B | Texte Operating Metrics | Annuel ? |
| $193.74B | Segment Data Center | Annuel |
| $162.36B | Segment Compute | Annuel |
| $78.8B / $76.4B-$79.6B | Guidance | Forward trimestriel |
| $39.3B | Prior Year colonne | Annuel ? Cohérent avec trimestriel Q4 FY2025 ? |
