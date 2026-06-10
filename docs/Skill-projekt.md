# Skill: `projekt` (orchestrator)

The default entry point. It drives the Projekt API end-to-end and owns the safety rules; the other five skills are specialized steps it routes to. **Start here.**

Trigger it by mentioning Projekt, a `pjk_live_` token, or asking to automate issues / backlog / sprint / estimations / time / workload / docs. Soporta español.

## Golden rules (non-negotiable)

1. **Connect once.** Always `auth_check.sh` then `context_sync.sh` first. Org/user/projects/members cache to `.projekt-run/context.json` — read that for every name→id resolution, never re-query.
2. **The 1.3 MB spec never enters context.** Use the [endpoint cheatsheet](API-Endpoints.md) for common ops; for anything else `spec_lookup.sh --search <term>` then read ONE block. Never `cat` the spec.
3. **Dry-run by default.** Every mutation prints a plan and writes nothing until `--apply`. Destructive/sensitive paths need a second `--admit`.
4. **Slim at the edge.** Pipe reads through `slim.jq` so full objects never reach the transcript. Report counts + keys, not raw JSON.
5. **Server verbs over loops.** Prefer `/issues/bulk`, server aggregates (`/workload`, `/capacity`, `/time-summary`) and `/issues/export-pdf` over fetch-everything-and-compute. Cap parallel writes at 3.
6. **Never print the token.** It lives in env or `~/.config/3xa-projekt/auth.json`; logs show only a fingerprint.

## The pipeline

Run the phases the task needs, in order. Each is idempotent and logged to `.projekt-run/`.

| # | Phase | What happens |
| --- | --- | --- |
| 1 | **CONNECT** | `auth_check.sh` — resolves user + org, writes context. Mandatory. |
| 2 | **DISCOVER** | `context_sync.sh` — caches projects + members. Then read `.projekt-run/context.json`. |
| 3 | **PLAN** | Build a dry-run table of intended writes (counts + payloads). Show the user. No writes yet. |
| 4 | **CREATE** | → [projekt-issues](Skill-projekt-issues.md) (bulk create from CSV/text). |
| 5 | **ASSIGN** | → [projekt-issues](Skill-projekt-issues.md) (assign-before-move). |
| 6 | **ESTIMATE** | → [projekt-estimate](Skill-projekt-estimate.md) (points→hours, roadmap, plan-vs-actual). |
| 7 | **TIME** | → [projekt-time](Skill-projekt-time.md) (batch log, timers, roll-ups). |
| 8 | **DOCUMENT** | → [projekt-docs](Skill-projekt-docs.md) (docs, bitácora, PDF). |
| 9 | **REPORT** | → [projekt-workload](Skill-projekt-workload.md) + a deterministic summary from the ledger. |

For a one-shot intent ("set up my sprint from this backlog") it walks 1→9, **pausing after PLAN for approval**.

## Reaching any endpoint (full surface)

The API has 800+ paths. The [cheatsheet](API-Endpoints.md) covers the automation core. For the long tail:

```bash
bash skills/projekt/scripts/fetch_spec.sh                          # once per session: cache + index
bash skills/projekt/scripts/spec_lookup.sh --search "invoice"       # find candidate paths
bash skills/projekt/scripts/spec_lookup.sh "/finance/invoices" post  # read ONE block on demand
```

Domain map (clients, finance, payroll, CRM, HR, contracts, …) → [API Endpoints → Full-surface domain map](API-Endpoints.md#full-surface-domain-map).

## Calling the API directly

```bash
source skills/projekt/scripts/lib/http.sh
pj_req GET  "/issues?project_id=$PID&limit=50" | jq -f skills/projekt/assets/slim.jq --arg view issue
pj_req POST "/issues" '{"project_id":"…","title":"…","assignee_id":"…","status":"To Do"}'
```

`pj_req` returns non-zero on 4xx/5xx and sets `PJ_LAST_STATUS`. See [Errors & Troubleshooting](Errors-and-Troubleshooting.md).

## Guardrails in practice

- **Dry-run → apply:** task scripts print a plan and exit. Re-run with `--apply` to write; again → dedupe; resume after interruption from the ledger automatically.
- **Destructive:** for DELETE / `admin` / `finance` / `payroll`, state the blast radius and require the confirmation flag (`--admit`). The [guard hook](Safety-and-Security.md#3--the-pretooluse-guard-hook) also blocks these without it.
- **Assignee rule:** an issue can't leave `Backlog`/`To Do` without an `assignee_id` (422). Assign first; surface un-assignable issues as "needs owner".

## Bundled references (loaded on demand)

`references/endpoints.md` · `domains.md` · `errors.md` · `units.md` · `auth-setup.md` · `recetas-es.md`. These are summarized across this wiki: [API Endpoints](API-Endpoints.md), [Errors & Troubleshooting](Errors-and-Troubleshooting.md), [Estimation Units](Estimation-Units.md), [Configuration](Configuration.md).

See also: [Architecture](Architecture.md) · [Safety & Security](Safety-and-Security.md).
