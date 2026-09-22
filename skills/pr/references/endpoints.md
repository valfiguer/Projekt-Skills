# Endpoint cheatsheet — automation core (/api/v1)

The ~90% of calls. For anything else, discover with `spec_lookup.sh --search <term>` then read
the one block. All paths are relative to the API base
(`https://api.projektrepublic.com/api/v1`). Every authenticated call needs
`Authorization: Bearer <pat>` (injected by `lib/http.sh` and `projekt_api.py`).

**The model — read this:** org + project live in the **PATH** for project resources; the
resource is **`tasks`**. Time entries and documents are **ORG-scoped**: their project is a
FIELD in the body, not a path segment. A **project-scoped PAT** may only touch its own project
and **self-discovers** `organization_id` + `project_id` from `GET /auth/me` → `api_key`.
Statuses are `todo | in_progress | done | cancelled` plus per-project custom slugs; tasks carry
a `reference` (e.g. `WEB-12`) and a `number`.

Conventions: `{org}`, `{proj}`, `{tid}` are UUIDs. Lists take `limit` + `offset`. Pipe reads
through `slim.jq` / `slim("task", …)`.

## Identity & context
| Method · Path | Purpose | Notes |
|---|---|---|
| `GET /auth/me` | Current user + PAT scope | With a PAT the `api_key` object carries `{id, name, organization_id, project_id}` — how a key self-discovers its scope (`project_id` null = org-wide). Cookie sessions get `api_key: null`. |
| `GET /organizations` | The caller's orgs | Array of `{id, name, slug, role, …}`. Works with a project-scoped key. |
| `GET /organizations/{org}/projects` | Projects in the org | `{id, key, name, status, …}`. **Org-wide key only** — a project-scoped key gets **403**. |
| `GET /organizations/{org}/members` | Member roster | `{user_id, name, email, role, employee_id, department, expected_hours_per_week, hourly_cost_rate, hourly_bill_rate, …}`. |

## Tasks
| Method · Path | Purpose | Required / gotcha |
|---|---|---|
| `GET …/projects/{proj}/tasks` | Filter/list | `limit, offset, status, priority, type, assignee_id, created_by, sprint_id, tag_id, q, due_before, due_after, parent_id, root_only, include_subprojects, sort, order` |
| `POST …/projects/{proj}/tasks` | Create | **required** `title`. Also `description, priority(low\|medium\|high\|urgent), type, assignee_id, story_points, estimated_hours, start_date, due_date, due_at, sprint_id, parent_id`. Born `todo` — `status` is the ONE field not accepted here. |
| `GET·PATCH·DELETE …/projects/{proj}/tasks/{tid}` | Detail / update / delete | PATCH adds **`status`** to the create fields; `assignee_id: null` unassigns. |
| `POST …/projects/{proj}/tasks/bulk` | Mutate ≤200 at once | `{task_ids*, op*, …}`; `op` ∈ `set_status, set_assignee, set_sprint, set_parent, set_priority, add_tags, remove_tags, delete`. Answers `{updated, skipped, errors}`. **Mutates only — never creates.** |
| `GET …/projects/{proj}/tasks/by-number/{n}` | Resolve `WEB-12` | One request, no sweep. |
| `POST …/projects/{proj}/tasks/search` | Complex filters | Filters as a body instead of a query string. |
| `GET·POST …/tasks/{tid}/comments` · `PATCH·DELETE …/comments/{cid}` | Comments | POST body field is **`body`** (+ optional `parent_id`). |
| `GET …/tasks/{tid}/activity` | The task's bitácora | Read-only audit feed, newest first. |
| `GET …/tasks/{tid}/subtasks` · `…/dependencies` · `…/status-time` · `…/attachments` | Extras | See `spec_lookup.sh`. |

There is **no bulk-create** endpoint: `tareas.py` posts sequentially at concurrency ≤3 and
dedupes on `(project, title)` + `external_ref`. Detail → `tasks.md`.

## Time tracking (ORG-scoped)
| Method · Path | Purpose | Notes |
|---|---|---|
| `POST /organizations/{org}/time-entries` | Log one entry | `{minutes*, entry_date*, project_id, task_id, description, is_billable}` |
| `GET /organizations/{org}/time-entries` | List | `project_id, user_id, from, to, limit, offset` |
| `GET /organizations/{org}/time-entries/summary` | Server-side totals | `project_id, user_id, from, to, group_by` → `{total_minutes, billable_minutes, entries_count, groups[]}` |
| `POST /organizations/{org}/time-entries/start` | Start the timer | `{project_id, task_id, description, is_billable}`; **409 `timer_already_running`** if one is live — ONE per user per org. |
| `GET /organizations/{org}/time-entries/active` | The running entry | How `stop` finds its id. |
| `POST /organizations/{org}/time-entries/{id}/stop` | Stop | No body — attach a note with a follow-up PATCH. |

Detail → `time.md`.

## Aggregates (all read-only)
| Method · Path | Gives | The range trap |
|---|---|---|
| `GET /organizations/{org}/workforce/capacity` | `{week_start, week_end, rows[{user_id, name, expected_hours, net_expected_hours, holiday_hours, absence_hours, logged_hours}]}` | **No parameters.** Always the CURRENT week, and it says which one. |
| `GET /organizations/{org}/dashboard/stats` | `{issues{}, projects{}, priority[], workload[{user_id,name,assigned,done}], finance{}, tasks_trend[], my_tasks[], most_active_projects[]}` | **No parameters.** Counts are ALL-HISTORY — labelling them with a period is a lie. |
| `GET /organizations/{org}/time-entries/summary` | logged minutes | The only one that honours `from`/`to`. |
| `GET …/projects/{proj}/sprints` · `…/sprints/{sid}/stats` · `/organizations/{org}/sprints/{sid}/burndown` | Sprint progress | |
| `GET /organizations/{org}/roadmap` | Org roadmap | **Read-only — no POST exists.** |

## Documents (ORG-scoped, plain markdown)
| Method · Path | Purpose | Notes |
|---|---|---|
| `GET /organizations/{org}/documents` | List | `project_id, parent_id, folder_id, kind, is_template, q, limit, offset` |
| `POST /organizations/{org}/documents` | Create | `{title*, content, project_id, folder_id, parent_id}` |
| `GET·PATCH·DELETE /organizations/{org}/documents/{id}` | Read / update / soft-delete | PATCH also takes `position`. |
| `GET …/documents/{id}/versions` · `…/publication` · `…/comments` · `…/template` | Extras | |

`content` is **plain markdown**. There is no EditorJS block format, no `blocks` field and no
`?format=markdown` — what you write is what you read back. `content` is always `null` when
`kind` is `file`.

## The rest

This page is the automation core only. The **whole** surface — 685 paths, 917 operations, 16
domains, with sensitivity and coverage per operation — is in `catalogo.md`, which is generated
from the spec by `scripts/catalogo.py` rather than written by hand. Drill in with
`spec_lookup.sh --domain <d>` / `--search <term>`, read ONE operation, then call it with
`llamar.py`. Never `cat` the spec.
