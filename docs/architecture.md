# UrbanAgent architecture through Phase 2

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
- `services/llm.py`: centralized OpenAI Responses API and error handling.
- `services/analysis.py`: current analysis and aspect persistence.
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

Next.js will consume HTTP endpoints. n8n will act as an external REST client for
Google Sheets/Forms and optional Gmail; it will never read the database directly.
The university dataset will use the same Excel adapter as any manual upload.

Keep SQLite and `create_all` for the initial local project. Introduce schema
migrations before evolving tables containing real data. `classify-all` is
synchronous and commits each record separately so one failure does not discard
earlier successes. There is no Validation Agent, trend analysis, recommendation or
report agent, n8n workflow, job queue, authentication, or dashboard in Phase 2.
