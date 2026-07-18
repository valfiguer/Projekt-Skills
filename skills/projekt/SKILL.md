---
name: projekt
description: >-
  Connect a Projekt organization (projekt.3xa.es) and automate work end-to-end via its REST API
  with the user's Personal Access Token: create/triage issues, plan sprints, estimate, log time,
  build workload/capacity reports, and write/maintain docs. Use whenever the user mentions Projekt,
  a pjk_live_ token, or asks to automate issues / backlog / sprint / estimations / time tracking /
  workload / project docs. Soporta español: incidencias, tareas, estimaciones, cargas de trabajo,
  documentación, fichajes de tiempo.
allowed-tools: Read, Grep, Bash(bash:*), Bash(python3:*), Bash(jq:*)
---

# Projekt — orchestrator

Drive the **Projekt** API (`projekt.3xa.es`) to automate issues, docs, workload, estimation and time.
This skill owns the pipeline and the safety rules; the `projekt-issues`, `projekt-estimate`,
`projekt-workload`, `projekt-time` and `projekt-docs` skills are specialized steps it routes to.

`SK="${CLAUDE_SKILL_DIR}/scripts"` · `AS="${CLAUDE_SKILL_DIR}/assets"` — use these for every command below.

## Golden rules (non-negotiable)

1. **Connect once.** Always run `auth_check.sh` then `context_sync.sh` first. Org/user/projects/members
   are cached in `.projekt-run/context.json` — read that for every name→id resolution, never re-query.
2. **The 1.3 MB spec never enters context.** For the common ops use `references/endpoints.md`. For
   anything else, discover with `spec_lookup.sh --search <term>` then read ONE block with
   `spec_lookup.sh <path>`. Never `cat` the spec.
3. **Dry-run by default.** Every mutation prints a plan and writes nothing until the user approves
   with `--apply`. Destructive/sensitive paths (DELETE, `admin/*`, `finance/*`, `payroll/*`) need a
   **second explicit confirmation** beyond `--apply`.
4. **Slim at the edge.** Pipe reads through `jq -f "$AS/slim.jq" --arg view <issue|member|project|time|doc>`
   so full objects never reach the transcript. Report counts + keys, not raw JSON.
5. **Server verbs over loops.** Prefer `/issues/bulk`, server aggregates (`/workload`, `/capacity`,
   `/time-summary`) and `/issues/export-pdf` over fetch-everything-and-compute. Cap parallel writes at 3.
6. **Never print the token.** It lives in env or `~/.config/3xa-projekt/auth.json`; logs show only a fingerprint.

## Setup

If `auth_check.sh` reports no token, point the user to `references/auth-setup.md` (mint a `pjk_live_`
key at Organization → Settings → General → Integraciones; export `TREXA_API_TOKEN` or write
`~/.config/3xa-projekt/auth.json`).

## The pipeline

Run the phases the task needs, in order. Each is idempotent and logged to `.projekt-run/`.

| # | Phase | Command / skill |
|---|-------|-----------------|
| 1 | **CONNECT**  | `bash "$SK/auth_check.sh"` — resolves user+org, writes context. Mandatory. |
| 2 | **DISCOVER** | `bash "$SK/context_sync.sh"` — caches projects+members. Then read `.projekt-run/context.json`. |
| 3 | **PLAN**     | Build a dry-run table of intended writes (counts + payloads). Show the user. No writes yet. |
| 4 | **CREATE**   | → skill `projekt-issues` (bulk create from CSV/text; `--apply` to execute). |
| 5 | **ASSIGN**   | → `projekt-issues` (assign-before-move; unassigned never enter working columns). |
| 6 | **ESTIMATE** | → skill `projekt-estimate` (story-points→hours, roadmap, plan-vs-actual). |
| 7 | **TIME**     | → skill `projekt-time` (batch log, timers, roll-ups). |
| 8 | **DOCUMENT** | → skill `projekt-docs` (project/sprint docs, issue bitácora, PDF export). |
| 9 | **REPORT**   | → skill `projekt-workload` + a deterministic summary from the ledger. |

For a one-shot intent ("set up my sprint from this backlog") walk 1→9, pausing after PLAN for approval.

## Reaching any endpoint (full surface)

The API has 800+ paths. `references/endpoints.md` covers the automation core. For the long tail:

```bash
bash "$SK/fetch_spec.sh"                         # once per session: cache + index the spec
bash "$SK/spec_lookup.sh" --search "invoice"      # find candidate paths (greps the index)
bash "$SK/spec_lookup.sh" "/finance/invoices" post   # read ONE path block on demand
```

Domain map (clients, finance, payroll, CRM, HR, contracts, …) → `references/domains.md`.

## Calling the API directly

Source the HTTP layer; it injects auth + `X-Org-Id` + rate-limit backoff:

```bash
source "$SK/lib/http.sh"
ORG="$(pj_org_id)"; PID="$(pj_project_id)"          # from context.json after auth_check
pj_req GET  "/organizations/$ORG/projects/$PID/tasks?limit=50" | jq -f "$AS/slim.jq" --arg view issue
pj_req POST "/organizations/$ORG/projects/$PID/tasks" '{"title":"…","type":"task","assignee_id":"…"}'
# NOTE: `status` is ignored on create (task is born `todo`) → move it afterwards:
#   pj_req PATCH "/organizations/$ORG/projects/$PID/tasks/$ID" '{"status":"done"}'
```

The API is **org-scoped in the path** (`/organizations/{org}/…`), not via a header, and the
entity is **`tasks`** (not `issues`). `pj_req` returns non-zero on 4xx/5xx and sets
`PJ_LAST_STATUS` — but that variable is set inside a subshell, so **branch on the exit code of
`X="$(pj_req …)"`, not on `PJ_LAST_STATUS` afterwards.** Error handling → `references/errors.md`.

## Guardrails in practice

- **Dry-run → apply:** task scripts print a plan and exit. Re-run with `--apply` to write. Re-run again →
  dedupe (creates 0). Resume after an interruption from the ledger automatically.
- **Destructive:** for DELETE / `admin/*` / `finance/*` / `payroll/*`, state the blast radius and require the
  user to type the confirmation the script asks for. The bundled hook also blocks these without `--admit`.
- **Assignee rule:** an issue can't leave `Backlog`/`To Do` without an `assignee_id` (422). Always assign first;
  surface un-assignable issues as "needs owner" rather than failing the whole batch.

## Reference & scripts (loaded on demand — keep them out of context until needed)

- `references/endpoints.md` — the ~core automation endpoints (method · path · fields · gotcha).
- `references/domains.md` — full-surface domain map → which `spec_lookup` term to use.
- `references/errors.md` — error envelope, 422/429/503/403 handling, retry policy.
- `references/units.md` — story-points→hours, AI-suggested flagging.
- `references/auth-setup.md` — PAT minting + token resolution.
- `references/recetas-es.md` — recetas paso a paso en español.
- `scripts/` — `auth_check.sh`, `context_sync.sh`, `spec_lookup.sh`, `spec_index.sh`, `fetch_spec.sh`,
  `lib/http.sh`, `lib/run_ledger.sh`. Execute them; do not read them into context.
