# Post-Mortem Template — Agentic Projects

Template for project post-mortems. Created after the AlphaRadar porting session (May 3, 2026) and refined during the stock-analysis-pipeline deployment (May 4, 2026).

## When to Write

After any project phase with ≥3 issues, failures, or lessons learned. Particularly useful after:
- Deployment to production (Vercel/Render)
- Cross-codebase porting (Kotlin → Python, Android → Web)
- Security incidents
- Complex debugging sessions

## Template

```markdown
# Post-Mortem — <Project Name>

**Date**: YYYY-MM-DD
**Project**: `<repo-name>`
**Stack**: <backend> + <frontend>
**Deployment**: <Render/Vercel/etc.>
**Repo**: https://github.com/USER/repo

## 1. What Worked

| Domain | Result |
|---|---|
| ... | ... |

## 2. What Broke / Slowed

| Problem | Cause | Fix |
|---|---|---|
| ... | ... | ... |

## 3. Lessons Learned

1. **Lesson** — context
2. ...

## 4. Future Improvements

- [ ] ...
```

## Real-World Examples

- `Codex/stock-analysis-pipeline/POSTMORTEM.md` — 9 problems, 5 lessons (deployment)
- AlphaRadar porting session — 9 procedural failures (cross-codebase)

## Rules

- Be concrete: every problem cites a specific file, command, or error message
- Distinguish root cause from symptom
- Every lesson must be actionable (a future agent reading it should know exactly what to do differently)
- Keep under 100 lines — a post-mortem is a briefing, not a novel
