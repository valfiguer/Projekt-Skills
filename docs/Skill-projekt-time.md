# Skill: `projekt-time`

Batch-log time on issues from a sheet, drive per-issue timers, and roll up totals via the server's `time-summary`. Covers the **TIME** pipeline phase. One script, three subcommands: `log`, `timer`, `summary`.

Soporta español: registrar/cargar tiempos, fichajes, horas trabajadas, temporizador, resumen de tiempos.

## Prerequisite — connect once

```bash
bash skills/projekt/scripts/auth_check.sh
bash skills/projekt/scripts/context_sync.sh
```

## Batch-log time from a sheet

Rows are `{issue, date, minutes, note?}` as CSV/TSV/JSON. `issue` is a **key** (`PRJ-123`) or a UUID **id**; `date` is `YYYY-MM-DD`; `minutes` is a positive integer. Column aliases accepted: `issue_id`/`key`, `duration_minutes`/`mins`, `description`/`comment`.

```bash
# DRY-RUN — prints a table (issue, date, minutes, note, action) + a skip list, writes nothing
python3 skills/projekt-time/scripts/time_log.py log ./timesheet.csv

# APPLY — posts the planned entries; re-run safely (dedupe → creates 0)
python3 skills/projekt-time/scripts/time_log.py log ./timesheet.csv --apply
```

What it validates:

- **Rejects** `minutes <= 0`, unparseable minutes, bad/empty dates, and **future dates** — each listed in the "Skipped / blocked" section with a reason, never silently dropped.
- **Resolves** each issue ref to `(issue_id, project_id)` — the POST path needs the project (`POST /projects/{pid}/issues/{iid}/time-entries`). UUIDs hit `GET /issues/{id}`; keys use `GET /issues?q=<key>` and match `key` exactly. Each unique issue is queried at most once per run.
- **Dedupes** on `(issue_id, date, note)` via the ledger — re-running the same sheet creates nothing new and resumes a half-finished run.

## Timers (single issue)

```bash
python3 skills/projekt-time/scripts/time_log.py timer start PRJ-123                # dry-run
python3 skills/projekt-time/scripts/time_log.py timer start PRJ-123 --apply        # POST timer-start
python3 skills/projekt-time/scripts/time_log.py timer stop  PRJ-123 --note "review" --apply  # POST timer-stop
```

- `timer-start` is **idempotent**: a timer already running returns 200 `"Timer already running"` — treated as success.
- `timer-stop` computes elapsed seconds and **rounds to the nearest minute, minimum 1 min**, creating exactly one entry. No active timer → 404, reported as a no-op (not a failure). `--note` is optional and applies only to `stop`.

## Roll-up (read-only)

```bash
python3 skills/projekt-time/scripts/time_log.py summary PRJ-123
```

Calls `GET /projects/{pid}/issues/{iid}/time-summary` and prints `total_minutes` (+ hours), `entry_count`, and the per-user breakdown. **Totals come from the server** — never summed in-model.

## Dry-run → apply (the contract)

`log` and `timer` print a plan and exit without writing. Add `--apply` to execute. Re-running after `--apply` dedupes and resumes from the ledger. `summary` is always read-only.

## Gotchas

- **`minutes` vs hours.** The API field is `duration_minutes` (integer ≥ 1). This skill takes **minutes**. If your sheet has hours, multiply by 60 first. Fractional minutes are rounded.
- **403 cross-org** stops the run — a PAT is bound to one org. **400** means `duration_minutes <= 0`. **422** is surfaced, not hidden.
- **Issues aren't in `context.json`** (only projects + members), so issue resolution does a memoised lookup — expected, not a cache violation.

## What it does NOT do

No editing/deleting existing entries (`PUT/DELETE .../time-entries/{entryId}`), no cross-issue or org-wide aggregation (use [projekt-workload](Skill-projekt-workload.md)), no points→hours estimation (→ [projekt-estimate](Skill-projekt-estimate.md)). It only logs minutes, drives one issue's timer, and reads one issue's roll-up.

See also: [API Endpoints → Time tracking](API-Endpoints.md#time-tracking) · [Estimation Units](Estimation-Units.md).
