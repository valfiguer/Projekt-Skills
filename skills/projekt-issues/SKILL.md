---
name: projekt-issues
description: >-
  Bulk-create and triage Projekt tasks (projekt.3xa.es) from a CSV/JSON backlog, and
  assign-then-move tasks across board columns safely. Use when the user wants to import
  a backlog, mass-create tasks, assign owners, or move tasks to In Progress/Done. Soporta
  español: crear incidencias/tareas en lote, importar backlog, asignar responsables, mover
  tareas de columna, triaje. Enforces the assignee-required rule so unassigned tasks never
  advance into a working status.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# Projekt — tasks (bulk create + assign/move)

Create tasks in bulk from a file, and assign+move existing tasks, with dry-run safety and
idempotent resume. Part of the `projekt` pipeline (phases CREATE + ASSIGN).

> **Rewrite note (/api/v1):** the API was rebuilt. The resource is now **`tasks`** (not
> `issues`), and **org + project live in the URL PATH**:
> `POST /organizations/{org}/projects/{project}/tasks`. Org + project are self-discovered
> from the PAT's own scope via `/auth/me` (`api_key.organization_id` / `api_key.project_id`),
> cached by `auth_check.sh`. Statuses are `todo | in_progress | done | cancelled`.

`SK="${CLAUDE_SKILL_DIR}/scripts"` — use it for every command below.

## Prerequisite (connect once)

Run the **`projekt`** skill's setup first; these scripts read `.projekt-run/context.json` and
never re-query identity:

```bash
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/auth_check.sh"
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/context_sync.sh"
```

If there's no token, see `skills/projekt/references/auth-setup.md`.

## 1. Bulk create — `bulk_issue_create.py`

Reads the columns of `skills/projekt/assets/import_template.csv`
(`title,description,status,assignee,estimated_hours,priority,type,labels,external_ref`) or a JSON
list. Resolves the project by key/name (or the PAT's own project scope if `--project` is omitted)
and each `assignee` (email or name) → `user_id` from context. Dedupes against a live
`GET .../tasks` sweep (by `title` and `external_ref`) **and** the Ledger.

```bash
# DRY-RUN: prints a create/skip table, writes nothing
python3 "$SK/bulk_issue_create.py" --project WEB --file backlog.csv

# APPLY: sequential POST .../tasks, ≤3 in flight, every create logged for resume
python3 "$SK/bulk_issue_create.py" --project WEB --file backlog.csv --apply

# --project may be omitted when using a project-scoped PAT (self-discovered):
python3 "$SK/bulk_issue_create.py" --file backlog.csv --apply
```

There is **no bulk-create endpoint** — creation is one `POST .../tasks` per row at concurrency ≤3
(`--concurrency`, capped at 3). Re-running creates 0 (idempotent).

**Create → PATCH flow.** A task is born `todo` and **unassigned** — the create body does NOT accept
`assignee_id`. So the script POSTs the task, then applies the `assignee_id` and any non-`todo`
`status` via a follow-up `PATCH .../tasks/{id}`. Body of create:
`{title*, description?, priority?, type?, estimated_hours?}`.

Flags: `--strict-status` skips (instead of holding at `todo`) rows that request a working status with
no owner.

## 2. Assign + move — `assign_and_move.py`  ⚠ NOT YET PORTED

> **TODO (port to /api/v1):** this script still targets the legacy flat `POST /issues/bulk`
> mutate endpoint, which **does not exist on the rewrite**. Port it to per-task
> `PATCH /organizations/{org}/projects/{project}/tasks/{id}` (`{assignee_id}` then `{status}`),
> resolving task ids by `reference` (e.g. `WEB-12`) from a `GET .../tasks` sweep. Until then, use
> `bulk_issue_create.py` (which does assign+advance on create) or PATCH tasks directly via the
> `projekt` skill's `pj_req`. See `skills/projekt/references/endpoints.md`.

## The assignee-required rule (critical)

A task **cannot advance out of `todo` into a working status** (`in_progress` / `done`) without an
`assignee_id`. See `skills/projekt/references/errors.md`.

- **create**: a row requesting a working status with no resolvable assignee is **left at `todo`** and
  flagged **"needs owner"** (never dropped). `--strict-status` skips it instead.
- Creating in `todo` without an assignee is always fine.

## Gotchas

- **org + project are in the PATH** now (`/organizations/{org}/projects/{project}/tasks`), not query
  params or an `X-Org-Id` header. A **project-scoped PAT** can only touch its own project (self-
  discovered from `/auth/me` `api_key.project_id`); listing sibling projects returns **403**.
- **Statuses** are `todo | in_progress | done | cancelled`. Localized/legacy names ("Backlog",
  "To Do", "In Progress", "En revisión") are normalized to these by the script.
- **Assignee is set via PATCH, not on create** — the create body ignores `assignee_id`.
- **Dedupe keys**: `(project,title)` + `external_ref`. Give every import row a stable `external_ref`
  so re-imports are safe even if a title is edited.
- **403** (wrong org/project/scope) is fatal and not retried. **429** is auto-backed-off by the
  client; keep concurrency ≤3. (errors.md)
- Re-run after fixing owners — create dedupes via the Ledger and resumes cleanly.

## What it does NOT do

No estimation (→ `projekt-estimate`), no time logging (→ `projekt-time`), no docs (→ `projekt-docs`), no
workload reports (→ `projekt-workload`). It never touches the full OpenAPI spec.
