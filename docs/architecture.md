# UrbanAgent architecture through Phase 6

```text
Excel (.xlsx) -> Excel adapter -> FeedbackCreate -> shared storage service -> SQLite
REST JSON --------------------> FeedbackCreate -> shared storage service -> SQLite
GET /api/feedback <-------------------------------------------------------- SQLite

Raw Feedback -> Classification Agent -> OpenAI structured output
                    ^                         |
                    |                         v
       assignment reference JSON    deterministic validation
                                              |
                                              v
                              FeedbackAnalysis + FeedbackAspect(s)
                                              |
                                              v
                                 independent Validation Agent
                                   ^                    |
                                   |                    v
                         source + reference JSON   typed output checks
                                                        |
                                                        v
                              FeedbackValidation + categories + issues
                                                        |
                                                        v
                                      deterministic analytics service
                                                        |
                                                        v
                  overview / distributions / patterns / timeline / emerging issues
                                      |                         |
                                      v                         v
                    Recommendation Agent              recovery rule engine
                       |          |                       |          |
                       v          v                       v          v
              pending proposal  evidence IDs        risk level   reason factors
                       |                                     |
                       v                                     v
              human approve/reject                 human case status workflow
```

- `backend/app/main.py`: application factory, startup table creation, session
  dependency and HTTP endpoints. Blocking database/Excel work uses FastAPI's worker
  thread pool via synchronous route handlers.
- `config.py`: environment settings; `database.py`: engine and session factory.
- `models.py`: raw feedback storage with a unique `(source, feedback_id)` key.
- `schemas.py`: input validation and documented API response contracts.
- `services/feedback.py`: common insertion and duplicate/conflict detection.
- `services/excel.py`: structural checks, row mapping and accounting.
- `reference.py`: validates assignment-derived categories and operational rules.
- `agents/classifier.py`: prompt construction and grounding checks.
- `agents/validator.py`: independent source-versus-classification review and
  human-review enforcement.
- `services/llm.py`: centralized OpenAI Responses API and error handling.
- `services/analysis.py`: current analysis and aspect persistence.
- `services/validation.py`: current validation, corrected categories and issue
  persistence.
- `services/analytics.py`: trusted on-demand metrics, recurring pattern rules,
  timeline grouping and spike detection.
- `agents/recommender.py`: typed business proposals from structured trusted trends.
- `services/recommendations.py`: trend input construction, evidence links, duplicate
  fingerprints, proposal persistence and approval history.
- `services/recovery.py`: transparent customer-risk scoring, recovery evaluation
  persistence and human-controlled case status changes.
- `tests/`: HTTP integration tests using temporary, isolated SQLite files.

The database is created on application startup, not module import. Each request
owns a session. An import commits its valid rows once, after the complete file has
passed structural checks. Invalid rows and duplicates are explicitly accounted
for. An unexpected database error rolls back the request; a structural failure
writes nothing. Duplicate detection is backed by a database constraint and SQLite
`ON CONFLICT DO NOTHING`, including duplicates within one upload.

`id` is UrbanAgent's internal primary key; `feedback_id` is the external source ID.
Input text is preserved; source and feedback ID surrounding whitespace is trimmed.
Source keys are case-sensitive. Submitted timestamps are optional: absent dates
stay null rather than being invented. Present dates are normalized to UTC; naive
dates are assumed UTC. SQLite stores naive UTC values and the API returns `Z`.

Classification results live in `feedback_analyses` and `feedback_aspects`, separate
from raw feedback. One current analysis belongs to each feedback record. Forced
reprocessing updates that result and replaces its aspects atomically. A later
production design can add immutable attempt history before audit history is needed.

`FeedbackAspect` is separate because one comment can describe several parts of the
experience with different sentiment, severity, and evidence. It also supports
category filtering without storing query-hostile JSON in the analysis row.

The classifier checks the external feedback ID, allowed categories, primary
category membership, verbatim evidence phrases, overall sentiment and severity,
and the configured confidence threshold after the typed LLM response is parsed.

Validation results remain separate from classifier results. `feedback_validations`
stores the validator status, confidence, corrected sentiment/severity and review
state. `validation_categories` keeps the accepted or corrected category set
relational for later trend queries. `validation_issues` stores field-level issue
type and message entries. This preserves the current classifier output for direct
comparison with the validator result.

The Validation Agent receives both the original source and current classification,
uses a distinct prompt, and returns a strict Pydantic model. Python then rejects
unknown categories or contradictory approved results, checks stored evidence against
the source, and forces human review for material disagreement, low confidence,
ambiguity, unsupported evidence, `needs_review`, or `rejected`. A forced
reclassification removes the now-stale current validation; a later production audit
design can store immutable classification and validation attempts.

Analytics trust only `approved` and `approved_with_changes` validations. Corrected
validator sentiment, severity and category values take precedence over classifier
values. `needs_review` and `rejected` remain available to review workflows without
affecting trusted metrics. Calculations run on demand and use typed response schemas;
there is no analytics snapshot table in Phase 4.

Feedback count means distinct trusted records. Aspect count means validated category
assignments, so a multi-category record contributes once to feedback totals and once
to each supported category. Recurring positive and negative patterns use distinct
external feedback IDs and the configured minimum. Daily and weekly timelines omit
missing dates. Emerging issues compare negative category counts in adjacent periods,
require a previous-period baseline and minimum current volume, and handle a zero
previous category count as a new issue without division.

The Recommendation Agent never receives the unfiltered dataset. The recommendation
service selects recurring negative or emerging negative categories from deterministic
analytics and supplies their exact IDs, counts, validated summaries, severity and
relevant assignment-derived rules. The structured response must preserve its evidence
set and always require management approval. Recommendations are stored as pending;
approval events form an append-only human decision history. A fingerprint of the full
structured trend input prevents duplicates for unchanged evidence.

Recovery evaluation does not call an LLM. It combines configured score thresholds
with visible rule factors such as validated severity/sentiment, repeated failure or
exit wording, multiple categories, unresolved support, wrong/damaged products and
serious delivery language. Each case retains the score and individual reasons.
High/Critical cases start open; lower-risk evaluations are retained as dismissed.
Status and assignment changes occur only through the recovery status endpoint. No
customer communication or operational action is executed.

Next.js consumes HTTP endpoints. n8n will act as an external REST client for
Google Sheets/Forms and optional Gmail; it will never read the database directly.
The university dataset will use the same Excel adapter as any manual upload.

Keep SQLite and `create_all` for the initial local project. Introduce schema
migrations before evolving tables containing real data. `classify-all` and
`validate-all` are synchronous and commit each record separately so one failure does
not discard earlier successes. There is no management report agent, n8n workflow,
job queue or authentication in the current phase.

## Phase 6 frontend boundary

The Next.js App Router workspace lives in `frontend/`. Shared layout and providers
wrap seven routes. Feature components use a centralized typed fetch client and
TanStack Query. Excel upload uses XHR in that same client for real upload progress.
The default `/backend` rewrite forwards browser requests to FastAPI on port 8000,
avoiding cross-origin changes to the backend. Keys remain in backend configuration.

The frontend joins raw feedback, analyses and validations by database ID after
retrieving all paginated responses. Local filtering/pagination serves the small
assignment dataset; future scale should introduce a server-side joined endpoint.
Charts consume deterministic analytics responses. Mixed sentiment and overlapping
categories are preserved. Source text, classifier evidence and validator corrections
remain separately visible for audit.

Human decisions use existing recommendation approval and recovery status endpoints.
The UI does not generate analyses automatically, execute proposals, contact customers
or connect to n8n. The human review queue permits inspection; manual adjudication
needs a future backend endpoint. Tests isolate mock data outside production modules.

Managers can explicitly confirm a combined analysis workflow in the app. The new
`services/pipeline.py` orchestrates the existing classifier, validator and recovery
services. New analyze/analysis-state endpoints expose this boundary; the frontend's
shared analysis provider owns confirmations, in-flight state and query refreshes.
See [analysis workflow](analysis-workflow.md) for pending rules, stage failures,
single-process duplicate protection and existing current-result replacement semantics.
