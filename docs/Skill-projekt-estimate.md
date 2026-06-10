# Skill: `projekt-estimate`

Fill missing issue estimates and report planned-vs-actual hours. One script (`estimate_rollup.py`), three subcommands: `estimate`, `rollup`, `roadmap`. **Dry-run by default; `--apply` to write.** Covers the **ESTIMATE** pipeline phase.

Soporta español: estimaciones, puntos, horas, planificado vs real, hoja de ruta.

## Prerequisite — connect once

```bash
bash skills/projekt/scripts/auth_check.sh
bash skills/projekt/scripts/context_sync.sh
```

Resolves project/member names → ids from `.projekt-run/context.json`; never re-queries.

## Commands

```bash
# 1) ESTIMATE — fill issues missing estimated_hours (project = id | key | name)
python3 skills/projekt-estimate/scripts/estimate_rollup.py estimate --project WEB                # DRY-RUN
python3 skills/projekt-estimate/scripts/estimate_rollup.py estimate --project WEB --apply        # PUT + flag AI
python3 skills/projekt-estimate/scripts/estimate_rollup.py estimate --project WEB --sprint <sid> --limit 20
python3 skills/projekt-estimate/scripts/estimate_rollup.py estimate --project WEB --no-ai        # median-of-siblings only
python3 skills/projekt-estimate/scripts/estimate_rollup.py estimate --project WEB --include-zero # also re-estimate 0h issues

# 2) ROLLUP — deterministic planned vs logged hours per assignee (no model tokens)
python3 skills/projekt-estimate/scripts/estimate_rollup.py rollup --project WEB
python3 skills/projekt-estimate/scripts/estimate_rollup.py rollup --project WEB --date-from 2026-06-01 --date-to 2026-06-30

# 3) ROADMAP (optional) — list, or create one
python3 skills/projekt-estimate/scripts/estimate_rollup.py roadmap --project WEB                 # list (read-only)
python3 skills/projekt-estimate/scripts/estimate_rollup.py roadmap --project WEB \
  --name "Q3 launch" --start-date 2026-07-01 --end-date 2026-09-30 --apply
```

### Dry-run → apply (estimate)

`estimate --project WEB` prints a table — `issue · points · hours · source · title` — plus a count of AI/heuristic values, and writes **nothing**. Re-run with `--apply` to `PUT /issues/{id} {estimated_hours}` and tag each touched issue with the `ai-estimated` label. Re-running `--apply` dedupes via the ledger (writes 0).

## How `estimate` decides hours (the trap)

`POST /ai/suggest-estimation` returns **story_points ONLY** — never hours. The script:

1. Calls the AI estimator (rate bucket `ai`, **throttled to ≤10/min**, ~6s between calls).
2. Maps points → hours via `skills/projekt/assets/points_hours.json` (nearest-point match if a value isn't in the table). **Calibrate that file per org** — see [Estimation Units](Estimation-Units.md).
3. On AI **503** (daily quota spent) it soft-skips and, for the rest of the run, falls back to the **median `estimated_hours` of sibling issues** (same project/sprint/type; widens to any sibling, else `default_hours`).
4. Flags every AI/median/default value with the `ai-estimated` label + a ledger note.

Source labels in the table: `ai` (points→hours), `median` (sibling median), `default` (no siblings).

## Rollup math is deterministic

`rollup` computes **planned = Σ estimated_hours** per assignee, and **logged** from `GET /workload` (preferred) or by summing per-issue `time-summary`. Delta and `logged/plan %` are plain arithmetic — **no model tokens spent on numbers**. Time-summary is in minutes; the script converts to hours.

## Gotchas

- **points ≠ hours.** Writing AI points straight into `estimated_hours` is the #1 mistake. The script always converts and flags.
- **AI bucket is 10/min + a daily cap.** The script self-throttles; a 503 mid-run flips the remainder to median fallback. Re-run later to fill `default` rows.
- **Assignee-required (422):** unowned issues stay in `Backlog`/`To Do`; they show as `(unassigned)` in both tables — assign via [projekt-issues](Skill-projekt-issues.md) before relying on the per-assignee roll-up.
- **403 cross-org:** the script stops and explains rather than retrying.
- **Resumable:** every write logs to `.projekt-run/<ts>.jsonl`; interrupt and re-run.

## What it does NOT do

No create/move issues (→ [projekt-issues](Skill-projekt-issues.md)), time (→ [projekt-time](Skill-projekt-time.md)), docs (→ [projekt-docs](Skill-projekt-docs.md)). Doesn't invent story points itself — relies on `/ai/suggest-estimation` + `points_hours.json` (with `--no-ai`, sibling medians only). Doesn't edit the conversion table or the `/workload` aggregates; it reads them.

See also: [Estimation Units](Estimation-Units.md) · [API Endpoints → Estimation & roadmap](API-Endpoints.md#estimation--roadmap).
