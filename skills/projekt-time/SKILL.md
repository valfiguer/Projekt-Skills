---
name: projekt-time
description: >-
  Batch-log time on Projekt issues from a sheet, drive per-issue timers
  (start/stop), and roll up totals via the server's time-summary. Use whenever
  the user wants to record/import worked time, log hours/minutes against issues,
  start or stop a timer, or get a time roll-up for an issue. Soporta español:
  registrar/cargar tiempos, fichajes, horas trabajadas, temporizador, resumen
  de tiempos por incidencia/tarea.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# Projekt — time tracking

> **⚠ NOT YET PORTED to /api/v1.** The base URL is fixed (shares `projekt_api.py`, now on
> `https://projekt.3xa.es/api/v1`), but the endpoint PATHS in `time_log.py` are still the **legacy
> flat** ones (`/issues?q=`, `/projects/{pid}/issues/{iid}/time-entries`, `…/time-summary`) and
> **will 404** on the rewrite. To port: resolve tasks via
> `GET /organizations/{org}/projects/{proj}/tasks?q=<ref>` and log time under
> `/organizations/{org}/projects/{proj}/tasks/{tid}/time-entries` (contract `paths/time-entries.yaml`;
> confirm with `bash ../projekt/scripts/spec_lookup.sh --search time-entries`). Working today:
> `projekt` connect + `projekt-issues` task create/list.

Log time in bulk, run timers, and roll up time-summary for Projekt tasks. This
is the **TIME** step of the `projekt` pipeline. `SK="${CLAUDE_SKILL_DIR}/scripts"`.

## Prerequisite — connect once

Run the orchestrator's auth + context first (this skill reads the cached context
for org/token; do not re-auth here):

```bash
PSK="${CLAUDE_SKILL_DIR}/../projekt/scripts"
bash "$PSK/auth_check.sh"      # resolves user + org, writes .projekt-run/context.json
bash "$PSK/context_sync.sh"    # caches projects + members
```

## Batch-log time from a sheet

Sheet rows are `{issue, date, minutes, note?}` as CSV/TSV/JSON. `issue` is an
issue **key** (`PRJ-123`) or a UUID **id**; `date` is `YYYY-MM-DD`; `minutes`
is a positive integer. Column aliases accepted: `issue_id`/`key`, `duration_minutes`/`mins`,
`description`/`comment`.

```bash
# DRY-RUN — prints a table (issue, date, minutes, note, action) + a skip list, writes nothing
python3 "$SK/time_log.py" log ./timesheet.csv

# APPLY — posts the planned entries; re-run safely (dedupe → creates 0)
python3 "$SK/time_log.py" log ./timesheet.csv --apply
```

What it validates and how it behaves:

- **Rejects** `minutes <= 0`, unparseable minutes, bad/empty dates, and **future
  dates** — each is listed in the "Skipped / blocked" section with the reason,
  never silently dropped.
- **Resolves** each issue ref to `(issue_id, project_id)` — the POST path needs
  the project (`POST /projects/{pid}/issues/{iid}/time-entries`). UUIDs hit
  `GET /issues/{id}`; keys use `GET /issues?q=<key>` and match `key` exactly.
  Each unique issue is queried at most once per run.
- **Dedupes** on `(issue_id, date, note)` via the shared Ledger, so re-running
  the same sheet creates nothing new and resumes a half-finished run.

## Timers (single issue)

```bash
python3 "$SK/time_log.py" timer start PRJ-123                 # dry-run
python3 "$SK/time_log.py" timer start PRJ-123 --apply         # POST timer-start
python3 "$SK/time_log.py" timer stop  PRJ-123 --note "review" --apply   # POST timer-stop
```

- `timer-start` is **idempotent**: if a timer is already running it returns 200
  with `message: "Timer already running"` — treated as success, not an error.
- `timer-stop` computes elapsed seconds and **rounds to the nearest minute,
  minimum 1 min**, creating exactly one entry. No active timer → 404, reported
  as a no-op (not a failure). `--note` is optional and only applies to `stop`.

## Roll-up (read-only)

```bash
python3 "$SK/time_log.py" summary PRJ-123
```

Calls `GET /projects/{pid}/issues/{iid}/time-summary` and prints
`total_minutes` (+ hours), `entry_count`, and the per-user breakdown. **Totals
come from the server** — this never sums rows in-model. Prefer this over listing
and adding `time-entries` yourself.

## Dry-run → apply (the contract)

`log` and `timer` print a plan and exit without writing. Add `--apply` to
execute. Re-running after `--apply` dedupes (logged entries are skipped) and
resumes from the ledger. `summary` is always read-only.

## Gotchas

- **`minutes` vs hours.** The API field is `duration_minutes` (integer ≥ 1).
  This skill takes **minutes**. If a sheet has hours, multiply by 60 before
  importing. Fractional minutes are rounded to the nearest whole minute.
- **403 cross-org** stops the run — a PAT is bound to one org; switch
  org/token. **400** means `duration_minutes <= 0` (already filtered in dry-run
  but logged if the server still rejects). **422** is surfaced, not hidden.
  See `../projekt/references/errors.md`.
- **Issues aren't in `context.json`** (only projects + members are), so issue
  resolution does a lookup — that's expected and memoised, not a context-cache
  violation.
- Units background: `../projekt/references/units.md`. Endpoint table:
  `../projekt/references/endpoints.md` → "Time tracking".

## What it does NOT do

No editing/deleting existing entries (`PUT/DELETE .../time-entries/{entryId}`),
no cross-issue or org-wide aggregation (use `projekt-workload` for `/workload`),
no points→hours estimation (that's `projekt-estimate`). It only logs minutes,
drives one issue's timer, and reads one issue's roll-up.
