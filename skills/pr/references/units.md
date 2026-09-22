# Estimation units — story points → hours

**The trap (historical):** the old API had `POST /ai/suggest-estimation`, which returned
**story_points only** while tasks store
`estimated_hours`. You must convert, and you must flag AI-derived values for human review.

- Conversion table: `assets/points_hours.json` (Fibonacci → hours; sane defaults, **calibrate per org**).
- Every value written from an AI suggestion is marked AI-suggested (prefix the issue's estimate note or
  add an `ai-estimated` label) so a human can confirm.
- On AI **503** (daily quota), don't block: fall back to **median estimated_hours of sibling issues**
  (same project/sprint/type). Mark those as `heuristic` too.

Default map (`points_hours.json`), calibrated to the 3XA org's real estimate distribution
(428 estimated issues; median 3 h, p90 10 h — mostly small tasks):

| Points | Hours |
|---|---|
| 1 | 1 |
| 2 | 2 |
| 3 | 4 |
| 5 | 8 |
| 8 | 13 |
| 13 | 20 |
| 21 | 40 |

`default_hours` (when a point value isn't in the map) = **3** (the org median).

Recalibrate for a different org: compare planned vs logged hours
(`pr-informes rollup`, which reads `/time-entries/summary`) — or
just the `estimated_hours` distribution — and edit `points_hours.json`; it's the single source of truth
for the `projekt-estimate` skill. Note: this org records estimates in **hours**, not story points, so the
table maps AI-suggested points onto that hours scale rather than being learned from point velocity.

## On /api/v1 there is no AI estimator

`/ai/suggest-estimation` **no longer exists**. `pr-informes estimate` therefore never asks a
model for points: it converts the `story_points` a human already set, and otherwise falls back
to the MEDIAN of sibling tasks' `estimated_hours`. Every row says which of the two it used, so
a derived number is never mistaken for a human's estimate.
