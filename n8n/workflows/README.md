# n8n workflow exports

Reserved for future sanitized workflow JSON exports. No workflows run in Phase 1.
Keep credentials in n8n, never in committed exports.

Future Google Sheets and Gmail workflows will map incoming records to the public
`POST /api/feedback` contract. Use a stable source and source feedback ID for retries.
n8n must not access the database or import backend implementation modules.
