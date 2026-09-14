# UrbanAgent: AI Customer Feedback Analyst

UrbanAgent is a university project for a multi-agent customer experience platform.
Its planned agents will classify feedback, independently validate results, detect
trends, recommend improvements and produce evidence-backed management reports.

**Current scope: Phase 2 foundation.** The FastAPI backend accepts raw feedback
through JSON or Excel and stores it in SQLite. The Classification Agent can send an
individual raw record to OpenAI, validate typed output, store one overall analysis
plus multiple evidence-backed aspects, and expose those results through REST.
The Validation Agent, trends, n8n, and frontend dashboard are not implemented.

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
│   │   ├── agents/classifier.py
│   │   └── services/
│   │       ├── analysis.py
│   │       ├── excel.py
│   │       ├── llm.py
│   │       └── feedback.py
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/README.md
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
│   ├── test_feedback.py
│   ├── test_excel.py
│   ├── test_reference.py
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
and n8n are not needed yet. The OpenAI key is only required by classification routes.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY and OPENAI_MODEL before using classification.
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
# Edit .env and set OPENAI_API_KEY and OPENAI_MODEL before using classification.
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
| GET | `/api/feedback/analyses` | List/filter analyses; limit 1–100 |
| POST | `/api/feedback` | Create one record; 201, validation 422, duplicate/conflict 409 |
| POST | `/api/import/excel` | Multipart field `file`; row summary 200, malformed file 400, oversized file 413 |
| POST | `/api/feedback/{id}/classify` | Classify once; `?force=true` reprocesses |
| POST | `/api/feedback/classify-all` | Classify records without results; `?force=true` reprocesses all |

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

### Manual real-API check in Swagger

After `OPENAI_API_KEY` and `OPENAI_MODEL` are set in `.env`, start FastAPI and open
`http://127.0.0.1:8000/docs`:

1. Expand `POST /api/import/excel`, select **Try it out**, choose
   `data/raw/urbanmart_feedback.xlsx` for `file`, and select **Execute**. A clean
   database returns `total_rows: 30` and `imported_rows: 30`; a repeat import returns
   `skipped_rows: 30`.
2. Expand `GET /api/feedback`, select **Try it out**, set `offset` to `0` and `limit`
   to `100`, then select **Execute**. Find the record whose external `feedback_id` is
   `F009` and note its integer `id`. Classification routes use this database ID.
3. Expand `POST /api/feedback/{id}/classify`, select **Try it out**, enter that
   integer ID, leave `force` as `false`, and select **Execute**. The behavioral goal
   is to preserve the positive product-related statement and negative Pricing
   statement as supported aspects, mark the comment mixed when warranted, and avoid
   unsupported details. This goal is not hard-coded into production logic.
4. Expand `GET /api/feedback/{id}/analysis`, enter the same integer ID, and select
   **Execute**. Confirm the saved response preserves external ID `F009`, includes
   grounded evidence phrases, and records the configured model.
5. Repeat the single-record check with F017 for neutral or unclear handling, F004
   for multiple issues, and F027 for positive Delivery feedback. Find each internal
   ID through the list endpoint first.

Calling the F009 classification route again with `force=false` returns its saved
result without a new paid API call. Use `force=true` only when intentionally testing
reclassification.

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
Coverage includes all Phase 1 behavior plus typed classification, negative,
positive, mixed and multi-category feedback, ambiguity review, invalid LLM output,
persistence, reprocessing rules, batch failures, and analysis filters. Tests use a
fake LLM service and never make paid OpenAI calls.

## Future phases (not implemented)

1. Manually test representative classifications with the configured OpenAI model.
2. Add a small Next.js upload form, import-result display and feedback list.
3. Add an independent Validation Agent with its own stored output and review state.
4. Add Trend Analysis with deterministic Python counts, evidence-backed
   Recommendations, and Management Report agents.
5. Connect Google Forms → Google Sheets → n8n → REST; optionally add Gmail later.
6. Add dashboard charts, emerging issue detection, recovery/escalation cases,
   customer-risk indicators and n8n SLA monitoring.

Findings must come from actual analyzed feedback. Nothing in this foundation
hard-codes a business problem, sentiment, theme or recommendation.
