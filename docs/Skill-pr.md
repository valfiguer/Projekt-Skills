# Skill: `pr` — Projekt Republic orchestrator

Owns authentication, the cached context, and the safety rules for the whole `pr-*` family.
It also carries the two areas every automation starts from: **tasks** and **time**.

Base URL: `https://api.projektrepublic.com/api/v1`.

## Connect (always first)

```bash
SK="$CLAUDE_PLUGIN_ROOT/skills/pr/scripts"
bash "$SK/auth_check.sh"      # /auth/me → user, org, PAT scope → .projekt-run/context.json
bash "$SK/context_sync.sh"    # caches projects + members
```

A PAT **self-discovers** its `organization_id` and `project_id` from `GET /auth/me` →
`api_key`. A project-scoped key may only touch its own project: listing sibling projects
returns 403, which is the key's scope working, not a bug.

Everything afterwards resolves names from `.projekt-run/context.json` and never re-queries
identity. Token setup → [Configuration](Configuration.md).

## Tasks

```bash
python3 "$SK/tareas.py" --project WEB --file backlog.csv            # dry-run
python3 "$SK/tareas.py" --project WEB --file backlog.csv --apply
python3 "$SK/mover.py" --tasks WEB-12,WEB-13 --assignee jane@acme.com --status in_progress --apply
python3 "$SK/mover.py" --tasks WEB-12 --priority urgent --apply
```

- `POST …/projects/{proj}/tasks` accepts `assignee_id`, `story_points`, `estimated_hours`,
  `sprint_id` and the dates. Only `status` is absent, so only a non-`todo` target needs a
  follow-up PATCH.
- `POST …/projects/{proj}/tasks/bulk` mutates up to 200 tasks per call
  (`set_status`, `set_assignee`, `set_sprint`, `set_parent`, `set_priority`, `add_tags`,
  `remove_tags`, `delete`) and answers `{updated, skipped, errors}`. It never creates.
- There is **no** "a task needs an owner to leave `todo`" rule. The 422 on a move is the
  destination column's `wip_limit`, and only for columns that set one.
- Bulk create has no endpoint: rows are posted sequentially at concurrency ≤3, deduped on
  `(project, title)` and `external_ref`, and logged for resume.

## Time

Time entries are **org-scoped** — the task is a body field, not a path segment.

```bash
python3 "$SK/tiempo.py" log ./timesheet.csv --apply
python3 "$SK/tiempo.py" timer start WEB-12 --apply
python3 "$SK/tiempo.py" timer stop --note "review" --apply
python3 "$SK/tiempo.py" summary --project WEB --date-from 2026-09-01 --date-to 2026-09-30
```

Fields are `minutes` and `entry_date`. There is **one timer per user per organization**: a
second `start` answers `409 timer_already_running`, reported as a no-op. `stop` reads
`/time-entries/active` for the entry id. Totals come from `/time-entries/summary` — the
server sums them, the model never does.

## Reaching the other 685 paths

```bash
bash "$SK/fetch_spec.sh"                   # cache + index the spec in ~/.cache
bash "$SK/spec_lookup.sh" --search invoice  # candidates from a few KB of index
bash "$SK/spec_lookup.sh" "/api/v1/organizations/{org_id}/invoices" post
```

The spec is JSON and never enters the model context. Map of domains →
[API-Endpoints](API-Endpoints.md).

## Safety

Dry-run by default; `--apply` to write. DELETE and `admin/*`, `finance/*`, `payroll/*`
need a second explicit confirmation and are blocked by the guard hook without `--admit`.
The token is never printed — only a fingerprint. See
[Safety and Security](Safety-and-Security.md).
