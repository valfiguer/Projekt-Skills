#!/usr/bin/env python3
"""tareas.py — create Projekt Republic TASKS in bulk from a CSV or JSON file.

Ported to the rewritten /api/v1 API: org + project live in the PATH and the
resource is `tasks` (not `issues`). There is NO bulk-create endpoint, so we create
one-at-a-time with sequential POST .../tasks (concurrency capped at 3).

Rewrite specifics that shape this script:
  · Endpoint: POST /organizations/{org}/projects/{project}/tasks (assignee_id included)
              GET  /organizations/{org}/projects/{project}/tasks   (dedupe sweep)
  · Create body: {title*, description?, priority?, type?, assignee_id?, story_points?,
                  estimated_hours?, start_date?, due_date?, sprint_id?, parent_id?}.
    The ASSIGNEE IS settable on create; `status` is NOT — a task is born `todo`.
  · A non-todo status is applied AFTER create via
    PATCH /organizations/{org}/projects/{project}/tasks/{id} (TaskUpdateIn).
  · Statuses are todo | in_progress | done | cancelled (localized/legacy names like
    "Backlog"/"To Do"/"In Progress" are normalized here).

Pipeline:
  1. Resolve org + project. org + project self-discovered from context.json
     (auth_check.sh reads the PAT's own api_key scope on /auth/me). --project may
     still override the project by key/name/id from context.projects.
  2. Read rows (CSV columns of assets/import_template.csv, or a JSON list).
  3. Resolve each row's assignee (email or name) -> user_id from context.members.
  4. Dedupe: sweep existing tasks for the project, skip any title or external_ref
     already present; also skip anything the Ledger has already created.
  5. DRY-RUN (default): print a create/skip table. Nothing is written.
  6. --apply: POST .../tasks for each row (≤3 in flight), then PATCH only
     (if requested) advance status. Every create is logged to the Ledger so
     re-runs are idempotent and resumable.

Assignee rule (references/errors.md): a task cannot ADVANCE out of `todo` into a
working status (in_progress / done) without an assignee. Rows requesting a working
status but lacking a resolvable assignee are LEFT in `todo` and flagged "needs
owner" (never dropped). --strict-status skips them instead.

Examples:
  python3 bulk_issue_create.py --project WEB --file backlog.csv          # dry-run
  python3 bulk_issue_create.py --project WEB --file backlog.csv --apply  # execute
"""
from __future__ import annotations
import argparse
import csv
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from projekt_api import Client, Ledger, slim, eprint  # noqa: E402

# Rewrite statuses. A task is created `todo`; it may not advance to a working
# status without an assignee. Aliases map legacy/localized column names.
TODO = "todo"
STATUS_ALIASES = {
    "todo": "todo", "to do": "todo", "to-do": "todo", "backlog": "todo",
    "por hacer": "todo", "pendiente": "todo", "open": "todo", "nuevo": "todo",
    "in_progress": "in_progress", "in progress": "in_progress", "in-progress": "in_progress",
    "wip": "in_progress", "en progreso": "in_progress", "en curso": "in_progress",
    "doing": "in_progress", "in review": "in_progress", "en revisión": "in_progress",
    "done": "done", "closed": "done", "hecho": "done", "completado": "done", "cerrado": "done",
    "cancelled": "cancelled", "canceled": "cancelled", "cancelado": "cancelled", "wontfix": "cancelled",
}
WORKING = {"in_progress", "done"}  # can't be reached from todo without an assignee
CSV_COLS = ("title", "description", "status", "assignee", "estimated_hours",
            "priority", "type", "labels", "external_ref")


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def norm_status(raw: str) -> str:
    """Map any localized/legacy column name to a canonical rewrite status."""
    return STATUS_ALIASES.get(_norm(raw), TODO)


def load_rows(path: pathlib.Path) -> list[dict]:
    """Read a CSV (import_template columns) or a JSON list of row objects."""
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data.get("issues", data.get("tasks", data)) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise SystemExit("✗ JSON must be a list of task objects (or {tasks:[…]}).")
        return [dict(r) for r in rows]
    rdr = csv.DictReader(text.splitlines())
    return [{k: (v or "").strip() for k, v in row.items()} for row in rdr]


def resolve_project(ctx: dict, ref: str | None) -> dict:
    """Resolve the target project. With no --project, use the self-discovered
    project_id (project-scoped PAT); else the sole cached project; else require --project."""
    projects = ctx.get("projects", [])
    if not ref:
        pid = ctx.get("project_id")
        if pid:
            for p in projects:
                if str(p.get("id")) == str(pid):
                    return p
            return {"id": pid, "key": ctx.get("key_name"), "name": None}
        if len(projects) == 1:
            return projects[0]
        keys = ", ".join(sorted(f"{p.get('key')}" for p in projects if p.get("key"))) or "(none)"
        raise SystemExit("✗ No --project given and org has multiple projects. "
                         "Pass --project <KEY>. Known keys: %s" % keys)
    ref_n = _norm(ref)
    for p in projects:
        if _norm(p.get("key")) == ref_n or _norm(p.get("name")) == ref_n or str(p.get("id")) == ref:
            return p
    keys = ", ".join(sorted(f"{p.get('key')}" for p in projects if p.get("key"))) or "(none)"
    raise SystemExit("✗ Project %r not in context. Known keys: %s\n"
                     "  Run the projekt skill's context_sync.sh first." % (ref, keys))


def build_member_index(ctx: dict) -> dict[str, dict]:
    """Map lowercased email AND name -> member, for assignee resolution."""
    idx: dict[str, dict] = {}
    for m in ctx.get("members", []):
        for key in (m.get("email"), m.get("name"), m.get("user_id")):
            if key:
                idx.setdefault(_norm(str(key)), m)
    return idx


def resolve_assignee(idx: dict[str, dict], raw: str) -> tuple[str | None, str | None]:
    """Return (user_id|None, error|None). Empty input -> (None, None) = unassigned."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    m = idx.get(_norm(raw))
    if not m:
        return None, "unknown assignee %r" % raw
    return m.get("user_id"), None


def existing_sweep(c: Client, org: str, pid: str) -> tuple[set[str], set[str]]:
    """Sweep current tasks of the project; return (titles_lower, external_refs)."""
    titles: set[str] = set()
    refs: set[str] = set()
    offset, page = 0, 200
    base = "/organizations/%s/projects/%s/tasks" % (org, pid)
    while True:
        data = c.get_json("%s?limit=%d&offset=%d" % (base, page, offset))
        rows = data if isinstance(data, list) else (
            data.get("data") or data.get("tasks") or data.get("issues") or [] if isinstance(data, dict) else [])
        if not rows:
            break
        for r in rows:
            if r.get("title"):
                titles.add(_norm(r["title"]))
            xr = r.get("external_ref") or r.get("externalRef")
            if xr:
                refs.add(str(xr).strip())
        if len(rows) < page:
            break
        offset += page
    return titles, refs


def plan_row(row: dict, midx: dict[str, dict], ledger: Ledger, dedupe_ns: str,
             have_titles: set[str], have_refs: set[str], strict_status: bool) -> dict:
    """Classify one row into a create/skip plan entry (no writes)."""
    title = (row.get("title") or "").strip()
    if not title:
        return {"action": "skip", "title": "(blank)", "reason": "missing title"}

    ext = (row.get("external_ref") or "").strip()
    dedupe_key = ext or "%s|%s" % (dedupe_ns, _norm(title))

    if _norm(title) in have_titles:
        return {"action": "skip", "title": title, "reason": "title exists in project"}
    if ext and ext in have_refs:
        return {"action": "skip", "title": title, "reason": "external_ref exists: %s" % ext}
    if ledger.seen("task.create", dedupe_key):
        return {"action": "skip", "title": title, "reason": "already created (ledger)"}

    uid, aerr = resolve_assignee(midx, row.get("assignee", ""))
    want_status = norm_status(row.get("status", ""))
    needs_owner = False
    note = None

    if aerr:  # unknown assignee -> create unassigned, surface the mismatch
        note = aerr
        uid = None

    # Assignee rule: a task can't advance to a working status without an assignee.
    # Leave it in `todo` and flag "needs owner" rather than failing or dropping.
    if want_status in WORKING and not uid:
        if strict_status:
            return {"action": "skip", "title": title,
                    "reason": "working status %r without assignee (strict)" % want_status}
        needs_owner = True
        note = (note + "; " if note else "") + "status %r held at todo (needs owner)" % want_status
        want_status = TODO

    # Create body. TaskCreateIn accepts assignee_id, story_points, estimated_hours,
    # sprint_id and the dates — only `status` is absent, so only that needs a PATCH.
    payload: dict = {"title": title}
    if uid:
        payload["assignee_id"] = uid
    if row.get("description"):
        payload["description"] = row["description"]
    if row.get("priority"):
        payload["priority"] = _norm(row["priority"])
    if row.get("type"):
        payload["type"] = _norm(row["type"])
    eh = (row.get("estimated_hours") or "").strip()
    if eh:
        try:
            payload["estimated_hours"] = float(eh) if "." in eh else int(eh)
        except ValueError:
            note = (note + "; " if note else "") + "bad estimated_hours %r ignored" % eh
    sp = str(row.get("story_points") or "").strip()
    if sp:
        try:
            payload["story_points"] = int(float(sp))
        except ValueError:
            note = (note + "; " if note else "") + "bad story_points %r ignored" % sp
    for src, field in (("sprint_id", "sprint_id"), ("parent_id", "parent_id"),
                       ("due_date", "due_date"), ("start_date", "start_date")):
        v = str(row.get(src) or "").strip()
        if v:
            payload[field] = v

    return {"action": "create", "title": title, "payload": payload, "dedupe_key": dedupe_key,
            "assignee_id": uid, "want_status": want_status, "needs_owner": needs_owner, "note": note}


def print_plan(plan: list[dict], project: dict, c: Client) -> None:
    creates = [p for p in plan if p["action"] == "create"]
    skips = [p for p in plan if p["action"] == "skip"]
    owners = [p for p in creates if p.get("needs_owner")]
    print("Project: %s — %s (%s)" % (project.get("key") or "—", project.get("name") or "(scoped)", project.get("id")))
    print("Token:   %s | org %s" % (c.fingerprint(), c.org))
    print("Plan:    %d create · %d skip · %d need owner\n" % (len(creates), len(skips), len(owners)))
    print("  %-7s  %-40s  %-12s  %-10s  %s" % ("ACTION", "TITLE", "STATUS", "ASSIGNEE", "NOTE"))
    print("  " + "-" * 96)
    for p in plan:
        if p["action"] == "create":
            print("  %-7s  %-40.40s  %-12s  %-10s  %s" % (
                "CREATE", p["title"], p.get("want_status", TODO),
                (p.get("assignee_id") or "—")[:10], p.get("note") or ""))
        else:
            print("  %-7s  %-40.40s  %-12s  %-10s  %s" % ("skip", p["title"], "", "", p["reason"]))
    if owners:
        print("\n  ⚠ %d task(s) need an owner (left in todo, can't advance until assigned)."
              % len(owners))


def do_create(c: Client, ledger: Ledger, org: str, pid: str, entry: dict) -> tuple[dict, int, str]:
    """POST the task (assignee included), then PATCH only if a non-todo status is wanted."""
    base = "/organizations/%s/projects/%s/tasks" % (org, pid)
    key = entry["dedupe_key"]
    st, data = c.request("POST", base, entry["payload"])
    if not (200 <= st < 300):
        if st == 403:
            ledger.add("create", "task.create", key, "error", ref="403")
            return entry, st, "403 cross-org/scope — stop, wrong token/org/project"
        ledger.add("create", "task.create", key, "error", ref=str(st))
        msg = data.get("message") or data.get("error") or data.get("detail") if isinstance(data, dict) else str(data)
        return entry, st, "HTTP %s: %s" % (st, msg)

    tslim = slim("task", data)
    tobj = (tslim[0] if isinstance(tslim, list) and tslim else tslim) if tslim else {}
    task_id = tobj.get("id") if isinstance(tobj, dict) else None
    ref = tobj.get("reference") if isinstance(tobj, dict) else None
    ledger.add("create", "task.create", key, "created", ref=ref or task_id)

    # A task is born `todo`: only a working status needs a follow-up PATCH.
    patch: dict = {}
    if entry.get("want_status") and entry["want_status"] != TODO:
        patch["status"] = entry["want_status"]
    if patch and task_id:
        pst, pdata = c.request("PATCH", "%s/%s" % (base, task_id), patch)
        if not (200 <= pst < 300):
            note = ", ".join(sorted(patch))
            msg = pdata.get("message") or pdata.get("error") or pdata.get("detail") if isinstance(pdata, dict) else str(pdata)
            ledger.add("create", "task.update", key, "blocked" if pst == 422 else "error", ref=str(pst))
            return entry, st, "created %s (⚠ %s patch %s: %s)" % (ref or "", note, pst, msg)
    tail = " assigned" if entry.get("assignee_id") else ""
    tail += " → %s" % entry["want_status"] if patch.get("status") else ""
    return entry, st, "created %s%s" % (ref or "", tail)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk-create Projekt tasks from CSV/JSON (dry-run by default).")
    ap.add_argument("--project", help="Project key, name, or id. Omit to use the PAT's own project scope.")
    ap.add_argument("--file", required=True, help="CSV (import_template columns) or .json list of rows.")
    ap.add_argument("--apply", action="store_true", help="Execute writes. Without it: dry-run only.")
    ap.add_argument("--strict-status", action="store_true",
                    help="Skip (don't hold at todo) rows requesting a working status with no assignee.")
    ap.add_argument("--concurrency", type=int, default=3, help="Parallel POSTs (capped at 3).")
    args = ap.parse_args()

    path = pathlib.Path(args.file)
    if not path.exists():
        raise SystemExit("✗ File not found: %s" % path)

    c = Client()
    if not c.org:
        raise SystemExit("✗ No org resolved. Run the projekt skill's auth_check.sh first.")
    ctx = c.context()

    project = resolve_project(ctx, args.project)
    pid = project["id"]
    midx = build_member_index(ctx)
    ledger = Ledger()
    rows = load_rows(path)
    if not rows:
        print("Nothing to do: file has 0 rows.")
        return 0

    eprint("Sweeping existing tasks for dedupe…")
    have_titles, have_refs = existing_sweep(c, c.org, pid)
    eprint("  found %d titles, %d external_refs already in project." % (len(have_titles), len(have_refs)))

    dedupe_ns = pid
    plan = [plan_row(r, midx, ledger, dedupe_ns, have_titles, have_refs, args.strict_status) for r in rows]
    print_plan(plan, project, c)

    creates = [p for p in plan if p["action"] == "create"]
    if not args.apply:
        print("\nDRY-RUN. Re-run with --apply to create %d task(s). No writes were made." % len(creates))
        return 0
    if not creates:
        print("\nNothing to create (all skipped). Ledger: %s" % ledger.summary())
        return 0

    conc = max(1, min(args.concurrency, 3))
    print("\nApplying: creating %d task(s) at concurrency %d…" % (len(creates), conc))
    ok = blocked = err = 0
    with ThreadPoolExecutor(max_workers=conc) as ex:
        futs = {ex.submit(do_create, c, ledger, c.org, pid, e): e for e in creates}
        for fut in as_completed(futs):
            entry, st, msg = fut.result()
            if 200 <= st < 300 and "⚠" not in msg:
                ok += 1
                tag = "✓"
            elif st == 403:
                err += 1
                tag = "✗"
            elif "⚠" in msg:
                blocked += 1
                tag = "⚠"
            else:
                err += 1
                tag = "✗"
            print("  %s %-40.40s %s" % (tag, entry["title"], msg))
            if st == 403:  # cross-org/scope is fatal for the whole batch
                eprint("✗ 403 — aborting. Use a token scoped to org %s / project %s." % (c.org, pid))
                break

    print("\nDone. created=%d partial(patch failed)=%d error=%d | ledger %s"
          % (ok, blocked, err, ledger.summary()))
    if blocked:
        print("⚠ %d task(s) were created but a follow-up assignee/status PATCH failed — "
              "fix owners, then re-run (idempotent: create is skipped, PATCH retried)." % blocked)
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
