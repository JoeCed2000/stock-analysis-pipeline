# Context Compaction → Lost Project Focus

## Pattern

After a session with multiple project switches gets compacted into a summary, the agent resumes
by acting on the summary's claims without verifying the active project. This causes the agent to
modify files in the WRONG project — a catastrophic error.

## How it happens

1. Context compaction merges work across 2+ projects (e.g., AlphaRadar + stock-analysis-pipeline)
2. Summary mentions pending work in Project A ("ticker validation fix en cours sur Android")
3. Agent resumes with a "Hello" → startup checklist → "Reprise de la session précédente..."
4. Agent navigates to Project A and starts modifying files
5. User corrects: "C'est parce que tu n'es pas sur le bon projet !"

## Detection signals

- User says "tu n'es pas sur le bon projet", "tu as divergé", "cherche dans X"
- `git log` in the current directory shows commits from a different project
- The project root doesn't match what the user is describing
- You're modifying Kotlin files when the user is talking about Python/React

## Prevention checklist (after context compaction)

Before modifying ANY file:
1. Identify the project the user is CURRENTLY talking about — not what the summary mentions
2. `read_file(AGENTS.md)` in the candidate project → verify the stack matches
3. `git log --oneline -3` → verify recent commits match the expected project
4. If uncertain → ASK "On est bien sur [projet] ?" before touching any file
5. Wiki-first: check `Codex/docs/llm-wiki/projects/<Project>.md` for project identity

## Concrete case (2026-05-04)

- Compaction merged AlphaRadar (Android/Kotlin ticker validation) + stock-analysis-pipeline (React/Python ticker validation)
- Agent resumed with Android fix, modified `WatchlistActions.kt` with broken code
- User: "C'est parce que tu n'es pas sur le bon projet ! Tu as divergé mais il faut chercher dans stock analysis"
- Root cause: agent trusted compacted context which mentioned "ticker validation en cours sur l'Android"
  instead of asking "which project are we working on?"

## Related
- `agentic-engineering-review` §13 — CONTEXTE COMPACTÉ ≠ VÉRITÉ
- `session-startup-checklist` Phase 2 — TARGET_PROJECT check
