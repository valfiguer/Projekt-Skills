---
name: pr
description: >-
  Connect a Projekt Republic organization and automate work over its REST API with a
  Personal Access Token: create and triage tasks, assign and move them in bulk, log time
  and drive the timer. The orchestrator for the pr-* family — run its connect step first.
  Use whenever the user mentions Projekt Republic, a pjk_live_ token, or asks to automate
  tasks, a backlog, a sprint or time tracking.
allowed-tools: Read, Grep, Bash(bash:*), Bash(python3:*), Bash(jq:*)
---

# pr — Projekt Republic orchestrator

Drive the Projekt Republic API (`https://api.projektrepublic.com/api/v1`) to automate
tasks and time. This skill owns auth, context and the safety rules; `pr-informes`,
`pr-docs` and `pr-tokens` are specialized steps.

`SK="${CLAUDE_SKILL_DIR}/scripts"` · `AS="${CLAUDE_SKILL_DIR}/assets"`.

## Connect first (always)

```bash
bash "$SK/auth_check.sh"      # resolves user + org from /auth/me → .projekt-run/context.json
bash "$SK/context_sync.sh"    # caches projects + members
```

Everything else reads `.projekt-run/context.json` for name→id resolution and never
re-queries identity. No token → `references/auth-setup.md`.

## Golden rules

1. **Connect once**, then resolve names from the cached context.
2. **Dry-run by default.** Every mutation prints a plan and writes nothing until `--apply`.
   DELETE and `admin/*`, `finance/*`, `payroll/*` need a second explicit confirmation.
3. **The spec never enters context.** Common paths are in `references/endpoints.md`. For
   the rest: `spec_lookup.sh --search <term>`, then read ONE block. Never `cat` the spec.
4. **Slim at the edge.** Pipe reads through `jq -f "$AS/slim.jq" --arg view <task|member|project|time|doc>`.
   Report counts and keys, not raw JSON.
5. **Server verbs over loops.** Prefer `tasks/bulk` and the server aggregates over
   fetch-everything-and-compute. Cap parallel writes at 3.
6. **Never print the token** — only its fingerprint.

## Commands

```bash
# Bulk-create tasks from a CSV/JSON backlog (columns: assets/import_template.csv)
python3 "$SK/tareas.py" --project WEB --file backlog.csv            # dry-run
python3 "$SK/tareas.py" --project WEB --file backlog.csv --apply

# Assign / move / re-prioritize / re-sprint in bulk, via .../tasks/bulk
python3 "$SK/mover.py" --tasks WEB-12,WEB-13 --assignee jane@acme.com --status in_progress --apply
python3 "$SK/mover.py" --tasks WEB-12 --priority urgent --apply

# Time: batch-log a sheet, drive the timer, read server-side totals
python3 "$SK/tiempo.py" log ./timesheet.csv --apply
python3 "$SK/tiempo.py" timer start WEB-12 --apply
python3 "$SK/tiempo.py" timer stop --note "review" --apply
python3 "$SK/tiempo.py" summary --project WEB --date-from 2026-09-01 --date-to 2026-09-30
```

Detail per area: `references/tasks.md` · `references/time.md`.

## The catalogue — all 917 operations

`references/catalogo.md` is the map: **685 paths · 917 operations · 16 domains**, how many of
each are sensitive, and which `pr-*` script already covers them (80 do). It is **generated**
from the spec by `scripts/catalogo.py`, so its numbers cannot drift the way the old
hand-written notes did.

The other 837 are reachable today — uncovered means "no convenience wrapper", not "out of
reach". Three steps, none of which put the spec in context:

```bash
bash "$SK/fetch_spec.sh"                       # once per session: cache the spec + index
bash "$SK/spec_lookup.sh" --domains            # the 16 domains with counts
bash "$SK/spec_lookup.sh" --domain crm         # every operation in one domain
bash "$SK/spec_lookup.sh" --sensitive          # everything the spec flags sensitive
bash "$SK/spec_lookup.sh" --uncovered finance  # what has no wrapper yet
bash "$SK/spec_lookup.sh" "«O»/crm/deals" post # ONE operation, in full — do this before calling
```

Then call it. `llamar.py` validates the path and method against the spec **before sending**,
is dry-run for anything that is not a GET, refuses sensitive operations and every `DELETE`
without `--admit`, and truncates the response so a list of invoices does not get re-read on
every later turn:

```bash
python3 "$SK/llamar.py" GET  "«O»/crm/deals" --query limit=10
python3 "$SK/llamar.py" POST "«O»/crm/deals" --body '{"title":"Acme"}'           # dry-run
python3 "$SK/llamar.py" POST "«O»/crm/deals" --body @deal.json --apply
python3 "$SK/llamar.py" GET  "«O»/invoices" --admit --out invoices.json
```

`«O»` is `/api/v1/organizations/{org_id}`; `{org_id}` and `{project_id}` come from the cached
context, other placeholders from `--path name=value`.

For the raw layer (the HTTP client injects auth + rate-limit backoff):

```bash
source "$SK/lib/http.sh"
ORG="$(pj_org_id)"; PROJ="$(jq -r .project_id .projekt-run/context.json)"
pj_req GET "/organizations/$ORG/projects/$PROJ/tasks?limit=50" | jq -f "$AS/slim.jq" --arg view task
```

`pj_req` returns non-zero on 4xx/5xx; read the status with `pj_last_status` (it runs in a
subshell, so `$PJ_LAST_STATUS` is stale). Errors → `references/errors.md`.

## What this skill does NOT do

Estimates, workload and sprint reports → `pr-informes`. Documents and the AI-context store
→ `pr-docs`. Token-cost measurement → `pr-tokens`. Limits and non-goals across the family:
`references/limits.md`.
