# Spec-to-Implementation Field-by-Field Audit

## When to use
When a PDF spec or requirements document exists and you need to verify implementation completeness. User expects "champ par champ, chiffre par chiffre" comparison with gaps in bold.

## Methodology

### Phase 1: Extract the ground truth
1. Read the spec PDF with PyMuPDF (`fitz.open()`) — NEVER work from markdown extracts
2. List every field, column, section heading, data point the spec requires
3. Note the expected format (table, numbered list, emoji markers)

### Phase 2: Map to code
1. Read the schema (Pydantic models, DB tables, API contracts)
2. Read the data provider functions
3. For each spec field: does the schema have it? Does the provider populate it?

### Phase 3: Cross-reference
Compare spec field-by-field against:
- Schema fields
- Provider availability (yfinance, Finnhub, Twelve Data, EODHD, SEC)
- Prompt templates (if LLM-based generation)

### Phase 4: Classify gaps
| Classification | Meaning | Action |
|---|---|---|
| ✅ Present | Schema + provider both support it | None |
| 🔴 Critical gap | Data available in provider but not extracted | Add to schema + extraction |
| ⚠️ Inherent gap | No structured source exists (e.g., segment breakdown) | Mark as DONNÉE NON DISPONIBLE |
| ⚪ Not applicable | Company-specific or optional | Skip |

### Phase 5: Output format
Present as a table:
```
| Spec Field | In Schema? | Provider? | Classification | Fix |
|---|---|---|---|---|
| Gross Profit | ❌ | ✅ yfinance | 🔴 Critical | Add `gross_profit: float` |
```

Mark gaps in **bold** so the user can see them immediately. Always include the fix column.

## Key principles
- **PDF is single source of truth** — not markdown extracts, not memory
- **Never invent data** — if missing, write DONNÉE NON DISPONIBLE
- **Provider comparison** — check ALL providers (Finnhub, Twelve Data, EODHD, yfinance) before concluding data is unavailable
- **Parallel calls considered** — can we get data from multiple providers in parallel?

## Real example
Stock Analysis Pipeline deep-dive spec audit (2026-05-05):
- 14-page PDF spec vs FinancialMetrics schema vs yfinance provider
- Found 8 critical gaps (data in yfinance but not extracted) + 5 inherent gaps
- Result: 10 new fields added, 0 extra HTTP calls
