# The catalogue — everything the API offers

**Generated** by `scripts/catalogo.py` from the cached spec. Do not edit by hand: re-run `bash scripts/fetch_spec.sh && python3 scripts/catalogo.py --md` and the numbers are today's. The previous hand-written notes drifted until five of eight skills pointed at endpoints that no longer existed.

**685 paths · 917 operations · 16 domains.** 358 operations carry an `x-tool` (these are the ones the MCP connector can expose), of which **128 are marked sensitive**. The remaining **559 have no `x-tool`**: they work over HTTP exactly like the rest, but they are invisible to the MCP catalogue, to profile selection and to Kern.

A `pr-*` script already drives **80** of them. Everything else is reachable today with `spec_lookup.sh` + `pj_req` — being uncovered means there is no convenience wrapper, not that it is out of reach.

## Domains

| Domain | Ops | Sensitive | Covered | What is in it |
|---|--:|--:|--:|---|
| `pm` | 69 | 0 | 41 | Projects, tasks, sprints, boards, tags, roadmap — the core of the product. |
| `finance` | 67 | 66 | 0 | Invoices, quotes, expenses, suppliers, contracts, profitability, fiscal export. |
| `crm` | 42 | 0 | 0 | Leads, deals, pipelines, clients, activities and the funnel analytics. |
| `hr` | 41 | 41 | 1 | Employees, departments, leave, absences, payroll and workforce capacity. |
| `support` | 29 | 1 | 0 | Support requests, SLAs and the client-facing portal. |
| `crossorg` | 27 | 0 | 0 | Shared projects and channels between organizations. |
| `context` | 15 | 7 | 0 | The Context Fabric surface: capsules, projections and retrieval. |
| `docs` | 15 | 0 | 15 | Documents, folders, templates, versions and publication. |
| `admin` | 10 | 10 | 0 | Organization settings, roles, API keys, members and invites. |
| `calendar` | 8 | 1 | 0 | Calendars, events and meetings. |
| `okr` | 8 | 0 | 0 | Objectives and key results. |
| `org` | 7 | 0 | 1 | Organization identity and the caller's own membership. |
| `automations` | 6 | 0 | 0 | Rules that fire on events. |
| `bi` | 6 | 2 | 0 | Dashboards and widgets built on the org's data. |
| `attachments` | 4 | 0 | 0 | File upload and download on tasks and other records. |
| `search` | 4 | 0 | 1 | Cross-domain search. |

## Outside the `x-tool` taxonomy

559 operations have no `x-tool`, grouped by their OpenAPI tag. `platform` is the superadmin surface and `auth` is the login flow the cookie session uses — neither belongs in an automation catalogue. The rest are candidates for an `x-tool` if they should become reachable from the MCP.

| Tag | Ops |
|---|--:|
| `platform` | 92 |
| `finance` | 75 |
| `auth` | 49 |
| `chat` | 40 |
| `projects` | 24 |
| `meetings` | 21 |
| `organizations` | 18 |
| `github` | 15 |
| `copilot` | 15 |
| `portal` | 12 |
| `notifications` | 11 |
| `documents` | 11 |
| `oauth-as` | 10 |
| `departments` | 10 |
| `support` | 10 |
| `billing` | 8 |
| `tasks` | 8 |
| `crm` | 8 |
| _28 more tags_ | 122 |

## Drilling in

The full index — one line per operation, with domain, profile, sensitivity, tags and the covering script — lives in the spec cache and is meant to be **grepped, never read into context**:

```bash
bash scripts/fetch_spec.sh                  # cache the spec + rebuild the index
bash scripts/spec_lookup.sh --domain finance   # every finance operation
bash scripts/spec_lookup.sh --sensitive        # everything flagged sensitive
bash scripts/spec_lookup.sh --search invoice   # free-text over the index
bash scripts/spec_lookup.sh "«O»/invoices" post  # ONE operation, in full
```

`«O»` abbreviates `/api/v1/organizations/{org_id}` in the index and in this page.

## Before calling something uncovered

Read the one operation with `spec_lookup.sh` first — the shapes are not guessable, and guessing is how the previous catalogue went wrong. Anything marked sensitive, plus every `DELETE`, needs the user's explicit confirmation; the guard hook blocks `admin/*`, `finance/*` and `payroll/*` without `--admit`.

