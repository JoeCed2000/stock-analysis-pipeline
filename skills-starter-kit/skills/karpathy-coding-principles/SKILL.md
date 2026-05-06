---
name: karpathy-coding-principles
description: "Karpathy's 4 coding principles for AI agents — Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution. Derived from Andrej Karpathy's observations on LLM coding pitfalls (102k+ stars repo). Applied as a mandatory self-check before any code generation task."
category: software-development
trigger:
  - Before any code generation or file modification
  - Before proposing an architecture or implementation plan
  - When reviewing code (self-review or Codex output)
  - "Karpathy check"
---

# Karpathy Coding Principles for Hermes

From [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (103k stars), derived from Andrej Karpathy's observations on LLM coding pitfalls.

**Tradeoff**: These guidelines bias toward caution over speed. For trivial tasks (typo, doc fix), use judgment.

---

## 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

**Before implementing:**
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.
- **Never hardcode values that can change** — IPs, URLs, ports, hostnames, API keys, thresholds. Use config files, environment variables, BuildConfig, or resource files. A hardcoded IP breaks silently when the network changes. **Caught 2026-05-04**: `100.116.52.125` hardcoded in 2 files → replaced with Tailscale DNS hostname via BuildConfig.

## 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

**Test**: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 2a. YAGNI for Shared Infrastructure (Client, Pool, Cache)

When creating shared infrastructure (HTTP clients, connection pools, caches):
- **Start with the absolute minimum viable.** `httpx.Client(timeout=30)` — nothing else.
- Features are added ONE-BY-ONE with a test or verified need. Never as a "package deal."
- **No speculative configuration** — `http2=True` without `h2` installed → guaranteed crash. `max_connections=50` without load testing → cargo cult.
- Each addition must answer: "What breaks without this?" If nothing breaks, don't add it.
- **Pitfall caught 2026-05-05**: `http2=True` added "just in case" to shared httpx client. Crash at import time because `h2` package wasn't installed. Would have been caught by: start with `httpx.Client(timeout=30)`, add features one by one.



### 2b. Fix Sale → Nettoyé Immédiatement

Un fix rapide écrit avec des patterns dynamiques ou fragiles ne survit pas à la session.

**Patterns interdits sans nettoyage immédiat :**
- `__import__("package").Something` — utiliser `import package` explicite
- `eval()`, `exec()` — sauf cas très spécifiques documentés
- `getattr(obj, dynamic_string)` où `dynamic_string` vient d'une source externe
- Commentaire `# TODO` ou `# FIXME` sans ticket associé
- `except Exception: pass` — au minimum logger l'erreur

**Règle** : Si un fix utilise un de ces patterns → le commit SUIVANT doit le nettoyer. Le fix sale ne passe pas la nuit.

**Pitfall caught 2026-05-05** : `__import__("httpx").TimeoutException` écrit comme fix rapide dans translator.py, laissé en place 3 jours. Codex l'a trouvé et corrigé en 30 secondes. Coût : 0. Le problème n'était pas le fix — c'était de ne pas l'avoir nettoyé immédiatement après.

Touch only what you must. Clean up only your own mess.

**When editing existing code:**
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

**When your changes create orphans:**
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

**The test**: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

Define success criteria. Loop until verified.

**Transform tasks into verifiable goals:**
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

**For multi-step tasks, state a brief plan:**
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### 4a. Commit After Every Working Change (MANDATORY)

**No commit = no safety net.** A fix that works but isn't committed is volatile — a single `rm -rf`, cross-fs corruption, or mistaken overwrite destroys it.

- Commit atomically after **every** feature/fix that works — don't batch unrelated changes
- Message: `type: what changed and why` (e.g. `fix: de-hardcode API URL → BuildConfig`)
- If the project has no Git repo → `git init` before making changes, never after
- If the project has a remote → push after commit
- **Anti-pattern caught 2026-05-04**: 3 files modified + build + deploy. Zero commits. No `.git` directory existed. User corrected via "cl" codeword.

## 5. When to Refactor vs Patch

Not all fixes should be incremental patches. Recognizing when to refactor is a core skill.

**Patch** when:
- The fix is <10 lines and contained to one function
- You understand exactly why the current code is wrong
- The fix doesn't change control flow or architecture
- The current design is fundamentally correct but has a bug

**Refactor** when:
- You've patched the same function 3+ times in one session
- The current design makes the correct behavior impossible (e.g., `UPLOAD_SECRET` read at module level before `.env` is loaded — patching won't fix it, the architecture must change)
- The fix requires restructuring control flow (sync vs async, module-level vs function-level)
- A previous patch introduced a new bug that also needs fixing

**Red flag:** "One more patch will fix it" after 3 failed patches → you need a refactor, not another patch. Stop patching. Redesign.

**Case study (stock-analysis-pipeline, 2026-05-04):** 8 patches applied to `async_dossier.py` and `main.py` over 70 minutes. Root cause: background thread was fundamentally unreliable on Render. Fixing individual thread steps wouldn't help — the entire architecture needed to move to synchronous generation. One refactor (move all generation into `analyze_ticker_fast`) replaced all 8 patches.

---

## Hermes Application

**When generating code (self or via Codex):**
- Run the 4-principle checklist BEFORE writing
- After writing: diff check — does every changed line trace to the request?
- After Codex returns code: apply this review lens

**Integration with existing methodology:**
- Principle 1 → Phase 0/1 of HERMES.md (cadrage + discovery)
- Principle 2 → Phase 2 (architecture — simplest robust approach)
- Principle 3 → Phase 4/6 (implementation + integration scope control)
- Principle 4 → Phase 7 (test-driven validation)

**These guidelines are working if**: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## KARPATHY.md — Fichier de transmission

Le fichier `/mnt/c/Users/cedon/Documents/Codex/micro_trading_lab/KARPATHY.md` contient :
- Les 4 principes détaillés
- Un prompt de délégation type prêt à copier-coller
- Les signes d'alerte (STOP immédiat)
- Les principes d'agentic engineering (Karpathy 2026)
- Les patterns de code "gros" à détecter

Transmettre ce fichier à tout agent IA avant une session de développement.
