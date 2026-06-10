# Errors & Troubleshooting

`lib/http.sh` returns non-zero on 4xx/5xx and sets `PJ_LAST_STATUS`. The error envelope is `{"error":"…","message":"…"}` — read `.message // .error`.

## Status code matrix

| Status | Meaning | What to do |
| --- | --- | --- |
| **422** | Validation. Most common: **assignee-required** — can't move an issue out of `Backlog`/`To Do` without `assignee_id`. Bulk returns `blocked_unassigned`. | Assign first, then move. Surface un-assignable items as "needs owner"; never silently drop. Don't report green if `blocked > 0` unless acknowledged. |
| **403** | Cross-org. The resource's org ≠ your `X-Org-Id`. | **Not a bug.** A PAT is bound to one org. Don't retry; switch org / use the right token. Shared reads need `?include_shared=true` and stay read-only. |
| **429** | Rate limited (global 600/60s; `ai` 10/min). | `http.sh` auto-backs off via `Retry-After`/`X-RateLimit-Reset`. For big batches keep concurrency ≤3 and run off-peak. |
| **503** | AI quota spent (per-org daily) on `/ai/*` (estimation, bitácora). | **Soft-skip**: keep prior content, fall back (e.g. median-of-siblings for estimates), continue the pipeline. Never overwrite good data with an error. |
| **404** | Not found — or a stale id from cache. | Re-run `context_sync.sh` if a cached id 404s. `/auth/refresh` 404 for PATs is expected noise. |
| **5xx** | Server. | Auto-retried with exponential backoff (1, 4, 9, 16, 25 s) up to `PJ_MAX_RETRIES`. |
| **401** | Unauthorized. | Token missing/expired/malformed. See [Configuration](Configuration.md); a valid token starts with `pjk_live_`. |

## Idempotency & resume

- Mutating scripts append to `.projekt-run/<ts>.jsonl` via `run_ledger.sh`. Re-running dedupes (`pj_ledger_seen`) and resumes from the last success.
- Dedupe keys: issues `(project_id,title)` + `external_ref` · time `(issue,date,note)` · docs by `title`.

## Status / column names

Board columns are per-project (`project.columns`). Canonical defaults: `Backlog`, `To Do`, `In Progress`, `In Review`, `Done`. The server normalizes localized inputs (e.g. "En revisión") to canonical. When in doubt, read the project's `columns` array before setting a status.

## Common situations

| Symptom | Cause / fix |
| --- | --- |
| Skill never triggers | Plugin not enabled (`/plugin`), or no token. See [Installation](Installation.md) / [Configuration](Configuration.md). |
| "No token" from `auth_check.sh` | Set `TREXA_API_TOKEN` or create `~/.config/3xa-projekt/auth.json`. |
| "No org resolved" | Set `TREXA_ORG_ID`, or switch your current org in Projekt. |
| Import created fewer than expected | Dedupe kicked in — already-created rows (by `title`/`external_ref`) are skipped. Check the dry-run table. |
| Issue won't move to In Progress | Assignee-required (422). Assign first via [projekt-issues](Skill-projekt-issues.md). |
| Estimates look ~3× too high | Stale `points_hours.json`. Recalibrate — see [Estimation Units](Estimation-Units.md). |
| A sensitive write was blocked | The [guard hook](Safety-and-Security.md#3--the-pretooluse-guard-hook) stopped it. State the blast radius and re-run with `--admit`. |
| PDF export is corrupt | `export-pdf` is **POST** and streams raw bytes — use the skill's `pdf` subcommand (it reads bytes); don't decode as text. |

See also: [Safety & Security](Safety-and-Security.md) · [API Endpoints](API-Endpoints.md) · [FAQ](FAQ.md).
