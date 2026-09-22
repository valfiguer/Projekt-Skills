#!/usr/bin/env python3
"""cargas.py — deterministic per-member workload & capacity report (read-only).

Three server-side aggregates, merged on user_id. The script does ALL the
arithmetic, so the model spends no tokens on numbers and writes nothing.

    GET /organizations/{org}/workforce/capacity?week_start=YYYY-MM-DD   (REQUIRED)
        → {week_start, week_end, rows:[{user_id,name,employee_id,expected_hours,
           expected_source,holiday_hours,absence_hours,net_expected_hours,logged_hours}]}
        `week_start` is ANY date inside the wanted week; the server normalizes it to
        that week's first day using the organization's own `week_start_day`, which is
        not necessarily Monday. Omitting it is a 422, not a default.
    GET /organizations/{org}/time-entries/summary?from&to&group_by=user
        → {total_minutes, billable_minutes, entries_count, groups:[{user_id,total_minutes,…}]}
    GET /organizations/{org}/dashboard/stats
        → {..., workload:[{user_id,name,assigned,done}], ...}

THE RANGE TRAP — read before labelling any output. The three sources do NOT
cover the same period, and two of them cannot be made to:
  · /workforce/capacity covers exactly ONE WEEK — the one containing `week_start`,
    snapped to the org's own first day of the week. It cannot cover a month.
  · /dashboard/stats takes NO parameters at all: its `assigned`/`done` counts are
    ALL-HISTORY. Printing them under a "September" heading states something the
    data does not say.
  · Only /time-entries/summary honours an arbitrary --from/--to.
This script therefore labels every column with the period it really covers, and
marks the all-history ones. When --from/--to span more than a week, the capacity
column still describes the week that --from falls in, and the header says so.

Utilization = logged hours in the window ÷ net expected hours for the capacity
week (expected minus holidays and absences). Comparing a month of logged hours
against one week of capacity is meaningless, so the header flags that too.

stdlib only · Python 3.10+ · GET-only, no --apply, always safe to re-run.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pr" / "scripts" / "lib"))
from projekt_api import Client, eprint  # noqa: E402

DEFAULT_OVER = 100.0
DEFAULT_UNDER = 50.0


def iso_week(today: dt.date | None = None) -> tuple[str, str]:
    d = today or dt.date.today()
    monday = d - dt.timedelta(days=d.weekday())
    return monday.isoformat(), (monday + dt.timedelta(days=6)).isoformat()


def _rows(data, *keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
    return []


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fetch(c: Client, date_from: str, date_to: str) -> dict:
    # week_start is REQUIRED (422 without it) and may be any date inside the week.
    cap = c.get_json("/organizations/%s/workforce/capacity?week_start=%s" % (c.org, date_from))
    summ = c.get_json("/organizations/%s/time-entries/summary?from=%s&to=%s&group_by=user"
                      % (c.org, date_from, date_to))
    try:
        stats = c.get_json("/organizations/%s/dashboard/stats" % c.org)
    except SystemExit as e:  # counts are a nice-to-have; capacity is the report
        eprint("  ! dashboard/stats unavailable (%s) — assigned/done columns will be blank." % e)
        stats = {}
    return {"capacity": cap, "summary": summ, "stats": stats}


def merge(payload: dict, names: dict[str, str]) -> tuple[list[dict], dict]:
    cap = payload["capacity"] if isinstance(payload["capacity"], dict) else {}
    rows = {}
    for r in _rows(cap, "rows", "data", "members"):
        uid = r.get("user_id")
        if not uid:
            continue
        rows[uid] = {
            "user_id": uid,
            "name": r.get("name") or names.get(uid) or uid,
            "expected": _f(r.get("expected_hours")),
            "net_expected": _f(r.get("net_expected_hours"), _f(r.get("expected_hours"))),
            "holiday": _f(r.get("holiday_hours")),
            "absence": _f(r.get("absence_hours")),
            "logged_week": _f(r.get("logged_hours")),
            "source": r.get("expected_source") or "—",
            "logged_window": 0.0, "billable_window": 0.0,
            "assigned": None, "done": None,
        }

    for g in _rows(payload["summary"], "groups", "data"):
        uid = g.get("user_id")
        if not uid:
            continue
        row = rows.setdefault(uid, {"user_id": uid, "name": names.get(uid) or uid,
                                    "expected": 0.0, "net_expected": 0.0, "holiday": 0.0,
                                    "absence": 0.0, "logged_week": 0.0, "source": "—",
                                    "logged_window": 0.0, "billable_window": 0.0,
                                    "assigned": None, "done": None})
        row["logged_window"] = _f(g.get("total_minutes")) / 60.0
        row["billable_window"] = _f(g.get("billable_minutes")) / 60.0

    for w in _rows(payload["stats"].get("workload") if isinstance(payload["stats"], dict) else [], "workload"):
        uid = w.get("user_id")
        if uid and uid in rows:
            rows[uid]["assigned"] = w.get("assigned")
            rows[uid]["done"] = w.get("done")
        elif uid:
            rows[uid] = {"user_id": uid, "name": w.get("name") or names.get(uid) or uid,
                         "expected": 0.0, "net_expected": 0.0, "holiday": 0.0, "absence": 0.0,
                         "logged_week": 0.0, "source": "—", "logged_window": 0.0,
                         "billable_window": 0.0, "assigned": w.get("assigned"), "done": w.get("done")}

    for r in rows.values():
        base = r["net_expected"]
        r["utilization"] = (100.0 * r["logged_window"] / base) if base > 0 else None
    return sorted(rows.values(), key=lambda r: (-(r["utilization"] or -1), r["name"])), cap


def flag(u: float | None, over: float, under: float) -> str:
    if u is None:
        return "— n/a"
    if u > over:
        return "⚠️ OVER"
    if u < under:
        return "↓ under"
    return "ok"


def render_markdown(rows, cap, args, org) -> str:
    wk = "%s → %s" % (cap.get("week_start") or "?", cap.get("week_end") or "?")
    out = [
        "# Workload & capacity — org %s" % org,
        "",
        "- **Capacity week** (the week `--from` falls in, snapped to this org's first "
        "day of the week): `%s`" % wk,
        "- **Logged-hours window** (`--from`/`--to`): `%s → %s`" % (args.date_from, args.date_to),
        "- **Assigned / Done**: all-history counts from `dashboard/stats` — that endpoint takes no",
        "  date range, so these two columns are NOT scoped to the window above.",
        "- Thresholds: over `%.0f%%` (%s) · under `%.0f%%`" % (args.over, args.over_source, args.under),
        "",
        "| Member | Expected | Net exp. | Logged (window) | Billable | Util. % | Assigned* | Done* | Flag |",
        "|---|--:|--:|--:|--:|--:|--:|--:|---|",
    ]
    for r in rows:
        u = r["utilization"]
        out.append("| %s | %.1f | %.1f | %.1f | %.1f | %s | %s | %s | %s |" % (
            r["name"], r["expected"], r["net_expected"], r["logged_window"], r["billable_window"],
            ("%.0f%%" % u) if u is not None else "—",
            "—" if r["assigned"] is None else r["assigned"],
            "—" if r["done"] is None else r["done"],
            flag(u, args.over, args.under)))
    span_note = ""
    try:
        d0 = dt.date.fromisoformat(args.date_from); d1 = dt.date.fromisoformat(args.date_to)
        if (d1 - d0).days > 7:
            span_note = ("\n> **The two spans differ.** Logged hours cover %d days; capacity covers "
                         "the single week `%s`. Utilization below compares them anyway, so read it "
                         "as a ratio, not a percentage of that week." % ((d1 - d0).days + 1, wk))
    except ValueError:
        pass
    if span_note:
        out.insert(len(out) - 2, span_note)
    tot_log = sum(r["logged_window"] for r in rows)
    tot_net = sum(r["net_expected"] for r in rows)
    out += ["", "**Team:** %.1f h logged in the window · %.1f h net expected for the capacity week"
            " · %s" % (tot_log, tot_net,
                       ("%.0f%% utilization" % (100.0 * tot_log / tot_net)) if tot_net > 0 else "no capacity set"),
            "", "`*` all-history column — see the note above."]
    return "\n".join(out)


def main() -> int:
    df, dt_ = iso_week()
    ap = argparse.ArgumentParser(
        description="Deterministic workload & capacity report (read-only; no --apply exists).")
    ap.add_argument("--from", dest="date_from", default=df, help="YYYY-MM-DD (logged-hours window)")
    ap.add_argument("--to", dest="date_to", default=dt_, help="YYYY-MM-DD (logged-hours window)")
    ap.add_argument("--over", type=float, default=None, help="over-allocation threshold %% (default 100)")
    ap.add_argument("--under", type=float, default=DEFAULT_UNDER, help="under-allocation threshold %%")
    ap.add_argument("--csv", action="store_true", help="CSV instead of Markdown")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON")
    args = ap.parse_args()

    if args.date_from > args.date_to:
        raise SystemExit("✗ --from (%s) is after --to (%s)." % (args.date_from, args.date_to))
    args.over_source = "flag" if args.over is not None else "default"
    if args.over is None:
        args.over = DEFAULT_OVER

    c = Client()
    if not c.org:
        raise SystemExit("✗ No org in context. Run ../pr/scripts/auth_check.sh + context_sync.sh first.")
    names = {m.get("user_id"): m.get("name") for m in c.context().get("members", [])}
    rows, cap = merge(fetch(c, args.date_from, args.date_to), names)
    if not rows:
        eprint("No members with capacity or logged time in this org/window.")
        return 1

    if args.json:
        print(json.dumps({"capacity_week": {"start": cap.get("week_start"), "end": cap.get("week_end")},
                          "logged_window": {"from": args.date_from, "to": args.date_to},
                          "counts_are_all_history": True, "rows": rows}, indent=2))
    elif args.csv:
        w = csv.writer(sys.stdout)
        w.writerow(["user_id", "name", "expected_h", "net_expected_h", "logged_window_h",
                    "billable_window_h", "utilization_pct", "assigned_all_time", "done_all_time", "flag"])
        for r in rows:
            w.writerow([r["user_id"], r["name"], "%.2f" % r["expected"], "%.2f" % r["net_expected"],
                        "%.2f" % r["logged_window"], "%.2f" % r["billable_window"],
                        "" if r["utilization"] is None else "%.1f" % r["utilization"],
                        r["assigned"] if r["assigned"] is not None else "",
                        r["done"] if r["done"] is not None else "",
                        flag(r["utilization"], args.over, args.under)])
    else:
        print(render_markdown(rows, cap, args, c.org))
    return 0


if __name__ == "__main__":
    sys.exit(main())
