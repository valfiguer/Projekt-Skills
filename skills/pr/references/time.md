# Time tracking

Script: `scripts/tiempo.py`.

## Time entries are ORG-scoped

The task is a **field in the body**, not a segment of the path. This is the single biggest
difference from the pre-rewrite API.

| Method | Path | Body / query |
|---|---|---|
| `POST` | `…/time-entries` | `{minutes*, entry_date*, project_id, task_id, description, is_billable}` |
| `GET` | `…/time-entries` | `project_id, user_id, from, to, limit, offset` |
| `GET` | `…/time-entries/summary` | `project_id, user_id, from, to, group_by` → `{total_minutes, billable_minutes, entries_count, groups[]}` |
| `POST` | `…/time-entries/start` | `{project_id, task_id, description, is_billable}` |
| `GET` | `…/time-entries/active` | the caller's running entry |
| `POST` | `…/time-entries/{id}/stop` | no body |
| `GET/PATCH/DELETE` | `…/time-entries/{id}` | edit or remove one entry |

Field names: **`minutes`** and **`entry_date`** (not `duration_minutes` / `date`).

## One timer per user, per organization

Starting a second one answers **`409 timer_already_running`** — `tiempo.py` reports that as a
no-op, not a failure. `stop` does not take a task: it reads `/time-entries/active` to find the
entry id. A `--note` on stop is applied with a follow-up PATCH, because the stop endpoint takes
no body.

## The parameters are `from` / `to`, and a wrong name is silent

Measured against production on 2026-09-22:

| Query | Answer |
|---|---|
| `?group_by=user` | 77.587 min — **all history** |
| `?from=2026-09-15&to=2026-09-21&group_by=user` | 37.432 min, and the response echoes `from_date`/`to_date` |
| `?date_from=…&date_to=…&group_by=user` | **77.587 min** — the range was dropped without a word |

An unknown query parameter is ignored, not rejected, so `date_from` silently widens the
answer to everything ever logged. **Always check the `from_date`/`to_date` the response
echoes back**: `null` there means no range was applied, whatever you thought you sent.

## Totals come from the server

`tiempo.py summary` calls `/time-entries/summary`, which sums server-side. Per-task totals have
no aggregate of their own, so that one path lists the project's entries and filters on
`task_id` locally — it prints the row count so a truncated page is visible rather than
silently wrong. Narrow it with `--date-from` / `--date-to`.

## Sheet format

Rows `{issue, date, minutes, note?}` as CSV/TSV/JSON. Aliases accepted: `issue_id`/`key`,
`duration_minutes`/`mins`, `description`/`comment`. Rejected in the dry-run, with the reason
printed and never silently dropped: `minutes <= 0`, unparseable minutes, bad or empty dates,
and future dates. Dedupe is `(task_id, date, note)` via the ledger.
