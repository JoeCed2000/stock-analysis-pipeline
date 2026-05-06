# Pydantic @property Serialization Pitfall

## The Bug

Pydantic `model_dump()` does **NOT** include `@property` computed fields. They are silently dropped from the serialized output.

```python
from pydantic import BaseModel

class Scoring(BaseModel):
    growth: int = 0
    profitability: int = 0

    @property
    def total(self) -> int:
        return self.growth + self.profitability

s = Scoring(growth=5, profitability=4)
print(s.total)           # 9 ✅
print(s.model_dump())    # {'growth': 5, 'profitability': 4} ❌ total missing!
```

**Symptom:** Frontend receives `scoring: {growth: 5, ...}` but `total` is `undefined` → displays as 0.
**Root cause:** `@property` is a Python descriptor, not a Pydantic field. `model_dump()` only serializes fields.

## Fix

### Option A: Manually inject in API layer (fastest)
```python
r = result.model_dump()
if "scoring" in r:
    r["scoring"]["total"] = result.scoring.total  # inject computed value
```

### Option B: Use `model_validate` + `model_dump` with `computed_field`
```python
from pydantic import computed_field

class Scoring(BaseModel):
    growth: int = 0
    profitability: int = 0

    @computed_field
    @property
    def total(self) -> int:
        return self.growth + self.profitability
```
Pydantic v2 only. Not supported in v1.

### Option C: Make it a regular field with a default factory
```python
class Scoring(BaseModel):
    growth: int = 0
    profitability: int = 0
    total: int = 0  # populated manually after init
```
Lose the auto-compute property. Must set manually.

## Detection

If frontend shows a value as 0/null/undefined but the Python object has the correct value → suspect a `@property` that Pydantic didn't serialize.

**Quick check:** `print(result.model_dump()["scoring"].keys())` — if `total` is missing, it's this pitfall.

## Real case (2026-05-04)

Stock Analysis Pipeline: `Scoring.total` is a `@property` summing 8 criteria. `model_dump()` in `backend/main.py` omitted `total` from the API response. Frontend `AnalysisCard` displayed "Score 0/40" for all 5 tickers because `scoring.total` was `undefined` in JS. Fixed by manually injecting `r["scoring"]["total"] = result.scoring.total` in the API handler.

**Files involved:** `backend/models.py` (Scoring class), `backend/main.py` (analyze endpoint), `frontend/src/components/AnalysisCard.jsx` (display).
