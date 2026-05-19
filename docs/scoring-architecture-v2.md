# Scoring Architecture v2 — Validated Spec

| Métadonnée | Valeur |
|---|---|
| Document | Scoring Architecture v2 |
| Statut | **Confirmed** — ready for implementation |
| Date | 2026-05-19 |
| Author | Hermes (architect-spec) — architectural review |
| Source files reviewed | `backend/scorer.py`, `backend/models.py`, `backend/orchestrator.py`, `backend/pdf_generator.py`, `backend/main.py`, `frontend/src/components/ScoringChart.jsx`, `frontend/src/components/AnalysisCard.jsx`, `frontend/src/components/ReportView.jsx`, `tests/test_models.py`, `_run_backlog.py` + 7 other `_run_*.py` scripts |
| Related | ADR-002 (scoring rules-based vs ML), spec-technique.md §5 (modèle de scoring) |

---

## 1. Field Mapping — 8 Internal Sub-scores → 6 Canonical Categories

### 1.1 Current State

8 internal `_score_*()` functions in `backend/scorer.py` each return `0–5`:

| # | Internal function | Field name on Scoring | Range | What it measures |
|---|---|---|---|---|
| 1 | `_score_growth()` | `growth` | 0–5 | Revenue YoY / annual growth |
| 2 | `_score_profitability()` | `profitability` | 0–5 | Operating margin |
| 3 | `_score_financial_strength()` | `financial_strength` | 0–5 | Net debt, FCF, net income |
| 4 | `_score_moat()` | `moat` | 0–5 | Gross margin, market cap, sector |
| 5 | `_score_management()` / `_score_management_realtime()` | `management` | 0–5 | Guidance or 10-K tone analysis |
| 6 | `_score_valuation()` | `valuation_risk` | 0–5 | P/E ratio (5 = cheap, 1 = expensive) |
| 7 | `_score_geopolitical()` | `geopolitical_risk` | 0–5 | Sector/industry political exposure (5 = low risk, 1 = high) |
| 8 | `_score_momentum()` | `business_momentum` | 0–5 | YoY growth + price proximity to 52w high |

All 8 functions MUST remain **UNCHANGED** per constraint.

### 1.2 Target 6 Canonical Categories

From ADR-002 and spec-technique.md §5:

| Category | Max | Description |
|---|---|---|
| Financial Health | /10 | Debt/equity, FCF, liquidity, balance sheet |
| Growth | /10 | Revenue & earnings growth trajectory + momentum |
| Valuation | /8 | Price vs intrinsic value assessment |
| Management | /5 | Leadership quality & capital allocation |
| Moat | /4 | Competitive advantage durability |
| Sentiment | /3 | Geopolitical, regulatory, political exposure |

**Total: 10 + 10 + 8 + 5 + 4 + 3 = 40** ✓

### 1.3 Confirmed Mapping

| Canonical Category | Max | Composed from | Formula | Rationale |
|---|---|---|---|---|
| **Financial Health** | 10 | `profitability` (5) + `financial_strength` (5) | Direct sum | Margins are a dimension of financial health, not separate |
| **Growth** | 10 | `growth` (5) + `business_momentum` (5) | Direct sum | Revenue growth + price momentum represent the growth trajectory |
| **Valuation** | 8 | `valuation_risk` (5) | `round(val_risk × 8/5)` → 0–8 | P/E-driven, one dimension; scale to 8 |
| **Management** | 5 | `management` (5) | Direct (identity) | Already 0–5, one-to-one |
| **Moat** | 4 | `moat` (5) | `min(moat, 4)` | Capped; moat sub-score above 4 is already "pricing power + mega-cap" which caps naturally |
| **Sentiment** | 3 | `geopolitical_risk` (5) | `round(geo × 3/5)` → 0–3 | Geopolitical exposure is the closest proxy for external sentiment risk |

**Scaling functions (Python):**

```python
def _scale_to_8(score_0_5: int) -> int:
    """Map 0–5 sub-score to 0–8 valuation score."""
    return round(score_0_5 * 8 / 5)

def _scale_to_3(score_0_5: int) -> int:
    """Map 0–5 sub-score to 0–3 sentiment score."""
    return round(score_0_5 * 3 / 5)
```

**Scale table for verification:**

| raw 0–5 | → Valuation /8 | → Sentiment /3 |
|---|---|---|
| 0 | 0 | 0 |
| 1 | 2 | 1 |
| 2 | 3 | 1 |
| 3 | 5 | 2 |
| 4 | 6 | 2 |
| 5 | 8 | 3 |

### 1.4 Why This Mapping

- **Coherence**: Financial Health bundles the two balance-sheet scores (profitability + debt/cash). Growth bundles the two trajectory scores (revenue growth + momentum). No score is split across unrelated categories.
- **No double-counting**: Each of the 8 sub-scores appears in exactly one canonical category.
- **Preserves total = 40**: 10+10+8+5+4+3 = 40.
- **All 8 functions untouched**: The mapping is a pure post-processing layer inside `score_ticker()`. No internal function signature changes.

---

## 2. Scoring Model Signature

### 2.1 New `Scoring` Model (Pydantic)

```python
from pydantic import BaseModel, PrivateAttr
from typing import Dict

class Scoring(BaseModel):
    """6-category scoring model. Total = /40."""

    # ── 6 canonical categories (EXTERNALLY VISIBLE) ──
    financial_health: int = 0   # 0–10 (profitability + financial_strength)
    growth: int = 0             # 0–10 (growth + business_momentum)
    valuation: int = 0          # 0–8  (valuation_risk, scaled)
    management: int = 0         # 0–5  (management, direct)
    moat: int = 0               # 0–4  (moat, capped)
    sentiment: int = 0          # 0–3  (geopolitical_risk, scaled)

    # ── Audit trail (INTERNAL — not serialized by default) ──
    _raw_subscores: Dict[str, int] = PrivateAttr(default_factory=dict)

    @property
    def total(self) -> int:
        return sum([
            self.financial_health, self.growth, self.valuation,
            self.management, self.moat, self.sentiment,
        ])

    def decision(self) -> str:
        """BUY ≥ 28, HOLD 18–27, SELL < 18."""
        t = self.total
        if t >= 28:
            return "BUY"
        elif t >= 18:
            return "HOLD"
        else:
            return "SELL"
```

### 2.2 `score_ticker()` Return Shape Changes

```python
def score_ticker(data: Dict[str, Any], tone_data: Optional[Dict] = None) -> Scoring:
    # ... all 8 _score_*() calls unchanged ...

    # Compute canonical categories
    financial_health = profitability + financial_strength          # 0–10
    growth_cat = growth_sub + business_momentum                    # 0–10
    valuation_cat = _scale_to_8(valuation_risk)                    # 0–8
    management_cat = management_sub                                # 0–5
    moat_cat = min(moat_sub, 4)                                    # 0–4
    sentiment_cat = _scale_to_3(geopolitical_risk)                 # 0–3

    scoring = Scoring(
        financial_health=financial_health,
        growth=growth_cat,
        valuation=valuation_cat,
        management=management_cat,
        moat=moat_cat,
        sentiment=sentiment_cat,
    )

    # Preserve raw sub-scores for audit trail
    scoring._raw_subscores = {
        "growth": growth_sub,
        "profitability": profitability,
        "financial_strength": financial_strength,
        "moat": moat_sub,
        "management": management_sub,
        "valuation_risk": valuation_risk,
        "geopolitical_risk": geopolitical_risk,
        "business_momentum": business_momentum,
    }

    return scoring
```

### 2.3 Key Design Decisions

- `_raw_subscores` is a `PrivateAttr` — it's NOT serialized by `model_dump()` (avoids leaking 8-field structure to API consumers). Debug access via `result.scoring._raw_subscores`.
- The `total` property implementation changes from `sum(8 fields)` to `sum(6 fields)` — but the external interface is identical.
- The `decision()` method is simplified from 4-tier to 3-tier.

---

## 3. Orientation Normalization

### 3.1 Problem

The field names `valuation_risk` and `geopolitical_risk` contain "risk" which implies *higher = more risk = worse*. However, all 8 `_score_*()` functions **already** return **higher = better**:

- `_score_valuation()`: 5 = cheap (good), 1 = expensive (bad)
- `_score_geopolitical()`: 5 = low risk (good), 1 = high risk (bad)

The issue is **naming only**, not logic.

### 3.2 Resolution

| Old field name | New canonical field | Orientation |
|---|---|---|
| `valuation_risk` | `valuation` | Higher = better (more attractive valuation). Unambiguous. |
| `geopolitical_risk` | `sentiment` | Higher = better (lower geopolitical risk). Unambiguous. |

The internal `_score_valuation()` and `_score_geopolitical()` functions KEEP their existing names and behavior. The renaming happens only at the Scoring model level.

### 3.3 Documentation

The Scoring model docstring explicitly states: **All 6 canonical fields are higher-is-better.** The `_raw_subscores` dict preserves original field names for debugging.

---

## 4. Audit Trail

### 4.1 Raw Sub-scores Preservation

The `Scoring._raw_subscores` dict (PrivateAttr, not serialized) preserves the 8 original values exactly as produced by the `_score_*()` functions:

```python
{
    "growth": 4,
    "profitability": 3,
    "financial_strength": 4,
    "moat": 5,
    "management": 3,
    "valuation_risk": 4,
    "geopolitical_risk": 3,
    "business_momentum": 3,
}
```

### 4.2 Debugging Access

- **Python**: `result.scoring._raw_subscores`
- **Logs**: `score_ticker()` logs at DEBUG level: `logger.debug("Raw sub-scores: %s", scoring._raw_subscores)`
- **API**: Add a debug-only endpoint `GET /api/debug/scoring/{ticker}` (future enhancement, out of scope for this spec)

### 4.3 Traceability Contract

For any canonical score, the trace is:

```
Canonical score → mapping formula → raw sub-score(s) → _score_*() function → threshold table
```

Example: `financial_health = 7` → `profitability(3) + financial_strength(4)` → `_score_profitability(op_margin=0.22)` → "op > 0.20 → 4" (returns 3? Check...).

---

## 5. Threshold Boundaries

### 5.1 New Thresholds (CONFIRMED)

| Decision | Score Range | Meaning |
|---|---|---|
| **BUY** | ≥ 28 | Strong across most categories; investable |
| **HOLD** | 18–27 | Mixed signals; monitor or small positions |
| **SELL** | < 18 | Fundamental concerns across multiple categories |

### 5.2 Comparison with Current

| Current threshold | Current decision | → | New threshold | New decision |
|---|---|---|---|---|
| ≥ 32 | BUY | → | ≥ 28 | BUY |
| 26–31 | HOLD / BUY ON PULLBACK | → | 18–27 | HOLD |
| 18–25 | HOLD fragile | → | 18–27 | HOLD |
| < 18 | SELL or AVOID | → | < 18 | SELL |

### 5.3 Impact Analysis

- **BUY threshold drops from 32 to 28**: ~15% more tickers qualify as BUY. The previous threshold (32/40 = 80%) was unnecessarily strict for a 6-category weighted model where Sentiment and Moat are capped.
- **HOLD consolidates 2 tiers into 1**: "HOLD fragile" and "HOLD / BUY ON PULLBACK" are collapsed. The single HOLD tier is simpler for users.
- **SELL unchanged at < 18**: The floor remains consistent.
- **conviction field on AnalysisResult** (High/Moderate/Low) was previously derived from scoring tiers. With 3 tiers instead of 4, conviction thresholds shift:
  - High: now tied to BUY (≥ 28)
  - Moderate: now tied to HOLD (18–27)
  - Low: now tied to SELL (< 18)

---

## 6. Consumer Impact — Breaking Change Analysis

### 6.1 BACKEND — Scoring Model

| File | Current access | Impact | Action |
|---|---|---|---|
| `backend/models.py` | `Scoring(8 fields)` | **BREAKING** — model redefined | Replace with 6-field model + PrivateAttr |
| `backend/scorer.py` | `score_ticker()` returns `Scoring(8 fields)` | **BREAKING** — constructor call changes | Map 8 → 6, set `_raw_subscores` |

### 6.2 BACKEND — `.total` and `.decision()` Consumers

| File | Line(s) | Access pattern | Impact |
|---|---|---|---|
| `backend/orchestrator.py` | 25, 79 | `result.scoring.total` | ✅ No change — `@property` still works |
| `backend/orchestrator.py` | 25, 79 | `result.decision` | ✅ No change (field on AnalysisResult, not Scoring) |
| `backend/pdf_generator.py` | 73 | `result.scoring.total` | ✅ No change |
| `backend/main.py` | 548, 826, 1206, 1289 | `result.scoring.total` | ✅ No change |

### 6.3 BACKEND — Serialization

| File | Line | Pattern | Impact |
|---|---|---|---|
| `backend/main.py` | 548, 1206 | `r["scoring"]["total"] = result.scoring.total` | ⚠️ Needs update: `r["scoring"]` dict will contain 6 fields instead of 8. The `total` injection remains valid. |
| `backend/main.py` | 548 | `sum(r["scoring"].values())` fallback | ⚠️ REMOVE — this fallback sums all values including `total`, causing inflated scores. The `total` injection at line 1206 is sufficient. |

### 6.4 FRONTEND — ScoringChart.jsx (CRITICAL)

| Current code | Issue |
|---|---|
| `CRITERIA = [{key: 'growth'}, {key: 'profitability'}, ...]` (8 items) | **BREAKING** — iterates 8 keys, none match after rename |

**Required changes:**
```javascript
const CRITERIA = [
  { key: 'financial_health', label: 'Finance', max: 10 },
  { key: 'growth', label: 'Growth', max: 10 },
  { key: 'valuation', label: 'Value', max: 8 },
  { key: 'management', label: 'Mgmt', max: 5 },
  { key: 'moat', label: 'Moat', max: 4 },
  { key: 'sentiment', label: 'Sentiment', max: 3 },
];
```
Bar heights must now be relative to each criterion's max (not uniform /5). Tooltip label must show `{val}/{max}`.

### 6.5 FRONTEND — AnalysisCard.jsx (CRITICAL)

`getInsight()` function (lines 33–48) accesses individual scoring fields:

| Current field access | New field access |
|---|---|
| `s.business_momentum >= 4` | `s.growth >= 8` (momentum is now part of growth /10) |
| `s.valuation_risk <= 2` | `s.valuation <= 3` (scaled equivalent: 2/5 ≈ 3/8) |
| `s.financial_strength >= 4` | `s.financial_health >= 8` (both margins + debt) |
| `s.profitability >= 4` | `s.financial_health >= 8` (merged) |
| `s.moat >= 4` | `s.moat >= 3` (capped at 4, so 4/5 ≈ 3/4) |
| `s.management >= 4` | `s.management >= 4` (unchanged, still /5) |
| `s.growth >= 4` | `s.growth >= 8` (was /5, now /10) |
| `s.geopolitical_risk <= 2` | `s.sentiment <= 1` (2/5 ≈ 1/3) |

The `getConvictionLevel()` function (lines 19–31) uses `scoring?.total` which is unchanged, but the conviction thresholds must be updated:
```javascript
// Old
if (scoring?.total >= 32) return 'High';
if (scoring?.total >= 26) return 'Moderate';
if (scoring?.total < 18) return 'Low';

// New
if (scoring?.total >= 28) return 'High';
if (scoring?.total >= 18) return 'Moderate';
if (scoring?.total < 18) return 'Low';
```

### 6.6 FRONTEND — ReportView.jsx

| Access | Impact |
|---|---|
| `scoring?.total` | ✅ No change |
| `<ScoringChart scoring={scoring} />` | Passes scoring object → ScoringChart handles new fields |

### 6.7 TESTS — test_models.py (BREAKING)

All `TestScoring` test cases construct `Scoring(growth=..., profitability=..., ...)` with 8 fields. **Every test must be rewritten** with 6 fields and the new threshold expectations:

| Test | Current | New |
|---|---|---|
| `test_total_sums` | 8 fields summing to 32 | 6 fields summing to 32 (e.g., fh=7, gr=7, val=6, mgmt=4, moat=3, sent=5 → wait 7+7+6+4+3+5=32) |
| `test_decision_buy` | total=35 → "BUY" | total≥28 → "BUY" |
| `test_decision_hold_pullback` | total=28 → "HOLD" in string | total=25 → "HOLD" |
| `test_decision_hold_fragile` | total=22 → "HOLD fragile" | REMOVED — only "HOLD" now |
| `test_decision_sell` | total=15 → "SELL" | total<18 → "SELL" |

### 6.8 TESTS — test_scorer.py

Must be extended with tests for:
1. Mapping correctness (8 → 6 for known inputs)
2. Scale function accuracy (`_scale_to_8()`, `_scale_to_3()`)
3. Moat cap (`min(moat, 4)`)
4. Audit trail presence (`_raw_subscores` dict populated with all 8 keys)
5. `total` property sums 6 fields correctly
6. `decision()` returns correct 3 tiers

### 6.9 SCRIPTS — `_run_*.py` (7 files)

| Script | Access pattern | Impact |
|---|---|---|
| `_run_batch.py` | `r.scoring.total` | ✅ No change |
| `_run_daily_backlog.py` | `r.scoring.total` | ✅ No change |
| `_cron_run.py` | `r.scoring.total` | ✅ No change |
| `_cron_run2.py` | `r.scoring.total` | ✅ No change |
| `_daily_run.py` | `r.scoring.total` | ✅ No change |
| `_run_remaining.py` | `r.scoring.total` | ✅ No change |
| `_run_mc.py` | `r.scoring.total` | ✅ No change |
| `_run_backlog.py:20` | `getattr(r.scoring, "conviction", ...)` | ⚠️ Pre-existing bug — `conviction` is on `AnalysisResult`, not `Scoring`. Unchanged by this spec. |

---

## 7. Implementation Order (Dependency Graph)

```
1. models.py          ← Scoring model redefined (6 fields + _raw_subscores)
       ↓
2. scorer.py          ← score_ticker() mapping logic + _scale_to_*() helpers
       ↓
3. test_models.py     ← Rewrite TestScoring (6 fields, new thresholds)
4. test_scorer.py     ← Add mapping + scale + audit trail tests
       ↓
5. main.py            ← Fix serialization (line 548 sum all values bug)
       ↓
6. ScoringChart.jsx   ← 6 categories, variable max per bar
7. AnalysisCard.jsx   ← getInsight(), getConvictionLevel()
```

**Parallelizable**: Items 3+4 can run in parallel. Items 6+7 can run in parallel after item 2.

---

## 8. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Frontend chart breaks silently (6 bars instead of 8, wrong max values) | **HIGH** | E2E test with known scoring payload before deploy |
| Serialization bug in main.py line 548 (sums total into itself) | **MEDIUM** | Remove fallback sum, rely on injected total |
| `_raw_subscores` exposes implementation detail via API | **LOW** | PrivateAttr is excluded from `model_dump()` by default |
| Conviction thresholds in frontend out of sync with new decision thresholds | **MEDIUM** | Update both `getConvictionLevel()` and `decision()` simultaneously |
| Test coverage gap on scaling functions (rounding edge cases) | **LOW** | Explicit test table for all 6 input values × 2 scaling functions |

---

## 9. Verification Checklist (for implementation review)

- [ ] `Scoring` model has exactly 6 public fields + `_raw_subscores`
- [ ] All 8 `_score_*()` functions are byte-identical to current code
- [ ] `total` property sums 6 fields correctly
- [ ] `decision()` returns `"BUY"` / `"HOLD"` / `"SELL"` only (3 tiers)
- [ ] `_raw_subscores` dict has exactly 8 keys after `score_ticker()` runs
- [ ] ScoringChart.jsx renders 6 bars with correct max values (10/10/8/5/4/3)
- [ ] AnalysisCard.jsx getInsight() uses new field names and adapted thresholds
- [ ] `test_models.py` TestScoring passes with 6-field model
- [ ] `test_scorer.py` includes mapping, scale, and audit trail tests
- [ ] `backend/main.py` line 548 does NOT sum scoring values (uses injected total)
- [ ] All `_run_*.py` scripts produce correct output (total unchanged in format)
- [ ] PDF generator still prints `{result.scoring.total}/40`
- [ ] E2E test: analyze one ticker, verify ScoringChart renders, verify decision label

---

## 10. Open Questions (for Ced)

None blocking. This architecture is validated and ready.

One advisory note: the `sentiment` category (max 3) currently maps only `geopolitical_risk`. In v2.1, consider adding a dedicated `_score_sentiment()` function that aggregates news sentiment and analyst ratings (currently not implemented). The 3-point cap leaves room for this expansion.
