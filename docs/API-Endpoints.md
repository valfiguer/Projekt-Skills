# API Endpoints

The Projekt API exposes **800+ paths**. This page is the **automation-core cheatsheet** (~90% of calls) plus the map for reaching everything else on demand. The full 1.3 MB OpenAPI spec is **never** loaded into context.

All paths are relative to the API base (`https://projekt.3xa.es/api`). Every authenticated call needs `Authorization: Bearer <pat>` + `X-Org-Id` — both injected by `lib/http.sh`. Conventions: `:pid` = project id, `:iid` = issue id (UUIDs). Lists take `limit` (≤200; issues ≤5000) + `offset`. Reads are piped through `slim.jq`.

## Identity & context

| Method · Path | Purpose | Notes |
| --- | --- | --- |
| `GET /me` | Current user + current org + all orgs | `.user`, `.organization`, `.organizations[]`. No `X-Org-Id` needed. |
| `GET /projects?limit=200` | Projects in the org | Returns a top-level **array**. `?include_shared=true` adds cross-org shares (read-only). |
| `GET /team` | Org member roster | Array of `{id,name,email,role,department,position}`. |

## Issues

| Method · Path | Purpose | Required / gotcha |
| --- | --- | --- |
| `GET /issues?project_id=&status=&assignee_id=&sprint_id=&q=` | Filter/list | offset pagination; `q` full-text. |
| `POST /issues` | Create | **required** `project_id`,`title`. Optional `status`(def Backlog),`priority`,`type`,`assignee_id`,`estimated_hours`,`labels`,`description`,`sprint_id`,`due_date`. |
| `GET /issues/:iid` | Detail (incl. `comments[]`) | |
| `PUT /issues/:iid` | Update (PATCH semantics) | `assignee_id:null` unassigns. **422** if moving Backlog/To Do→working without assignee. |
| `POST /issues/bulk` | Bulk **mutate** existing | body `{issue_ids:[…], action, value}`. **Does NOT create.** Use for assign / status / priority / labels. |
| `POST /issues/:iid/archive` · `/unarchive` | Soft-delete / restore | Hard delete not exposed. |
| `POST /issues/:iid/duplicate` | Clone within project | |
| `GET·POST /issues/:iid/comments` | Read / add comment | POST body `{text}` (markdown), optional `parent_id`. |

> Bulk **create** has no endpoint → either `POST /imports/execute` (batch) or sequential `POST /issues` at concurrency ≤3. Dedupe by `(project_id,title)` + `external_ref`.

## Time tracking

| Method · Path | Purpose | Notes |
| --- | --- | --- |
| `POST /projects/:pid/issues/:iid/time-entries` | Log time | `{duration_minutes>0, date:"YYYY-MM-DD", description?}`. |
| `POST …/time-entries/timer-start` · `timer-stop` | Timer | start idempotent (200 if running); stop rounds to ≥1 min. |
| `GET /projects/:pid/issues/:iid/time-summary` | Aggregate | `{total_minutes, entry_count, per-user}`. Prefer over summing rows. |

## Workload & capacity (read-only aggregates)

Do the math server-side.

| Method · Path | Purpose |
| --- | --- |
| `GET /workload?date_from=&date_to=` | Per-member assigned / in-progress / done / hours |
| `GET /workload/capacity` | Utilization vs capacity target |
| `GET /capacity` · `GET /capacity/threshold` | Per-member open+estimated; org overload threshold |

## Estimation & roadmap

| Method · Path | Purpose | Gotcha |
| --- | --- | --- |
| `POST /ai/suggest-estimation` | AI estimate | returns **story_points only** → convert via [Estimation Units](Estimation-Units.md). Rate bucket `ai` (10/min + daily); 503 when spent. |
| `GET·POST /projects/:pid/roadmap` | Milestones/epics | `{name,start_date,end_date,progress,item_type,color}`. |
| `POST /projects/:pid/roadmap/dependencies` | Link items | `{from,to}`; type auto-detected. |

## Docs

| Method · Path | Purpose | Notes |
| --- | --- | --- |
| `GET·POST /projects/:pid/docs` | List / create | create needs `title`; body uses **EditorJS blocks** (object or JSON-string). `parent_doc_id` nests. |
| `GET·PATCH /projects/:pid/docs/:did` | Fetch / update | PATCH `is_archived`,`blocks`,`title`,`position`. |
| `POST /issues/:iid/bitacora/regenerate` | AI logbook (HdU) | 503 on AI quota → **soft-skip**, keep prior content. |
| `GET /issues/export-pdf` | Issue digest PDF | _Cheatsheet shorthand_ — the spec actually defines this as **POST** with an `issue_ids` body. Fetch the artifact; don't render in-model. |

---

## Full-surface domain map

For anything outside the core, discover the path then read ONE block:

```bash
bash skills/projekt/scripts/spec_lookup.sh --search "<term>"      # list matching paths
bash skills/projekt/scripts/spec_lookup.sh "/exact/path" [method]  # print that block only
```

> ⚠️ Anything under **admin / finance / payroll / tax / gl / consolidation / gdpr** is sensitive: state the blast radius and require a second confirmation (`--admit`) before any write. See [Safety & Security](Safety-and-Security.md).

| Domain (search term) | What's there |
| --- | --- |
| `projects` | Projects, board columns, sprints, roadmap, members, settings (~51 paths). |
| `issues` | Issues, comments, bitácora, dependencies, attachments, export. |
| `me` · `team` · `org` · `orgs` | Identity, roster, org settings, invites, switching. |
| `mywork` · `timesheets` · `time-reports` · `schedules` | Personal queue, timesheets, schedules. |
| `workload` · `capacity` · `evm` | Workload, capacity, earned-value metrics. |
| `docs` · `doc-archive` | Project docs (EditorJS) + archived store. |
| `clients` · `crm` · `crossorg` | Clients, CRM pipeline, cross-org sharing. |
| `invoices` · `arap` · `finance` · `gl` · `budgets` | Invoicing, AR/AP, finance, general ledger, budgets. 🔒 |
| `expenses` · `approvals` · `purchase-orders` | Expenses, approval flows, POs. 🔒 |
| `payroll` · `payroll-v2` · `leave` · `employees` | Payroll, leave, employee records. 🔒 PII |
| `contracts` · `compliance` · `gdpr` | Contracts, compliance, GDPR/data requests. 🔒 |
| `tax-multi` · `consolidation` · `finint` | Multi-jurisdiction tax, consolidation, finance integrations. 🔒 |
| `inventory` · `assets` | Inventory, fixed assets. |
| `supplier-portal` · `addons` · `webhooks` | Supplier portal, add-ons, webhooks. |
| `bi` · `ai` | BI/analytics, AI endpoints (rate bucket `ai`, daily quota). |
| `admin` | Org administration (~44 paths). 🔒 highest privilege. |
| `auth` · `push` · `github` · `settings` · `integrations` | Auth, push, GitHub, settings, integrations. |

Counts drift as the API grows — `spec_lookup.sh --search <term>` is always the source of truth. If the cheatsheet and a lookup disagree, **trust the lookup** (the [drift CI](Contributing.md#spec-drift-ci) will flag it).

See also: [Errors & Troubleshooting](Errors-and-Troubleshooting.md) for status codes and the retry policy.
