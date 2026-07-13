---
name: projekt-workload
description: >-
  Deterministic per-member workload & capacity report for a Projekt organization (projekt.3xa.es),
  read-only via the user's PAT. Pulls /workload, /workload/capacity, /capacity and /capacity/threshold,
  then renders a Markdown (or CSV) table of assigned / in-progress / done / hours-logged + utilization %,
  flagging over- and under-allocated members. The script does all the math — zero model tokens. Use when
  the user wants to balance the team, see who's overloaded, or report capacity for a week/range. Soporta
  español: cargas de trabajo, capacidad, utilización, sobreasignación, quién está saturado, informe del equipo.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# Projekt — workload & capacity report (read-only)

> **⚠ NOT YET PORTED to /api/v1.** The base URL is fixed (shares `projekt_api.py`, now on
> `https://projekt.3xa.es/api/v1`), but the endpoint PATHS in `workload_report.py` are still the
> **legacy flat** aggregates (`/workload`, `/workload/capacity`, `/capacity`, `/capacity/threshold`)
> and **will 404** on the rewrite. To port: rediscover the equivalents under the org-scoped surface
> (likely `/organizations/{org}/…`) with `bash ../projekt/scripts/spec_lookup.sh --search workload`
> and `--search capacity`, then re-key rows on `user_id`. Working today: the `projekt` connect
> (auth/context) + `projekt-issues` task create/list.

One job: a **deterministic** team workload report. The script fetches the four server-side aggregates and
computes every number itself — the model spends **no tokens on arithmetic** and writes nothing.

`SK_CORE="${CLAUDE_SKILL_DIR}/../projekt/scripts"` · `SK="${CLAUDE_SKILL_DIR}/scripts"`.

## Prerequisite — connect once

Run the **`projekt`** skill's setup first so the token is resolved and member names are cached
(`.projekt-run/context.json`); this script reads that cache for name resolution and never re-queries the roster:

```bash
bash "$SK_CORE/auth_check.sh"      # resolves user + org, writes context
bash "$SK_CORE/context_sync.sh"    # caches projects + members
```

## Run it

```bash
# Current ISO week (Mon→Sun), Markdown table to stdout:
python3 "$SK/scripts/workload_report.py"

# Explicit window:
python3 "$SK/scripts/workload_report.py" --from 2026-06-01 --to 2026-06-07

# CSV for a spreadsheet:
python3 "$SK/scripts/workload_report.py" --csv > workload.csv

# Tune the bands (otherwise over = org /capacity/threshold or 100%, under = 50%):
python3 "$SK/scripts/workload_report.py" --over 90 --under 40

# Machine-readable summary:
python3 "$SK/scripts/workload_report.py" --json
```

It reads `GET /workload?date_from=&date_to=`, `GET /workload/capacity`, `GET /capacity` and
`GET /capacity/threshold` (see `references/endpoints.md` → *Workload & capacity*), merges them per
`user_id`, and prints one row per member: assigned · in-progress · done · hours-logged · est. hours ·
capacity · **utilization %** · flag. Members above the over-threshold are flagged `⚠️ OVER`, below the
under-threshold `↓ under`, and those with no capacity target `— n/a`.

## Dry-run / apply

There is **nothing to apply** — this skill is read-only by construction. It makes only `GET` calls, takes
no `--apply`/`--admit` flag, and is always safe to re-run. (The dry-run-by-default rule is satisfied: it
never mutates.)

## Output columns

| Column | Source |
|---|---|
| Assigned / In progress / Done | counts from `/workload` (open + WIP + completed in the window) |
| Hours logged | logged hours from `/workload` over `[from,to]` |
| Est. hours | estimated open load from `/capacity` (falls back to `/workload`) |
| Capacity | per-member target hours from `/capacity` or `/workload/capacity` |
| Utilization % | the server's value if given, else `100 × est-or-logged ÷ capacity` |
| Flag | `OVER` > over-threshold · `under` < under-threshold · `n/a` if no capacity |

## Gotchas (this domain)

- **Threshold source.** `--over` wins; else the org's `/capacity/threshold`; else `100%`. The header line
  states which was used (`flag` / `org` / `default`).
- **Field-name drift.** The aggregates use varied keys across orgs/versions; the script normalizes common
  aliases (`in_progress`/`inProgress`/`wip`, `hours_logged`/`logged_hours`, …) and tolerates `array` or
  `{data:[…]}`/`{members:[…]}` envelopes — the same defensive shape `context_sync.sh` uses.
- **No capacity set.** Members with a `0`/missing capacity target show utilization `—` and flag `n/a`
  rather than dividing by zero or being silently dropped.
- **Names.** Resolved from `.projekt-run/context.json`. If you skipped `context_sync.sh`, rows fall back to
  user-ids and a warning prints on stderr.
- **Window default.** Current ISO week, Monday→Sunday, computed locally. Dates must be `YYYY-MM-DD`;
  `--from` after `--to` exits non-zero.
- **403 cross-org / 429 / 5xx.** A PAT is bound to one org (403 → switch org/token, not a bug); 429 and
  5xx are auto-retried with backoff by the shared client. See `references/errors.md`.

## What it does NOT do

No writes, no rebalancing, no assignment changes, no estimation, no time logging — it only *reports*. To act
on the findings (assign/move issues, log time, document) route back through the **`projekt`** orchestrator to
`projekt-issues`, `projekt-time` or `projekt-docs`. Token resolution + error envelope live in the shared
`references/auth-setup.md` and `references/errors.md`.
