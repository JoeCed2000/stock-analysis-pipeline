# Final NVDA PDF Audit — after feedback-fix Kanban wave

Date: 2026-06-17
Task: `t_6f9613ac` — Audit regenerated NVDA PDF after feedback fixes
Verdict: **REQUEST_CHANGES**

## Scope

Audit of the regenerated NVDA FY2027 Q1 Earnings Deep-Dive outputs after the seven parent feedback-fix cards completed.

Parent fixes expected to be integrated:
- Net Cash value fixed to **$72.1B**.
- Revenue estimate policy accepts **Investing.com 79.19B** as explicitly cited consensus override.
- Source column moved into a table note where applicable.
- Quality section removed within approved scope.
- Profitability / Capital Efficiency explanation condensed.
- EPS & Revenue wording shortened.
- Title includes earnings date **2026-05-20**.

## Evidence gathered

- Backend health: `GET http://127.0.0.1:8780/api/health` returned HTTP 200.
- Backend commit reported by health endpoint during audit: `ad32bb0`.
- Generated fresh EN and JP deep-dive markdown via `/api/earnings/deep-dive` into:
  - `analyses/nvda_audit_en/`
  - `analyses/nvda_audit_jp/`
- Both generation runs completed and produced `deep_dive_validation.json` with `passed: true` and no validator issues.
- Audit was performed on the regenerated markdown because the previous PDFs in `reports/generated/` were stale relative to the June 16/17 parent fixes.

## Findings

### 1. EN EPS & Revenue table still misses the consensus overrides

Observed in regenerated EN output:

```text
| EPS | — | — | — | — | Not disclosed in quarterly filing or transcript |
| Revenue | — | $82B | — | +85% | Earnings Call transcript, total revenue statement |
```

Expected:
- EPS estimate should use the approved consensus override **$1.77**.
- Revenue estimate should use the approved Investing.com consensus override **$79.19B**.
- Source should cite the approved source policy, not fall back to missing/filing/transcript wording.

Impact: **client-facing financial table remains incorrect/incomplete**.

### 2. JP output uses wrong estimate/source values

Observed in regenerated JP output:

```text
EPS (Diluted, GAAP): $0.88 actual / $0.89 estimate — Bloomberg consensus
EPS (Diluted, Non-GAAP): $0.88 actual / $0.90 estimate — Bloomberg consensus
Revenue: $79.9B estimate / $82.0B actual — Bloomberg consensus
```

Expected:
- EPS consensus override: **$1.77** from Investing.com.
- Revenue consensus override: **$79.19B** from Investing.com.
- Source label should not be `Bloomberg consensus` for this approved override path.

Impact: **EN/JP parity and source-policy compliance fail**.

### 3. Concision fixes are not visible in the regenerated output

Expected from parent cards:
- EPS & Revenue section: max 2 short bullets, one line each.
- Capital Efficiency / Profitability explanation: compact key takeaways.

Observed:
- Output still uses long numbered paragraph format such as `① ② ③`.
- Capital Efficiency / Cash Flow style remains verbose and does not reflect the intended concise format.

Impact: **parent prompt changes appear not to be reaching the active generation path, or the model is ignoring them**.

### 4. `Official Website: Not disclosed` placeholder leaks into the report

Observed:
- The report still contains an official website placeholder instead of a proper URL or clean omission.

Likely technical cause noted by reviewer:
- `_company_website_from_metrics` returns `None`, causing markdown rendering to fall back to `Not disclosed`.

Impact: **presentation-quality regression and forbidden placeholder style**.

### 5. Integrated output contains internal numeric contradictions

Examples observed by reviewer:
- Total revenue appears as `$42.3B` in one place and `$82B` in another.
- Dividend values differ between EN/JP sections.

Impact: **the integrated report is not financially coherent enough for client-facing use**.

## Root-cause hypothesis

The parent cards produced isolated `kverify READY` proofs, but the end-to-end generation path does not consume those changes consistently.

Most likely areas to investigate:
1. Standalone `/api/earnings/deep-dive` path may not propagate `consensus_overrides` into the LLM prompt the same way focused tests do.
2. Running backend may be using stale loaded prompt/code state or a different generation path than the tested functions.
3. JP and EN paths may diverge in estimate/source mapping.
4. Website fallback logic leaks `Not disclosed` instead of suppressing or resolving the URL.

## Verdict

**REQUEST_CHANGES** — the regenerated NVDA Deep-Dive is **not client-approvable**.

Do not proceed to artifact capture (`t_929fd401`, `t_0a780af6`) or JP/EN parity classification (`t_57b6b5f2`) until the integrated generation path is fixed and a fresh audit passes.

## Required follow-up

Create/execute repair work for:
1. Trace and fix why `consensus_overrides` are not applied in the standalone deep-dive generation path.
2. Verify the running backend uses the latest `prompts.py` / markdown path; restart if stale, but prove via output.
3. Fix EN/JP estimate and source-label parity for EPS and Revenue.
4. Remove or resolve the `Official Website: Not disclosed` leak.
5. Regenerate EN and JP outputs, then rerun this final audit.

## Kanban note

The reviewer run hit the iteration budget before it could persist this report and call the structured Kanban handoff. This file transcribes the reviewer’s findings from the worker log so the blocked card has durable evidence.
