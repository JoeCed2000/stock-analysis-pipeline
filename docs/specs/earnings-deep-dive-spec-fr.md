# Earnings Call Deep-Dive — Spécification Complète (FR)
# Traduction de la spec Nami — tous les emojis et détails préservés
# Source: Earnings Documents.pdf

## Vue d'ensemble
Analyse complète des résultats trimestriels produisant des rapports investisseurs structurés bilingues (EN/JP).

---

## Sections requises

### 1. 📊 EPS & Revenue Summary
**Format : Tableau** — Estimation vs Réel vs Écart Estimation vs Variation YoY

**Exemple (GEV Q1 2026) :**
- EPS : $1,79-$1,95 estimé → $17,44 réel (+$15 vs est, +16% YoY depuis $8,03B)
- Revenue : $9,27B-$9,29B estimé → $9,34B réel (+$0,5B-$0,7B vs est, +1500% depuis $0,91B)

**一言まとめ :** Le chiffre s'explique en une phrase, le lecteur comprend immédiatement si c'est bon ou mauvais.

---

### 2. 🌟 Highlights & ⚠️ Lowlights
- 🌟 **Highlights** (points positifs) — numérotés, avec preuves chiffrées
- ⚠️ **Lowlights** (points de vigilance) — numérotés, avec niveau de sévérité
- Format japonais avec analyse détaillée en bullets
- Chaque point doit citer une donnée du transcript

**一言まとめ :** La thèse résumée en une ligne — ce qu'il faut retenir.

---

### 3. 🧠 Operating Metrics
**Format : Tableau + Analyse**

| Métrique | Valeur | YoY |
|----------|--------|-----|
| Revenue | | |
| Gross Profit / Marge Brute | | |
| OpEx | | |
| Operating Income / Marge Op. | | |
| Net Income | | |

**Exemple (AAPL Q2 2026) :**
- Revenue $111,18B (+16,6%)
- Marge Brute 49,3% (+2,3pt)
- OpEx $18,90B (+23,7%)
- Op Income $35,89B (+21,3%), Marge Op. 32,3% (+1,3pt)
- Net Income $29,58B (+19,4%)

**一言まとめ :** La tendance des marges — compression ou expansion ?

---

### 4. 💰 Cash Flow
**Format : Tableau + Analyse**

| Métrique | Valeur | YoY |
|----------|--------|-----|
| OCF (Operating Cash Flow) | | |
| CapEx | | |
| FCF (Free Cash Flow) | | |

**Exemple (AAPL) :** OCF $82,63B (+53%), CapEx $4,34B (-28%), FCF $78,28B (+63%)

**Analyse :** Qualité de la génération de cash, conversion du résultat net en cash, soutenabilité.

**一言まとめ :** La boîte génère-t-elle du cash ou en brûle-t-elle ?

---

### 5. 🎯 Capital Efficiency
**Format : Métriques + Interprétation**

- ROE, ROTCE/ROTE, ROA, ROIC
- Analyse de ce qui drive les chiffres

**Exemple (AAPL) :** ROE ~65-70%, ROTCE ~80%, ROA ~16-18%, ROIC ~45-55%

**一言まとめ :** Le rendement du capital est-il supérieur au coût du capital ?

---

### 6. 🧩 Segments
**Format : Tableaux + Analyse**

- Par catégorie de produit (tableau)
- Par zone géographique (tableau)
- Analyse des mix shifts, risques de concentration

**一言まとめ :** Quel segment tire la croissance ? Y a-t-il un risque de concentration ?

---

### 7. 📈 Forward P/E
**Format : Tableau**

- Forward P/E actuel
- Contexte : secteur, historique 5 ans, justified P/E

**一言まとめ :** La valorisation est-elle soutenable par la croissance ?

---

### 8. 📦 Backlog Quality (conditionnel — certaines sociétés uniquement)
- **Quantité :** combien (montant en $, trimestres de couverture)
- **Qualité :** engagements fermes vs pipeline souple

**Exemple (SanDisk) :** Contrats NBM $42B minimum garanti, ~7 trimestres de couverture, garanties financières $11B+

**一言まとめ :** La visibilité sur le carnet de commandes est-elle solide ou fragile ?

---

### 9. 🔮 Guidance
**Format : Tableau**

| Métrique | Guidance T+1 | QoQ |
|----------|-------------|-----|
| Revenue | | |
| Marge Brute | | |
| EPS | | |

**Exemple (SanDisk Q4 guide) :** Revenue $7,75B-$8,25B, Marge Brute 79-81%, EPS $30-$33

- Analyse QoQ
- Signaux directionnels moyen-terme

**一言まとめ :** Le management est-il confiant ou prudent pour le prochain trimestre ?

---

### 10. 🏆 Verdict / 総合評価
- Verdict analyste structuré
- Forces / Faiblesses / Opportunités / Risques
- **一言まとめ :** Thèse d'investissement en une phrase

---

## Règles de format
- Chaque section : question en EN + JP, puis réponse structurée
- **Tableaux pour TOUTES les données numériques** (pas seulement certaines sections)
- 🌟⚠️🧠🎯🧩💰📈📦🔮🏆 emojis pour balises visuelles
- **"Nami-san向け"** (pour Nami) — annotations avec la perspective d'une investisseuse japonaise
- **Chaque section se termine par 一言まとめ** (résumé en une ligne)

## Langue
- Bilingue EN+JP par défaut dans les exemples de la spec
- L'utilisateur configure la langue de sortie

## Sources
- **Seeking Alpha :** transcripts des earnings calls + présentations
- **Site officiel :** communiqués de presse
- **Fallback :** présentations earnings depuis les pages IR des sociétés
