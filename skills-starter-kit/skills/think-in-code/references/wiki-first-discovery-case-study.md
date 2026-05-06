# Wiki-First Discovery — Session Case Study (2026-05-04)

## The Mistake

Session started with user saying "discovery du codebase". Instead of checking the wiki,
I did manual discovery:

```
find /home/ced/Codex -maxdepth 4 -type f -name "pipeline.py"
find /home/ced -maxdepth 3 -type d -name "*stock*analysis*"
find /home/ced /mnt/c/Users/cedon -maxdepth 4 -type f -name "alpha_vantage.py"
find /mnt/c/Users/cedon/Documents/Codex -maxdepth 4 ...
```
**Result:** 6 find/search_files calls, 4 read_file calls, ~45s spent. Project not found at first.

## The Fix

Wiki page existed at `Codex/docs/llm-wiki/projects/Stock_Analysis_Pipeline.md` with:
- Path: `/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline`
- Stack: React, Vite, Python, FastAPI
- 7 endpoints (GET/POST)
- Architecture from AGENTS.md
- LOC: 8,157
- Test commands

**1 read_file** would have given everything in ~3s.

## Cost Comparison

| Approach | Tool calls | Time | Information |
|----------|-----------|------|-------------|
| Manual discovery | 10-15 (find + search_files + read_file) | ~60s | Fragmented, partial |
| Wiki-first | 1 (read_file) | ~3s | Complete: path, stack, endpoints, architecture, conventions |

## User Correction

> "Pour le discovery du codebase tu devrais toujours regarder le Wiki en premier !"

User was right. The wiki page also had duplicate "Express" entries (generator bug) —
fixed during the session by removing them and adding the new batch endpoints.
