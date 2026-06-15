# SA feedback intake orchestration gap spec

Task: `t_02411fdb`
Date: 2026-06-15
Project: `stock-analysis-pipeline`
Scope: specification only — no production code changes.

## 1. Executive summary

The current SA feedback chain is split into three partially overlapping paths:

1. User-facing feedback page: `/api/feedback` stores text/files in `analyses/feedback_<BUCKET>/index.json`.
2. Shared cron script: `~/.hermes/shared/scripts/sa_feedback_auto_intake.py` scans unprocessed entries and marks them `taken_into_account`, but acts directly and does not create Kanban/council work.
3. Chat feedback pipeline: `backend/chat.py` detects/consents correction requests, then `backend/feedback_pipeline.py` either runs direct automation (`USE_KANBAN=False`) or a legacy Kanban path (`USE_KANBAN=True`). The Kanban path is currently disabled by design.

Desired target chain:

Nami remark/PDF upload → `taken_into_account` / `in_progress` → Fusion-style council → atomic Kanban tasks with model/reasoning routing → preflight/go → corrected/closed status → email to Nami.

Main gap:

The storage and display layers already preserve feedback, attachments, public/admin visibility, and coarse fix state. The orchestration layer does not yet provide a durable state machine, council decision artifact, atomic task DAG, preflight hold/release, reviewer closure, or email notification.

## 2. Verified current behavior

### 2.1 Endpoints

Evidence from `backend/main.py`:

- `POST /api/feedback` is public by design, validates ticker/category/text/files, saves entries through `backend.feedback_store.save_feedback`, and auto-imports/probes `.har` files.
- `GET /api/feedback` is public by design and returns `{total, unprocessed, entries}` for user-facing status.
- `GET /api/feedback/{ticker}` is protected and returns bucket-specific history.
- `GET /api/admin/feedback` is protected and returns all feedback through `get_all_admin_feedback()`.
- `GET /api/feedback-file/{bucket}/{filename}` serves only indexed attachment files from the feedback store.

Live local verification on 2026-06-15:

- `GET http://127.0.0.1:8780/api/health` → HTTP 200, commit `263cb48`.
- `GET http://127.0.0.1:8780/api/feedback` → HTTP 200, `total=14`, `unprocessed=0`.
- `GET http://127.0.0.1:8780/api/admin/feedback` → HTTP 200 from local loopback.
- Current live status counters: `status=taken_into_account:14`, `fix_status=pending:14`.

### 2.2 Storage model

Evidence from `backend/feedback_store.py`:

- Buckets: `feedback_<TICKER>` and `feedback_GENERAL`.
- Entry fields at save time: `id`, `ticker`, `category`, `submitted_at`, `text`, `files`, `processed`, `processed_at`, `notes`.
- Decoration adds `status` and `_ticker`:
  - `status="pending"` when `processed` is false.
  - `status="taken_into_account"` when `processed` is true.
- `fix_status` is separate from `status`; current documented values are `pending | in_progress | corrected`.
- `mark_processed()` can set `fix_status` and `correction`, but there is no first-class `closed`, `not_reproducible`, `rejected`, `email_sent`, `kanban_task_ids`, or `council_id` field.

### 2.3 Current direct auto-intake

Evidence from `~/.hermes/shared/scripts/sa_feedback_auto_intake.py`:

- Scans all `analyses/feedback_*/index.json` entries where `processed` is false.
- Classifies by regex into: `pdf_access_issue`, `correction_request`, `site_availability`, `har_upload_issue`, `har_export_help`, `bug_report`, or `general_feedback`.
- Applies direct actions:
  - PDF/correction with ticker → POST `/api/analyze?force_refresh=true&skip_codex=true&lang=en`.
  - site availability → `systemctl --user restart sa-backend`.
  - HAR/help/bug/general → notes only.
- Marks entry:
  - `processed=true`
  - `status="taken_into_account"`
  - `fix_status="corrected"` on successful direct action, otherwise `in_progress` or `pending`
  - `correction` and `notes`
- Script is explicitly “direct action, no Kanban”.

### 2.4 Chat correction consent path

Evidence from `backend/chat.py`:

- Detects feedback after assistant response with `_detect_feedback()`.
- Direct fix requests launch the feedback pipeline immediately.
- Otherwise stores `_pending_fixes[session_id]` and waits for short explicit confirmation.
- Confirmation patterns include English, French, and Japanese forms.
- Declines discard pending fixes.

Evidence from `backend/feedback_pipeline.py`:

- `USE_KANBAN = False` by default with comment: “Ced: on reviendra au kanban quand il sera opérationnel”.
- With `USE_KANBAN=False`, `process_feedback()` calls `process_feedback_direct()`.
- Direct mode acknowledges in chat, runs simple direct action, and returns an action key.
- Legacy Kanban mode can create one broad `[CHAT-FB]` task and monitor completion, but it does not use the new atomic routing model.
- PDF failure intake also has direct mode and a disabled legacy Kanban mode.

### 2.5 Tests run

Command:

```bash
PYTHONPATH=. backend/.venv/bin/pytest tests/test_feedback.py tests/test_feedback_pipeline_scheduling.py -q
```

Result:

- `29 passed, 2 warnings in 2.69s`.

Coverage confirmed:

- Public user feedback submit/list.
- Admin feedback protection and local access.
- Attachment save/download safety.
- HAR and upload constraints indirectly through feedback tests.
- PDF failure scheduling both inside and outside an event loop.

## 3. Gap analysis

| Desired capability | Current state | Gap |
|---|---|---|
| Nami remark/PDF upload captured | Yes: `/api/feedback`, chat feedback, attachments, HAR auto-import | Capture exists, but no unified orchestration envelope |
| `taken_into_account` | Yes, derived from `processed=true` | Collapses “accepted for processing” and “already processed by cron” |
| `in_progress` | Partial: `fix_status` can be `in_progress` | No durable task/council linkage or progress reason |
| Fusion-style council | Missing | No council artifact, no reviewer actors, no verdict schema |
| Atomic Kanban tasks | Disabled / legacy only | `USE_KANBAN=False`; legacy task body is broad and would fail current atomicity expectations |
| Model/reasoning routing | Missing | No `hermes-routing` metadata generated from feedback severity/ambiguity |
| Preflight/go | Partial | `run_preflight_gate()` exists, but not in direct script and not tied to staged/manual release |
| Corrected/closed status | Partial | `fix_status=corrected` exists; no closure semantics, reviewer approval, or visible close reason |
| Email to Nami | Missing | No stored email target, no notification event, no outbox/log |
| Audit trail | Partial | feedback JSON and chat events exist, but no orchestration run record |
| Storm/noise control | Partial | PDF failure idempotency exists; page feedback script has no Kanban/council dedupe key |

## 4. Target state machine

Keep `status` as the customer-visible lifecycle and keep `fix_status` only if backward compatibility needs it. New implementation should migrate toward a single durable lifecycle:

1. `pending`
   - Entry saved, not yet triaged.
2. `taken_into_account`
   - Intake accepted it, assigned an orchestration ID, and wrote first visible acknowledgment.
3. `needs_clarification`
   - Cannot act without missing detail; visible message asks for the smallest needed input.
4. `in_progress`
   - Council/spec/task DAG accepted and at least one atomic task is staged/running.
5. `blocked`
   - Preflight, provider, auth, data, or verification blocker; visible reason required.
6. `corrected`
   - Fix deployed or corrective action completed; verification evidence attached.
7. `closed`
   - Nami notified and no further action pending.
8. `rejected` or `not_reproducible`
   - Explicit non-fix decision with reason and evidence.

Backward-compatible mapping:

- For the existing frontend/admin views, expose:
  - `status`: the target lifecycle value.
  - `fix_status`: derived compatibility alias: `pending | in_progress | corrected`.
  - `processed`: true once status is not `pending`.

## 5. Proposed orchestration contract

Each feedback entry that is actionable should gain an `orchestration` object:

```json
{
  "orchestration": {
    "id": "sa-fb-<entry_id>-<hash>",
    "source": "feedback_page|chat|pdf_failure",
    "dedupe_key": "stable hash of bucket + entry_id + category + normalized text + files",
    "status": "taken_into_account|in_progress|blocked|corrected|closed",
    "severity": "low|medium|high|critical",
    "ambiguity": 1,
    "council": {
      "required": true,
      "status": "pending|done|skipped",
      "artifact_path": "docs/feedback-council/<id>.md",
      "verdict": "ACT|CLARIFY|REJECT|HOLD"
    },
    "kanban": {
      "board": "sa-pipeline",
      "preflight_status": "GO|WARN|NO-GO",
      "created_task_ids": [],
      "root_task_id": null
    },
    "notification": {
      "email_required": true,
      "email_sent_at": null,
      "email_log_id": null
    },
    "evidence": {
      "tests": [],
      "live_checks": [],
      "artifacts": []
    }
  }
}
```

Storage should remain JSON-file compatible for V1, but all mutations must be atomic-write protected and resilient to concurrent cron/API writes.

## 6. Classification and routing rules

### 6.1 Intake decision

- `har_export_help`, generic “how do I” questions: acknowledge/help, no Kanban.
- `har_upload_issue`: status `needs_clarification` or `in_progress` depending on whether a HAR file is present; no council unless upload/probe fails.
- `pdf_access_issue`: high severity; council only if root cause is unclear after probe/status check.
- `correction_request` / `bug_report`: council required when it touches PDF content, financial data, scoring, or production UI.
- `feature_request`: council/spec first; no direct implementation.
- `site_availability`: direct operational runbook first; Kanban only if recurring or root cause unknown.

### 6.2 Routing metadata

For every Kanban card emitted from feedback, include:

```yaml
# hermes-routing
atom: 1
diff: <1-5>
crit: <1-5>
amb: <1-3>
ver: <1-3>
impact_count: 1
route:
  assignee_profile: <profile>
  builder_model: <model>
  builder_reasoning: <low|medium|high|max>
  reviewer_model: <model>
  reviewer_reasoning: <low|medium|high|max>
project: stock-analysis-pipeline
write_scope:
  - <atomic files only>
read_scope:
  - <minimal discovery files>
expected_tests:
  - <focused tests>
risk: <low|medium|high>
idempotency_key: <stable key>
```

Routing defaults:

- Spec/ambiguous/cross-module: `architect-spec`, builder `codex-gpt-5.5`, high reasoning.
- Python backend implementation: `python-builder`, builder `codex-gpt-5.5`, medium/high reasoning.
- UI/browser validation: `frontend-ux-recette`.
- Final QA: `reviewer-qa`, reviewer `claude-opus` or `minimax-m3` depending availability.
- PDF audit: `pdf-report-auditor`.

## 7. Proposed architecture

### 7.1 New module boundaries

Implement later as separate cards, not in this spec task:

- `backend/feedback_orchestration.py`
  - Owns lifecycle transitions, dedupe keys, orchestration object, and council/task creation contract.
- `backend/feedback_store.py`
  - Remains persistence layer; add atomic update helpers only.
- `backend/feedback_pipeline.py`
  - Keep chat/PDF compatibility but delegate orchestration decisions to `feedback_orchestration.py`.
- `~/.hermes/shared/scripts/sa_feedback_auto_intake.py`
  - Stop direct correction for complex/actionable feedback; call the orchestrator in dry-run/cron-safe mode.
- `backend/feedback_notifications.py`
  - Email/outbox abstraction; no silent external send without configured recipient and log.

### 7.2 Council artifact

Council output should be a small markdown or JSON artifact, linked from feedback entry:

- Problem restatement in user-facing language.
- Evidence inspected: feedback text, files, latest PDF/status/API if safe.
- Verdict: `ACT`, `CLARIFY`, `REJECT`, or `HOLD`.
- Atomic task list with file scopes and dependencies.
- Verification recipe.
- Notification text draft.

### 7.3 Preflight and go gate

Before task creation or promotion:

1. Run Kanban preflight (`tb preflight -q` or shared script JSON mode).
2. Run atomicity validation for each planned task.
3. Stage cards as no-spawn/triage if supported; otherwise create only after GO.
4. Create one root/spec task first when ambiguity is high.
5. Do not dispatch if provider/council actors are unavailable.

## 8. Atomic future implementation cards

These are proposed cards only; this spec task does not create them.

### Card 1 — Add feedback orchestration state contract

Assignee: `python-builder`

Write scope:

- `backend/feedback_store.py`
- `tests/test_feedback.py`

Read scope:

- `backend/main.py`
- current feedback JSON fixtures from temp test store only

Expected tests:

- New tests for `orchestration` defaults on saved entries.
- Backward-compatible `status`, `processed`, `fix_status` decoration.
- Atomic update helper preserves existing entries and files.

Acceptance criteria:

- Existing `29` feedback/scheduling tests still pass.
- New feedback entries can expose `orchestration.status` without breaking current API consumers.

### Card 2 — Introduce feedback orchestration decision module

Assignee: `python-builder`

Write scope:

- `backend/feedback_orchestration.py`
- `tests/test_feedback_orchestration.py`

Read scope:

- `backend/feedback_pipeline.py`
- `~/.hermes/shared/scripts/sa_feedback_auto_intake.py`

Expected tests:

- Classifies entries into `ACK_ONLY`, `DIRECT_OPS`, `COUNCIL_REQUIRED`, `CLARIFY`, `REJECT`.
- Produces stable dedupe key.
- Produces routing metadata from category/severity/ambiguity.

Acceptance criteria:

- No file IO or Kanban side effects in pure decision tests.
- Explicitly covers PDF upload, correction request, HAR help, site down, generic feedback.

### Card 3 — Generate council artifact and atomic task plan

Assignee: `architect-spec`

Write scope:

- `backend/feedback_orchestration.py`
- `docs/feedback-council/README.md`
- `tests/test_feedback_orchestration.py`

Read scope:

- `docs/sa-feedback-orchestration-gap-spec.md`

Expected tests/checks:

- Artifact renderer produces deterministic markdown/JSON from a sample feedback entry.
- Atomic plan contains per-card `write_scope`, `read_scope`, `expected_tests`, `risk`, `idempotency_key`.

Acceptance criteria:

- No broad implementation cards are emitted.
- Ambiguous feedback emits a spec/root card before builder cards.

### Card 4 — Wire auto-intake script to orchestration dry-run/apply modes

Assignee: `python-builder`

Write scope:

- `/home/ced/.hermes/shared/scripts/sa_feedback_auto_intake.py`
- `tests/test_sa_feedback_auto_intake.py` or equivalent script-level test under project tests if feasible

Read scope:

- `backend/feedback_orchestration.py`
- `backend/feedback_store.py`

Expected tests:

- `--dry-run` reports planned lifecycle transition without mutating files.
- apply mode marks `taken_into_account` and writes orchestration metadata.
- complex correction requests do not run direct reanalysis silently.

Acceptance criteria:

- Cron remains silent when no work exists.
- No Kanban task is created unless preflight and atomicity gates pass.

### Card 5 — Safe Kanban task creation adapter

Assignee: `python-builder`

Write scope:

- `backend/feedback_orchestration.py`
- `tests/test_feedback_orchestration_kanban.py`

Read scope:

- `backend/feedback_pipeline.py`
- `/home/ced/.hermes/shared/scripts/kanban_preflight.py`
- `/home/ced/.hermes/scripts/check-kanban-atomicity.py`

Expected tests:

- Mocks preflight GO/WARN/NO-GO.
- Mocks atomicity pass/fail.
- Verifies no task creation on NO-GO or atomicity fail.
- Verifies created task body includes `hermes-routing` metadata.

Acceptance criteria:

- Adapter is side-effect-free under tests.
- Runtime path uses Hermes Kanban tool/CLI only through a narrow wrapper.

### Card 6 — Feedback status transitions from Kanban/reviewer completion

Assignee: `python-builder`

Write scope:

- `backend/feedback_orchestration.py`
- `backend/feedback_store.py`
- `tests/test_feedback_orchestration_status.py`

Read scope:

- Kanban task result schema from existing board examples

Expected tests:

- `done + approved` transitions entry to `corrected`.
- `blocked` transitions entry to `blocked` with visible reason.
- `review-required` does not close feedback.
- `closed` only after notification is recorded.

Acceptance criteria:

- Status transitions are idempotent and append evidence.

### Card 7 — Email/outbox notification to Nami

Assignee: `python-builder`

Write scope:

- `backend/feedback_notifications.py`
- `backend/feedback_orchestration.py`
- `tests/test_feedback_notifications.py`

Read scope:

- project environment/config docs

Expected tests:

- No email sent when recipient/config missing; outbox records `pending_config`.
- Email body uses user-facing language: issue, action taken, verification, next step.
- Success records `email_sent_at` and `email_log_id`.

Acceptance criteria:

- No secrets in logs/tests.
- Notification failure leaves feedback `corrected` but not `closed`.

### Card 8 — Admin/user API visibility for lifecycle and evidence

Assignee: `python-builder`

Write scope:

- `backend/main.py`
- `tests/test_feedback.py`

Read scope:

- `frontend/src/components/FeedbackPanel.jsx`
- `frontend/src/components/AdminPage.jsx`

Expected tests:

- `/api/feedback` exposes lifecycle fields safe for user view.
- `/api/admin/feedback` exposes full orchestration/evidence fields.
- Public response does not leak internal model/provider logs.

Acceptance criteria:

- Existing API shape stays backward-compatible.

### Card 9 — Frontend/admin status display

Assignee: `frontend-ux-recette`

Write scope:

- `frontend/src/components/FeedbackPanel.jsx`
- `frontend/src/components/AdminPage.jsx`
- `frontend/src/i18n.js`

Read scope:

- API response from Card 8

Expected tests/checks:

- Build passes.
- Browser verifies pending/taken/in_progress/corrected/closed labels.
- JP wording avoids internal “client/Kanban” vocabulary.

Acceptance criteria:

- User sees clear status and next step, not internal cron/worker wording.

### Card 10 — End-to-end QA gate

Assignee: `reviewer-qa`

Write scope:

- `docs/qa/sa-feedback-orchestration-e2e.md`

Read scope:

- all previous card outputs

Expected tests/checks:

- Submit sample feedback with attachment in temp/test store.
- Verify status progression through orchestrator with mocked Kanban/email.
- Verify current tests plus targeted new tests pass.
- Live API/browser check if feature is deployed.

Acceptance criteria:

- No feedback is closed without evidence and notification state.

## 9. Non-goals for first implementation slice

- No automatic broad code fixing from vague feedback.
- No direct Seeking Alpha transcript bypass work.
- No email to real recipient until config and consent are explicit.
- No Kanban fan-out if preflight/provider/council actors are unavailable.
- No migration of historical feedback JSON unless a separate migration card is created.

## 10. Recommended first delivery slice

Smallest useful slice:

1. Add orchestration metadata defaults and lifecycle contract to feedback store.
2. Add pure decision module with tests.
3. Wire auto-intake dry-run/apply to mark `taken_into_account` and classify into `ACK_ONLY` vs `COUNCIL_REQUIRED`, but do not create tasks yet.

Stop line:

- Existing feedback APIs still pass.
- Admin/user can see that a feedback was taken into account with a reason.
- Complex items are not silently “corrected” by reanalysis.

Only after that slice is verified should Kanban creation, council artifacts, and email closure be enabled.
