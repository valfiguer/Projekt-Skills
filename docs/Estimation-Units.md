# Estimation Units — story points → hours

**The trap:** `POST /ai/suggest-estimation` returns **story_points only**, but issues store `estimated_hours`. You must convert — and you must flag AI-derived values for human review. The [projekt-estimate](Skill-projekt-estimate.md) skill does both automatically.

## The conversion table

`skills/projekt/assets/points_hours.json` is the **single source of truth**, calibrated to the 3XA org's real estimate distribution (428 estimated issues; median 3 h, p90 10 h — mostly small tasks):

| Points | Hours |
| --- | --- |
| 1 | 1 |
| 2 | 2 |
| 3 | 4 |
| 5 | 8 |
| 8 | 13 |
| 13 | 20 |
| 21 | 40 |

`default_hours` (when a point value isn't in the map) = **3** (the org median). Nearest-point match is used for in-between values.

## How a value is chosen

1. **AI** — `/ai/suggest-estimation` returns points → mapped to hours via the table. Source label: `ai`.
2. **Median fallback** — on AI **503** (daily quota spent), the median `estimated_hours` of sibling issues (same project/sprint/type; widens to any sibling with an estimate). Source label: `median`.
3. **Default** — no siblings with estimates → `default_hours` (3). Source label: `default`.

Every AI/median/default value is tagged with the `ai-estimated` label + a ledger note so a human can confirm.

## Recalibrating for another org

This org records estimates in **hours**, not story points (0 issues carry points), so the table maps AI-suggested points onto that hours scale rather than being learned from point velocity.

To recalibrate:

1. Compare planned vs logged hours (`/time-summary`, `/workload`) — or just the `estimated_hours` distribution.
2. Edit `skills/projekt/assets/points_hours.json`.

That file is read by `projekt-estimate` on every run — no code change needed.

> History: v0.2.1 replaced the original Fibonacci defaults (1 pt = 2 h … 21 pt = 96 h), which ran ~3× high for this org. See [Changelog](Changelog.md).

See also: [Skill: projekt-estimate](Skill-projekt-estimate.md).
