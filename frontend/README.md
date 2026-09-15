# UrbanAgent web workspace — Phase 6

A light management interface built with Next.js App Router, React, TypeScript,
Tailwind CSS, Recharts and lucide-react. TanStack Query manages request state and
cache invalidation. All production records and metrics come from FastAPI.

## Start locally

Use Node.js 22.18 or newer and Python 3.12+. Open two PowerShell terminals.

Backend, from the repository root:

```powershell
cd E:\urban-agent
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Keep your existing root `.env` and OpenAI key. If you have no virtual environment,
first run `py -3.12 -m venv .venv`. See the root README for backend configuration.

Frontend, in a second terminal:

```powershell
cd E:\urban-agent\frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev
```

Copy the environment example only on first setup; preserve any existing `.env.local`.
Visit <http://127.0.0.1:3000>. Swagger is at <http://127.0.0.1:8000/docs>.
On macOS/Linux use `npm` and `.venv/bin/python` instead of the Windows executables.

## Environment and API boundary

| Variable                   | Default                 | Purpose                                         |
| -------------------------- | ----------------------- | ----------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | `/backend`              | Browser API prefix, centralized in `lib/api.ts` |
| `BACKEND_API_URL`          | `http://127.0.0.1:8000` | Server rewrite destination in `next.config.ts`  |

The browser requests `/backend/api/...` on the Next.js origin. Next forwards it to
FastAPI `/api/...`; `/backend/health` forwards to `/health`. This same-origin proxy
works without changing backend routes or adding CORS. A direct cross-origin API
URL would require a separately configured CORS policy. Rebuild production after
changing environment values; restart development after environment changes.

Never place the OpenAI key in `NEXT_PUBLIC_*` variables or frontend code. It stays
in the backend `.env`. Opening pages makes no paid AI calls. Managers can confirm
**Analyze pending feedback** or an individual **Analyze feedback** action in the UI.
UrbanAgent then classifies, validates and evaluates recovery without Swagger.
Recommendation generation remains a separate backend operation.

## Pages

| Page                               | Capabilities                                                                                                                        |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Dashboard `/`                      | Feedback, negative, high-risk and trend KPIs; sentiment/category/severity charts; weekly timeline and emerging issues               |
| Feedback `/feedback`               | Text/ID search, sentiment/severity/category/source filters, 15-row pagination, source and evidence detail dialog                    |
| Analytics `/analytics`             | Submitted-date range, validation coverage, aspects, ratings, category detail, positive/negative patterns, evidence links and spikes |
| Recovery `/recovery`               | Status totals, risk/status filters, original source, risk points/reasons, action/draft, assignee and explicit status saving         |
| Recommendations `/recommendations` | Priority/status filters, problem/action/rationale, confidence, evidence IDs, approval history and confirmed approve/reject          |
| Human Review `/human-review`       | Classifier/validator review flags, `needs_review` and `rejected` records, with comparative detail                                   |
| Settings `/settings`               | Connection check, API prefix and workspace operating boundaries                                                                     |

The health indicator polls every 30 seconds. Query results stay fresh for 30 seconds;
Dashboard and Analytics offer Refresh. Import invalidates cached views. Decisions
refresh affected recommendations or recovery/dashboard data. Errors offer retry.

## Import and inspect

1. Click **Import feedback** on Dashboard, Feedback, Analytics or Human Review.
2. Select or drop `data/raw/urbanmart_feedback.xlsx` from the repository root.
3. Click **Import workbook**. Progress shows transferred bytes, then server processing.
4. Inspect total/imported/skipped/failed counts and every returned row error.
5. Choose **Analyze N feedback** after import, or **Analyze pending feedback** on
   Feedback. The count covers all pending records in the workspace, not just this upload.
6. Confirm, wait for the indeterminate analyzing state, then inspect the success,
   human-review and failure totals. Feedback, analytics and recovery refresh automatically.
7. Open a feedback row to compare source and results. **Analyze feedback** resumes
   missing work; **Re-analyze** requires confirmation and reruns both AI steps.

Required columns: `feedback_id`, `feedback_text`. Optional: `source`, `submitted_at`,
`rating`, `customer_name`, `customer_email`. One nonempty `.xlsx` up to 10 MB is
accepted, matching the default backend limit. Server validation remains authoritative.
Reimport uses the existing duplicate prevention. Import does not automatically run AI.

## Interpreting results

- Analytics trust `approved` and `approved_with_changes` validations, including
  review-flagged records when the backend includes them. The review queue stays visible.
- Feedback filters prefer validator corrections, falling back to classifier output.
  Details preserve both assessments; classifier aspects remain separately identified.
- Mixed sentiment is a distinct fourth group. Categories overlap across records;
  category sentiment counts describe record-level validation, not aspect sentiment.
- Time charts use supplied submission dates only. Date ranges exclude undated records.
  Emerging signals use the backend's latest applicable week and configured thresholds.
- **Active Trends** counts recurring negative categories. **High-Risk Cases** counts
  High/Critical cases excluding resolved/dismissed. Risk scores are rule-based points.
- Approval records management intent, not execution. Approved-for-contact status does
  not send a message. Response drafts remain drafts until a human acts outside this UI.

## Checks

```powershell
cd E:\urban-agent\frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run format:check
npm.cmd test
npm.cmd run build
npm.cmd run start
```

With backend and frontend running, run `npm.cmd run test:e2e` in another terminal.
Browser smoke tests use installed Microsoft Edge in headless mode. They visit all
pages, inspect real feedback when present, reject an invalid file without uploading,
and check tablet overflow. They never classify, approve, send messages or import data.
Set `PLAYWRIGHT_BASE_URL` for another local frontend port. Screenshots/traces go to
the ignored root `.artifacts/` directory.

`npm.cmd run test:pipeline` runs the complete manager workflow in Edge using a
temporary database and an offline LLM fixture. It starts isolated servers on ports
13001/18001 with a separate Next cache, imports synthetic workbooks, confirms batch
and individual analysis, checks refresh/review navigation and re-analysis. It never
uses your OpenAI key or working database. This Windows test expects the root `.venv`.

Component tests isolate fixtures in `tests/` and mock the API. They cover dashboard
and error states, filters, evidence, management decisions, imports and API pagination.
No fixtures are imported by production components. `npm.cmd run format` formats the
frontend; the lockfile pins installed dependencies.

## Known limitations

- Local university demonstration scope: authentication and user roles are not implemented.
- Feedback/analysis/validation are fetched in API pages of 100 and joined by database
  ID; search/filter/pagination run locally. Large deployments need server-side joined
  filtering and count endpoints.
- Human Review supports inspection; no manual adjudication endpoint exists yet.
  Recovery exposes timestamps but no status-event history, so history is not invented.
- Analysis is synchronous and guarded against overlapping pipeline requests in a
  single backend process. Use one worker locally. A production multiworker setup needs
  shared job locks and durable jobs. Browser/proxy timeout is 30 minutes; a disconnected
  request may continue server-side. Check status before retrying; completed work is reused.
- Re-analysis follows existing current-result persistence: successful classification
  replaces aspects, invalidates validation and its recovery case, and reruns validation.
  It does not create an analysis history. Existing recovery case decisions are replaced.
- No automatic AI generation, contact, n8n, Management Report Agent, live integrations,
  dark mode or account management is added in this phase.
- A dependent request failure shows a page error instead of partial totals. Empty
  charts reflect missing eligible data and never display demonstration metrics.
- Keyboard controls, native modal focus handling, visible focus, chart descriptions,
  reduced motion and tablet layouts are included; no formal accessibility audit is claimed.

## Screenshots

Placeholder for curated university report screenshots. Browser checks produce
`dashboard-desktop.png`, `dashboard-tablet.png`, individual page captures,
`feedback-detail.png` and `import-validation.png` in `.artifacts/screenshots/`.
Review screenshots for customer information before sharing them.
