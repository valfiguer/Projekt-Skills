# Skill: `pr-informes` — workload, estimates, sprints

Read-only reporting plus estimate filling. Every number is computed by the scripts, so the
model spends no tokens on arithmetic. Requires the [`pr`](Skill-pr.md) connect step.

```bash
SK="$CLAUDE_PLUGIN_ROOT/skills/pr-informes/scripts"
```

## Workload & capacity

```bash
python3 "$SK/cargas.py"                                   # current ISO week, Markdown
python3 "$SK/cargas.py" --from 2026-09-01 --to 2026-09-07
python3 "$SK/cargas.py" --csv > cargas.csv
python3 "$SK/cargas.py" --over 90 --under 40
python3 "$SK/cargas.py" --json
```

There is no `--apply`: the report is read-only by construction.

### The range trap

Three aggregates feed the report and **only one takes dates**:

| Source | Covers | Accepts `from`/`to`? |
|---|---|---|
| `GET …/workforce/capacity` | the current week, and it names it in `week_start`/`week_end` | **No parameters at all** |
| `GET …/dashboard/stats` → `workload[]` | **all history** (assigned / done counts) | **No parameters at all** |
| `GET …/time-entries/summary` | exactly the window asked for | Yes |

`--from`/`--to` therefore move only the logged-hours column. The report labels each column
with the period it really covers and marks all-history columns with `*`. Presenting
`dashboard/stats` counts under a date heading states something the data does not say.

Utilization = logged hours in the window ÷ net expected hours (expected minus holidays and
absences) for the capacity week. Members with no capacity target show `—` and flag `n/a`
instead of dividing by zero.

## Estimates and plan-vs-actual

```bash
python3 "$SK/estimaciones.py" estimate --project WEB            # dry-run
python3 "$SK/estimaciones.py" estimate --project WEB --apply
python3 "$SK/estimaciones.py" rollup  --project WEB --date-from 2026-09-01 --date-to 2026-09-30
python3 "$SK/estimaciones.py" sprint  --project WEB [--sprint <id>]
python3 "$SK/estimaciones.py" roadmap
```

**There is no AI estimator on `/api/v1`** — `/ai/suggest-estimation` is gone. `estimate`
converts the `story_points` a human already set through
`skills/pr/assets/points_hours.json`, and otherwise uses the **median** of sibling tasks'
`estimated_hours` (or `default_hours` with no siblings). Every row prints its source —
`points`, `median` or `default` — and the run warns how many values were not derived from a
human's points. Nothing is invented. Calibrate the table per organization; see
[Estimation Units](Estimation-Units.md).

`rollup` prints planned (Σ `estimated_hours` over **all** the project's tasks) against logged
(the server's summary **for the window**), with both spans labelled so they are never
conflated.

`roadmap` is read-only: `GET /organizations/{org}/roadmap` has no POST counterpart. Contract
milestones are a finance resource, not a project roadmap.
