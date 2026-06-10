# Architecture

How Projekt-Skills is put together, and **why it stays token-cheap**.

## The shape

```
projekt-skills (plugin)
├─ projekt            ← orchestrator: owns the pipeline, safety rules, shared scripts/refs
├─ projekt-issues     ← CREATE + ASSIGN
├─ projekt-estimate   ← ESTIMATE + plan-vs-actual
├─ projekt-workload   ← REPORT (read-only)
├─ projekt-time       ← TIME
└─ projekt-docs       ← DOCUMENT
```

The five task skills are specialized steps. The **`projekt`** orchestrator routes to them and owns the shared contract — the HTTP layer, auth, context cache, ledger, spec lookup, and the reference docs. Every task skill connects through the orchestrator's scripts first (`auth_check.sh` → `context_sync.sh`) and reads the same `.projekt-run/context.json`.

## Connect once, resolve forever

```bash
bash skills/projekt/scripts/auth_check.sh     # resolves user + org + role
bash skills/projekt/scripts/context_sync.sh   # caches projects + members
```

`context_sync.sh` writes `.projekt-run/context.json` holding the org, projects and member roster. Every later name→id resolution (project key/name → UUID, assignee email/name → user_id) reads that file. **Identity is never re-queried** mid-run.

> Note: **issues are not in `context.json`** (only projects + members). Skills that need an issue id (e.g. `projekt-time`) do a memoised lookup — expected, not a cache violation.

## How it stays token-cheap

Four deliberate moves keep the model's context (and your bill) small:

1. **The 1.3 MB OpenAPI spec never enters context.** The 90% case is a hand-curated cheatsheet ([API Endpoints](API-Endpoints.md)). For the long tail, `spec_lookup.sh --search <term>` greps an index and `spec_lookup.sh <path>` prints exactly one endpoint block. The spec is fetched on demand and **git-ignored** — never committed.
2. **Connect once** (above) — auth + org + roster resolve a single time and cache.
3. **Slim at the edge.** API reads are piped through `jq -f assets/slim.jq --arg view <issue|member|project|time|doc>` so full objects never hit the transcript. Skills report counts + keys, not raw JSON.
4. **Math is deterministic.** Roll-ups, workload reports and docs are built by bundled Python/shell scripts. The model is spent only on genuinely new narrative.

## Shared scripts (orchestrator)

Under `skills/projekt/scripts/`:

| Script | Role |
| --- | --- |
| `auth_check.sh` | Resolve token + user + org + role; write context. Mandatory first step. |
| `context_sync.sh` | Cache projects + members into `.projekt-run/context.json`. |
| `fetch_spec.sh` | Fetch + index the OpenAPI spec (once per session) for full-surface lookups. |
| `spec_lookup.sh` | `--search <term>` to find paths; `<path> [method]` to print one block. |
| `spec_index.sh` | Builds the searchable index the lookup reads. |
| `lib/http.sh` | The HTTP layer: `pj_req METHOD PATH [BODY]`. Injects auth + `X-Org-Id`, backs off on 429, retries 5xx. Sets `PJ_LAST_STATUS`; non-zero return on 4xx/5xx. |
| `lib/projekt_api.py` | Python client used by the task scripts: slim projections + ledger + the same auth/retry contract. |
| `lib/run_ledger.sh` | Append-only ledger primitives (`pj_ledger_seen`, …). |

Assets under `skills/projekt/assets/`:

| Asset | Role |
| --- | --- |
| `slim.jq` | Field projections per view (`issue`/`member`/`project`/`time`/`doc`). |
| `points_hours.json` | Story-points → hours map. The single source of truth for [estimation](Estimation-Units.md). |
| `import_template.csv` | Column template for [bulk issue import](Skill-projekt-issues.md). |

## Calling the API directly

```bash
source skills/projekt/scripts/lib/http.sh
pj_req GET  "/issues?project_id=$PID&limit=50" | jq -f skills/projekt/assets/slim.jq --arg view issue
pj_req POST "/issues" '{"project_id":"…","title":"…","assignee_id":"…","status":"To Do"}'
```

`pj_req` returns non-zero on 4xx/5xx and sets `PJ_LAST_STATUS`. Error envelope is `{"error":"…","message":"…"}`. See [Errors & Troubleshooting](Errors-and-Troubleshooting.md).

## Idempotency & resume (the ledger)

Every mutating script appends to `.projekt-run/<timestamp>.jsonl`. Re-running:

- **dedupes** — already-applied actions are skipped (creates 0), so re-running an import is safe.
- **resumes** — an interrupted run picks up from the last success.

Dedupe keys: issues `(project_id,title)` + `external_ref` · time `(issue,date,note)` · docs by `title`.

## The guard hook

`hooks/hooks.json` registers a `PreToolUse` hook on `Bash` → `hooks/guard.sh`. It's a **belt-and-suspenders** layer on top of each script's own dry-run/confirm: it blocks any Projekt API Bash command that hits a **sensitive surface** (DELETE, or `admin`/`finance`/`payroll`/`tax-multi`/`gl`/`consolidation`/`gdpr`) unless the command carries `--admit`. Everything else passes untouched. Details in [Safety & Security](Safety-and-Security.md).

## Spec-drift CI

`.github/workflows/spec-drift-check.yml` runs `scripts/check_drift.sh`, which fetches the live spec and asserts the cheatsheet's core paths still exist — so [API Endpoints](API-Endpoints.md) never silently rots. See [Contributing](Contributing.md).

Next: **[Safety & Security](Safety-and-Security.md)** →
