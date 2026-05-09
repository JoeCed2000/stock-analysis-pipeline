# Codex Mission — Stock Analysis Pipeline: PDF Parity Fix

## CONTEXT
Stock Analysis Pipeline in `/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/`.
Generates earnings deep-dive PDF reports. Target: parity with model PDF at `docs/specs/modele.pdf`.

Server running on `localhost:8780` (FastAPI). LLM providers: DeepSeek (primary, works), Gemini (fallback, works).
.env at project root has all keys. NEVER commit .env.

## REMAINING ISSUES (verified 2026-05-09)

### P0.1 — Emoji Rendering Broken
- **Symptom**: Section titles show Greek chars (Ὄ) instead of emojis (📊)
- **Root cause**: `/home/ced/.fonts/Symbola.ttf` is NOT a proper emoji font — maps U+1F300+ codepoints to random Greek glyphs
- **Fix**: In `backend/earnings_deep_dive/pdf_renderer.py`:
  1. Remove `_register_symbola()` call and Symbola font registration
  2. Update `_SECTION_PREFIXES` (line ~71) and `_SECTION_PREFIXES_JP` to use ONLY Unicode BMP symbols that exist in DejaVu Sans / Arial
  3. Remove `_wrap_emoji()` or make it a no-op
  4. Remove `_EMOJI_PATTERN` usage in `_glyph_safe()` (line ~219) — let emoji chars be stripped as before
  - Mapping: 📊→▸, 🌟→★, ⚠️→⚠, 🧠→◆, 💵→$, 🏦→◈, 🧩→◫, 📈→▲, 📦→■, 🔮→◇, 🏆→♛, 👉→→
  - These symbols MUST exist in DejaVu Sans (test with `_glyph_safe()`)

### P0.2 — Backlog Section Missing
- **Symptom**: `📦 Backlog Quality` section shows "Section unavailable. Not disclosed."
- **Root cause**: LLM returned no valid markdown table → validator rejected it → placeholder
- **Fix in `backend/earnings_deep_dive/generator.py`**:
  1. Find the Backlog section generation (around line 102-110)
  2. Increase max_tokens for Backlog from 2000 to 3000 (it needs a table)
  3. Add retry with explicit instruction: "You MUST include a markdown table with columns: Metric, Value, Change, Visibility Signal, Source"
  4. In `backend/earnings_deep_dive/validators.py`: check if Backlog validation is too strict — the table format might be different from what the validator expects. The model PDF uses a simpler Backlog format.

### P1.1 — "?" Characters in Prose
- **Symptom**: `"EPS missed estimates by 16% ? a mixed quarter"` — question marks where there should be em-dashes or nothing
- **Root cause**: LLM output contains `?` where it meant to write `—` or where it's uncertain; `_clean_prose()` in `mapper.py` line 1201-1213 only catches runs of 3+ `?`
- **Fix in `mapper.py`**: 
  1. After `_GARBAGE_RE`, add: replace isolated ` ? ` (space-question-space) with ` — ` (space-emdash-space)
  2. Replace ` ?\n` with `.\n`

### P1.2 — Content Truncation
- **Symptom**: Sections end mid-sentence (e.g., "the 200bps" cut off)
- **Root cause**: `SECTION_MAX_CHARS = 2400` (generator.py line 43) is too low for complex sections
- **Fix**: Increase to 3200 for all sections, or selectively increase for Operating Metrics, Cash Flow, Verdict (the densest sections)
- **File**: `generator.py` line 43 and the per-section `max_tokens` calls

### P2.1 — Table Column Names Differ from Model
- Model PDF uses: Estimate | Actual | YoY Change (no "vs Estimate" column)
- Generated uses: Estimate | Actual | vs Estimate | YoY Change
- **Fix**: This is a design choice — "vs Estimate" adds value. Keep it but add a comment.

### P2.2 — Missing "一口まとめ" (One-line Summary) Boxes
- Model PDF ends each section with a summary box
- Generated has "takeaway" lines but not styled as boxes
- **Low priority** — skip for now, note for future

## PLAN

### Step 1: Fix Emojis (P0.1)
1. Read `backend/earnings_deep_dive/pdf_renderer.py` fully
2. Backup: `cp pdf_renderer.py pdf_renderer.py.bak-$(date +%Y%m%d-%H%M%S)`
3. Replace `_SECTION_PREFIXES` with BMP-safe symbols
4. Comment out `_register_symbola()` call (line 472)
5. Make `_wrap_emoji()` a no-op or remove it
6. In `_glyph_safe()` (line ~219), strip emoji chars instead of keeping them
7. Test rendering: `python3 -c "from backend.earnings_deep_dive.pdf_renderer import _SECTION_PREFIXES; print(_SECTION_PREFIXES)"`
8. Commit: "fix: replace broken Symbola emoji font with BMP-safe Unicode symbols"

### Step 2: Fix Backlog Section (P0.2)
1. Read `generator.py` fully, focus on Backlog section generation
2. Read `validators.py`, focus on `check_table_presence` for Backlog
3. Read `prompts.py`, find Backlog prompt template
4. Make Backlog validator less strict OR improve prompt to generate correct table
5. Test: regenerate Backlog section only
6. Commit: "fix: Backlog section table validation + prompt improvement"

### Step 3: Fix "?" Prose + Truncation (P1.x)
1. In `mapper.py` `_clean_prose()`: add isolated-? fix
2. In `generator.py`: increase SECTION_MAX_CHARS to 3200
3. Commit: "fix: clean isolated ? in prose, increase section max chars to 3200"

### Step 4: Full Regeneration + Verification
1. Kill+restart server with `find backend/ -name __pycache__ -exec rm -rf {} \;`
2. Regenerate AAPL: `curl -X POST http://localhost:8780/api/dossier/AAPL/download?quarter=2026Q1`
3. Extract PDF from ZIP
4. Verify:
   a. `python3 -c "import fitz; doc=fitz.open('pdf'); [print(p.get_text()[:100]) for p in doc]"`
   b. Check 0 occurrences of "Section unavailable"
   c. Check emojis are BMP symbols (▸ ★ ⚠ ◆ etc.), NOT Greek chars (Ὄ ἱ ᾞ)
   d. Check 0 occurrences of isolated " ? "
   e. Check Backlog section has a table, not placeholder

## FILES ALLOWED
- `backend/earnings_deep_dive/pdf_renderer.py`
- `backend/earnings_deep_dive/generator.py`
- `backend/earnings_deep_dive/validators.py`
- `backend/earnings_deep_dive/mapper.py`
- `backend/earnings_deep_dive/prompts.py`

## FILES FORBIDDEN
- `.env` — NEVER read or modify
- `docs/specs/` — read-only reference
- Any file outside `stock-analysis-pipeline/backend/earnings_deep_dive/`

## CONTEXT FILES (read first)
- `docs/specs/modele_expected_chatgpt.json` — canonical spec
- `docs/specs/modele.pdf` — reference PDF (14 pages, Japanese template)
- `AGENTS.md` — project rules

## RULES
- Backup before EVERY file modification
- Atomic commits after each fix
- NEVER use replace_all=true on code
- NEVER commit .env
- Test after each fix before moving to next
- If stuck more than 3 attempts on same issue → report and move on