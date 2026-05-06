# Pitfall: Timestamps in Dedup Keys

## Symptom
A deduplication mechanism exists but fails silently — every poll adds a new entry despite identical content.

## Root Cause
The dedup key includes a **timestamp or timer** that changes on every iteration. Even though the base content is identical, the timestamp makes each entry "unique".

## Real Case — Gemini Cockpit Timeline (2026-05-04)
The `_append_step` function correctly deduplicated consecutive identical steps. But the stored step text was `"Gemini is processing... [05:23]"` — the timer `[MM:SS]` changed every second. Result: 31 identical entries instead of 1.

**Fix:** Store the base step text for dedup, attach the timer only for live display.
```python
# ❌ Wrong — timer in dedup key
job.steps_json = _append_step(steps, f"{step} [{mins:02d}:{secs:02d}]")

# ✅ Right — base text for dedup, timer for display only
job.current_step = f"{step} [{mins:02d}:{secs:02d}]"  # display
job.steps_json = _append_step(steps, step)             # dedup
```

## Detection Pattern
If you see N entries that differ only by a number/timestamp, the dedup key is flawed. Check what goes into the dedup comparison — strip dynamic parts before comparing.
