# Skill: `projekt-workload`

A **deterministic, read-only** per-member workload & capacity report. The script fetches the four server-side aggregates and computes every number itself — the model spends **zero tokens on arithmetic** and writes nothing. Covers the **REPORT** pipeline phase.

Soporta español: cargas de trabajo, capacidad, utilización, sobreasignación, quién está saturado, informe del equipo.

## Prerequisite — connect once

```bash
bash skills/projekt/scripts/auth_check.sh
bash skills/projekt/scripts/context_sync.sh
```

Reads `.projekt-run/context.json` for member-name resolution; never re-queries the roster.

## Run it

```bash
# Current ISO week (Mon→Sun), Markdown table to stdout:
python3 skills/projekt-workload/scripts/workload_report.py

# Explicit window:
python3 skills/projekt-workload/scripts/workload_report.py --from 2026-06-01 --to 2026-06-07

# CSV for a spreadsheet:
python3 skills/projekt-workload/scripts/workload_report.py --csv > workload.csv

# Tune the bands (default: over = org threshold or 100%, under = 50%):
python3 skills/projekt-workload/scripts/workload_report.py --over 90 --under 40

# Machine-readable summary:
python3 skills/projekt-workload/scripts/workload_report.py --json
```

It reads `GET /workload`, `GET /workload/capacity`, `GET /capacity` and `GET /capacity/threshold`, merges them per `user_id`, and prints one row per member.

## Output columns

| Column | Source |
| --- | --- |
| Assigned / In progress / Done | counts from `/workload` (open + WIP + completed in the window) |
| Hours logged | logged hours from `/workload` over `[from,to]` |
| Est. hours | estimated open load from `/capacity` (falls back to `/workload`) |
| Capacity | per-member target hours from `/capacity` or `/workload/capacity` |
| Utilization % | the server's value if given, else `100 × est-or-logged ÷ capacity` |
| Flag | `⚠️ OVER` > over-threshold · `↓ under` < under-threshold · `— n/a` if no capacity |

## Dry-run / apply

There is **nothing to apply** — read-only by construction. Only `GET` calls, no `--apply`/`--admit`, always safe to re-run.

## Gotchas

- **Threshold source.** `--over` wins; else the org's `/capacity/threshold`; else `100%`. The header line states which was used (`flag` / `org` / `default`).
- **Field-name drift.** Aggregates use varied keys across orgs/versions; the script normalizes aliases (`in_progress`/`inProgress`/`wip`, `hours_logged`/`logged_hours`, …) and tolerates `array` or `{data:[…]}`/`{members:[…]}` envelopes.
- **No capacity set.** Members with a `0`/missing target show utilization `—` and flag `n/a` rather than dividing by zero or being dropped.
- **Names.** From `.projekt-run/context.json`. Skipped `context_sync.sh`? Rows fall back to user-ids + a stderr warning.
- **Window default.** Current ISO week, Monday→Sunday, computed locally. Dates `YYYY-MM-DD`; `--from` after `--to` exits non-zero.
- **403 / 429 / 5xx.** A PAT is bound to one org (403 → switch org/token, not a bug); 429 and 5xx auto-retry with backoff.

## What it does NOT do

No writes, no rebalancing, no assignment changes, no estimation, no time logging — it only *reports*. To act on the findings, route back through the [`projekt`](Skill-projekt.md) orchestrator to [projekt-issues](Skill-projekt-issues.md), [projekt-time](Skill-projekt-time.md) or [projekt-docs](Skill-projekt-docs.md).

See also: [API Endpoints → Workload & capacity](API-Endpoints.md#workload--capacity-read-only-aggregates) · [Errors & Troubleshooting](Errors-and-Troubleshooting.md).
