# Tasks — create, assign, move

Scripts: `scripts/tareas.py` (bulk create) · `scripts/mover.py` (bulk mutate).

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `…/projects/{proj}/tasks` | `limit, offset, status, priority, type, assignee_id, sprint_id, tag_id, q, due_before, due_after, parent_id, root_only, sort, order` |
| `POST` | `…/projects/{proj}/tasks` | `{title*, description, priority, type, assignee_id, story_points, estimated_hours, start_date, due_date, due_at, sprint_id, parent_id}` |
| `PATCH` | `…/projects/{proj}/tasks/{id}` | same fields **plus `status`** |
| `POST` | `…/projects/{proj}/tasks/bulk` | `{task_ids*(≤200), op*, status\|assignee_id\|sprint_id\|parent_id\|priority\|tag_ids}` |
| `GET` | `…/projects/{proj}/tasks/by-number/{n}` | resolve `WEB-12` in one request |
| `POST` | `…/projects/{proj}/tasks/search` | complex filters as a body |

`op` ∈ `set_status · set_assignee · set_sprint · set_parent · set_priority · add_tags · remove_tags · delete`.
Bulk answers `{updated, skipped, errors}` — `skipped` are tasks already in the target state
(idempotent no-op), `errors` give a reason per id. It is per-project and commits once.

## Two things the pre-rewrite skill got wrong

1. **`assignee_id` IS settable on create.** The old "POST then PATCH the assignee" dance was
   unnecessary. `status` is the only field absent from the create body, so only a non-`todo`
   target still needs a follow-up PATCH.
2. **There is no "a task needs an owner to leave `todo`" rule.** That was a legacy invention;
   nothing in the contract or the service enforces it. Unassigned tasks move fine. The real
   422 on a move is the destination column's **`wip_limit`**, and only for columns that set
   one (default columns have `wip_limit = null` and restrict nothing).

## Statuses

`todo · in_progress · done · cancelled`, plus per-project custom slugs (`^[a-z0-9_]+$`, ≤20).
`mover.py` normalizes the usual human names — "Backlog", "To Do", "En curso", "Hecho" — to
these. A slug it does not know is passed through, because a project may have defined it.

## Dedupe

`tareas.py` sweeps the project's existing tasks and skips on `(project, title)` or a matching
`external_ref`, and also consults the ledger. Give every import row a stable `external_ref` so
a re-import stays safe even after a title is edited.
