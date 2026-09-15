# UrbanAgent: AI Customer Feedback Analyst

UrbanAgent is a university project for a multi-agent customer experience platform.
Its planned agents will classify feedback, independently validate results, detect
trends, recommend improvements and produce evidence-backed management reports.

**Current scope: Phase 6 web workspace.** The FastAPI backend accepts raw feedback
through JSON or Excel and stores it in SQLite. The Classification Agent can send an
individual raw record to OpenAI, validate typed output, store one overall analysis
plus multiple evidence-backed aspects, and expose those results through REST. An
independent Validation Agent checks that classification against the raw source,
stores corrections and structured issues separately, and identifies records that
need human review. Deterministic analytics now calculate trusted distributions,
recurring patterns, timelines, and emerging issue spikes. An evidence-backed
Recommendation Agent proposes actions from trusted negative trends, while
deterministic recovery rules flag customer-risk cases for human review. Management
reporting and n8n are not implemented. A Next.js management workspace now provides
feedback exploration, Excel import, analytics charts, recovery case management,
recommendation decisions and an auditable human review queue.

The repository includes the 30 assignment-provided UrbanMart records and the
approved category, business-rule, sentiment, and severity reference data.

## Structure

```text
urban-agent/
├── backend/
│   ├── app/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── reference.py
│   │   ├── schemas.py
│   │   ├── agents/
│   │   │   ├── classifier.py
│   │   │   ├── recommender.py
│   │   │   └── validator.py
│   │   └── services/
│   │       ├── analysis.py
│   │       ├── analytics.py
│   │       ├── excel.py
│   │       ├── feedback.py
│   │       ├── llm.py
│   │       ├── recommendations.py
│   │       ├── recovery.py
│   │       └── validation.py
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── app/                  # Seven App Router pages and shared layout
│   ├── components/           # Dashboard, charts, feedback, recovery, decisions, shell
│   ├── lib/                  # Typed API client, response types, display/filter helpers
│   ├── styles/globals.css    # Restrained light theme and responsive layouts
│   ├── tests/                # Mocked component and API tests
│   ├── e2e/                  # Browser smoke checks against the local backend
│   ├── .env.example
│   ├── package.json
│   ├── package-lock.json
│   └── README.md
├── data/sample/
│   ├── feedback_template.xlsx
│   └── README.md
├── data/raw/
│   ├── urbanmart_feedback.xlsx
│   └── README.md
├── data/reference/
│   ├── categories.json
│   ├── business_rules.json
│   ├── urbanmart_dataset_manifest.json
│   └── README.md
├── tests/
│   ├── conftest.py
│   ├── test_classification.py
│   ├── test_analytics.py
│   ├── test_feedback.py
│   ├── test_excel.py
│   ├── test_reference.py
│   ├── test_recommendations.py
│   ├── test_recovery.py
│   ├── test_validation.py
│   └── test_urbanmart_dataset.py
├── n8n/workflows/README.md
├── docs/architecture.md
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

Python package directories also contain `__init__.py`. Runtime databases, virtual
environments and caches are excluded from version control. See
[architecture details](docs/architecture.md) for boundaries and future extension points.

## Setup and run

Use Python **3.12 or later**. Run all commands from the repository root. Node.js
and n8n are not needed yet. The OpenAI key is required only by classification and
validation routes and recommendation generation. Analytics and recovery evaluation
do not call OpenAI.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY and OPENAI_MODEL before using AI routes.
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

If `py` cannot find Python, use the full path to an installed Python 3.12+ executable
instead of `py -3.12`. Calling the virtual environment's executable directly avoids
PowerShell activation-policy issues. For runtime-only installs, use `backend/requirements.txt`.

macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY and OPENAI_MODEL before using AI routes.
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/docs** for the interactive API, including an Excel file
picker under `POST /api/import/excel`. The database is created automatically at
`data/urbanagent.db`. `.env` is optional; defaults work from the project root.
Create the parent directory yourself if configuring a custom database location.
The default database path without an override is anchored to the repository;
relative paths in `DATABASE_URL` are relative to the process working directory.

This is a local development backend without authentication. Authentication and
deployment upload limits should be added before exposing customer data publicly.

## API

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/health` | Checks database connectivity; returns `{"status":"ok"}` |
| GET | `/api/feedback?offset=0&limit=50` | List ordered by internal ID; limit 1–100 |
| GET | `/api/feedback/{id}` | Retrieve by internal integer ID; 404 if missing |
| GET | `/api/feedback/{id}/analysis` | Retrieve the completed current analysis |
| GET | `/api/feedback/analysis-state` | Pending/review counts and pipeline running state |
| POST | `/api/feedback/{id}/analyze` | Run or resume the complete analysis workflow; optional `force=true` |
| POST | `/api/feedback/analyze-pending` | Analyze pending feedback with isolated stage failures |
| GET | `/api/feedback/analyses` | List/filter analyses; limit 1–100 |
| GET | `/api/feedback/{id}/validation` | Retrieve the completed current validation |
| GET | `/api/feedback/validations` | List/filter validations; limit 1–100 |
| POST | `/api/feedback` | Create one record; 201, validation 422, duplicate/conflict 409 |
| POST | `/api/import/excel` | Multipart field `file`; row summary 200, malformed file 400, oversized file 413 |
| POST | `/api/feedback/{id}/classify` | Classify once; `?force=true` reprocesses |
| POST | `/api/feedback/classify-all` | Classify records without results; `?force=true` reprocesses all |
| POST | `/api/feedback/{id}/validate` | Validate a completed classification once; `?force=true` revalidates |
| POST | `/api/feedback/validate-all` | Validate classified records without results; `?force=true` revalidates all |
| GET | `/api/analytics/overview` | Trusted counts, ratings, sources, and recurring-pattern totals |
| GET | `/api/analytics/sentiment` | Validated sentiment counts and percentages |
| GET | `/api/analytics/categories` | Category feedback/aspect counts and breakdowns |
| GET | `/api/analytics/severity` | Severity totals and high-severity combinations |
| GET | `/api/analytics/trends` | Recurring negative and positive patterns with evidence IDs |
| GET | `/api/analytics/timeline` | Daily or weekly validated metrics |
| GET | `/api/analytics/emerging-issues` | Current-versus-previous period spike detection |
| POST | `/api/recommendations/generate` | Generate pending proposals from qualifying negative trends |
| GET | `/api/recommendations` | List/filter saved recommendations |
| GET | `/api/recommendations/{id}` | Retrieve one recommendation and its evidence/approval history |
| PATCH | `/api/recommendations/{id}/approval` | Record a human approved/rejected decision |
| POST | `/api/recovery/evaluate/{feedback_id}` | Deterministically evaluate one trusted external feedback ID |
| POST | `/api/recovery/evaluate-all` | Evaluate trusted records without existing recovery evaluations |
| GET | `/api/recovery/cases` | List/filter recovery evaluations |
| GET | `/api/recovery/cases/{id}` | Retrieve one recovery evaluation and its reasons |
| PATCH | `/api/recovery/cases/{id}/status` | Record a human workflow status and optional assignee |

Minimal JSON request to `POST /api/feedback`:

```json
{"feedback_id":"FORM-001","source":"google_forms","feedback_text":"The staff answered my question."}
```

`source` defaults to `manual` through either input method. Choose a stable source
name for your dataset or connector; the transport does not determine provenance.
`processing_status`, internal `id` and `created_at` are server-controlled.
Unknown JSON fields are rejected to catch mapping mistakes.

Example upload on Windows (use `curl` on macOS/Linux):

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/import/excel -F "file=@data/sample/feedback_template.xlsx"
```

## Classification Agent

Copy `.env.example` to `.env` and fill these values locally. The model name is
configured once and stored with each result:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
CLASSIFICATION_REVIEW_THRESHOLD=0.70
VALIDATION_REVIEW_THRESHOLD=0.70
TREND_MIN_FEEDBACK=3
SPIKE_MIN_CURRENT_COUNT=3
SPIKE_PERCENT_INCREASE=50
RECOVERY_HIGH_SCORE=5
RECOVERY_CRITICAL_SCORE=9
```

The code uses the OpenAI Responses API with a Pydantic response model, following the
[official OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
Sentiment is
restricted to `Positive`, `Neutral`, or `Negative`; severity is restricted to `Low`,
`Medium`, or `High`. Categories come only from `data/reference/categories.json`.
The API rejects changed feedback IDs, unsupported categories, evidence not copied
from the raw text, inconsistent overall sentiment, inconsistent maximum severity,
and malformed structured output.

One `FeedbackAnalysis` stores the overall result. Its `FeedbackAspect` children
store each category with its own sentiment, severity, and evidence phrase. Mixed
feedback can therefore preserve praise and criticism separately. A positive and a
negative aspect forces `is_mixed=true`, even if the model returned false. Confidence
below the configured threshold forces `requires_review=true`.

The source-backed files are documented in `data/reference/README.md`.
Classification responds with HTTP 503 when those files, the key, or the model are
missing. API/invalid-response failures use 502 and
timeouts use 504. A failed first attempt changes only `processing_status` to
`classification_failed`; it does not alter the source ID, text, or optional inputs.

Classify one internal database record:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/feedback/1/classify"
```

Calling it again returns the saved result without another paid call. Explicitly
reprocess only when needed:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/feedback/1/classify?force=true"
```

Classify all records that do not have a completed result:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/feedback/classify-all"
```

The synchronous batch response reports `total`, `processed`, `failed`,
`requires_review`, and row-level errors. Each result commits separately so one
failure does not discard earlier successes. `force=true` makes paid calls for all
records, so review the record count first.

Retrieve and filter results:

```powershell
curl.exe "http://127.0.0.1:8000/api/feedback/1/analysis"
curl.exe "http://127.0.0.1:8000/api/feedback/analyses?sentiment=Negative&severity=High&category=Delivery&requires_review=true"
```

## Validation Agent

The Validation Agent receives the original raw feedback and the saved classifier
result in a separate OpenAI request. It independently checks category relevance,
sentiment, severity, mixed status, omissions, evidence grounding, unsupported facts,
and confidence. It uses the same centralized OpenAI client and model configuration,
but has its own prompt and strict Pydantic response schema.

`validation_status` is restricted to `approved`, `approved_with_changes`,
`needs_review`, or `rejected`. Validated sentiment is `Positive`, `Neutral`,
`Negative`, or `Mixed`; severity remains `Low`, `Medium`, or `High`; categories must
come from `data/reference/categories.json`. Corrections live in
`FeedbackValidation` and `ValidationCategory`, while structured concerns live in
`ValidationIssue`. The original `FeedbackAnalysis` and `FeedbackAspect` values are
preserved so classifier and validator outputs can be compared.

Python forces `requires_human_review=true` when validated fields materially differ,
confidence is below `VALIDATION_REVIEW_THRESHOLD`, an issue is uncertain or
unsupported, or status is `needs_review`/`rejected`. This rule is applied after the
typed model response, so the model cannot suppress a required review flag.

Validate and retrieve one classified internal database record:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/feedback/1/validate"
curl.exe "http://127.0.0.1:8000/api/feedback/1/validation"
```

Repeating the first command returns the saved validation without another paid call.
Use `?force=true` only for deliberate revalidation. Batch validation processes only
completed classifications without validation by default:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/feedback/validate-all"
curl.exe "http://127.0.0.1:8000/api/feedback/validations?validation_status=needs_review&requires_human_review=true"
```

The batch response separates `validated` (approved and approved-with-changes),
`needs_review`, `rejected`, and `failed`. A forced reclassification invalidates the
current validation because that validation no longer applies to the changed
classifier output.

### Manual real-API check in Swagger

After `OPENAI_API_KEY` and `OPENAI_MODEL` are set in `.env`, start FastAPI and open
`http://127.0.0.1:8000/docs`:

1. Expand `POST /api/import/excel`, select **Try it out**, choose
   `data/raw/urbanmart_feedback.xlsx` for `file`, and select **Execute**. A clean
   database returns `total_rows: 30` and `imported_rows: 30`; a repeat import returns
   `skipped_rows: 30`.
2. Expand `GET /api/feedback`, set `offset=0` and `limit=100`, and execute it. Find
   external `feedback_id` **F009** and note its internal integer `id`. The remaining
   routes use this internal ID.
3. Run `POST /api/feedback/{id}/classify` with that ID and `force=false`.
4. Run `GET /api/feedback/{id}/analysis`. Confirm that the classifier preserved
   `F009`, used grounded evidence, and represented both positive product wording and
   the pricing concern when supported by the text.
5. Run `POST /api/feedback/{id}/validate` with the same ID and `force=false`.
6. Run `GET /api/feedback/{id}/validation`. Compare its validated sentiment,
   severity, categories, status, confidence, and issues with the classifier output
   from step 4. F009 is intended to exercise mixed-feedback validation; production
   code does not hard-code its result.
7. Repeat steps 2–6 with **F017** for neutral feedback, **F004** for multiple issues
   and severity, and **F027** for positive Delivery feedback. Their source wording is:

   - F009: “The products are good but I think some prices could be more competitive.”
   - F017: “Everything was okay. Nothing particularly good or bad.”
   - F004: “I received the wrong product and had to contact support twice before getting help.”
   - F027: “Delivery was on time and the product arrived in good condition.”
8. Only after the single-record checks work, run `POST /api/feedback/classify-all`
   with `force=false` if you want to classify the remaining imported records, then
   run `POST /api/feedback/validate-all` with `force=false`. These routes make one
   paid call per eligible record. Validation processes only completed classifications
   without a saved validation; if every classified record was already validated in
   the single-record checks, `total: 0` is expected. Use
   `GET /api/feedback/validations` to inspect results and its two filters.

Calling either F009 AI route again with `force=false` returns its saved result
without a new paid API call. Reclassification and revalidation with `force=true`
each make a new model request.

## Deterministic analytics

Analytics are calculated on demand by `backend/app/services/analytics.py`; no LLM
counts records, calculates percentages, or decides whether a threshold was met. No
snapshot table is needed at the current scale.

Trusted metrics include only records with a completed validation status of
`approved` or `approved_with_changes`. The latter uses `validated_sentiment`,
`validated_severity`, and `ValidationCategory` corrections. `needs_review` and
`rejected` records do not affect trusted sentiment, category, severity, pattern,
timeline, or spike results. They remain visible in validation retrieval and the
overview's human-review count.

Validated `Mixed` sentiment stays a separate bucket so it is not silently forced
into Positive, Neutral, or Negative. Missing `submitted_at` values remain included
in non-time metrics but are excluded from timelines and date-filtered results.

Category responses distinguish two denominators:

- `trusted_feedback_count` counts distinct trusted customer feedback records.
- `total_aspect_count` counts validated category assignments. One feedback record
  with Delivery and Customer Service contributes one feedback record and two aspects.
- A category's `percentage` is its share of trusted feedback records and can sum to
  more than 100% across categories. `aspect_percentage` is its share of assignments.

A negative or positive category pattern becomes recurring when at least
`TREND_MIN_FEEDBACK` distinct external feedback IDs support it. The response always
returns the supporting IDs and the threshold used.

Emerging issues compare negative category feedback in the current daily or weekly
period with the previous comparable period. By default, the current period is based
on the latest dated trusted record; `as_of=YYYY-MM-DD` makes the comparison explicit.
A result is a `spike` when current volume reaches `SPIKE_MIN_CURRENT_COUNT` and its
increase is at least `SPIKE_PERCENT_INCREASE`. When the previous comparable period
contains feedback but has zero complaints for that category, reaching the minimum
creates `new_emerging_issue` without division by zero. If the previous period has no
feedback at all, no issue is flagged because there is no comparison baseline.

All analytics endpoints accept `start_date`, `end_date`, `source`, and `category`.
Timeline and emerging-issue routes also accept `period=daily|weekly`; emerging issues
accept optional `as_of`.

Example sentiment response:

```json
{
  "total": 30,
  "positive": 10,
  "neutral": 3,
  "negative": 16,
  "mixed": 1,
  "positive_percentage": 33.33,
  "neutral_percentage": 10.0,
  "negative_percentage": 53.33,
  "mixed_percentage": 3.33
}
```

These numbers only illustrate the response shape; UrbanMart findings are always
calculated from the classifications and validations stored in your database.

### Analytics Swagger flow for the real UrbanMart dataset

1. Complete the import, classification, and validation flow above. Analytics are
   read-only and do not make OpenAI calls.
2. Run `GET /api/analytics/overview` and compare `total_feedback_count` with
   `trusted_validated_feedback_count` and `records_requiring_human_review`.
3. Run `GET /api/analytics/sentiment` for the trusted sentiment distribution.
4. Run `GET /api/analytics/categories`; compare `trusted_feedback_count` with
   `total_aspect_count`, then inspect category sentiment and severity breakdowns.
5. Run `GET /api/analytics/severity` for Low/Medium/High totals, high-severity
   negative records, and high severity by category.
6. Run `GET /api/analytics/trends` and inspect recurring negative patterns, recurring
   positive patterns, their thresholds, and supporting feedback IDs.
7. Run `GET /api/analytics/timeline?period=daily`, then repeat with `period=weekly`.
8. Run `GET /api/analytics/emerging-issues?period=weekly`. For a reproducible period,
   add an `as_of` date found in the imported dataset.
9. Repeat a metric with `source`, `category`, `start_date`, or `end_date` and confirm
   that its population changes. An unsupported category or reversed date range
   returns HTTP 422.

## Recommendations and customer recovery

Analytics establish what is present in trusted data. The Recommendation Agent only
receives qualifying deterministic negative trends, supporting feedback IDs, saved
analysis/validation summaries, severity counts, relevant business rules, and any
emerging-issue state. It does not scan raw rows or calculate its own trend totals.
Recurring positive patterns remain visible in analytics and do not generate
corrective recommendations.

Recommendation output is strict and uses priority `Low`, `Medium`, `High`, or
`Critical`. The agent must preserve every evidence ID and evidence count. Every saved
proposal starts with `approval_status=pending` and
`requires_management_approval=true`. A SHA-256 fingerprint of the structured trend
input prevents another model call for the same unchanged trend. If its evidence,
validated summaries, business context, or emerging status changes, the new input can
produce a new proposal while older recommendations remain available for audit.

Only `PATCH /api/recommendations/{id}/approval` records an `approved` or `rejected`
human decision. Each decision is appended to `approval_history`; generating a
recommendation never calls that endpoint or changes operations.

Customer recovery uses deterministic rules rather than an LLM. The explainable score
currently assigns:

- High severity: 5; Medium severity: 2.
- Negative sentiment: 2; Mixed sentiment: 1.
- Customer-exit language: 4; repeated failure/contact language: 2.
- Multiple validated categories: 1; unresolved service language: 2.
- Wrong product, damaged/failed product, or serious delivery language: 2 each.
- High severity already requiring human review: 1 additional point.

`RECOVERY_HIGH_SCORE` defaults to 5 and `RECOVERY_CRITICAL_SCORE` to 9. Scores below
2 are Low, scores from 2 below the High threshold are Medium, and configured High or
Critical results set `recovery_required=true`. Every trusted evaluation is stored for
audit. Non-urgent evaluations are stored as `dismissed`; required cases start `open`.
Reasons preserve each matched factor. Suggested actions are internal review prompts,
`response_draft` remains empty, and no contact, refund, replacement, or email occurs.

Recovery workflow statuses are `open`, `under_review`, `approved_for_contact`,
`resolved`, and `dismissed`. The status endpoint is the human-controlled transition
point and can record `assigned_to`. A later n8n workflow may notify staff about open
cases, but it must not treat detection as permission to contact a customer.

### Phase 5 Swagger flow

1. Complete classification and validation, then inspect
   `GET /api/analytics/trends`. Recommendation generation needs a recurring negative
   pattern or emerging negative issue.
2. Run `POST /api/recommendations/generate` with `period=weekly`. This makes one
   OpenAI call per eligible unchanged trend. A repeated request reports it under
   `skipped_duplicates` without another call.
3. Run `GET /api/recommendations`, then test `priority`, `category`, and
   `approval_status` filters. Retrieve one item with `GET /api/recommendations/{id}`.
4. As a human test action, call `PATCH /api/recommendations/{id}/approval` with either
   `{"approval_status":"approved"}` or `{"approval_status":"rejected"}`. Confirm
   the pending status changed and `approval_history` gained an event.
5. Run `POST /api/recovery/evaluate/F004`. Inspect the risk score and reasons for the
   wrong product, repeated support contact, severity, and multiple validated
   categories actually present in its saved validation.
6. Repeat recovery evaluation for F011 (damaged package), F016 (next-day delivery
   failure), and F020 (early product failure). Results depend on validated fields.
7. Run `POST /api/recovery/evaluate/F024`. Its positive support wording should not be
   escalated unless its trusted validation contains contradictory serious indicators.
8. Run `GET /api/recovery/cases`, test `risk_level` and `status` filters, then retrieve
   a case with `GET /api/recovery/cases/{id}`.
9. Use `PATCH /api/recovery/cases/{id}/status` with
   `{"status":"under_review","assigned_to":"Store manager"}`. Later test
   `approved_for_contact`, `resolved`, or `dismissed` as explicit human decisions.
10. After single-record checks, run `POST /api/recovery/evaluate-all`. It processes
    only trusted validations without an existing recovery evaluation and makes no
    OpenAI calls.

## UrbanMart assignment dataset

`data/raw/urbanmart_feedback.xlsx` contains exactly 30 supplied records. It preserves
the original IDs, dates, ratings, feedback strings, and source labels. Customer name
and email columns are absent because those optional values were not supplied. Its
columns are:

```text
feedback_id, source, submitted_at, rating, customer_name, customer_email, feedback_text
```

Then import it through the unchanged Phase 1 route:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/import/excel -F "file=@data/raw/urbanmart_feedback.xlsx"
```

`tests/test_urbanmart_dataset.py` verifies all five source fields for every row,
exactly 30 unique IDs from F001 through F030, successful import, duplicate
prevention, and useful malformed-row errors. It does not trigger classification.

## Excel format and import rules

Use the supplied [sample template](data/sample/feedback_template.xlsx). It contains
three synthetic rows, not conclusions from a real dataset. Replace them before
importing the converted university dataset through this same endpoint.

| Column | Required | Example / rule |
| --- | --- | --- |
| `feedback_id` | Yes | `001` stored as Excel Text; 1–200 characters |
| `source` | No | `university_dataset`; default `manual`; 1–100 characters |
| `submitted_at` | No | Native Excel date, `2026-09-01`, or `2026-09-01T10:00:00+05:45` |
| `rating` | No | Any finite number; no rating scale is assumed initially |
| `customer_name` | No | Up to 200 characters |
| `customer_email` | No | Up to 320 characters; retained as source text, no deliverability check |
| `feedback_text` | Yes | Non-whitespace text, up to 50,000 characters |

- Use exactly **one worksheet**, with column names in row 1. Column order is flexible.
  Optional columns may be absent or blank. Header whitespace is trimmed; names are
  case-sensitive. Unknown/duplicate/blank headers and unheaded data are rejected.
- IDs must be text in Excel. Numeric IDs are rejected to avoid pretending to
  preserve leading zeroes or digits already rounded by Excel. Changing the cell
  display format alone cannot restore digits already lost.
- Formula and Excel error cells fail their rows. Paste literal values instead.
  Text fields are not inferred from numbers; invalid dates/ratings fail their rows.
- Dates without time zones are assumed UTC; aware dates are converted to UTC.
  Missing dates remain null. `created_at` records ingestion time separately.
- Defaults: 10 MiB upload, 50 MiB uncompressed workbook, 10,000 data rows.
  `.env.example` documents configuration. The upload limit is checked after multipart
  parsing; production deployments also need an upstream request-body limit.
- Duplicate key: **`(source, feedback_id)`**, case-sensitive after trimming surrounding
  whitespace. Exact matches are skipped. Matching keys with changed input fail as
  conflicts; existing records are never overwritten. Reusing an ID in another source
  is allowed. Different IDs with identical text are distinct records.
- Structural errors reject the whole file before any writes. Once structure is
  valid, each data row is validated separately. Valid rows commit together, even if
  other rows fail. Unexpected database failures roll back the entire import.
- `total_rows` counts worksheet rows after the header through the scanned extent,
  including internal/explicit blank rows. Blank rows are skipped with a reason;
  unrepresented trailing empty Excel grid rows are not counted. Hidden and filtered
  rows are still imported. No secondary sheet is silently ignored.

Example summary for a mixed import:

```json
{
  "total_rows": 3,
  "imported_rows": 1,
  "skipped_rows": 1,
  "failed_rows": 1,
  "errors": [
    {"row": 3, "feedback_id": "001", "code": "duplicate", "message": "Identical source and feedback_id already stored."},
    {"row": 4, "feedback_id": "003", "code": "validation_error", "message": "feedback_text: Field required"}
  ]
}
```

The counts always reconcile: `total_rows = imported_rows + skipped_rows + failed_rows`.
`errors` includes reasons for **both skipped and failed rows**, with 1-based Excel
row numbers. A 200 response means the summary is available, not that every row
succeeded. Structural failures return an explanatory `detail` instead. Correct
failed rows and retry; already imported unchanged rows will be skipped.

## Tests and code quality

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
```

On macOS/Linux replace `.venv\Scripts\python.exe` with `.venv/bin/python`.
To apply formatting, run `python -m ruff format .` using the virtual environment.
Tests use temporary databases and do not modify your working feedback database.
Coverage includes all Phase 1 and Phase 2 behavior plus independent validation,
approvals, mixed feedback, corrections, fabricated evidence, low-confidence review,
persistence, duplicate prevention, forced revalidation, batch accounting, filters,
and malformed structured output. Phase 4 tests cover trusted/excluded records,
corrected fields, distributions, multi-category counts, recurring thresholds,
positive patterns, daily/weekly timelines, spikes, zero baselines, and filters.
Phase 5 tests cover recommendation eligibility, evidence/business-rule grounding,
structured failures, duplicate prevention, approval history, deterministic recovery
risk, reason retention, batch processing, filters and human status transitions.
Tests use a fake LLM service and never make paid OpenAI calls.

## Phase 6 frontend

The frontend consumes existing REST endpoints through a same-origin Next.js proxy.
No backend restructuring was needed. Start the backend with the commands above;
in another PowerShell terminal run:

```powershell
cd E:\urban-agent\frontend
npm.cmd ci
Copy-Item .env.example .env.local  # First setup only; preserve an existing file
npm.cmd run dev
```

Open <http://127.0.0.1:3000>. Keep your OpenAI key in the existing backend `.env`.
The frontend environment contains only API routing configuration, never AI secrets.

Managers can now choose **Analyze pending feedback** and confirm inside the app.
UrbanAgent classifies, independently validates, evaluates trusted recovery risk and
refreshes the workspace. An individual record offers **Analyze feedback** to resume
missing work or **Re-analyze** with an explicit confirmation to repeat both steps.
See [workflow, failure handling and re-analysis semantics](docs/analysis-workflow.md).

Dashboard, Feedback, Analytics, Recovery, Recommendations, Human Review and Settings
are reachable from the sidebar. Use **Import feedback** to select
`data/raw/urbanmart_feedback.xlsx`. Charts reflect validated records; import alone
does not perform paid classification or validation. Recommendations require a human
decision, and recovery status changes never send customer messages.

See [frontend setup, pages, test commands, screenshot placeholder and limitations](frontend/README.md).

## Future phases (not implemented)

1. Manually inspect UrbanMart recommendations and recovery cases against their
   supporting validations and evidence IDs.
2. Add authenticated management access and explicit manual review adjudication.
3. Add the Management Report Agent.
4. Connect Google Forms → Google Sheets → n8n → REST; optionally add Gmail later.
5. Add n8n SLA monitoring for human-approved workflows.

Findings must come from actual analyzed feedback. Nothing in this foundation
hard-codes a business problem, sentiment, theme or recommendation.
