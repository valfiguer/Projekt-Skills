# Errors & retry policy

`lib/http.sh` returns non-zero on 4xx/5xx and sets `PJ_LAST_STATUS`. Error envelope is
`{"error": "...", "message": "..."}`. Read `.message // .error`.

| Status | Meaning | What to do |
|---|---|---|
| **422** | Validation. On a status move the usual cause is the destination column's **`wip_limit`** being full (only columns that set one restrict anything; default columns have `wip_limit = null`). Also: an `assignee_id` that is not a member of the org, a `sprint_id` from another project, `tag_ids` outside the org. Bulk reports them per id in `errors[]`. | Read the per-id reason; `tasks/bulk` still commits the rest. Don't report a run green while `errors` is non-empty. There is NO "a task needs an owner to leave todo" rule — that was a legacy invention. |
| **403** | Cross-org. The resource's org ≠ your `X-Org-Id`. | Not a bug. A PAT is bound to one org. Don't retry; tell the user to switch org / use the right token. Shared reads need `?include_shared=true` and stay read-only. |
| **429** | Rate limited (global 600/60s; `ai` 10/min). | `http.sh` auto-backs off via `Retry-After`/`X-RateLimit-Reset`. For big batches keep concurrency ≤3 and run off-peak. |
| **503** | AI quota spent (per-org daily) on `/ai/*` (estimation, bitácora). | **Soft-skip**: keep prior content, fall back (e.g. median-of-siblings for estimates), continue the pipeline. Never overwrite good data with an error. |
| **404** | Not found — or a stale id from a cache. | Re-run `context_sync.sh` if a cached id 404s. Note: `/auth/refresh` 404 for PATs is expected noise. |
| **5xx** | Server. | Auto-retried with exponential backoff (1,4,9,16,25s) up to `PJ_MAX_RETRIES`. |

## Idempotency & resume
- Mutating scripts append to `.projekt-run/<ts>.jsonl` via `run_ledger.sh`. Re-running dedupes
  (`pj_ledger_seen`) and resumes from the last success.
- Dedupe keys: issues `(project_id,title)`+`external_ref`; time `(issue,date,note)`; docs by `title`.

## Status names
Board columns are per-project (`project.columns`). Canonical defaults: `Backlog`, `To Do`, `In Progress`,
`In Review`, `Done`. The server normalizes localized inputs (e.g. "En revisión") to canonical. When in
doubt, read the project's `columns` array before setting a status.
