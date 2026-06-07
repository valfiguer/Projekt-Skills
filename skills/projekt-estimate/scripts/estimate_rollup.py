#!/usr/bin/env python3
"""estimate_rollup.py — Projekt estimation + plan-vs-actual roll-up (stdlib only).

Two modes (subcommands):

  estimate   For issues missing estimated_hours: ask POST /ai/suggest-estimation
             (rate bucket `ai`, throttled <=10/min) which returns story_points ONLY,
             then map points->hours via skills/projekt/assets/points_hours.json.
             On 503 (AI daily quota) fall back to the MEDIAN estimated_hours of
             sibling issues (same project / sprint / type). DRY-RUN prints the
             proposed (issue, points, hours, source) table; --apply writes
             PUT /issues/{id} {estimated_hours} and FLAGS AI/heuristic values by
             adding the `ai-estimated` label (best-effort) + a ledger note.

  rollup     Plan-vs-actual: planned = sum(estimated_hours) per project/assignee;
             logged  = from GET /projects/{pid}/issues/{iid}/time-summary +
             GET /workload. Prints a DETERMINISTIC table. No model tokens for math.

  roadmap    Optional. List GET /projects/{pid}/roadmap, or with --apply create a
             milestone via POST /projects/{pid}/roadmap.

Conventions (see skills/projekt/SKILL.md):
  * DRY-RUN by default; --apply to write.
  * Idempotent + resumable via Ledger.seen / Ledger.add.
  * Never prints the token (only c.fingerprint()).
  * Slim every surfaced read.
  * 422 assignee -> surface "needs owner"; 429 -> client backoff; 503 -> soft-skip;
    403 -> stop with explanation.

THE TRAP (references/units.md): /ai/suggest-estimation returns story_points only.
Issues store estimated_hours. You MUST convert via points_hours.json and FLAG the
result for human review. Never treat AI points as hours.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

# ── shared client (path is install-location independent) ──
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "projekt" / "scripts" / "lib"))
from projekt_api import Client, Ledger, slim, eprint  # noqa: E402

POINTS_HOURS = pathlib.Path(__file__).resolve().parents[2] / "projekt" / "assets" / "points_hours.json"

AI_LABEL = "ai-estimated"
AI_RATE_PER_MIN = 10          # `ai` bucket ceiling
AI_MIN_INTERVAL = 60.0 / AI_RATE_PER_MIN  # ≥6s between AI calls -> <=10/min


# ─────────────────────────── helpers ───────────────────────────

def load_points_map() -> tuple[dict[int, float], float]:
    """Return ({points:int -> hours:float}, default_hours)."""
    try:
        cfg = json.loads(POINTS_HOURS.read_text())
    except Exception as e:  # pragma: no cover - config must ship with the skill
        raise SystemExit("✗ Cannot read %s: %s" % (POINTS_HOURS, e))
    raw = cfg.get("map", {}) or {}
    pmap: dict[int, float] = {}
    for k, v in raw.items():
        try:
            pmap[int(k)] = float(v)
        except (TypeError, ValueError):
            continue
    default = float(cfg.get("default_hours", 8))
    return pmap, default


def points_to_hours(points, pmap: dict[int, float], default: float) -> float:
    """Map story_points -> hours. Exact hit, else nearest defined point, else default."""
    if points is None:
        return default
    try:
        p = int(round(float(points)))
    except (TypeError, ValueError):
        return default
    if p in pmap:
        return pmap[p]
    if not pmap:
        return default
    nearest = min(pmap.keys(), key=lambda k: (abs(k - p), k))
    return pmap[nearest]


def resolve_project(c: Client, ctx: dict, project: str) -> dict:
    """Resolve a project from cached context by id / key / name. Never re-queries."""
    projects = ctx.get("projects") or []
    if not projects:
        raise SystemExit("✗ No projects in .projekt-run/context.json — run context_sync.sh first.")
    needle = (project or "").strip().lower()
    for p in projects:
        if str(p.get("id", "")).lower() == needle:
            return p
    for p in projects:
        if str(p.get("key", "")).lower() == needle:
            return p
    for p in projects:
        if str(p.get("name", "")).lower() == needle:
            return p
    keys = ", ".join("%s/%s" % (p.get("key") or "—", p.get("name") or "?") for p in projects[:20])
    raise SystemExit("✗ Project '%s' not found in context. Known: %s" % (project, keys))


def member_name(ctx: dict, user_id) -> str:
    if not user_id:
        return "(unassigned)"
    for m in ctx.get("members") or []:
        if str(m.get("user_id")) == str(user_id):
            return m.get("name") or m.get("email") or str(user_id)
    return str(user_id)


def fetch_issues(c: Client, pid: str, sprint: str | None) -> list[dict]:
    path = "/issues?project_id=%s&limit=5000" % pid
    if sprint:
        path += "&sprint_id=%s" % sprint
    data = c.get_json(path)
    rows = data if isinstance(data, list) else (
        data.get("data") or data.get("issues") or [] if isinstance(data, dict) else []
    )
    return [r for r in rows if isinstance(r, dict)]


def issue_hours(it: dict) -> float | None:
    v = it.get("estimated_hours")
    if v in (None, "", 0, "0"):
        return None if v in (None, "") else 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sibling_median(issue: dict, pool: list[dict]) -> float | None:
    """Median estimated_hours of siblings (same sprint + type) with a real estimate."""
    sid = issue.get("sprint_id")
    typ = issue.get("type")
    vals: list[float] = []
    for s in pool:
        if s.get("id") == issue.get("id"):
            continue
        if s.get("sprint_id") != sid or s.get("type") != typ:
            continue
        h = issue_hours(s)
        if h and h > 0:
            vals.append(h)
    if not vals:  # widen: any sibling in the project with an estimate
        for s in pool:
            if s.get("id") == issue.get("id"):
                continue
            h = issue_hours(s)
            if h and h > 0:
                vals.append(h)
    if not vals:
        return None
    return round(statistics.median(vals), 2)


def ai_suggest_points(c: Client, issue: dict) -> tuple[str, object]:
    """Return (kind, value). kind in {points, quota, error}.

    POST /ai/suggest-estimation -> {story_points}. 503 = daily AI quota spent.
    """
    body = {
        "issue_id": issue.get("id"),
        "title": issue.get("title"),
        "description": issue.get("description") or "",
    }
    st, data = c.request("POST", "/ai/suggest-estimation", body)
    if st == 503:
        return "quota", None
    if not (200 <= st < 300):
        return "error", "%s %s" % (st, _msg(data))
    pts = None
    if isinstance(data, dict):
        pts = data.get("story_points")
        if pts is None and isinstance(data.get("data"), dict):
            pts = data["data"].get("story_points")
    return ("points", pts) if pts is not None else ("error", "no story_points in response")


def _msg(data) -> str:
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or data)
    return str(data)


def fmt_table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(str(cell)))
    line = lambda cells: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells))
    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)


# ─────────────────────────── estimate ───────────────────────────

def cmd_estimate(c: Client, ctx: dict, args) -> int:
    proj = resolve_project(c, ctx, args.project)
    pid = proj["id"]
    pmap, default_hours = load_points_map()

    issues = fetch_issues(c, pid, args.sprint)
    # default: only truly-missing (None). --include-zero also re-estimates 0h entries.
    if args.include_zero:
        missing = [it for it in issues if issue_hours(it) in (None, 0.0)]
    else:
        missing = [it for it in issues if issue_hours(it) is None]

    eprint("• org=%s token=%s project=%s/%s issues=%d missing_estimate=%d"
           % (c.org, c.fingerprint(), proj.get("key") or "—", proj.get("name"), len(issues), len(missing)))

    if not missing:
        print("Nothing to estimate — every issue already has estimated_hours.")
        return 0

    DEFAULT_BATCH = 25
    if args.limit:
        missing = missing[: args.limit]
    elif not args.all and len(missing) > DEFAULT_BATCH:
        eprint("  ⚠ %d issues missing estimates; doing the first %d this run (AI is rate-limited "
               "+ daily-capped). Use --limit N or --all to change." % (len(missing), DEFAULT_BATCH))
        missing = missing[:DEFAULT_BATCH]

    led = Ledger()
    proposals: list[dict] = []
    ai_calls = 0
    quota_hit = False
    last_ai = 0.0

    for it in missing:
        iid = it.get("id")
        key = it.get("key") or iid
        source = "ai"
        points = None
        hours = None

        if quota_hit or args.no_ai:
            source = "median"
        else:
            # throttle the `ai` bucket to <=10/min
            gap = AI_MIN_INTERVAL - (time.monotonic() - last_ai)
            if gap > 0:
                time.sleep(gap)
            kind, val = ai_suggest_points(c, it)
            last_ai = time.monotonic()
            ai_calls += 1
            if kind == "points":
                points = val
                hours = points_to_hours(points, pmap, default_hours)
            elif kind == "quota":
                eprint("  503 AI quota spent — switching remaining issues to median-of-siblings.")
                quota_hit = True
                source = "median"
            else:
                eprint("  ! %s on %s — falling back to median." % (val, key))
                source = "median"

        if hours is None:  # median fallback (quota / error / --no-ai)
            med = sibling_median(it, issues)
            if med is None:
                hours = default_hours
                source = "default"
            else:
                hours = med
                source = "median"

        proposals.append({
            "id": iid, "key": key, "title": (it.get("title") or "")[:48],
            "points": points if points is not None else "—",
            "hours": hours, "source": source,
            "assignee": member_name(ctx, it.get("assignee_id")),
        })

    # ── dry-run table ──
    by_src: dict[str, int] = {}
    for p in proposals:
        by_src[p["source"]] = by_src.get(p["source"], 0) + 1
    total_h = round(sum(p["hours"] for p in proposals), 2)

    table = fmt_table(
        [[p["key"], str(p["points"]), "%.2f" % p["hours"], p["source"], p["title"]] for p in proposals],
        ["issue", "points", "hours", "source", "title"],
    )
    print("\nProposed estimates (project %s/%s)%s:"
          % (proj.get("key") or "—", proj.get("name"), "" if args.apply else "  [DRY-RUN]"))
    print(table)
    print("\nΣ %d issues · %.2f h · sources=%s · ai_calls=%d"
          % (len(proposals), total_h, by_src, ai_calls))

    flagged = [p for p in proposals if p["source"] in ("ai", "median", "default")]
    print("⚑ %d values are AI/heuristic-derived → flagged '%s' for human review."
          % (len(flagged), AI_LABEL))

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to PUT estimated_hours and add the '%s' label." % AI_LABEL)
        return 0

    # ── apply ──
    print("\nApplying %d estimates…" % len(proposals))
    written = skipped = errors = 0
    for p in proposals:
        iid = p["id"]
        if led.seen("estimate", iid):
            skipped += 1
            led.add("estimate", "estimate", iid, "ok", ref="dedupe")
            continue
        st, data = c.request("PUT", "/issues/%s" % iid, {"estimated_hours": p["hours"]})
        if not (200 <= st < 300):
            errors += 1
            if st == 403:
                eprint("  403 cross-org on %s — stopping (PAT bound to one org)." % p["key"])
                led.add("estimate", "estimate", iid, "error", ref="403")
                break
            eprint("  ! PUT /issues/%s → %s: %s" % (p["key"], st, _msg(data)))
            led.add("estimate", "estimate", iid, "error", ref=str(st))
            continue
        written += 1
        led.add("estimate", "estimate", iid, "updated", ref="%sh/%s" % (p["hours"], p["source"]))

        # best-effort flag (don't fail the run if labeling errors)
        if not led.seen("label", iid):
            lst, _ = c.request("POST", "/issues/bulk",
                               {"issue_ids": [iid], "action": "add_label", "value": AI_LABEL})
            if 200 <= lst < 300:
                led.add("estimate", "label", iid, "ok", ref=AI_LABEL)
            else:
                eprint("  (note) couldn't add '%s' to %s (HTTP %s) — estimate saved anyway."
                       % (AI_LABEL, p["key"], lst))
                led.add("estimate", "label", iid, "skip", ref=str(lst))

    print("✓ updated=%d skipped(dedupe)=%d errors=%d" % (written, skipped, errors))
    print("  ledger=%s summary=%s" % (led.path, led.summary()))
    return 0 if errors == 0 else 1


# ─────────────────────────── rollup ───────────────────────────

def parse_time_summary(data) -> float:
    """Return logged hours from /time-summary ({total_minutes,...})."""
    if not isinstance(data, dict):
        return 0.0
    if data.get("total_minutes") is not None:
        try:
            return float(data["total_minutes"]) / 60.0
        except (TypeError, ValueError):
            return 0.0
    if data.get("total_hours") is not None:
        try:
            return float(data["total_hours"])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def workload_logged_by_user(data) -> dict[str, float]:
    """Best-effort: pull logged/spent hours per user_id from /workload."""
    rows = data if isinstance(data, list) else (
        data.get("data") or data.get("workload") or data.get("members") or []
        if isinstance(data, dict) else []
    )
    out: dict[str, float] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        uid = str(r.get("user_id") or r.get("id") or "")
        if not uid:
            continue
        # /workload members carry `hours_logged`; tolerate older aliases too.
        hrs = r.get("hours_logged")
        if hrs is None:
            hrs = r.get("logged_hours")
        if hrs is None and r.get("logged_minutes") is not None:
            try:
                hrs = float(r["logged_minutes"]) / 60.0
            except (TypeError, ValueError):
                hrs = None
        if hrs is None:
            hrs = r.get("hours")
        try:
            out[uid] = out.get(uid, 0.0) + float(hrs)
        except (TypeError, ValueError):
            continue
    return out


def cmd_rollup(c: Client, ctx: dict, args) -> int:
    proj = resolve_project(c, ctx, args.project)
    pid = proj["id"]
    issues = fetch_issues(c, pid, args.sprint)

    eprint("• org=%s token=%s project=%s/%s issues=%d (deterministic math — no model tokens)"
           % (c.org, c.fingerprint(), proj.get("key") or "—", proj.get("name"), len(issues)))

    # planned per assignee (sum estimated_hours)
    planned: dict[str, float] = {}
    for it in issues:
        uid = str(it.get("assignee_id") or "")
        h = issue_hours(it) or 0.0
        planned[uid] = planned.get(uid, 0.0) + h

    # logged per assignee: prefer /workload aggregate; fall back to per-issue /time-summary
    logged: dict[str, float] = {}
    wl = None
    qs = ""
    if args.date_from:
        qs += ("&" if qs else "?") + "date_from=%s" % args.date_from
    if args.date_to:
        qs += ("&" if qs else "?") + "date_to=%s" % args.date_to
    try:
        wl = c.get_json("/workload" + qs)
        logged = workload_logged_by_user(wl)
    except SystemExit as e:
        eprint("  (note) /workload unavailable (%s) — summing per-issue time-summary." % e)

    logged_source = "/workload (org-wide, current window)"
    DEEP_CAP = 300
    if getattr(args, "deep", False):
        # Project-accurate but expensive: one /time-summary per issue. Bounded so a
        # large project can't fan out hundreds of calls — scope with --sprint instead.
        if len(issues) > DEEP_CAP:
            eprint("  ✗ --deep refused: %d issues > cap %d. Scope with --sprint, or drop --deep "
                   "to use the /workload aggregate." % (len(issues), DEEP_CAP))
            return 2
        eprint("  --deep: summing per-issue time-summary for %d issues (project-scoped)…" % len(issues))
        logged = {}
        for n, it in enumerate(issues, 1):
            iid = it.get("id")
            if not iid:
                continue
            st, data = c.request("GET", "/projects/%s/issues/%s/time-summary" % (pid, iid))
            if not (200 <= st < 300):
                continue
            hrs = parse_time_summary(data)
            if hrs <= 0:
                continue
            uid = str(it.get("assignee_id") or "")
            logged[uid] = logged.get(uid, 0.0) + hrs
        logged_source = "per-issue time-summary (project-scoped)"
    elif not logged:
        eprint("  (note) /workload returned no logged hours; showing planned only. "
               "Use --deep (≤%d issues) for project-scoped logged time." % DEEP_CAP)

    users = sorted(set(planned) | set(logged),
                   key=lambda u: -(planned.get(u, 0.0) + logged.get(u, 0.0)))
    rows = []
    tot_p = tot_l = 0.0
    for u in users:
        p = round(planned.get(u, 0.0), 2)
        l = round(logged.get(u, 0.0), 2)
        delta = round(l - p, 2)
        pct = ("%d%%" % round(l / p * 100)) if p > 0 else ("—" if l == 0 else "∞")
        tot_p += p
        tot_l += l
        rows.append([member_name(ctx, u), "%.2f" % p, "%.2f" % l, "%+.2f" % delta, pct])

    delta_t = round(tot_l - tot_p, 2)
    pct_t = ("%d%%" % round(tot_l / tot_p * 100)) if tot_p > 0 else "—"
    rows.append(["—— TOTAL ——", "%.2f" % tot_p, "%.2f" % tot_l, "%+.2f" % delta_t, pct_t])

    print("\nPlan vs actual — %s/%s%s%s"
          % (proj.get("key") or "—", proj.get("name"),
             "  sprint=%s" % args.sprint if args.sprint else "",
             qs.replace("?", "  ").replace("&", "  ") if qs else ""))
    print(fmt_table(rows, ["assignee", "planned_h", "logged_h", "delta_h", "logged/plan"]))
    print("\nSource: planned=Σ estimated_hours (this project) · logged=%s. Math is deterministic."
          % logged_source)
    return 0


# ─────────────────────────── roadmap (optional) ───────────────────────────

def cmd_roadmap(c: Client, ctx: dict, args) -> int:
    proj = resolve_project(c, ctx, args.project)
    pid = proj["id"]
    eprint("• org=%s token=%s project=%s/%s" % (c.org, c.fingerprint(), proj.get("key") or "—", proj.get("name")))

    if not args.apply:
        data = c.get_json("/projects/%s/roadmap" % pid)
        rows = data if isinstance(data, list) else (
            data.get("data") or data.get("items") or [] if isinstance(data, dict) else []
        )
        if not rows:
            print("No roadmap items for %s/%s." % (proj.get("key") or "—", proj.get("name")))
        else:
            tbl = fmt_table(
                [[str(r.get("name") or "?")[:40], str(r.get("item_type") or "—"),
                  str(r.get("start_date") or "—"), str(r.get("end_date") or "—"),
                  str(r.get("progress") if r.get("progress") is not None else "—")]
                 for r in rows if isinstance(r, dict)],
                ["name", "type", "start", "end", "progress"],
            )
            print("Roadmap — %s/%s (%d items):" % (proj.get("key") or "—", proj.get("name"), len(rows)))
            print(tbl)
        if args.name:
            print("\n[DRY-RUN] Would POST /projects/%s/roadmap {name:%r, item_type:%r, start_date:%r, end_date:%r}"
                  % (pid, args.name, args.item_type, args.start_date, args.end_date))
            print("Re-run with --apply to create it.")
        return 0

    if not args.name:
        raise SystemExit("✗ --apply on roadmap needs --name (the milestone/epic name).")
    led = Ledger()
    dkey = "%s|%s" % (pid, args.name)
    if led.seen("roadmap", dkey):
        print("Roadmap item '%s' already created (dedupe). Nothing to do." % args.name)
        return 0
    body = {"name": args.name, "item_type": args.item_type}
    if args.start_date:
        body["start_date"] = args.start_date
    if args.end_date:
        body["end_date"] = args.end_date
    st, data = c.request("POST", "/projects/%s/roadmap" % pid, body)
    if not (200 <= st < 300):
        if st == 403:
            raise SystemExit("✗ 403 cross-org — your PAT is bound to another org.")
        led.add("roadmap", "roadmap", dkey, "error", ref=str(st))
        raise SystemExit("✗ POST roadmap → %s: %s" % (st, _msg(data)))
    led.add("roadmap", "roadmap", dkey, "created", ref=args.item_type)
    rid = data.get("id") if isinstance(data, dict) else None
    print("✓ Created roadmap item '%s' (id=%s, type=%s)." % (args.name, rid, args.item_type))
    return 0


# ─────────────────────────── cli ───────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="estimate_rollup.py",
        description="Projekt estimation (AI points->hours w/ median fallback) + "
                    "deterministic plan-vs-actual roll-up + optional roadmap. "
                    "Dry-run by default; --apply to write.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("estimate", help="Fill missing estimated_hours (AI points->hours, 503->median).")
    e.add_argument("--project", required=True, help="Project id, key or name (resolved from cached context).")
    e.add_argument("--sprint", help="Restrict to a sprint_id.")
    e.add_argument("--limit", type=int, help="Cap how many issues to estimate this run.")
    e.add_argument("--all", action="store_true",
                   help="Estimate ALL missing (override the default 25-issue safety cap; heavy on the AI quota).")
    e.add_argument("--no-ai", action="store_true",
                   help="Skip /ai/suggest-estimation entirely; use median-of-siblings only.")
    e.add_argument("--include-zero", action="store_true",
                   help="Also (re)estimate issues whose estimated_hours is 0.")
    e.add_argument("--apply", action="store_true", help="Execute PUTs (default = dry-run).")

    r = sub.add_parser("rollup", help="Plan vs actual hours per assignee (deterministic).")
    r.add_argument("--project", required=True, help="Project id, key or name (resolved from cached context).")
    r.add_argument("--sprint", help="Restrict to a sprint_id.")
    r.add_argument("--date-from", dest="date_from", help="Workload window start YYYY-MM-DD.")
    r.add_argument("--date-to", dest="date_to", help="Workload window end YYYY-MM-DD.")
    r.add_argument("--deep", action="store_true",
                   help="Project-scoped logged hours via one /time-summary per issue "
                        "(accurate but expensive; capped at 300 issues — scope with --sprint).")

    rm = sub.add_parser("roadmap", help="List roadmap items, or --apply --name to create one.")
    rm.add_argument("--project", required=True, help="Project id, key or name (resolved from cached context).")
    rm.add_argument("--name", help="Item name (required with --apply).")
    rm.add_argument("--item-type", dest="item_type", default="milestone",
                    help="milestone|epic|phase (default milestone).")
    rm.add_argument("--start-date", dest="start_date", help="YYYY-MM-DD.")
    rm.add_argument("--end-date", dest="end_date", help="YYYY-MM-DD.")
    rm.add_argument("--apply", action="store_true", help="Create the roadmap item (default = dry-run/list).")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    c = Client()
    ctx = c.context()
    if not ctx.get("projects"):
        eprint("⚠ No cached context — run the projekt skill's context_sync.sh first.")
    if args.cmd == "estimate":
        return cmd_estimate(c, ctx, args)
    if args.cmd == "rollup":
        return cmd_rollup(c, ctx, args)
    if args.cmd == "roadmap":
        return cmd_roadmap(c, ctx, args)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        eprint("\n✗ Interrupted. Re-run to resume (ledger dedupes).")
        raise SystemExit(130)
