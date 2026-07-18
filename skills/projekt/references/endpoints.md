# Endpoint cheatsheet — automation core (current API, 2026-07)

The API is **org-scoped in the PATH** (not via an `X-Org-Id` header) and **version-prefixed**.
All paths are relative to the API base **`https://projekt.3xa.es/api/v1`** (`pj_api_base`;
`pj_req` prepends it). Every authenticated call needs `Authorization: Bearer <pat>` (injected
by `lib/http.sh`). A `pjk_live_` PAT is scoped to **one org** and often **one project**.

> Terminology: the UI says "incidencias/issues", but the **API entity is `tasks`**
> (`type ∈ epic|story|task|bug|spike|chore`). There is **no** `/issues` collection.
> Statuses are **per-project board columns**, not a fixed enum — read them, don't hardcode.

## Identity & scope
| Method · Path | Purpose | Notes |
|---|---|---|
| `GET /auth/me` | Current user **+ the calling key's scope** | Flat `{ id, name, email, …, api_key:{ organization_id, project_id } }`. Pin `org_id=.api_key.organization_id`, `project_id=.api_key.project_id`. No `.organization`/`.organizations[]`. |
| `GET /organizations` | Orgs the **user** belongs to | User-level (any key). `[{id,name,slug}]`. Use only to resolve an org **name**; a key can still only ACT on its own org. |

**Project-scoped PAT** → `403` on org-level lists; `200` only under its own
`/organizations/{org}/projects/{project}/…`. **Org-scoped PAT** → can list the org's projects/members.

## Projects & members
| Method · Path | Purpose | Notes |
|---|---|---|
| `GET /organizations/{org}/projects?limit=200` | List org projects | Top-level **array** `{id,key,name,status}`. `403` for a project-scoped key → use the single-project GET. |
| `GET /organizations/{org}/projects/{project}` | One project | Works for a project-scoped key. |
| `GET /organizations/{org}/members` | Org roster | `[{user_id,name,email,role}]`. `403` for a project-scoped key. |
| `GET /organizations/{org}/projects/{project}/board-columns` | This project's statuses | `[{status_key,name,category,position}]`. `status_key` = a task's `.status` (e.g. `todo,in_progress,done,cancelled` + custom). |

## Tasks (the "issues") — base `/organizations/{org}/projects/{project}/tasks`
| Method · Path | Purpose | Required / gotcha |
|---|---|---|
| `GET .../tasks?limit=&status=&assignee_id=&sprint_id=&q=&type=` | List / filter | Top-level **array** of **top-level** tasks (a `parent_id` filter is ignored — use the subtasks route for children). |
| `POST .../tasks` | Create | **required** `title`. Optional `type`(def `task`), `priority`(low/medium/high/urgent), `description`, `assignee_id`, `parent_id`, `sprint_id`, `story_points`, `estimated_hours`, `start_date`, `due_date`. **GOTCHA: `status` is IGNORED on create — a new task is always `todo`.** PATCH to set it. |
| `GET .../tasks/{id}` | Detail | `reference` (`PJKT-1824`), `number`, `subtask_count`, `subtasks_done`. |
| `PATCH .../tasks/{id}` | Partial update | Set `status` here (`{"status":"done"}`). `assignee_id:null` unassigns. **422** if moving out of a `todo` column **without** an `assignee_id` → assign first. |
| `GET .../tasks/{epic}/subtasks` | Children of an epic/task | Returns **`{ "subtasks":[…] }`** (not a bare array). |
| `DELETE .../tasks/{id}` | Delete | Sensitive — confirm first. |

**Epic + children (verified):** create epic (`type:"epic"`) → capture `id` → create each child
with `parent_id` + `assignee_id` → **PATCH `{status:"done"}`** per child (create ignores status).

## Long tail (sprints · time · roadmap · docs · workload · finance · HR · …)
The pre-2026 flat paths (`/issues`, `/team`, `/workload`, `/projects/:pid/…`) are **gone** — the
whole surface moved under `/organizations/{org}/…` (and project resources under
`/organizations/{org}/projects/{project}/…`). **Do NOT trust old flat paths.** Discover the exact
current path before every non-core call:

```bash
bash "$SK/fetch_spec.sh"                                   # caches https://projekt.3xa.es/api/openapi.json
bash "$SK/spec_lookup.sh" --search sprint                  # find candidates
bash "$SK/spec_lookup.sh" "/organizations/{org}/projects/{project}/sprints" post
```

`domains.md` maps domains → `spec_lookup` search terms. A PAT only reaches its own org/project.
