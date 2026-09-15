# Manager analysis workflow

The Phase 6 analysis controls reuse the existing agents and persistence services.
No n8n workflow, new AI agent, schema migration or dashboard redesign is introduced.

## Endpoints

| Method | Path | Behaviour |
| --- | --- | --- |
| POST | `/api/feedback/{id}/analyze` | Classify if needed, validate if needed, evaluate recovery for trusted results, return combined result |
| POST | `/api/feedback/{id}/analyze?force=true` | Explicitly rerun classification and validation |
| POST | `/api/feedback/analyze-pending` | Process pending records; there is intentionally no batch force option |
| GET | `/api/feedback/analysis-state` | Workspace total, pending count, review count and running flag |

Numeric database IDs identify individual records. External feedback IDs are retained
in every result/error. Pending means missing completed classification, missing
validation, or a previous recovery-stage failure. Needs-review/rejected validations
are completed assessments requiring human attention, so batches do not pay to repeat them.

`pipeline.py` calls `classify_and_save`, `validate_and_save` and
`RecoveryService.evaluate_validation`. Analytics already calculate from stored
validations, so refreshing reads the updated evidence without another AI call.
Recommendation generation is not triggered by this workflow.

## Results and failures

Single responses include `status` (`completed`, `requires_review`, `failed`), stage
statuses, `requires_human_review`, `reused`, analysis, validation, recovery and a safe
stage-specific error when applicable. A handled stage failure returns HTTP 200 with
`status=failed`, allowing the caller to inspect preserved partial results. Missing
records return 404; overlapping pipeline submissions return 409. Infrastructure
initialization failures can return 503.

Batch counts are mutually exclusive:

```text
total_pending = completed + requires_review + failed
failed = classification_failures + validation_failures + recovery_failures
```

Every row has a combined result, including failed feedback IDs. Each existing service
commits its stage. Failure rolls back only uncommitted work; later records continue.
A retry reuses a saved classification if validation failed. Recovery-only retries do
not call the AI service. Provider exceptions are mapped to concise messages rather
than exposing arbitrary diagnostic text or secrets.

## Duplicate protection and history

The frontend uses one shared mutation provider, disables submissions while processing,
and never retries a POST automatically. Batch and force actions require confirmation;
individual analysis also confirms before starting. The backend uses one process-local
lock across the new orchestration endpoints, rejects overlap, and releases the lock
in `finally`. Fully completed results are reused by default even without an API key.

Run one FastAPI worker for this local project. The lock is not a distributed lock,
and the older developer-only classify/validate routes remain separate; do not run
those concurrently with the manager pipeline. Shared jobs/locks and durable progress
belong in a future production hardening task.

Existing persistence stores a current assessment, not a version history. Successful
forced classification replaces aspects and invalidates validation and its recovery
case (including assignment/status). Validation creates the new assessment; trusted
results receive a new deterministic recovery case. If forced classification fails,
the previous complete result is kept. If subsequent validation fails, the new
classification remains and previous validation is no longer considered applicable.
Original feedback is never changed. The confirmation discloses this replacement.

## User experience

Import never starts paid processing automatically. Its analysis CTA reflects the
actual workspace pending count; duplicate-only imports show no CTA when none remain.
Feedback and Dashboard provide analysis entry points. The dashboard uses an em dash
for negative feedback and trends when there is no validated denominator.

The UI shows indeterminate progress for synchronous calls and a traceable completion
summary. Feedback, dashboard/analytics, recovery and review counts refresh on settle.
Running-state polling helps another open page discover completion. The shared provider
keeps an active request across route navigation. Browser and Next proxy allow up to
30 minutes; closing a tab or losing the connection does not necessarily cancel backend
work. Check status and resume pending work after an interruption.

Human Review reuses classifier/validator flags and rejected/needs-review results.
It allows inspection, not manual adjudication. No customer message is sent.

## Verification

Backend tests use mocked structured LLM responses. Frontend component tests mock the
API. `npm.cmd run test:pipeline` additionally runs the real import, pipeline, storage,
analytics and UI against a test-only server with a temporary database and offline LLM.
The test checks its server identity before submitting any analysis. Test routes and
synthetic feedback live only under `tests/` and are never mounted in production.

For a manual check with your configured model: import a workbook, confirm **Analyze
pending feedback**, inspect the summary, open a record, navigate to Dashboard and
Human Review, then confirm **Re-analyze** only when another assessment is intended.
These real-model actions use your configured OpenAI account.
