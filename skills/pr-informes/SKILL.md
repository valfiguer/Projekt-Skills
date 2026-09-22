---
name: pr-informes
description: >-
  Read-only reports for a Projekt Republic organization, plus estimate filling: per-member
  workload and capacity, planned-vs-actual hours, sprint stats and burndown, and the org
  roadmap. The scripts do all the arithmetic, so the model spends no tokens on numbers.
  Use for team balance, who is overloaded, capacity for a week, estimations, story points
  or plan-vs-actual. Requires the `pr` skill's connect step first.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# pr-informes — workload, estimates, sprints

`SK="${CLAUDE_SKILL_DIR}/scripts"`. Connect first with the `pr` skill:

```bash
PR="${CLAUDE_SKILL_DIR}/../pr/scripts"
bash "$PR/auth_check.sh" && bash "$PR/context_sync.sh"
```

## Workload & capacity (read-only by construction — no `--apply` exists)

```bash
python3 "$SK/cargas.py"                                   # current ISO week, Markdown
python3 "$SK/cargas.py" --from 2026-09-01 --to 2026-09-07
python3 "$SK/cargas.py" --csv > cargas.csv
python3 "$SK/cargas.py" --over 90 --under 40
python3 "$SK/cargas.py" --json
```

**The range trap — the whole reason this report is shaped the way it is.** Three aggregates,
and only one of them takes dates:

| Source | Covers | Takes `from`/`to`? |
|---|---|---|
| `/workforce/capacity` | the **current week**, and it says which | **No parameters** |
| `/dashboard/stats` → `workload[]` | **all history** (assigned/done counts) | **No parameters** |
| `/time-entries/summary` | exactly the window you ask for | Yes |

So `--from`/`--to` move **only** the logged-hours column. The report labels every column with
the period it really covers, and marks the all-history ones with `*`. Printing
`dashboard/stats` counts under a "June 1–7" heading would be a lie — that mistake has been
made before. Utilization = logged hours in the window ÷ net expected hours (expected minus
holidays and absences) for the capacity week.

## Estimates & plan-vs-actual

```bash
python3 "$SK/estimaciones.py" estimate --project WEB            # dry-run table
python3 "$SK/estimaciones.py" estimate --project WEB --apply    # PATCH estimated_hours
python3 "$SK/estimaciones.py" rollup  --project WEB --date-from 2026-09-01 --date-to 2026-09-30
python3 "$SK/estimaciones.py" sprint  --project WEB             # list; add --sprint <id> for stats
python3 "$SK/estimaciones.py" roadmap                           # org roadmap (read-only)
```

**There is no AI estimator on `/api/v1`.** `/ai/suggest-estimation` is gone. `estimate` converts
the `story_points` a human already set via `../pr/assets/points_hours.json`, and otherwise falls
back to the **median** of sibling tasks' `estimated_hours` (or `default_hours` when there are no
siblings). Every row prints its source — `points`, `median` or `default` — and the run warns how
many values were not derived from a human's points. Nothing is invented. Calibrate the
conversion table per org.

`rollup` is plain arithmetic: planned = Σ `estimated_hours` over the project's tasks (**all of
them**, not the window), logged = the server's `/time-entries/summary` for the window. Both
labels are printed so the two spans are never conflated.

## Gotchas

- **403 cross-org** is fatal and not retried: a PAT is bound to one org.
- **Members with no capacity target** show `—` and flag `n/a` instead of dividing by zero.
- `dashboard/stats` may be unavailable to a narrow PAT; the report then blanks the
  assigned/done columns and says so rather than failing.
- **Roadmap is read-only** — `GET /organizations/{org}/roadmap` has no POST. Contract
  milestones (`/contracts/{id}/milestones`) are a finance resource, not a project roadmap.

Shared: `../pr/references/endpoints.md` · `errors.md` · `units.md` · `limits.md`.
