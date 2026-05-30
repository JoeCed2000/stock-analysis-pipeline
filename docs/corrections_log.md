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

<!-- Entries appended automatically by _learn_from_fix() in feedback_pipeline.py -->
