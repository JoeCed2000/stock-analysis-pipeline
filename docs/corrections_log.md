# Corrections Log — Stock Analysis Pipeline

> 📚 **Purpose:** Every correction from Nami's live chat is logged here with root cause analysis.
> This is the "brain" that accumulates knowledge — the feedback pipeline **apprend** de chaque bug
> pour réduire les bugs futurs.

## How It Works

```
Nami: "Le PEG est faux sur NVDA"
        ↓
_detect_feedback() → type: "correction"
        ↓
tb preflight -q → 🔒 GO
        ↓
Kanban task créée + dispatched
        ↓
python-builder fix → reviewer-qa validate → deploy
        ↓
_send_completion_response() → _learn_from_fix()
        ↓
📝 Logged here with: category, root cause, suggested validator rule
```

## Categories

| Category | Description | Typical Root Cause |
|---|---|---|
| `data_source` | API/provider/data issue | Missing yfinance field, stale cache, wrong source |
| `prompt_quality` | LLM output quality | Missing instruction, ambiguous prompt |
| `renderer_logic` | PDF/display rendering | Layout bug, truncation, wrong helper |
| `calculation_error` | Math/formula bug | Wrong computation, double-count, sign error |
| `i18n_missing` | Translation/language | Missing JP label, EN-only text |
| `frontend_display` | UI/UX issue | React state, conditional rendering, CSS |
| `validator_gap` | Should have been caught | Missing pre-render rule, weak validation |

## Learning Metrics

Tracked automatically:
- **Corrections per week** → trending down = learning works
- **Repeated categories** → signal to harden that validator
- **Validator rules added** → proactive prevention

---

## History

| Date | Source | Description | Category | Root Cause | Fix | Validator |
|------|--------|-------------|----------|------------|-----|-----------|
| 2026-05-30 | Live Chat (Nami) | NVIDIA PEG = 0.66 is incorrect | `calculation_error` | PEG used yfinance `pegRatio` (forward-looking, 5yr expected growth = ~25%). This was inconsistent with trailing data displayed alongside (trailing PE 32.38, trailing EPS growth 214.5%). `pegRatio * implied_growth = 32.38/0.66 = 49%`, but actual trailing growth is 214.5%. | Changed all 3 code paths to compute trailing PEG = trailing PE / (earningsGrowth × 100) = 32.38/214.5 = 0.15. Fixed `mapper.py:_build_valuation_section`, `mapper.py:_build_valuation_context`, `company_overview_pdf.py:_render_kpis`. | Added `test_peg_ttm_nvda_like` regression test in `test_valuation_context.py`. |

<!-- Entries appended automatically by _learn_from_fix() in feedback_pipeline.py -->
