#!/usr/bin/env python3
"""tiempo.py — batch time logging, timers and roll-ups for Projekt Republic tasks.

Modes (subcommands):
  log     Batch-log time entries from a CSV/JSON sheet of
          {issue, date, minutes, note?} rows.
  timer   Start / stop / show the caller's running timer.
  summary Roll-up totals via the server's own aggregate (server math).

DRY-RUN BY DEFAULT for every write. `log` and `timer` print a plan and write
nothing until you pass --apply. `summary` is read-only.

Endpoints (/api/v1, see ../references/endpoints.md → "Time tracking").
Time entries are ORG-scoped; the task is a field in the body, not in the path:
  POST /organizations/{org}/time-entries          {minutes*, entry_date*, task_id, project_id, description, is_billable}
  POST /organizations/{org}/time-entries/start    {project_id, task_id, description, is_billable}
  GET  /organizations/{org}/time-entries/active
  POST /organizations/{org}/time-entries/{id}/stop
  GET  /organizations/{org}/time-entries/summary?project_id&user_id&from&to&group_by

Task resolution: a row's `issue` may be a UUID id OR a task reference (PRJ-123).
A reference is split into project key + number and resolved with
GET .../projects/{pid}/tasks/by-number/{n} using the project ids cached in
context.json. Resolutions are memoised: each unique task is queried at most once.

Idempotency: each posted entry is deduped on (task_id, date, note) via the
shared Ledger; re-runs create 0. There is ONE running timer per user: `start`
with one already running is reported as a no-op, and `stop` reads
/time-entries/active to find the entry id.

stdlib only · Python 3.10+ · never prints the token (fingerprint only).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import pathlib

# ── shared client (path is install-location independent) ──
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from projekt_api import Client, Ledger, slim, eprint  # noqa: E402

PHASE = "time"
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ───────────────────────── helpers ─────────────────────────
def _is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s.strip()))


def _today() -> dt.date:
    return dt.datetime.now().date()


def _parse_date(raw: str) -> dt.date | None:
    raw = (raw or "").strip()
    if not _DATE_RE.match(raw):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_minutes(raw) -> int | None:
    """Accept int-like minutes. Returns None if unparseable (caller flags it)."""
    try:
        # tolerate "30", "30.0", 30, 30.0 — but reject fractions that don't round clean
        f = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if f != int(f):
        # round to nearest minute, matching the server's minimum-1-minute rule
        f = round(f)
    return int(f)


def _dedupe_key(issue_id: str, date: str, note: str) -> str:
    return "%s|%s|%s" % (issue_id, date, (note or "").strip())


def _truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


# ───────────────────────── row loading ─────────────────────────
def load_rows(path: pathlib.Path) -> list[dict]:
    """Read CSV or JSON. Normalize to {issue,date,minutes,note} dicts."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json" or (suffix not in (".csv", ".tsv") and text.lstrip()[:1] in "[{"):
        data = json.loads(text)
        if isinstance(data, dict):
            for k in ("rows", "data", "entries"):
                if isinstance(data.get(k), list):
                    data = data[k]
                    break
        if not isinstance(data, list):
            raise SystemExit("✗ JSON must be a list of row objects (or {rows:[…]}).")
        raw_rows = data
    else:
        delim = "\t" if suffix == ".tsv" else ","
        raw_rows = list(csv.DictReader(text.splitlines(), delimiter=delim))

    out: list[dict] = []
    for r in raw_rows:
        if not isinstance(r, dict):
            raise SystemExit("✗ Each row must be an object with issue/date/minutes.")
        out.append({
            "issue": str(r.get("issue") or r.get("issue_id") or r.get("key") or "").strip(),
            "date": str(r.get("date") or "").strip(),
            "minutes": r.get("minutes", r.get("duration_minutes", r.get("mins"))),
            "note": str(r.get("note") or r.get("description") or r.get("comment") or "").strip(),
        })
    return out


# ───────────────────────── issue resolution ─────────────────────────
class Resolver:
    """Resolve a task ref (UUID or PRJ-123 reference) → (task_id, project_id), memoised."""

    def __init__(self, client: Client):
        self.c = client
        self._cache: dict[str, tuple[str, str] | None] = {}
        ctx = client.context()
        self._projects = [p for p in ctx.get("projects", []) if p.get("id")]
        # key (upper) → project id, for splitting a PRJ-123 reference
        self._by_key = {str(p.get("key", "")).upper(): p["id"] for p in self._projects if p.get("key")}

    def resolve(self, ref: str) -> tuple[str, str] | None:
        ref = (ref or "").strip()
        if not ref:
            return None
        if ref in self._cache:
            return self._cache[ref]
        result = self._resolve_uuid(ref) if _is_uuid(ref) else self._resolve_reference(ref)
        self._cache[ref] = result
        return result

    def _candidate_projects(self) -> list[str]:
        """PAT's own project first (a project-scoped PAT 403s on siblings), then the rest."""
        ids = [self.c.project] if self.c.project else []
        ids += [p["id"] for p in self._projects if p["id"] not in ids]
        return ids

    def _get(self, path: str, label: str):
        try:
            return self.c.request("GET", path)
        except SystemExit as e:  # network error after retries — don't kill the batch
            eprint("  ! lookup failed for %s: %s" % (label, e))
            return None, None

    def _resolve_uuid(self, tid: str) -> tuple[str, str] | None:
        """A task id alone does not say which project it is in — probe the cached ones."""
        for pid in self._candidate_projects():
            st, data = self._get("/organizations/%s/projects/%s/tasks/%s" % (self.c.org, pid, tid), tid)
            if st is None or st in (403, 404):
                continue
            if 200 <= st < 300 and isinstance(data, dict) and data.get("id"):
                return (tid, data.get("project_id") or pid)
            eprint("  ! GET task %s in project %s → %s" % (tid, pid, st))
        return None

    def _resolve_reference(self, ref: str) -> tuple[str, str] | None:
        """PRJ-123 → project key + number → GET .../tasks/by-number/{n}."""
        key, _, num = ref.rpartition("-")
        if not key or not num.isdigit():
            eprint("  ! %r is neither a UUID nor a PRJ-123 reference" % ref)
            return None
        pid = self._by_key.get(key.upper())
        if not pid:
            known = ", ".join(sorted(self._by_key)) or "(context.json has no projects — run context_sync.sh)"
            eprint("  ! unknown project key %r in %r. Known: %s" % (key, ref, known))
            return None
        st, data = self._get(
            "/organizations/%s/projects/%s/tasks/by-number/%s" % (self.c.org, pid, num), ref)
        if st is None or st == 404:
            return None
        if st == 403:
            raise SystemExit("\u2717 403 on %s \u2014 the PAT cannot read project %s. "
                             "Switch org/token (references/errores.md)." % (ref, key))
        if not (200 <= st < 300) or not isinstance(data, dict):
            eprint("  ! GET %s \u2192 %s" % (ref, st))
            return None
        tid = data.get("id")
        return (tid, data.get("project_id") or pid) if tid else None


# ───────────────────────── log mode ─────────────────────────
def cmd_log(args, c: Client) -> int:
    rows = load_rows(pathlib.Path(args.sheet))
    if not rows:
        eprint("✗ No rows found in %s" % args.sheet)
        return 1

    led = Ledger()
    resolver = Resolver(c)
    today = _today()

    plan: list[dict] = []   # rows we'd post (action=create)
    skips: list[dict] = []  # rows blocked, deduped, or unresolved
    batch_keys: set[str] = set()  # in-sheet dedupe (Ledger.seen only sees committed lines)

    for i, r in enumerate(rows, 1):
        issue_ref, date_raw, note = r["issue"], r["date"], r["note"]
        minutes = _parse_minutes(r["minutes"])
        d = _parse_date(date_raw)

        # ── validation (collect reasons, never silently drop) ──
        if not issue_ref:
            skips.append({"row": i, "issue": "—", "reason": "missing issue ref"}); continue
        if minutes is None:
            skips.append({"row": i, "issue": issue_ref, "reason": "minutes not a number"}); continue
        if minutes <= 0:
            skips.append({"row": i, "issue": issue_ref, "reason": "minutes<=0 (%s)" % minutes}); continue
        if d is None:
            skips.append({"row": i, "issue": issue_ref, "reason": "bad date '%s' (want YYYY-MM-DD)" % date_raw}); continue
        if d > today:
            skips.append({"row": i, "issue": issue_ref, "reason": "future date %s" % d}); continue

        resolved = resolver.resolve(issue_ref)
        if not resolved:
            skips.append({"row": i, "issue": issue_ref, "reason": "issue not found in this org"}); continue
        iid, pid = resolved

        dk = _dedupe_key(iid, str(d), note)
        if led.seen("time", dk):
            skips.append({"row": i, "issue": issue_ref, "reason": "already logged (dedupe)"}); continue
        if dk in batch_keys:
            skips.append({"row": i, "issue": issue_ref, "reason": "duplicate row in sheet (dedupe)"}); continue
        batch_keys.add(dk)

        plan.append({
            "row": i, "issue": issue_ref, "issue_id": iid, "project_id": pid,
            "date": str(d), "minutes": minutes, "note": note, "dk": dk,
        })

    _print_log_plan(plan, skips, c, applying=args.apply)

    if not args.apply:
        eprint("\nDry-run only. Re-run with --apply to post %d entr%s."
               % (len(plan), "y" if len(plan) == 1 else "ies"))
        return 0
    if not plan:
        eprint("\nNothing to post.")
        return 0

    posted = failed = 0
    for p in plan:
        body = {"minutes": p["minutes"], "entry_date": p["date"],
                "task_id": p["issue_id"], "project_id": p["project_id"]}
        if p["note"]:
            body["description"] = p["note"]
        if args.billable is not None:
            body["is_billable"] = args.billable
        st, data = c.request("POST", "/organizations/%s/time-entries" % c.org, body)
        if st == 201 or 200 <= st < 300:
            ref = data.get("id") if isinstance(data, dict) else None
            led.add(PHASE, "time", p["dk"], "created", ref=ref)
            posted += 1
            print("  ✓ %-12s %s  %dm" % (p["issue"], p["date"], p["minutes"]))
        elif st == 400:
            led.add(PHASE, "time", p["dk"], "skipped", ref="400 duration<=0")
            failed += 1
            eprint("  ✗ %-12s rejected (400: minutes<=0)" % p["issue"])
        elif st == 422:
            led.add(PHASE, "time", p["dk"], "skipped", ref="422 validation")
            failed += 1
            eprint("  ✗ %-12s 422 validation: %s" % (p["issue"], _msg(data)))
        elif st == 403:
            eprint("  ✗ %-12s 403 cross-org — stopping." % p["issue"])
            return 2
        else:
            led.add(PHASE, "time", p["dk"], "error", ref=str(st))
            failed += 1
            eprint("  ✗ %-12s HTTP %s: %s" % (p["issue"], st, _msg(data)))

    print("\n%s  posted=%d  failed=%d  skipped=%d  (ledger: %s)"
          % ("done" if not failed else "done with errors", posted, failed, len(skips), led.summary()))
    return 0 if not failed else 1


def _print_log_plan(plan, skips, c: Client, applying: bool) -> None:
    print("Projekt time — batch log   org=%s   token=%s" % (c.org or "?", c.fingerprint()))
    print("Mode: %s\n" % ("APPLY (writing)" if applying else "DRY-RUN (no writes)"))
    if plan:
        print("Will log %d entr%s:" % (len(plan), "y" if len(plan) == 1 else "ies"))
        print("  %-12s %-10s %7s  %-30s %s" % ("ISSUE", "DATE", "MINUTES", "NOTE", "ACTION"))
        print("  " + "-" * 74)
        total = 0
        for p in plan:
            total += p["minutes"]
            print("  %-12s %-10s %7d  %-30s %s"
                  % (_truncate(p["issue"], 12), p["date"], p["minutes"],
                     _truncate(p["note"], 30), "create"))
        print("  " + "-" * 74)
        print("  %-12s %-10s %7d  (%d entries)" % ("TOTAL", "", total, len(plan)))
    else:
        print("Will log 0 entries.")
    if skips:
        print("\nSkipped / blocked (%d) — NOT logged:" % len(skips))
        for s in skips:
            print("  · row %-3s %-12s — %s" % (s["row"], _truncate(s["issue"], 12), s["reason"]))


# ───────────────────────── timer mode ─────────────────────────
def _active_timer(c: Client):
    """GET the caller's running entry, or None. There is at most ONE per user."""
    st, data = c.request("GET", "/organizations/%s/time-entries/active" % c.org)
    if st == 404 or not isinstance(data, dict):
        return None
    if st == 403:
        raise SystemExit("\u2717 403 reading the active timer \u2014 switch org/token (references/errores.md).")
    if not (200 <= st < 300):
        eprint("  ! GET /time-entries/active \u2192 %s" % st)
        return None
    entry = data.get("entry") if isinstance(data.get("entry"), dict) else data
    return entry if entry and entry.get("id") else None


def cmd_timer(args, c: Client) -> int:
    led = Ledger()
    action = args.action  # start | stop | show

    print("Projekt time — timer %s   org=%s   token=%s" % (action, c.org or "?", c.fingerprint()))

    # ── show: read-only ──
    if action == "show":
        entry = _active_timer(c)
        if not entry:
            print("  • no timer running.")
            return 0
        print("  ▸ running since %s on %s (entry %s)"
              % (entry.get("started_at") or entry.get("created_at") or "?",
                 entry.get("task_reference") or entry.get("task_id") or "(no task)", entry.get("id")))
        return 0

    # ── start ──
    if action == "start":
        tid = pid = None
        if args.issue:
            resolved = Resolver(c).resolve(args.issue)
            if not resolved:
                eprint("✗ Task '%s' not found in this org." % args.issue)
                return 1
            tid, pid = resolved
        body = {k: v for k, v in (("task_id", tid), ("project_id", pid),
                                  ("description", args.note)) if v}
        if args.billable is not None:
            body["is_billable"] = args.billable
        print("Task %s  (id=%s)" % (args.issue or "—", tid or "—"))
        print("Mode: %s\n" % ("APPLY (writing)" if args.apply else "DRY-RUN (no writes)"))
        print("  POST /organizations/%s/time-entries/start  body=%s" % (c.org, sorted(body)))
        if not args.apply:
            running = _active_timer(c)
            if running:
                eprint("\nNote: a timer is ALREADY running (entry %s) — one per user. Stop it first."
                       % running.get("id"))
            eprint("\nDry-run. Re-run with --apply to start the timer.")
            return 0
        st, data = c.request("POST", "/organizations/%s/time-entries/start" % c.org, body)
        if 200 <= st < 300:
            eid = data.get("id") if isinstance(data, dict) else None
            led.add(PHASE, "timer-start", tid or "(no task)", "created", ref=eid)
            print("  ✓ timer started (entry=%s)" % eid)
            return 0
        if st == 409:
            led.add(PHASE, "timer-start", tid or "(no task)", "ok", ref="already-running")
            print("  • a timer is already running (409) — no-op: %s" % _msg(data))
            return 0
        if st == 403:
            eprint("  ✗ 403 cross-org — switch org / token (references/errores.md).")
            return 2
        eprint("  ✗ timer start → HTTP %s: %s" % (st, _msg(data)))
        return 1

    # ── stop: the entry id comes from /active, not from the task ──
    entry = _active_timer(c)
    if not entry:
        print("  • no active timer to stop — no-op.")
        return 0
    eid = entry["id"]
    print("  POST /organizations/%s/time-entries/%s/stop" % (c.org, eid))
    print("Mode: %s\n" % ("APPLY (writing)" if args.apply else "DRY-RUN (no writes)"))
    if not args.apply:
        eprint("\nDry-run. Re-run with --apply to stop entry %s." % eid)
        return 0
    st, data = c.request("POST", "/organizations/%s/time-entries/%s/stop" % (c.org, eid), None)
    if 200 <= st < 300:
        mins = (data or {}).get("minutes") if isinstance(data, dict) else None
        led.add(PHASE, "timer-stop", eid, "created", ref=eid)
        print("  ✓ timer stopped → entry %s (%s min)" % (eid, mins if mins is not None else "?"))
        if args.note:
            st2, _ = c.request("PATCH", "/organizations/%s/time-entries/%s" % (c.org, eid),
                               {"description": args.note})
            print("  %s note attached" % ("✓" if 200 <= st2 < 300 else "!"))
        return 0
    if st == 404:
        print("  • entry %s was not running (404) — no-op." % eid)
        return 0
    if st == 403:
        eprint("  ✗ 403 cross-org — switch org / token.")
        return 2
    eprint("  ✗ timer stop → HTTP %s: %s" % (st, _msg(data)))
    return 1


# ───────────────────────── summary mode ─────────────────────────
def cmd_summary(args, c: Client) -> int:
    """Server-side aggregate. Totals come from the API — never summed in-model."""
    qs = []
    pid = None
    if args.issue:  # one task → we still need its project to scope the query
        resolved = Resolver(c).resolve(args.issue)
        if not resolved:
            eprint("✗ Task '%s' not found in this org." % args.issue)
            return 1
        tid, pid = resolved
        return _summary_one_task(c, args, tid, pid)
    if args.project:
        pid = _project_id(c, args.project)
        if not pid:
            return 1
        qs.append("project_id=%s" % pid)
    for flag, key in (("date_from", "from"), ("date_to", "to"), ("user", "user_id")):
        v = getattr(args, flag, None)
        if v:
            qs.append("%s=%s" % (key, v))
    qs.append("group_by=%s" % (args.group_by or "user"))
    data = c.get_json("/organizations/%s/time-entries/summary?%s" % (c.org, "&".join(qs)))
    if not isinstance(data, dict):
        eprint("✗ Unexpected time-entries/summary payload.")
        return 1
    total = data.get("total_minutes", 0) or 0
    print("Time summary — org=%s   %s → %s   group_by=%s"
          % (c.org or "?", data.get("from_date") or "—", data.get("to_date") or "—",
             data.get("group_by") or args.group_by))
    print("  total: %d min (%.2f h)   billable: %d min   entries: %d"
          % (total, total / 60.0, data.get("billable_minutes", 0) or 0,
             data.get("entries_count", 0) or 0))
    names = {m.get("user_id"): m.get("name") for m in c.context().get("members", [])}
    projects = {p.get("id"): p.get("name") or p.get("key") for p in c.context().get("projects", [])}
    groups = data.get("groups") or []
    if groups:
        print("  groups:")
        for g in groups:
            label = names.get(g.get("user_id")) or projects.get(g.get("project_id")) \
                or g.get("user_id") or g.get("project_id") or "?"
            gm = g.get("total_minutes", 0) or 0
            print("    · %-28s %6d min (%6.2f h)  billable=%d  [%d]"
                  % (_truncate(label, 28), gm, gm / 60.0,
                     g.get("billable_minutes", 0) or 0, g.get("entries_count", 0) or 0))
    return 0


def _summary_one_task(c: Client, args, tid: str, pid: str) -> int:
    """No per-task aggregate exists: list the project's entries and filter on task_id.

    The listing is paged server-side; totals are summed over the rows the API
    returned for THIS task only, and the row count is printed so a truncated
    page is visible rather than silently wrong.
    """
    qs = ["project_id=%s" % pid, "limit=200"]
    for flag, key in (("date_from", "from"), ("date_to", "to")):
        v = getattr(args, flag, None)
        if v:
            qs.append("%s=%s" % (key, v))
    rows, offset = [], 0
    while True:
        data = c.get_json("/organizations/%s/time-entries?%s&offset=%d" % (c.org, "&".join(qs), offset))
        page = data if isinstance(data, list) else (data.get("data") or data.get("entries") or [])
        rows += [r for r in page if r.get("task_id") == tid]
        if len(page) < 200:
            break
        offset += 200
        if offset > 5000:
            eprint("  ! stopped paging at 5000 entries — narrow with --date-from/--date-to.")
            break
    total = sum(r.get("minutes", 0) or 0 for r in rows)
    print("Time summary — task %s  (id=%s)   org=%s" % (args.issue, tid, c.org or "?"))
    print("  total: %d min (%.2f h)   entries: %d" % (total, total / 60.0, len(rows)))
    names = {m.get("user_id"): m.get("name") for m in c.context().get("members", [])}
    by_user: dict[str, list[int]] = {}
    for r in rows:
        u = r.get("user_id") or "?"
        acc = by_user.setdefault(u, [0, 0])
        acc[0] += r.get("minutes", 0) or 0
        acc[1] += 1
    if by_user:
        print("  by user:")
        for u, (mins, n) in sorted(by_user.items(), key=lambda kv: -kv[1][0]):
            print("    · %-24s %6d min (%6.2f h)  [%d]"
                  % (_truncate(names.get(u) or u, 24), mins, mins / 60.0, n))
    return 0


def _project_id(c: Client, ref: str) -> str | None:
    """Resolve a project id | key | name from the cached context. Never re-queries."""
    if _is_uuid(ref):
        return ref
    norm = ref.strip().lower()
    for p in c.context().get("projects", []):
        if norm in (str(p.get("key", "")).lower(), str(p.get("name", "")).lower()):
            return p.get("id")
    known = ", ".join(str(p.get("key") or p.get("name")) for p in c.context().get("projects", []))
    eprint("✗ Unknown project %r. Known: %s  (run context_sync.sh if empty)" % (ref, known or "—"))
    return None


def _msg(data) -> str:
    if isinstance(data, dict):
        return data.get("message") or data.get("error") or json.dumps(data)
    return str(data)


# ───────────────────────── CLI ─────────────────────────
def _billable(p):
    g = p.add_mutually_exclusive_group()
    g.add_argument("--billable", dest="billable", action="store_true", default=None,
                   help="mark the entries billable")
    g.add_argument("--no-billable", dest="billable", action="store_false",
                   help="mark the entries non-billable")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tiempo.py",
        description="Batch-log time, drive the timer, and roll up server-side totals for "
                    "Projekt Republic tasks. Dry-run by default; pass --apply to write.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("log", help="batch-log entries from a CSV/JSON sheet "
                                    "{issue,date,minutes,note?}")
    pl.add_argument("sheet", help="path to .csv/.tsv/.json with rows {issue,date,minutes,note?}")
    pl.add_argument("--apply", action="store_true", help="execute writes (default: dry-run)")
    _billable(pl)
    pl.set_defaults(func=cmd_log)

    pt = sub.add_parser("timer", help="start/stop/show the caller's timer (ONE per user)")
    pt.add_argument("action", choices=["start", "stop", "show"])
    pt.add_argument("issue", nargs="?", default="",
                    help="task reference (PRJ-123) or UUID — for `start`; ignored by stop/show")
    pt.add_argument("--note", default="", help="description for the entry")
    pt.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    _billable(pt)
    pt.set_defaults(func=cmd_timer)

    ps = sub.add_parser("summary", help="server-side time roll-up (read-only)")
    ps.add_argument("issue", nargs="?", default="",
                    help="one task reference/UUID; omit to roll up the whole org or a project")
    ps.add_argument("--project", default="", help="project id | key | name (org-wide if omitted)")
    ps.add_argument("--user", default="", help="filter by user id")
    ps.add_argument("--date-from", dest="date_from", default="", help="YYYY-MM-DD")
    ps.add_argument("--date-to", dest="date_to", default="", help="YYYY-MM-DD")
    ps.add_argument("--group-by", dest="group_by", default="user", choices=["user", "project"],
                    help="server-side grouping (default: user)")
    ps.set_defaults(func=cmd_summary)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        c = Client()
    except SystemExit as e:
        eprint(str(e))
        return 1
    return args.func(args, c)


if __name__ == "__main__":
    sys.exit(main())
