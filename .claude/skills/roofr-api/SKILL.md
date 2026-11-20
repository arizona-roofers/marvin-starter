---
name: roofr-api
description: Read Arizona Roofers' job pipeline (jobs, stages, lead sources, values, owners) from the Roofr External API. Use for any question about jobs, leads, sales, close rates, revenue or the pipeline, such as "how many jobs did we win last month", "what is our close rate by lead source", or "export this week's jobs".
---

# Roofr External API

Read-only access to Arizona Roofers' job pipeline at
`https://roofr-search.vercel.app/api/external`. The dashboard at
https://roofr-search.vercel.app shows the same data visually.

## Auth

Every request except `/health` needs the header `Authorization: Bearer <token>`.
The token is `ROOFR_EXTERNAL_TOKEN` in the workspace `.env` file.

- Never print the token, log it, or put it in a reply or a file other than `.env`.
- Read it inside the command so it never shows on screen (see the examples).
- If `.env` has no token, tell the person to ask Travis for it. Do not guess one.

## Endpoints

| Endpoint | Use |
|----------|-----|
| `/health` | Liveness check, no auth |
| `/schema` | Column reference and endpoint list. Call this when unsure of a field. |
| `/summary` | Server-side totals, close rates, and breakdowns by category, workflow, owner and lead source |
| `/jobs` | Paginated job list. Filters: `from`, `to` (YYYY-MM-DD), `stage`, `stage_category`, `workflow`, `owner`. `format=json` or `csv`. Max 1000 rows a page. |
| `/job/<id>` | One job by its Roofr ID |

## Which one to call

1. **Counts, totals, averages, breakdowns: call `/summary` first.** It is one fast request.
2. Call `/jobs` only when row-level detail is needed.
3. For a spreadsheet, use `/jobs?format=csv` with a tight date range.
4. Page with `next_offset` until it is null.
5. Never loop `/job/<id>` over many jobs. Use `/jobs` with filters.

## Limits

- 60 seconds a request, 1000 rows a page.
- More than 10,000 rows: split the request by month.
- Dates are `YYYY-MM-DD`.
- `stage_category` values are lowercase: `won`, `lost`, `in_progress`, `unqualified`, `rescheduling`.

## Examples

Mac, or Git Bash on Windows:

```bash
TOKEN=$(grep '^ROOFR_EXTERNAL_TOKEN=' .env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://roofr-search.vercel.app/api/external/summary?from=2026-01-01&to=2026-01-31"
```

PowerShell:

```powershell
$token = (@(Get-Content .env) -match '^ROOFR_EXTERNAL_TOKEN=')[0] -replace '^ROOFR_EXTERNAL_TOKEN=', ''
Invoke-RestMethod "https://roofr-search.vercel.app/api/external/summary?from=2026-01-01&to=2026-01-31" `
  -Headers @{ Authorization = "Bearer $token" }
```

When reporting numbers, say the date range they cover.
