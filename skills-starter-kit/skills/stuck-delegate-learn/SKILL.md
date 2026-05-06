---
name: stuck-delegate-learn
description: "When Hermes loops 3+ times on the same bug, stop, delegate to Codex, and learn from the outcome — instead of burning more turns in circles."
version: 1.0.0
metadata:
  hermes:
    tags: [delegation, anti-pattern, learning, codex, hermes-orchestration]
---

# Stuck → Delegate → Learn

## Trigger

Activate this skill when:
- You've attempted the same fix 3+ times without success
- You're guessing parameters/signatures instead of inspecting them
- You're reading the same error message for the third time
- You feel the urge to say "let me try one more thing"

## Rule

> **3 strikes → delegate.** Do NOT attempt a 4th blind fix.

## Procedure

1. **Admit you're stuck.** Say it explicitly: "I'm looping on this, let me delegate."
2. **Package full context** — include:
   - The error + full traceback
   - What you've tried (all attempts)
   - File paths and relevant code snippets
   - Your current hypothesis
3. **Delegate to Codex** with a clear goal: "Fix X" or "Explain why Y is happening"
4. **Read the result carefully.** Don't just apply the fix — understand it.
5. **Update memory/skills** with what you learned. The most valuable outcome is not the fix itself — it's understanding the *category* of mistake so you don't make it again.

## Anti-patterns

- "Let me try with different parameters" (without knowing what they do)
- "Maybe if I restart the server" (without checking if the old one is still running)
- "Let me check the logs again" (after already checking them twice)
- "I'll just try a slightly different approach" (without understanding why the first one failed)
- **"I'll delegate 3 independent tasks in parallel"** — when all 3 need to write files or call rate-limited APIs (e.g., skill_manage). Batch delegation to sub-agents works for READ-ONLY tasks (audit, search, review). For WRITE-heavy tasks, sub-agents fail silently (timeout, HTTP 429, empty output). Do them sequentially or handle the first one yourself to validate the approach, then delegate the rest. See 2026-05-04 session: 3 parallel delegates → 0/3 usable output.

## Today's example

F5-TTS BytesIO bug: Hermes tried 3 different workarounds (different response types, different WAV encoding) instead of delegating to Codex immediately. Codex found the root cause (`torchaudio.save(BytesIO)` → `soundfile`) in minutes. Cost: ~30 min of looping vs ~5 min of delegation.

## The meta-lesson

Knowing *when* to delegate is as important as knowing *how* to code. The best orchestrator doesn't do everything — they know when to hand off.

## Patch Counter

**When fixing the same bug:** keep a mental count of consecutive patches applied to the same file/function in one session.

- 1-2 patches → normal debugging
- 3 patches → ⚠️ WARNING: you're probably guessing. Stop. List hypotheses. Test the simplest one first.
- 4+ patches → 🔴 DELEGATE: you're in a loop. Package full context and delegate to Codex immediately.

**Anti-pattern:** 10+ commits fixing the same 2 files (`async_dossier.py`, `main.py`) in one session without ever delegating. Each patch reveals a new symptom; the root cause was never found.

**Case study (stock-analysis-pipeline, 2026-05-04):** 15 commits in 70 minutes on the same 3 files. Bugs #2-8 were all symptoms of the same architectural flaw (background thread on Render). A single delegation after the 3rd failure would have revealed this in 5 minutes instead of 50.
