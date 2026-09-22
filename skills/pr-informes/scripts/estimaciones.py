#!/usr/bin/env python3
"""estimaciones.py — fill missing estimates and report plan-vs-actual.

Subcommands: `estimate`, `rollup`, `sprint`, `roadmap`.
DRY-RUN BY DEFAULT for every write; `--apply` to persist.

WHAT CHANGED vs the pre-rewrite skill — read this before trusting old notes:
  · There is NO `/ai/suggest-estimation` endpoint on /api/v1. The AI estimator is
    gone, so `estimate` no longer asks a model for story points. It derives hours
    from the points a human already put on the task, and falls back to the MEDIAN
    of sibling tasks. Nothing is invented; every value says where it came from.
  · Tasks update with PATCH (not PUT):
        PATCH /organizations/{org}/projects/{proj}/tasks/{id} {estimated_hours}
  · Logged hours come from GET /organizations/{org}/time-entries/summary
    (?from&to&group_by=user) — the server does the sum.
  · `roadmap` is READ-ONLY: GET /organizations/{org}/roadmap has no POST. Creating
    a milestone is a finance/contract operation, not a project one.

Arithmetic is done here, never by the model.

stdlib only · Python 3.10+.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pr" / "scripts" / "lib"))
from projekt_api import Client, Ledger, slim, eprint  # noqa: E402

PHASE = "estimate"
POINTS_TABLE = pathlib.Path(__file__).resolve().parents[2] / "pr" / "assets" / "points_hours.json"


def load_points_table() -> dict:
    try:
        return json.loads(POINTS_TABLE.read_text())
    except Exception:
        eprint("  ! %s unreadable — falling back to 1 point = 4 h." % POINTS_TABLE.name)
        return {"points_to_hours": {"1": 4}, "default_hours": 4}


def points_to_hours(points, table: dict) -> float | None:
    if points in (None, ""):
        return None
    try:
        p = int(float(points))
    except (TypeError, ValueError):
        return None
    m = {int(k): float(v) for k, v in (table.get("points_to_hours") or {}).items()}
    if not m:
        return None
    if p in m:
        return m[p]
    nearest = min(m, key=lambda k: abs(k - p))  # Fibonacci gaps: snap to the closest rung
    return m[nearest]


def project_id(c: Client, ref: str | None) -> str:
    ctx = c.context()
    if not ref:
        if c.project:
            return c.project
        raise SystemExit("✗ --project is required (the PAT is not project-scoped).")
    n = ref.strip().lower()
    for p in ctx.get("projects", []):
        if n in (str(p.get("id", "")).lower(), str(p.get("key", "")).lower(),
                 str(p.get("name", "")).lower()):
            return p["id"]
    known = ", ".join(str(p.get("key") or p.get("name")) for p in ctx.get("projects", []))
    raise SystemExit("✗ Unknown project %r. Known: %s\n  (run ../pr/scripts/context_sync.sh)"
                     % (ref, known or "—"))


def fetch_tasks(c: Client, pid: str, sprint: str | None = None) -> list[dict]:
    out, offset = [], 0
    q = "&sprint_id=%s" % sprint if sprint else ""
    while True:
        data = c.get_json("/organizations/%s/projects/%s/tasks?limit=200&offset=%d%s"
                          % (c.org, pid, offset, q))
        rows = data if isinstance(data, list) else (data.get("data") or data.get("tasks") or [])
        out += rows
        if len(rows) < 200:
            break
        offset += 200
        if offset > 4000:
            eprint("  ! stopped paging at 4000 tasks.")
            break
    return out


# ───────────────────────── estimate ─────────────────────────
def cmd_estimate(args, c: Client) -> int:
    pid = project_id(c, args.project)
    table = load_points_table()
    tasks = fetch_tasks(c, pid, args.sprint)
    if not tasks:
        eprint("No tasks in that project/sprint.")
        return 1

    def has_estimate(t):
        eh = t.get("estimated_hours")
        return eh is not None and (float(eh) > 0 or args.include_zero is False and float(eh) == 0)

    known = [float(t["estimated_hours"]) for t in tasks
             if t.get("estimated_hours") not in (None, "") and float(t["estimated_hours"]) > 0]
    median = statistics.median(known) if known else None

    plan = []
    for t in tasks:
        eh = t.get("estimated_hours")
        filled = eh not in (None, "") and float(eh) > (0 if not args.include_zero else -1)
        if filled and not (args.include_zero and float(eh) == 0):
            continue
        hours = points_to_hours(t.get("story_points"), table)
        source = "points"
        if hours is None:
            hours, source = (median, "median") if median else (float(table.get("default_hours", 4)), "default")
        plan.append({"id": t["id"], "ref": t.get("reference") or t["id"],
                     "title": t.get("title") or "", "points": t.get("story_points"),
                     "hours": round(float(hours), 2), "source": source})
        if args.limit and len(plan) >= args.limit:
            break

    print("Project %s   org=%s   token=%s" % (args.project or pid, c.org, c.fingerprint()))
    print("Tasks: %d total · %d already estimated · %d to fill" % (len(tasks), len(known), len(plan)))
    print("Median of the %d known estimates: %s h\n"
          % (len(known), ("%.2f" % median) if median else "— (no siblings)"))
    print("  %-12s  %-6s  %-7s  %-8s  %s" % ("REF", "POINTS", "HOURS", "SOURCE", "TITLE"))
    print("  " + "-" * 78)
    for p in plan:
        print("  %-12.12s  %-6s  %-7.2f  %-8s  %-34.34s"
              % (p["ref"], p["points"] if p["points"] is not None else "—",
                 p["hours"], p["source"], p["title"]))
    by_src = {}
    for p in plan:
        by_src[p["source"]] = by_src.get(p["source"], 0) + 1
    print("\n  sources: %s" % (", ".join("%s=%d" % kv for kv in sorted(by_src.items())) or "—"))
    if by_src.get("median") or by_src.get("default"):
        print("  ⚠ %d value(s) are NOT derived from points a human set — review before trusting them."
              % (by_src.get("median", 0) + by_src.get("default", 0)))

    if not args.apply:
        print("\nDRY-RUN. Re-run with --apply to PATCH %d task(s)." % len(plan))
        return 0
    if not plan:
        print("\nNothing to fill.")
        return 0

    led = Ledger()
    ok = bad = 0
    for p in plan:
        if led.seen("task.estimate", p["id"]):
            continue
        st, data = c.request("PATCH", "/organizations/%s/projects/%s/tasks/%s" % (c.org, pid, p["id"]),
                             {"estimated_hours": p["hours"]})
        if 200 <= st < 300:
            led.add(PHASE, "task.estimate", p["id"], "updated", ref=p["ref"])
            ok += 1
            print("  ✓ %-12s %.2f h (%s)" % (p["ref"], p["hours"], p["source"]))
        elif st == 403:
            eprint("  ✗ 403 cross-org/scope — stopping.")
            return 2
        else:
            led.add(PHASE, "task.estimate", p["id"], "error", ref=str(st))
            bad += 1
            msg = data.get("message") if isinstance(data, dict) else data
            eprint("  ✗ %-12s HTTP %s: %s" % (p["ref"], st, msg))
    print("\ndone  updated=%d  failed=%d  (ledger: %s)" % (ok, bad, led.summary()))
    return 0 if not bad else 1


# ───────────────────────── rollup ─────────────────────────
def cmd_rollup(args, c: Client) -> int:
    pid = project_id(c, args.project)
    tasks = fetch_tasks(c, pid, args.sprint)
    names = {m.get("user_id"): m.get("name") for m in c.context().get("members", [])}

    planned: dict[str, float] = {}
    counts: dict[str, int] = {}
    for t in tasks:
        uid = t.get("assignee_id") or "(unassigned)"
        planned[uid] = planned.get(uid, 0.0) + float(t.get("estimated_hours") or 0)
        counts[uid] = counts.get(uid, 0) + 1

    qs = ["project_id=%s" % pid, "group_by=user"]
    for flag_, key in (("date_from", "from"), ("date_to", "to")):
        v = getattr(args, flag_, None)
        if v:
            qs.append("%s=%s" % (key, v))
    summ = c.get_json("/organizations/%s/time-entries/summary?%s" % (c.org, "&".join(qs)))
    logged = {g.get("user_id"): (g.get("total_minutes") or 0) / 60.0
              for g in (summ.get("groups") or []) if isinstance(g, dict)}

    window = "%s → %s" % (args.date_from or "(all time)", args.date_to or "(all time)")
    print("Plan vs actual — project %s   org=%s" % (args.project or pid, c.org))
    print("Planned: Σ estimated_hours over %d task(s) (ALL of them, not the window)." % len(tasks))
    print("Logged:  server time-entries/summary for %s\n" % window)
    print("  %-26s  %-6s  %-9s  %-9s  %-9s  %s" % ("MEMBER", "TASKS", "PLANNED", "LOGGED", "DELTA", "LOGGED/PLAN"))
    print("  " + "-" * 82)
    tp = tl = 0.0
    for uid in sorted(set(planned) | set(logged),
                      key=lambda u: -(planned.get(u, 0) + logged.get(u, 0))):
        p, l = planned.get(uid, 0.0), logged.get(uid, 0.0)
        tp += p
        tl += l
        pct = ("%.0f%%" % (100.0 * l / p)) if p > 0 else "—"
        print("  %-26.26s  %-6s  %-9.2f  %-9.2f  %-+9.2f  %s"
              % (names.get(uid) or uid, counts.get(uid, 0), p, l, l - p, pct))
    print("  " + "-" * 82)
    print("  %-26s  %-6d  %-9.2f  %-9.2f  %-+9.2f  %s"
          % ("TOTAL", len(tasks), tp, tl, tl - tp,
             ("%.0f%%" % (100.0 * tl / tp)) if tp > 0 else "—"))
    return 0


# ───────────────────────── sprint ─────────────────────────
def cmd_sprint(args, c: Client) -> int:
    pid = project_id(c, args.project)
    sprints = c.get_json("/organizations/%s/projects/%s/sprints" % (c.org, pid))
    rows = sprints if isinstance(sprints, list) else (sprints.get("data") or sprints.get("sprints") or [])
    if not rows:
        print("No sprints in this project.")
        return 0
    if not args.sprint:
        print("Sprints in project %s:" % (args.project or pid))
        for s in rows:
            print("  · %-36s  %-10s  %s → %s"
                  % (s.get("name") or s.get("id"), s.get("status") or "?",
                     s.get("start_date") or "?", s.get("end_date") or "?"))
        print("\nPass --sprint <id> for stats + burndown.")
        return 0
    stats = c.get_json("/organizations/%s/projects/%s/sprints/%s/stats" % (c.org, pid, args.sprint))
    print("Sprint %s — stats" % args.sprint)
    for k, v in (stats or {}).items():
        if not isinstance(v, (dict, list)):
            print("  %-22s %s" % (k, v))
    try:
        burn = c.get_json("/organizations/%s/sprints/%s/burndown" % (c.org, args.sprint))
        pts = burn if isinstance(burn, list) else (burn.get("data") or burn.get("points") or [])
        if pts:
            print("\n  burndown: %d point(s), %s → %s"
                  % (len(pts), pts[0].get("date", "?"), pts[-1].get("date", "?")))
    except SystemExit as e:
        eprint("  ! burndown unavailable: %s" % e)
    return 0


# ───────────────────────── roadmap ─────────────────────────
def cmd_roadmap(args, c: Client) -> int:
    """READ-ONLY. GET /organizations/{org}/roadmap has no POST counterpart."""
    data = c.get_json("/organizations/%s/roadmap" % c.org)
    rows = data if isinstance(data, list) else (
        data.get("items") or data.get("data") or data.get("roadmap") or [])
    print("Roadmap — org %s   (%d item(s))" % (c.org, len(rows) if isinstance(rows, list) else 0))
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            print("  · %-40.40s  %-12s  %s → %s"
                  % (r.get("name") or r.get("title") or r.get("id") or "?",
                     r.get("status") or r.get("type") or "",
                     r.get("start_date") or r.get("starts_at") or "?",
                     r.get("end_date") or r.get("ends_at") or "?"))
    elif isinstance(data, dict):
        print(json.dumps(data, indent=2)[:1500])
    print("\n  (read-only: the API exposes no roadmap write on /api/v1.)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="estimaciones.py",
        description="Fill missing estimates and report plan-vs-actual. Dry-run by default.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("estimate", help="fill missing estimated_hours (points → hours, else median)")
    pe.add_argument("--project", default="", help="project id | key | name")
    pe.add_argument("--sprint", default="", help="restrict to one sprint id")
    pe.add_argument("--limit", type=int, default=0, help="cap how many tasks to touch")
    pe.add_argument("--include-zero", action="store_true", help="also re-estimate tasks sitting at 0 h")
    pe.add_argument("--apply", action="store_true", help="execute PATCHes (default: dry-run)")
    pe.set_defaults(func=cmd_estimate)

    pr = sub.add_parser("rollup", help="planned vs logged hours per assignee (read-only)")
    pr.add_argument("--project", default="", help="project id | key | name")
    pr.add_argument("--sprint", default="", help="restrict to one sprint id")
    pr.add_argument("--date-from", dest="date_from", default="", help="YYYY-MM-DD (logged window)")
    pr.add_argument("--date-to", dest="date_to", default="", help="YYYY-MM-DD (logged window)")
    pr.set_defaults(func=cmd_rollup)

    ps = sub.add_parser("sprint", help="list sprints, or one sprint's stats + burndown (read-only)")
    ps.add_argument("--project", default="", help="project id | key | name")
    ps.add_argument("--sprint", default="", help="sprint id for stats + burndown")
    ps.set_defaults(func=cmd_sprint)

    prm = sub.add_parser("roadmap", help="org roadmap (read-only — no write exists)")
    prm.set_defaults(func=cmd_roadmap)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    c = Client()
    if not c.org:
        raise SystemExit("✗ No org in context. Run ../pr/scripts/auth_check.sh + context_sync.sh first.")
    return args.func(args, c)


if __name__ == "__main__":
    sys.exit(main())
