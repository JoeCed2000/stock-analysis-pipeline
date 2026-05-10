# Audit visuel comparatif PDF - NVDA vs modele

Date: 2026-05-10  
PDF genere: `reports/generated/NVDA_earnings_deep_dive.pdf` (19 pages)  
PDF modele: `docs/specs/modele.pdf` (14 pages)  
Methode: extraction texte page par page avec PyMuPDF (`.venv/bin/python`), rendu PNG a 200 dpi dans `/tmp`, inspection visuelle des PNG disponibles. `browser_navigate` n'est pas disponible dans cet environnement; les controles visuels ont ete faits via les PNG locaux.

## Verdict global

Le PDF NVDA n'est pas encore au niveau de parite du modele.

Les titres et les tableaux existent, mais le document genere diverge fortement sur trois axes: donnees non renseignees dans les tableaux, incoherence entre tableaux et prose, et pagination/formatage non conforme au modele. Le modele est compact, principalement en listes structurees avec separateurs horizontaux; le genere est plus long, avec une page blanche, des sections etirees sur deux pages, des fragments Markdown visibles, et plusieurs phrases contenant des valeurs manquantes.

## Tableau recapitulatif

| Page | Section | Type d'ecart | Severite | Description |
|---:|---|---|---|---|
| 1 | Earnings Documents | Contenu / sources | P1 | Plusieurs sources critiques sont `Not available` ou `N/A` (IR, press release, presentation). Le modele affiche les emplacements de sources, mais le genere devrait fournir des URL reelles ou une mention auditable de non-disponibilite. |
| 1 | Earnings Documents | Format | P2 | Structure plus proche d'un tableau de controle que du modele; aucune question rouge detectee dans le genere, ce qui est correct. |
| 2 | EPS & Revenue | Contenu | P0 | Table incoherente: EPS table `$4.91` vs prose `$1.76`; estimation table `$11.29` vs prose `$2.82`; revenue table `Not available` alors que la prose cite `$68.13B`. |
| 2 | EPS & Revenue | Format | P1 | Fragments de rendu visibles: ligne `For` separee de `Nami-san`, fleches seules, puces vides, bloc `[VALIDATED DATA: ...]`, titre `One-line summary` orphelin en bas de page. |
| 3 | EPS & Revenue continuation | Contenu / format | P1 | Page de continuation quasi vide: `NVDA reported EPS of $4.91 and revenue of ;`. Valeur manquante transformee en trou de phrase. |
| 4 | Highlights | Structure | P2 | Section prose seulement, sans tableau, alors que le modele preserve une structure dense en listes et sous-parties. Pas de vrai tableau comparatif. |
| 4 | Highlights | Contenu | P1 | Melange de valeurs TTM/quarterly sans periode explicite (`TTM revenue`, EPS last four quarters) et conclusion sur miss/beat non alignee avec la page EPS. |
| 5 | Highlights continuation | Format | P2 | Page courte de continuation avec citation Markdown `>` et resume; rupture de flux peu conforme au modele. |
| 6 | Operating Metrics | Contenu | P0 | Tableau majoritairement `Not available`: Revenue, OpEx, Operating income, Net income et comparatifs prior-year absents, alors que la prose affirme gross margin 75%, operating margin 65%, net income $120.1B. |
| 6 | Operating Metrics | Texte indesirable | P1 | Caracteres carres/tofu avant plusieurs numerotations (`(1) □`), signe d'un mapping glyph/emoji incomplet. |
| 7 | Operating Metrics continuation | Format | P2 | Continuation sans titre de section; davantage de prose que le modele et peu de structure scannable. |
| 8 | Cash Flow | Contenu | P0 | Tableau 100% ou quasi 100% `Not available`, mais prose donne OCF `$36.19B`, CapEx `$1.28B`, FCF `$34.90B`, net debt `$435M`. La table n'est pas une source de verite. |
| 8 | Cash Flow | Format | P1 | Puces mixtes `-`, `●`, fleches seules et tirets isoles; rendu Markdown non normalise. |
| 9 | Cash Flow continuation | Format | P2 | Page de continuation courte; pas de titre, pas de tableau, densite faible vs modele. |
| 10 | Capital Efficiency | Contenu | P0 | Tableau incoherent: ROE `+1.0%`, ROA `+51.2%`, ROIC `Not available`, mais prose dit ROE `27.3%` et ROIC `25.9%`. Buybacks manquants dans table, mais prose affirme une capacite de rachats. |
| 10 | Capital Efficiency | Format | P2 | Resume et sous-titre `Capital efficiency takeaway` orphelins en bas de page. |
| 11 | Segments | Contenu | P1 | Tableau segments mieux renseigne, mais le texte contient `Data not available in transcript` pour plusieurs sous-analyses. Le modele attend des segments clairs ou une non-disponibilite explicite et concise. |
| 11 | Segments | Format | P2 | Caracteres tofu avant certains paragraphes. Colonnes de table lisibles mais tres compressees. |
| 12 | Segments continuation | Contenu | P1 | Analyse geographique speculative (`US hyperscalers`, China) alors que le texte indique absence de breakdown regional/china revenue. Risque anti-invention. |
| 13 | Forward P/E | Contenu | P1 | Table assez renseignee, mais `Forward EPS basis` reference `Not available`; prose cite des comparables et projections non toutes visibles dans la table/source. |
| 14 | Page blanche | Structure / visuel | P0 | Page totalement blanche detectee dans texte et PNG. Ecart majeur de pagination. |
| 15 | Backlog | Contenu | P1 | `N/A` dans la table peut etre acceptable si NVDA ne publie pas de backlog, mais la section devrait etre reduite ou marquee `Not disclosed`, pas traitee comme un tableau de donnees. |
| 15 | Backlog | Structure | P2 | Le modele integre backlog/guidance dans un flux dense; le genere consomme une page entiere pour une section non applicable. |
| 16 | Guidance | Contenu | P1 | Table contient `Not available` pour forward guidance/margin/outlook, mais prose affirme une fourchette de guidance `$76.4B-$79.6B`; source et periode non stabilisees. |
| 16 | Guidance | Format | P2 | `Data: Not available in transcript` visible dans les puces; rendu acceptable mais pas conforme a la densite du modele. |
| 17 | Guidance continuation | Contenu | P1 | Resume affirme une guidance significativement au-dessus du consensus, alors que page 18 parle d'une guidance miss. Contradiction inter-sections. |
| 18 | Verdict | Contenu | P0 | Verdict contradictoire: table dit `EPS did not beat consensus`, prose dit `GAAP EPS of $1.76 beat consensus`; guidance tantot au-dessus, tantot en dessous du consensus. |
| 18 | Verdict | Structure | P2 | Le modele fourni ne contient pas de page verdict equivalent aussi longue; section supplementaire a cadrer si elle reste requise. |
| 19 | Sources / final verdict | Contenu | P0 | Phrase finale tronquee: `revenue of (+73.2% YoY)`. Source `Official Investor Relations: □□□□□□` illisible. `margin below 15%` semble incoherent avec operating margin `+65.0%`. |
| 19 | Sources | Format | P1 | Titre Sources present, mais aucune URL exploitable; glyphs carres au lieu d'une mention anglaise propre. |

## Synthese - top 5 problemes

1. **P0 - Incoherence donnees table vs prose.** EPS, revenue, cash flow, capital efficiency et verdict utilisent des valeurs differentes selon la zone du PDF. La prose semble reutiliser des champs LLM/yfinance differents de ceux de la table.
2. **P0 - Tableaux remplis de `Not available` malgre des valeurs en prose.** Cash Flow et Operating Metrics sont les cas les plus graves: le lecteur ne peut pas auditer les conclusions a partir des tableaux.
3. **P0 - Page 14 blanche.** La pagination cree une page vide entre Forward P/E et Backlog.
4. **P1 - Placeholders transformes en phrases cassees.** Exemples: `revenue of ;`, `Revenue , +73.2% YoY`, `Official Investor Relations: □□□□□□`.
5. **P1 - Markdown et listes mal nettoyes.** `>`, tirets seuls, fleches seules, puces vides, `For` / `Nami-san` separes, et caracteres tofu degradent le rendu visuel par rapport au modele.

## Comparaison structurelle

Modele observe:
- Document compact de 14 pages.
- Flux principalement en listes courtes avec separateurs horizontaux.
- Les sections se suivent avec peu de pages quasi vides.
- Certaines pages modele contiennent du texte rouge/instructions, mais ce sont des artefacts du modele source; elles ne sont pas presentes en rouge dans le PDF NVDA.

Genere NVDA:
- 19 pages, dont une page blanche.
- Une section commence presque toujours sur une nouvelle page, ce qui augmente fortement le nombre de pages.
- Plusieurs pages de continuation contiennent peu de contenu et pas de rappel de titre.
- Les tableaux sont presents, mais trop souvent non renseignes ou incoherents avec la prose.
- Aucun `Please summarize...` ou `Question (EN):` detecte dans le genere; aucun span rouge detecte dans le genere.

## Recommandations pour `backend/earnings_deep_dive/pdf_renderer.py`

1. **Bloquer les pages blanches.** Ajouter une validation post-render PyMuPDF qui echoue si une page a `len(page.get_text("text").strip()) == 0`, puis corriger la logique `PageBreak()` pour eviter les doubles ruptures ou les ruptures avant section vide/non applicable.
2. **Limiter les orphelins.** Encapsuler titre + table + premier bloc d'analyse dans un groupe type `KeepTogether` lorsque possible, et eviter qu'un label de resume (`One-line summary`, `Capital efficiency takeaway`) parte seul en bas de page.
3. **Normaliser Markdown avant ReportLab.** Traiter explicitement blockquotes (`>`), listes `-`, puces vides, tirets seuls et fleches seules. Les lignes vides ou markers sans texte doivent etre supprimes.
4. **Corriger les retours de ligne autour de `For Nami-san`.** Le remplacement actuel par marqueur casse parfois `For` et `Nami-san` sur deux lignes. Utiliser une regex sur phrase complete au lieu de `replace()` sur fragments.
5. **Rendre les sources avec la meme hygiene glyph/langue que le reste.** Dans le bloc Sources, passer par `_paragraph_md` ou `_glyph_safe`, et convertir toute note japonaise `データ未取得` en `Not available` en mode anglais.
6. **Ajouter une QA visuelle automatique minimale.** Apres rendu: compter pages blanches, detecter `□`, `revenue of ;`, `Revenue ,`, `Not available` excessif, `>` en debut de ligne, et ecrire/lever une erreur de validation.

## Recommandations pour `backend/earnings_deep_dive/mapper.py`

1. **Rendre les formatters dependants de la langue.** `_money`, `_eps`, `_pct`, `_multiple`, `_yoy_pct` renvoient actuellement `データ未取得` pour valeur manquante, puis le renderer anglais peut le supprimer ou l'afficher en tofu. En mode anglais, retourner `Not available` ou mieux `DONNEE NON DISPONIBLE` selon la regle produit.
2. **Creer une source de verite unique par metrique.** Les tables et la prose doivent lire le meme objet normalise: periode, valeur, source, type (`quarterly`, `TTM`, `guidance`, `consensus`). Ne pas melanger EPS quarterly, EPS annualise, EPS TTM et estimates dans une meme section sans libelle.
3. **Verifier la coherence avant rendu.** Ajouter une etape qui compare les nombres presents dans `section.analysis` avec les cellules de table. Si la prose cite `$36.19B` OCF, la table Cash Flow doit contenir cette valeur et sa source, sinon la prose doit etre remplacee par `DONNEE NON DISPONIBLE`.
4. **Ne pas garder de prose affirmative quand la table est vide.** Si une section data-driven a plus de 50% de cellules manquantes, soit enrichir depuis les sources, soit remplacer par un court paragraphe de non-disponibilite auditable.
5. **Distinguer `Not available`, `Not disclosed`, `N/A`, `Not calculable`.** Backlog NVDA devrait etre `Not disclosed / not applicable` avec justification, pas un tableau plein de `N/A`. Une donnee attendue mais absente doit etre marquee explicitement et sourcée.
6. **Durcir les sources obligatoires.** Si `investor_relations_url`, `press_release_url` ou `presentation_url` sont absents, ne pas produire une source illisible; produire une ligne propre `DONNEE NON DISPONIBLE - source file missing` ou exclure la ligne selon la regle choisie.
7. **Recalculer le verdict uniquement depuis les metriques validees.** Le verdict doit etre derive des tables finales, pas d'une analyse LLM contradictoire. Les contradictions actuelles sur guidance beat/miss et EPS beat/miss doivent bloquer la generation.

## Donnees de controle

- PyMuPDF disponible via `.venv/bin/python`, pas via `python3` systeme.
- PNG modeles rendus: `/tmp/model_page_01.png` a `/tmp/model_page_14.png`.
- PNG NVDA rendus: `/tmp/nvda_page_01.png` a `/tmp/nvda_page_19.png`.
- Extraction texte temporaire: `/tmp/pdf_text/model_page_*.txt`, `/tmp/pdf_text/nvda_page_*.txt`.
- Artefacts d'analyse temporaire: `/tmp/pdf_audit_extract.json`.
