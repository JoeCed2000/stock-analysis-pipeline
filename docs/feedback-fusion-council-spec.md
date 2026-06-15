# SA Feedback Fusion Council — research note and implementation spec

Date: 2026-06-15
Task: `t_baba6401`
Project: `stock-analysis-pipeline`
Status: SPEC ONLY — no production code changes

## 1. Verdict

OpenRouter Fusion is not documented as a public standalone research paper or technical report as of this research pass. The reliable public sources found are:

- OpenRouter Fusion Router docs: https://openrouter.ai/docs/guides/routing/routers/fusion-router
- OpenRouter Fusion plugin docs: https://openrouter.ai/docs/guides/features/plugins/fusion
- OpenRouter Fusion server tool docs: https://openrouter.ai/docs/guides/features/server-tools/fusion
- OpenRouter blog announcement / DRACO benchmark write-up: https://openrouter.ai/blog/announcements/fusion-beats-frontier/
- Local video review: `/home/ced/codex-projects/docs/veille/agent-behavior-playbook/OPENROUTER_FUSION_VIDEO_REVIEW_2026-06-15.md`

Related public research exists for the general methodology family:

- Mixture-of-Agents Enhances Large Language Model Capabilities — arXiv:2406.04692 — https://arxiv.org/html/2406.04692
- Rethinking Mixture-of-Agents: Is Mixing Different Large Language Models Beneficial? — arXiv:2502.00674 — https://arxiv.org/html/2502.00674v1

Conclusion for SA feedback: use the Fusion methodology as a small, explicit council pattern, not as a default automation path. The SA feedback workflow should stay manual-first and consent-first; Fusion/Council is only for ambiguous, high-impact, or root-cause-heavy feedback where one model’s answer is likely insufficient.

## 2. What OpenRouter Fusion actually does

The public docs describe the same core pipeline across three entry points: `openrouter/fusion`, the `fusion` plugin, and the `openrouter:fusion` server tool.

Process:

1. The outer model receives the user prompt.
2. The outer model decides whether deliberation is useful, unless the request forces tool usage with `tool_choice: "required"`.
3. A panel of 1–8 analysis models answers the same prompt in parallel.
4. Panel calls can use `openrouter:web_search` and `openrouter:web_fetch`.
5. A judge model compares panel outputs.
6. The judge returns structured analysis: consensus, contradictions, partial coverage / coverage gaps, unique insights, blind spots.
7. The outer model uses that analysis to produce the final answer.

Important distinction from the docs: the judge compares; it does not simply merge.

## 3. Evidence and caveats

### Evidence from OpenRouter docs

- Fusion is intended for research questions, expert critique, compare/contrast prompts, and high-stakes tasks where the cost of being wrong exceeds extra completion cost.
- Fusion is explicitly overkill for short tactical prompts and simple questions.
- It can be called through a model alias or as a server tool with configurable `analysis_models`, judge `model`, `max_tool_calls`, `max_completion_tokens`, `reasoning`, and `temperature`.
- The successful tool result includes both structured `analysis` and raw panel `responses`.

### Evidence from OpenRouter blog

OpenRouter reports DRACO deep-research benchmark results on 100 tasks:

- Fable 5 + GPT-5.5 synthesized by Opus 4.8: 69.0%.
- Claude Fable 5 solo: 65.3%.
- Budget panel Gemini 3 Flash + Kimi K2.6 + DeepSeek V4 Pro synthesized by Opus 4.8: 64.7%.

Caveat: this is OpenRouter’s own announcement, not an independent peer-reviewed evaluation. It targets deep research tasks, not long-horizon coding or SA-specific feedback triage.

### Evidence from related research

MoA (arXiv:2406.04692) supports the broad idea that multiple proposer responses plus aggregation can improve output quality without model weight changes.

Rethinking MoA (arXiv:2502.00674) adds an important caution: mixed-model diversity is not automatically beneficial. Proposer quality can matter more than diversity, and repeated sampling from a strong model can beat mixing weaker models. This matters for Ced’s council design: never add a weak reviewer “for diversity” if it lowers signal quality.

## 4. SA Feedback Council scope

### Use only when at least one condition is true

- Feedback implies a client-visible defect but the root cause is ambiguous.
- There are two or more plausible remediation paths with different risks.
- The issue touches data integrity, PDF output, Seeking Alpha direct transcript retrieval, auth/cookie handling, or security.
- A previous single-agent diagnosis failed or contradicted observed UI/PDF evidence.
- The change could create new Kanban tasks, but the task boundaries are unclear.

### Do not use for

- Ticker-only notes such as `NVDA` with no defect description.
- Simple copy/UI text fixes.
- Already-confirmed manual fixes.
- Urgent SA feedback where Ced explicitly wants manual handling.
- Non-anonymized client data sent to cloud models.
- Any workflow that auto-creates Kanban tasks without explicit consent.

## 5. Recommended internal architecture

Name: `SA Feedback Fusion Council V1`

Inputs:

- Feedback item text and metadata.
- Optional ticker and analysis folder.
- Relevant user-facing artifact excerpts: PDF text extract, screenshot observations, API response snippets.
- Existing feedback status/history.
- Current SA policy constraints: manual-first, consent before correction tickets, no StockAnalysis fallback for SA transcript goals.

Panel roles:

1. Root-cause analyst — proves what failed and why.
2. Product/UX reviewer — checks user-facing wording, severity, and whether the issue is actionable.
3. Risk/security reviewer — checks auth/cookie, data leakage, client privacy, and automation risks.

Judge role:

- Compare the panel outputs.
- Do not merge uncritically.
- Produce a strict JSON object with consensus, contradictions, partial coverage, unique insights, blind spots, confidence, and recommended tasks.

Default model policy for Ced’s local ecosystem:

- Primary high-stakes reviewer: Codex GPT-5.5 where available.
- Independent second reviewer: Claude/Anthropic CLI when quota is available and the task warrants it.
- Budget/backup reviewer: MiniMax-M3 or DeepSeek depending on current profile availability.
- Do not claim a model participated unless a smoke/quota check succeeded.

## 6. Judge output schema

The judge output must be JSON-serializable and persistable as an audit artifact.

```json
{
  "schema_version": "sa_feedback_fusion_council_v1",
  "feedback_id": "string|null",
  "ticker": "string|null",
  "decision": "NO_ACTION|ASK_CONSENT|CREATE_TASKS|MANUAL_REVIEW_REQUIRED|BLOCKED",
  "consensus": [
    {
      "point": "string",
      "supporting_models": ["string"],
      "evidence": ["string"],
      "confidence": "low|medium|high"
    }
  ],
  "contradictions": [
    {
      "topic": "string",
      "stances": [
        {"model": "string", "stance": "string", "evidence": ["string"]}
      ],
      "resolution_needed": "string"
    }
  ],
  "partial_coverage": [
    {
      "point": "string",
      "covered_by": ["string"],
      "missing_from": ["string"],
      "impact": "low|medium|high"
    }
  ],
  "unique_insights": [
    {
      "model": "string",
      "insight": "string",
      "why_it_matters": "string",
      "verification_step": "string"
    }
  ],
  "blind_spots": [
    {
      "missing_question": "string",
      "why_it_matters": "string",
      "required_evidence": "string"
    }
  ],
  "confidence": {
    "overall": "low|medium|high",
    "root_cause": "low|medium|high",
    "recommended_action": "low|medium|high"
  },
  "recommended_tasks": [
    {
      "title": "string",
      "assignee": "architect-spec|python-builder|frontend-ux-recette|reviewer-qa|pdf-report-auditor|test-coverage-engineer",
      "write_scope": ["string"],
      "read_scope": ["string"],
      "expected_tests": ["string"],
      "risk": "low|medium|high",
      "requires_consent": true,
      "atomicity_notes": "string"
    }
  ],
  "user_facing_summary": "string",
  "operator_notes": "string"
}
```

Hard validation rules:

- `decision=CREATE_TASKS` is invalid unless every `recommended_tasks[].requires_consent` is false because the user directly requested a fix, or explicit consent has already been recorded.
- `recommended_tasks[].write_scope` must be non-empty and must fit Kanban atomicity gates.
- `confidence.overall=high` is invalid if unresolved high-impact contradictions remain.
- `blind_spots` must not be empty unless the judge explicitly states `none_identified` inside `operator_notes`.

## 7. Curl-ready OpenRouter examples

### 7.1 Direct alias call

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openrouter/fusion",
    "messages": [
      {
        "role": "user",
        "content": "Analyze this anonymized SA feedback. Return consensus, contradictions, partial_coverage, unique_insights, blind_spots, confidence, and recommended_tasks as JSON. Feedback: PDF says Sources is empty but API /api/sources/NVDA returns rows. What is the likely root cause and what should be verified first?"
      }
    ],
    "tool_choice": "required"
  }'
```

### 7.2 Server tool with explicit panel and judge

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "~anthropic/claude-opus-latest",
    "messages": [
      {
        "role": "user",
        "content": "You are judging an anonymized Stock Analysis Pipeline feedback item. Compare root-cause hypotheses and emit only the SA Feedback Fusion Council JSON schema."
      }
    ],
    "tools": [
      {
        "type": "openrouter:fusion",
        "parameters": {
          "analysis_models": [
            "~openai/gpt-latest",
            "~google/gemini-pro-latest",
            "deepseek/deepseek-v3.2"
          ],
          "model": "~anthropic/claude-opus-latest",
          "max_tool_calls": 4,
          "max_completion_tokens": 4000,
          "reasoning": {"effort": "medium"},
          "temperature": 0.0
        }
      }
    ],
    "tool_choice": "required"
  }'
```

### 7.3 Local internal API shape for a future SA endpoint

This is not implemented in this task; it is a contract proposal.

```json
{
  "endpoint": "POST /api/admin/feedback/{feedback_id}/fusion-council",
  "auth": "admin_required",
  "request": {
    "mode": "dry_run|ask_consent|execute_after_consent",
    "models": {
      "panel": ["codex-gpt-5.5", "claude-opus", "minimax-m3"],
      "judge": "codex-gpt-5.5"
    },
    "privacy": {
      "anonymize": true,
      "allow_cloud": false,
      "redact_fields": ["visitor_name", "ip", "email", "cookies", "tokens", "raw_user_agent"]
    },
    "feedback_context": {
      "feedback_id": "FB-2026-06-15-001",
      "ticker": "NVDA",
      "description": "PDF Sources section is empty while the admin page shows source rows.",
      "artifact_refs": ["analysis_folder/07_final_report/report.pdf"],
      "api_refs": ["/api/sources/NVDA"]
    }
  },
  "response": {
    "council_result": "<SA Feedback Fusion Council JSON schema>",
    "audit_artifact_path": "docs/feedback-council-runs/FB-2026-06-15-001.json",
    "kanban_tasks_created": []
  }
}
```

## 8. Operational gates

Before running any council:

1. Verify the feedback is concrete enough. Ticker-only context is not actionable.
2. Decide privacy tier: local-only, anonymized cloud, or blocked.
3. Run model availability/quota checks for required actors.
4. Estimate cost/time and set a stop line.
5. If the output recommends remediation, ask consent unless the feedback was already a direct fix request.
6. If Kanban tasks are created later, run the atomicity gate for each task before creation.

After running a council:

1. Persist the raw panel outputs and judge JSON in a non-secret audit artifact.
2. Redact PII, cookies, tokens, IPs, raw user agents, and any SA auth material.
3. Store only the user-facing summary in feedback history.
4. Do not auto-dispatch SA feedback Kanban work while the SA feedback workflow remains manual-first.

## 9. Recommended V1 rollout

Smallest useful slice:

1. Manual dry-run on 2–3 historical SA feedback items.
2. Save judge JSON artifacts under `docs/feedback-council-runs/`.
3. Compare against Ced/manual root-cause decisions.
4. Only then implement a backend endpoint or dashboard button.

Stop line:

- Do not integrate OpenRouter Fusion globally.
- Do not create automatic SA feedback Kanban cards from Fusion output.
- Do not send non-anonymized client/visitor data to OpenRouter or any cloud panel.

## 10. Open questions

- Whether Ced wants OpenRouter itself tested with credit, or only the internal council pattern reproduced with existing profiles.
- Whether Claude/Anthropic CLI is mandatory for SA council runs or optional depending on quota.
- Where audit artifacts should live long-term: `docs/feedback-council-runs/` vs `.state/feedback-council/`.
- Whether the future UI should be admin-only button, cron-style dry-run, or a CLI tool first.
