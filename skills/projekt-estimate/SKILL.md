---
name: projekt-estimate
description: >-
  Estimate Projekt issues and report plan-vs-actual. Fills missing estimated_hours by
  asking the AI estimator (story_points only) and converting points→hours, with a
  median-of-siblings fallback when the AI daily quota is spent; then rolls up planned vs
  logged hours per assignee. Use when the user asks to estimate / estimación / estimaciones,
  story points / puntos de historia, capacity or plan-vs-actual, or to read/create roadmap
  milestones for a Projekt project. Soporta español: estimaciones, puntos, horas, planificado
  vs real, hoja de ruta. Requires the `projekt` skill's auth + context first.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# Projekt — estimate & plan-vs-actual

Fill missing issue estimates and report planned vs logged hours. One script, three
subcommands: `estimate`, `rollup`, `roadmap`. **Dry-run by default; `--apply` to write.**

`SK="${CLAUDE_SKILL_DIR}/scripts"` — use it for every command below.

## Prerequisite (run once per session, from the `projekt` skill)

```bash
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/auth_check.sh"     # resolves token + org → .projekt-run/context.json
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/context_sync.sh"   # caches projects + members
```

This script resolves project/member **names → ids from `.projekt-run/context.json`** and
never re-queries that. If context is missing it warns and project lookups fail fast.

## Commands

```bash
# 1) ESTIMATE — fill issues missing estimated_hours (project = id | key | name)
python3 "$SK/estimate_rollup.py" estimate --project WEB                 # DRY-RUN: proposed table, 0 writes
python3 "$SK/estimate_rollup.py" estimate --project WEB --apply         # PUT estimated_hours + flag AI values
python3 "$SK/estimate_rollup.py" estimate --project WEB --sprint <sid> --limit 20
python3 "$SK/estimate_rollup.py" estimate --project WEB --no-ai         # skip AI; median-of-siblings only
python3 "$SK/estimate_rollup.py" estimate --project WEB --include-zero  # also re-estimate 0h issues

# 2) ROLLUP — deterministic planned vs logged hours per assignee (no model tokens)
python3 "$SK/estimate_rollup.py" rollup --project WEB
python3 "$SK/estimate_rollup.py" rollup --project WEB --date-from 2026-06-01 --date-to 2026-06-30

# 3) ROADMAP (optional) — list items, or create one
python3 "$SK/estimate_rollup.py" roadmap --project WEB                                   # list (read-only)
python3 "$SK/estimate_rollup.py" roadmap --project WEB --name "Q3 launch" --start-date 2026-07-01 --end-date 2026-09-30 --apply
```

### Dry-run → apply (estimate)

`estimate --project WEB` prints a table — `issue · points · hours · source · title` — plus a count
of how many values are AI/heuristic-derived. It writes **nothing**. Re-run with `--apply`
to `PUT /issues/{id} {estimated_hours}` and tag each touched issue with the `ai-estimated`
label so a human can confirm. Re-running `--apply` dedupes via the ledger (writes 0).

## How estimate decides hours (the trap)

`POST /ai/suggest-estimation` returns **story_points ONLY** — never hours. The script:

1. Calls the AI estimator (rate bucket `ai`, **throttled to ≤10/min**, ~6s between calls).
2. Maps points → hours via `skills/projekt/assets/points_hours.json` (Fibonacci defaults;
   nearest-point match if a value isn't in the table). **Calibrate that file per org.**
3. On AI **503** (daily quota spent) it soft-skips and, for the rest of the run, falls back
   to the **median `estimated_hours` of sibling issues** (same project/sprint/type; widens to
   any sibling with an estimate, else `default_hours`).
4. Flags every AI/median/default value with the `ai-estimated` label + a ledger note.

Source labels in the table: `ai` (points→hours), `median` (sibling median), `default`
(no siblings). Full rationale: `skills/projekt/references/units.md`.

## Rollup math is deterministic

`rollup` computes **planned = Σ estimated_hours** per assignee and **logged** from
`GET /workload` (preferred aggregate) or, if unavailable, by summing
`GET /projects/{pid}/issues/{iid}/time-summary` per issue. Delta and `logged/plan %` are
plain arithmetic — **no model tokens are spent on the numbers**. Time-summary is in minutes;
the script converts to hours.

## Gotchas (this domain)

- **points ≠ hours.** Writing AI points straight into `estimated_hours` is the #1 mistake.
  Always convert via `points_hours.json`; the script does this and flags the result.
- **AI bucket is 10/min + a daily cap.** The script self-throttles; a 503 mid-run flips the
  remainder to median fallback rather than blocking. Re-run later to fill any `default` rows.
- **Assignee-required (422):** issues without an owner stay in `Backlog`/`To Do`. Estimating
  doesn't move them, but a blank assignee shows as `(unassigned)` in both tables — assign via
  the `projekt-issues` skill before relying on the per-assignee roll-up.
- **403 cross-org:** a PAT is bound to one org; the script stops and explains rather than
  retrying. See `skills/projekt/references/errors.md`.
- **Resumable:** every write is logged to `.projekt-run/<ts>.jsonl`; interrupt and re-run.

## What it does NOT do

- Does **not** create or move issues (use `projekt-issues`), log time (`projekt-time`), or
  write docs (`projekt-docs`).
- Does **not** invent story points itself — it relies on `/ai/suggest-estimation` and the
  shared `points_hours.json`; with `--no-ai` it uses only sibling medians.
- Does **not** edit the conversion table or `/workload`/`/capacity` aggregates; it reads them.

Shared references: `skills/projekt/references/units.md` (points→hours),
`errors.md` (422/429/503/403), `endpoints.md` (paths). Conversion table:
`skills/projekt/assets/points_hours.json`.
