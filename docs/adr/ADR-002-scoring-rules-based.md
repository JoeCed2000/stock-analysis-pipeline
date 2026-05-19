# ADR-002 — Scoring rules-based vs ML

| Métadonnée | Valeur |
|---|---|
| Statut | Accepté |
| Date | 2026-05-18 |
| Décideurs | Ced + Hermes |
| Domaine | Scoring |

## 1. Contexte

Le pipeline doit attribuer une note sur 40 points à chaque ticker analysé (6 catégories : Financial Health, Growth, Valuation, Management, Moat, Sentiment) et produire une recommandation BUY/HOLD/SELL. La question est : rules-based engine ou modèle ML entraîné ?

## 2. Décision

**Choix : Rules-based engine déterministe (40 pts, 6 catégories)**

## 3. Options considérées

| Option | Avantages | Inconvénients | Décision |
|---|---|---|---|
| Rules-based | Transparent, auditable, déterministe, pas de données d'entraînement | Rigide, ne s'améliore pas automatiquement | **retenue** |
| ML léger (sklearn) | Peut apprendre des feedbacks utilisateur | Nécessite données labellisées, boîte noire, overfitting possible | rejetée |
| LLM scoring | Compréhension narrative, contexte | Coût tokens, non déterministe, hallucinations | rejetée |

## 4. Justification

- **Auditabilité :** L'utilisateur doit pouvoir comprendre pourquoi un ticker obtient 28/40. Un rules-based engine permet de tracer chaque point à une règle précise.
- **Déterminisme :** Même ticker, mêmes données → même score. Critique pour la confiance.
- **Pas de données d'entraînement :** Pas d'historique de scores humains pour entraîner un modèle.
- **Feedback :** Le feedback utilisateur corrige les règles (ex: ajuster un seuil), pas le modèle.

## 5. Conséquences

**Positives :**
- Score traçable : chaque point a une justification (ex: "PER < 15 → +2 pts")
- Reproductible : même entrée → même sortie
- Modifiable : les règles et seuils sont dans scorer.py (~140 lignes)

**Négatives :**
- Rigidité : ne s'adapte pas automatiquement aux nouvelles conditions de marché
- Maintenance : les seuils doivent être revus périodiquement
- Pas d'apprentissage : ne s'améliore pas avec l'usage

## 6. Évolution future

Si le volume de feedbacks utilisateur devient suffisant (> 100 feedbacks labellisés), une migration vers un modèle ML hybride (rules + ML calibration layer) pourra être réévaluée.
