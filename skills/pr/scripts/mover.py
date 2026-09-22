#!/usr/bin/env python3
"""mover.py — assign, move, re-prioritize or re-sprint tasks in bulk.

Uses the real bulk endpoint, which MUTATES existing tasks only (it does NOT
create — use tareas.py for that):

    POST /organizations/{org}/projects/{project}/tasks/bulk
         {task_ids: […≤200], op: "set_status"|"set_assignee"|"set_sprint"
                                 |"set_parent"|"set_priority"|"add_tags"|"remove_tags",
          status? | assignee_id? | sprint_id? | parent_id? | priority? | tag_ids?}

It is PER-PROJECT and transactional per call, and answers
{updated, skipped, errors} — `skipped` are the tasks already in the target
state (idempotent no-op), `errors` carry a reason per id.

What this script does NOT assume: there is no "a task needs an owner to leave
todo" rule on /api/v1 — that was a legacy invention. The real 422 on a move is
the destination column's `wip_limit` (only for columns that set one). Unassigned
tasks move fine; `--assignee` is applied first purely because that is the order
a human means by "assign and move".

Tasks are given as references (WEB-12) or UUIDs. A reference is split into
project key + number and resolved with GET .../tasks/by-number/{n} using the
project ids cached in .projekt-run/context.json — one request per task, no sweep.

Examples:
  python3 mover.py --tasks WEB-12,WEB-13 --assignee jane@acme.com --status in_progress
  python3 mover.py --tasks WEB-12,WEB-13 --assignee jane@acme.com --status in_progress --apply
  python3 mover.py --tasks WEB-12 --priority urgent --apply
  python3 mover.py --tasks WEB-12,WEB-13 --sprint <sprint-uuid> --apply
"""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from projekt_api import Client, Ledger, slim, eprint  # noqa: E402

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_BATCH = 200  # server cap on task_ids

# Localized / legacy column names → the status slugs the API takes.
STATUS_ALIASES = {
    "backlog": "todo", "to do": "todo", "to-do": "todo", "todo": "todo",
    "por hacer": "todo", "pendiente": "todo",
    "in progress": "in_progress", "in-progress": "in_progress", "wip": "in_progress",
    "en progreso": "in_progress", "en curso": "in_progress", "haciendo": "in_progress",
    "done": "done", "hecho": "done", "completado": "done", "terminado": "done",
    "cancelled": "cancelled", "canceled": "cancelled", "cancelado": "cancelled",
}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match((s or "").strip()))


def norm_status(raw: str) -> str:
    """Map a human column name to a status slug. Custom slugs pass through."""
    n = _norm(raw)
    if n in STATUS_ALIASES:
        return STATUS_ALIASES[n]
    slug = re.sub(r"[^a-z0-9_]+", "_", n).strip("_")
    return slug[:20]


def resolve_assignee(ctx: dict, raw: str) -> str:
    raw = (raw or "").strip()
    if _is_uuid(raw):
        return raw
    for m in ctx.get("members", []):
        for key in (m.get("email"), m.get("name"), m.get("user_id")):
            if key and _norm(str(key)) == _norm(raw):
                return m.get("user_id")
    names = ", ".join(sorted(m.get("name") or m.get("email") or "?" for m in ctx.get("members", [])))
    raise SystemExit("✗ Assignee %r not in context members.\n  Known: %s\n"
                     "  (run context_sync.sh if that list is empty)" % (raw, names or "(none)"))


def resolve_tasks(c: Client, ctx: dict, tokens: list[str]) -> tuple[list[dict], list[str]]:
    """Map reference/UUID tokens → task dicts (with project_id). Returns (found, unresolved)."""
    by_key = {str(p.get("key", "")).upper(): p["id"] for p in ctx.get("projects", []) if p.get("key")}
    candidates = ([c.project] if c.project else []) + \
                 [p["id"] for p in ctx.get("projects", []) if p.get("id") and p["id"] != c.project]
    found: list[dict] = []
    unresolved: list[str] = []

    for t in tokens:
        if _is_uuid(t):
            hit = None
            for pid in candidates:
                st, data = c.request(
                    "GET", "/organizations/%s/projects/%s/tasks/%s" % (c.org, pid, t))
                if 200 <= st < 300 and isinstance(data, dict) and data.get("id"):
                    hit = dict(slim("task", data))
                    hit["project_id"] = data.get("project_id") or pid
                    break
            (found.append(hit) if hit else unresolved.append(t))
            continue

        key, _, num = t.rpartition("-")
        pid = by_key.get(key.upper())
        if not pid or not num.isdigit():
            unresolved.append(t)
            continue
        st, data = c.request(
            "GET", "/organizations/%s/projects/%s/tasks/by-number/%s" % (c.org, pid, num))
        if st == 403:
            raise SystemExit("✗ 403 reading %s — the PAT cannot see project %s. Switch org/token." % (t, key))
        if 200 <= st < 300 and isinstance(data, dict) and data.get("id"):
            hit = dict(slim("task", data))
            hit["project_id"] = data.get("project_id") or pid
            found.append(hit)
        else:
            unresolved.append(t)
    return found, unresolved


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def run_bulk(c: Client, ledger: Ledger, pid: str, task_ids: list[str],
             op: str, field: str, value, label: str, applying: bool) -> int:
    """One bulk op against ONE project. Returns 0 ok, 1 partial/soft-fail, 2 fatal."""
    rc = 0
    for batch in _chunks(task_ids, MAX_BATCH):
        key = "%s:%s:%s:%s" % (op, pid, value, ",".join(sorted(batch)))
        if ledger.seen("task.bulk", key):
            print("  • %s already applied (ledger) — skipping %d task(s)." % (label, len(batch)))
            continue
        if not applying:
            print("  POST .../projects/%s/tasks/bulk  op=%s %s=%s  ×%d"
                  % (pid[:8], op, field, value, len(batch)))
            continue
        body = {"task_ids": batch, "op": op}
        if field:
            body[field] = value
        st, data = c.request("POST", "/organizations/%s/projects/%s/tasks/bulk" % (c.org, pid), body)
        msg = (data.get("message") or data.get("error") or data.get("detail")
               if isinstance(data, dict) else str(data))
        if 200 <= st < 300 and isinstance(data, dict):
            ledger.add("bulk", "task.bulk", key, "ok", ref=op)
            errs = data.get("errors") or []
            print("  ✓ %s: updated=%s skipped=%s errors=%s"
                  % (label, data.get("updated"), data.get("skipped"),
                     len(errs) if isinstance(errs, list) else errs))
            if errs:
                rc = rc or 1
                for e in (errs if isinstance(errs, list) else [])[:5]:
                    print("      · %s" % e)
        elif st == 422:
            ledger.add("bulk", "task.bulk", key, "blocked", ref="422")
            print("  ⚠ 422 on %s: %s" % (label, msg))
            print("      (a destination column with a wip_limit that is full gives this)")
            rc = rc or 1
        elif st == 403:
            ledger.add("bulk", "task.bulk", key, "error", ref="403")
            raise SystemExit("✗ 403 cross-org/scope on %s — wrong token, org or project." % label)
        else:
            ledger.add("bulk", "task.bulk", key, "error", ref=str(st))
            print("  ✗ %s failed HTTP %s: %s" % (label, st, msg))
            rc = 2
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bulk assign / move / re-prioritize Projekt Republic tasks "
                    "via .../tasks/bulk. Dry-run by default; --apply to write. Does NOT create.")
    ap.add_argument("--tasks", "--issues", dest="tasks", required=True,
                    help="Comma-separated task references (WEB-12) or UUIDs.")
    ap.add_argument("--assignee", help="Email/name/UUID of the owner to set (op=set_assignee).")
    ap.add_argument("--status", help="Target column/status, e.g. 'In Progress' or in_progress.")
    ap.add_argument("--priority", choices=["low", "medium", "high", "urgent"],
                    help="Set priority (op=set_priority).")
    ap.add_argument("--sprint", help="Sprint UUID to move into (op=set_sprint).")
    ap.add_argument("--apply", action="store_true", help="Execute. Without it: dry-run only.")
    args = ap.parse_args()

    if not any((args.assignee, args.status, args.priority, args.sprint)):
        raise SystemExit("✗ Nothing to do: pass at least one of --assignee/--status/--priority/--sprint.")

    tokens = [t.strip() for t in args.tasks.split(",") if t.strip()]
    if not tokens:
        raise SystemExit("✗ No tasks given.")

    c = Client()
    ctx = c.context()
    if not ctx.get("org_id"):
        raise SystemExit("✗ No context. Run the pr skill's auth_check.sh + context_sync.sh first.")

    assignee_id = resolve_assignee(ctx, args.assignee) if args.assignee else None
    target = norm_status(args.status) if args.status else None

    eprint("Resolving %d task(s)…" % len(tokens))
    tasks, unresolved = resolve_tasks(c, ctx, tokens)

    by_project: dict[str, list[dict]] = {}
    for t in tasks:
        by_project.setdefault(t["project_id"], []).append(t)

    print("Token:  %s | org %s" % (c.fingerprint(), c.org))
    print("Ops:    %s" % ", ".join(filter(None, [
        "assignee=%s" % assignee_id if assignee_id else None,
        "status=%s" % target if target else None,
        "priority=%s" % args.priority if args.priority else None,
        "sprint=%s" % args.sprint if args.sprint else None])))
    print("Plan:   %d task(s) across %d project(s) · %d unresolved\n"
          % (len(tasks), len(by_project), len(unresolved)))
    print("  %-14s  %-30s  %-13s  %s" % ("REF", "TITLE", "STATUS", "OWNER"))
    print("  " + "-" * 76)
    for t in tasks:
        print("  %-14.14s  %-30.30s  %-13.13s  %s"
              % (t.get("reference") or t.get("id"), t.get("title") or "",
                 t.get("status") or "?", (t.get("assignee_id") or "—")[:12]))
    for t in unresolved:
        print("  %-14.14s  %-30s  %-13s  %s" % (t, "(unresolved — bad ref/UUID, or", "", "not in this org)"))

    if not tasks:
        print("\nNothing resolved. No writes made.")
        return 1

    applying = args.apply
    if not applying:
        print("\nDRY-RUN — calls that WOULD be made:")

    ledger = Ledger()
    rc = 0
    # Order matters: a human saying "assign and move" means the owner lands first.
    steps = [(assignee_id, "set_assignee", "assignee_id", assignee_id, "assign"),
             (args.priority, "set_priority", "priority", args.priority, "priority"),
             (args.sprint, "set_sprint", "sprint_id", args.sprint, "sprint"),
             (target, "set_status", "status", target, "move")]
    for guard, op, field, value, label in steps:
        if not guard:
            continue
        for pid, rows in by_project.items():
            step_rc = run_bulk(c, ledger, pid, [r["id"] for r in rows], op, field, value, label, applying)
            rc = max(rc, step_rc)
        if rc == 2:
            break

    if not applying:
        print("\nDRY-RUN. Re-run with --apply. No writes were made.")
        return 0
    print("\nDone. ledger %s" % ledger.summary())
    if unresolved:
        print("⚠ %d token(s) unresolved and untouched." % len(unresolved))
        rc = rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
