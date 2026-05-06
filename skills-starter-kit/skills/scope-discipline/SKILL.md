---
name: scope-discipline
description: Prevents working on adjacent projects without explicit user request. Triggered when user mentions another project in passing — ask before acting.
version: 1.0.0
metadata:
  hermes:
    tags: [discipline, scope, project-management]
    priority: critical
---

# Scope Discipline

## The Rule

**Never work on a project the user hasn't explicitly asked you to modify.**

If the user mentions another project in passing ("AlphaRadar aussi faudrait...", "TradingAgents a le même problème..."), it is NOT permission to start working on it.

## Trigger

Any message that mentions a project OTHER than the one currently being worked on.

## Response Required

Before touching ANY file in another project:

1. Acknowledge the mention
2. Ask: "Tu veux que je m'en occupe maintenant ou je reste sur [current project] ?"
3. Only proceed if the user explicitly says yes

## Why

- Context switching without permission creates chaos
- The user may have a specific order/priority in mind
- Multi-project work without coordination causes merge conflicts and lost work
- "Fais toi plaisir" ≠ "travaille sur tous mes projets en même temps"

## Anti-pattern

```
User: "Le pipeline est lent. AlphaRadar a le même problème de perf d'ailleurs."
Agent: *commence à modifier AlphaRadar* ❌
```

## Correct

```
User: "Le pipeline est lent. AlphaRadar a le même problème de perf d'ailleurs."
Agent: "Noté pour AlphaRadar. Tu veux que je regarde maintenant ou je finis le pipeline d'abord ?"
User: "Pipeline d'abord."
Agent: *continue sur le pipeline* ✅
```

## Exception

If the user EXPLICITLY says "fais les deux" or "passe sur AlphaRadar", it's a direct instruction — follow it.
