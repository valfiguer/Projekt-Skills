# Endpoint cheatsheet — automation core (rewritten /api/v1)

The ~90% of calls. For anything else, discover with `spec_lookup.sh --search <term>` then read the
block. All paths are relative to the API base (`https://projekt.3xa.es/api/v1`). Every authenticated
call needs `Authorization: Bearer <pat>` (both injected by `lib/http.sh`; it also still sends a
harmless `X-Org-Id`).

**Rewrite model — READ THIS:** org + project live in the **PATH**, not in query params or a header.
The resource is **`tasks`** (not `issues`). A **project-scoped PAT** may only touch its own project;
it **self-discovers** its `organization_id` + `project_id` from `GET /auth/me` → `api_key`. Statuses
are `todo | in_progress | done | cancelled`; tasks carry a `reference` (e.g. `WEB-12`) + `number`.

Conventions: `{org}` = organization id, `{proj}` = project id, `{tid}` = task id (all UUIDs). Lists
take `limit` + `offset`. Reads should be piped through `slim.jq` / `slim("task", …)`.

## Identity & context
| Method · Path | Purpose | Notes |
|---|---|---|
| `GET /auth/me` | Current user + PAT scope | Returns the `User`; when authed with a PAT the `api_key` object carries `{id, name, organization_id, project_id}` — **this is how a key self-discovers its org + project** (`project_id` null = org-wide key). Cookie sessions get `api_key: null`. |
| `GET /organizations` | The caller's orgs | Top-level **array** of `{id, name, slug, role, …}`. Works even with a project-scoped key. |
| `GET /organizations/{org}/projects` | Projects in the org | Array of `{id, key, name, status, …}`. **Org-wide key only** — a project-scoped key gets **403** (use `/auth/me` `api_key.project_id` instead). |
| `GET /organizations/{org}/members` | Org member roster | Array of `{user_id, name, email, role, joined_at}`. Assignee resolution. |

## Tasks
| Method · Path | Purpose | Required / gotcha |
|---|---|---|
| `GET /organizations/{org}/projects/{proj}/tasks?status=&assignee_id=&sprint_id=&q=` | Filter/list | offset pagination; `q` full-text. Top-level array. |
| `POST /organizations/{org}/projects/{proj}/tasks` | Create | **required** `title`. Optional `description`,`priority`(low/medium/high/urgent),`type`(epic/story/task/bug/spike/chore),`story_points`,`estimated_hours`,`start_date`,`due_date`,`sprint_id`,`parent_id`. Starts `todo`. **No `assignee_id` on create** — set it via PATCH. |
| `GET /organizations/{org}/projects/{proj}/tasks/{tid}` | Detail | |
| `PATCH /organizations/{org}/projects/{proj}/tasks/{tid}` | Update | body `TaskUpdateIn`: `status`,`assignee_id`(null unassigns),`priority`,`type`,`title`,`description`,`sprint_id`,`parent_id`,`story_points`,`estimated_hours`,`start_date`,`due_date`. **Can't move `todo`→working without an assignee.** |
| `DELETE /organizations/{org}/projects/{proj}/tasks/{tid}` | Delete | |
| `GET·POST /organizations/{org}/projects/{proj}/tasks/{tid}/comments` | Read / add comment | POST body field is **`body`** (+ optional `parent_id`). |
| `PATCH·DELETE /organizations/{org}/projects/{proj}/tasks/{tid}/comments/{cid}` | Edit / delete comment | |

Bulk **create** has no endpoint → sequential `POST .../tasks` at concurrency ≤3. Dedupe by
`(project,title)` + an `external_ref`. To assign+advance: create, then `PATCH` `assignee_id` then
`status`.

## Time tracking · Workload · Estimation · Docs — ⚠ PATHS NOT YET PORTED
The skills below still carry the **legacy flat paths** and need porting to the org-scoped `/api/v1`
shape (see their SKILL.md TODOs). Discover the real rewrite paths with the spec tools:

```bash
bash scripts/fetch_spec.sh                       # once: cache + index the /api/v1 spec
bash scripts/spec_lookup.sh --search "time-entries"
bash scripts/spec_lookup.sh --search "workload"
```

Known rewrite locations (verify shapes before use):
- **Time entries** → under `/organizations/{org}/projects/{proj}/tasks/{tid}/time-entries` (contract file `paths/time-entries.yaml`).
- **Docs** → `/organizations/{org}/projects/{proj}/documents` (contract file `paths/documents.yaml`); Markdown round-trip via `?format=markdown`.
- **Comments** → `paths/task-comments.yaml` (body field `body`).
- **Workload / capacity / roadmap / estimation** → discover via `spec_lookup.sh`; the flat
  `/workload`, `/capacity`, `/ai/suggest-estimation`, `/projects/:pid/roadmap` paths no longer exist.

See `domains.md` for the other 200+ endpoints (finance, payroll, CRM, HR, …).
