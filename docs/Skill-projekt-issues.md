# Skill: `projekt-issues`

Bulk-create issues from a CSV/JSON backlog, and assign-then-move existing issues across board columns — with dry-run safety and idempotent resume. Covers the **CREATE** + **ASSIGN** pipeline phases.

Soporta español: crear incidencias en lote, importar backlog, asignar responsables, mover tareas de columna, triaje.

## Prerequisite — connect once

```bash
bash skills/projekt/scripts/auth_check.sh
bash skills/projekt/scripts/context_sync.sh
```

These read `.projekt-run/context.json` and never re-query identity. No token? → [Configuration](Configuration.md).

## 1 — Bulk create (`bulk_issue_create.py`)

Reads the columns of `skills/projekt/assets/import_template.csv`:

```
title,description,status,assignee,estimated_hours,priority,type,labels,external_ref
```

(or a JSON list). Resolves the project by key/name and each `assignee` (email or name) → `user_id` from context. Dedupes against a live `GET /issues` sweep (by `title` and `external_ref`) **and** the ledger.

```bash
# DRY-RUN: prints a create/skip table, writes nothing
python3 skills/projekt-issues/scripts/bulk_issue_create.py --project WEB --file backlog.csv

# APPLY: sequential POST /issues, ≤3 in flight, every create logged for resume
python3 skills/projekt-issues/scripts/bulk_issue_create.py --project WEB --file backlog.csv --apply
```

There is **no bulk-create endpoint** — `/issues/bulk` only *mutates* existing issues. Creation is one `POST /issues` per row at concurrency ≤3 (`--concurrency`, capped at 3). Re-running creates 0 (idempotent).

| Flag | Effect |
| --- | --- |
| `--project <id\|key\|name>` | Target project. |
| `--file <path>` | CSV/JSON backlog. |
| `--apply` | Execute (default is dry-run). |
| `--concurrency <n>` | Parallel creates, capped at 3. |
| `--strict-status` | **Skip** (instead of demote) rows that target a working column with no owner. |

## 2 — Assign + move (`assign_and_move.py`)

Assigns an owner, then moves issues to a target column via `POST /issues/bulk` — two actions in order: `{action:"assignee",value}` then `{action:"status",value}`.

```bash
# DRY-RUN
python3 skills/projekt-issues/scripts/assign_and_move.py \
  --issues WEB-12,WEB-13 --assignee jane@acme.com --status "In Progress"

# APPLY
python3 skills/projekt-issues/scripts/assign_and_move.py \
  --issues WEB-12,WEB-13 --assignee jane@acme.com --status "In Progress" --apply
```

`--issues` takes keys (`WEB-12`) or ids. `--assignee` is **optional** — omit it when the issues already have owners and you only need to move them.

## The assignee-required rule (critical)

An issue **cannot leave `Backlog`/`To Do`** for a working column (In Progress / In Review / Done) without an `assignee_id` — the API returns **422** (`blocked_unassigned`).

- **create:** a row targeting a working column with no resolvable assignee is **demoted to To Do** and flagged **"needs owner"** (never dropped). `--strict-status` skips it instead.
- **assign/move:** any issue still unassigned after the optional assign step is **pre-filtered out of the move** and reported as "needs owner"; the rest of the batch still moves.

Creating or parking in `Backlog`/`To Do` without an assignee is always fine.

## Gotchas

- `/issues/bulk` **does NOT create** — only mutates (assignee/status/priority/labels). Use `bulk_issue_create.py` for creation.
- **Dedupe keys:** `(project_id,title)` + `external_ref`. Give every import row a stable `external_ref` so re-imports are safe even if a title is edited.
- **Status names** are per-project (`project.columns`); the server normalizes localized inputs ("En revisión"). Defaults: `Backlog`, `To Do`, `In Progress`, `In Review`, `Done`.
- **403 cross-org** is fatal and not retried — a PAT is bound to one org. **429** is auto-backed-off; keep concurrency ≤3.
- Re-run after fixing owners — both scripts dedupe via the ledger and resume cleanly.

## What it does NOT do

No estimation (→ [projekt-estimate](Skill-projekt-estimate.md)), time (→ [projekt-time](Skill-projekt-time.md)), docs (→ [projekt-docs](Skill-projekt-docs.md)), or workload (→ [projekt-workload](Skill-projekt-workload.md)). No hard delete (use `/issues/:iid/archive`). It never touches the 1.3 MB spec.

See also: [API Endpoints → Issues](API-Endpoints.md#issues) · [Errors & Troubleshooting](Errors-and-Troubleshooting.md).
