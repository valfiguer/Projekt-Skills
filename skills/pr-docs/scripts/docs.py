#!/usr/bin/env python3
"""docs.py — title-keyed UPSERT of Projekt Republic documents, plus reads.

Subcommands: `upsert`, `list`, `get`, `activity`, `export`.
DRY-RUN BY DEFAULT for every write; `--apply` to persist.

WHAT CHANGED vs the pre-rewrite skill — three claims that are no longer true:
  1. Documents are ORG-scoped, not project-scoped. The project is a FIELD:
        GET   /organizations/{org}/documents?project_id&parent_id&q&limit&offset
        POST  /organizations/{org}/documents   {title*, content, project_id, folder_id, parent_id}
        PATCH /organizations/{org}/documents/{id} {title, content, project_id, folder_id, parent_id, position}
  2. The body is PLAIN MARKDOWN in `content`. There is no EditorJS block format,
     no `blocks` field and no `?format=markdown` round-trip — reading a document
     gives back the markdown that was written. All the block-shape lore is gone.
  3. There is no AI "bitácora regenerate" and no issues→PDF export. `bitácora` now
     means a task's read-only activity feed
     (GET /organizations/{org}/projects/{proj}/tasks/{id}/activity), and the only
     PDFs the API makes are for quotes and invoices. An org-wide ZIP lives at
     GET /organizations/{org}/export.

Idempotency: the document TITLE is the key, matched trimmed + case-insensitively
within the chosen scope (project + parent). Re-running UPSERT PATCHes the same
document; it never creates a second one.

stdlib only · Python 3.10+.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pr" / "scripts" / "lib"))
from projekt_api import Client, Ledger, eprint  # noqa: E402

PHASE = "docs"


def _norm(s) -> str:
    return (str(s or "")).strip().lower()


def project_id(c: Client, ref: str | None) -> str | None:
    if not ref:
        return None
    ctx = c.context()
    n = _norm(ref)
    for p in ctx.get("projects", []):
        if n in (_norm(p.get("id")), _norm(p.get("key")), _norm(p.get("name"))):
            return p["id"]
    known = ", ".join(str(p.get("key") or p.get("name")) for p in ctx.get("projects", []))
    raise SystemExit("✗ Unknown project %r. Known: %s\n  (run ../pr/scripts/context_sync.sh)"
                     % (ref, known or "—"))


def list_documents(c: Client, pid: str | None = None, parent: str | None = None,
                   q: str | None = None) -> list[dict]:
    out, offset = [], 0
    while True:
        params = {"limit": "200", "offset": str(offset)}
        if pid:
            params["project_id"] = pid
        if parent:
            params["parent_id"] = parent
        if q:
            params["q"] = q
        data = c.get_json("/organizations/%s/documents?%s" % (c.org, urllib.parse.urlencode(params)))
        rows = data if isinstance(data, list) else (data.get("data") or data.get("documents") or [])
        out += rows
        if len(rows) < 200:
            break
        offset += 200
        if offset > 2000:
            eprint("  ! stopped paging at 2000 documents.")
            break
    return out


def find_by_title(docs: list[dict], title: str) -> dict | None:
    n = _norm(title)
    hits = [d for d in docs if _norm(d.get("title")) == n]
    if len(hits) > 1:
        eprint("  ! %d documents share the title %r — the first one wins. Rename the others."
               % (len(hits), title))
    return hits[0] if hits else None


def read_body(args) -> str:
    if args.body_file:
        if args.body_file == "-":
            return sys.stdin.read()
        return pathlib.Path(args.body_file).read_text(encoding="utf-8")
    if args.body == "-":
        return sys.stdin.read()
    return args.body or ""


def cmd_upsert(args, c: Client) -> int:
    pid = project_id(c, args.project)
    body = read_body(args)
    if not body.strip() and not args.allow_empty:
        raise SystemExit("✗ Empty body. Pass --body/--body-file, or --allow-empty on purpose.")

    docs = list_documents(c, pid)
    parent_id = None
    if args.parent:
        parent = find_by_title(docs, args.parent)
        if not parent:
            titles = ", ".join(sorted(d.get("title") or "?" for d in docs)[:20])
            raise SystemExit("✗ Parent %r not found in this scope. Existing: %s\n"
                             "  Create the parent first." % (args.parent, titles or "—"))
        parent_id = parent["id"]

    scope = [d for d in docs if (not parent_id or d.get("parent_id") == parent_id)]
    existing = find_by_title(scope, args.title)
    action = "UPDATE" if existing else "CREATE"

    print("Document UPSERT — org=%s  project=%s  parent=%s"
          % (c.org, args.project or "(org-level)", args.parent or "—"))
    print("  %-7s  %-44.44s  %d chars of markdown"
          % (action, args.title, len(body)))
    if existing:
        print("  target id: %s" % existing["id"])
    print("  Mode: %s" % ("APPLY (writing)" if args.apply else "DRY-RUN (no writes)"))

    if not args.apply:
        print("\nDRY-RUN. Re-run with --apply.")
        return 0

    led = Ledger()
    payload = {"title": args.title, "content": body}
    if pid:
        payload["project_id"] = pid
    if parent_id:
        payload["parent_id"] = parent_id

    if existing:
        st, data = c.request("PATCH", "/organizations/%s/documents/%s" % (c.org, existing["id"]), payload)
        did = existing["id"]
    else:
        st, data = c.request("POST", "/organizations/%s/documents" % c.org, payload)
        did = data.get("id") if isinstance(data, dict) else None

    if 200 <= st < 300:
        led.add(PHASE, "doc.upsert", _norm(args.title), "updated" if existing else "created", ref=did)
        print("  ✓ %s → %s" % (action.lower(), did))
        return 0
    if st == 403:
        eprint("  ✗ 403 — no write permission on this org/project, or a cross-org token.")
        return 2
    msg = data.get("message") or data.get("error") if isinstance(data, dict) else data
    led.add(PHASE, "doc.upsert", _norm(args.title), "error", ref=str(st))
    eprint("  ✗ HTTP %s: %s" % (st, msg))
    return 1


def cmd_list(args, c: Client) -> int:
    pid = project_id(c, args.project)
    docs = list_documents(c, pid, q=args.q or None)
    print("Documents — org %s%s  (%d)"
          % (c.org, "  project=%s" % args.project if args.project else "", len(docs)))
    by_parent: dict[str | None, list[dict]] = {}
    for d in docs:
        by_parent.setdefault(d.get("parent_id"), []).append(d)
    def show(parent, depth):
        for d in sorted(by_parent.get(parent, []), key=lambda x: (x.get("position") or 0,
                                                                  _norm(x.get("title")))):
            print("  %s· %-46.46s  %-8s  %s"
                  % ("  " * depth, d.get("title") or "?", d.get("kind") or "", d.get("id")))
            show(d.get("id"), depth + 1)
    show(None, 0)
    orphan_parents = set(by_parent) - {None} - {d.get("id") for d in docs}
    for p in orphan_parents:  # children whose parent is outside this scope
        show(p, 0)
    return 0


def cmd_get(args, c: Client) -> int:
    docs = list_documents(c, project_id(c, args.project))
    target = args.document if args.document else None
    doc = None
    if target and "-" in target and len(target) > 30:
        doc = {"id": target}
    else:
        doc = find_by_title(docs, target or "")
    if not doc:
        raise SystemExit("✗ No document matched %r." % target)
    data = c.get_json("/organizations/%s/documents/%s" % (c.org, doc["id"]))
    if args.meta:
        print(json.dumps({k: v for k, v in data.items() if k != "content"}, indent=2))
        return 0
    content = data.get("content")
    if content is None:
        eprint("(document is empty, or kind=file — content is always null for a file)")
        return 0
    if args.out:
        pathlib.Path(args.out).write_text(content, encoding="utf-8")
        print("✓ %d chars → %s" % (len(content), args.out))
    else:
        print(content)
    return 0


def cmd_activity(args, c: Client) -> int:
    """A task's bitácora = its read-only activity feed. No AI, nothing to regenerate."""
    pid = project_id(c, args.project) or c.project
    if not pid:
        raise SystemExit("✗ --project is required (the PAT is not project-scoped).")
    data = c.get_json("/organizations/%s/projects/%s/tasks/%s/activity" % (c.org, pid, args.task))
    rows = data if isinstance(data, list) else (data.get("data") or data.get("entries") or [])
    print("Activity (bitácora) — task %s   (%d entries, newest first)" % (args.task, len(rows)))
    for r in rows[: args.limit]:
        print("  · %-20.20s  %-14.14s  %s"
              % (r.get("created_at") or "?", r.get("type") or r.get("action") or "",
                 (r.get("summary") or r.get("description") or r.get("message") or "")[:70]))
    if len(rows) > args.limit:
        print("  … %d more (raise --limit)" % (len(rows) - args.limit))
    return 0


def cmd_export(args, c: Client) -> int:
    """GET /organizations/{org}/export streams a ZIP of the whole organization."""
    print("Organization export — org %s" % c.org)
    print("  GET /organizations/%s/export  → application/zip" % c.org)
    print("  Mode: %s" % ("APPLY (downloading)" if args.apply else "DRY-RUN (no request)"))
    if not args.apply:
        print("\nDRY-RUN. Re-run with --apply to download to %s." % args.out)
        return 0
    import urllib.request
    req = urllib.request.Request(c.base + "/organizations/%s/export" % c.org)
    req.add_header("Authorization", "Bearer " + c.token)
    req.add_header("Accept", "application/zip")
    try:
        with urllib.request.urlopen(req, timeout=300) as r, open(args.out, "wb") as f:
            f.write(r.read())
    except Exception as e:
        raise SystemExit("✗ export failed: %s" % e)
    size = pathlib.Path(args.out).stat().st_size
    print("  ✓ %s (%.1f MB). Do NOT read it into the model — hand the path to the user."
          % (args.out, size / 1e6))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="docs.py",
        description="Title-keyed UPSERT of Projekt Republic documents (plain markdown), "
                    "plus reads. Dry-run by default.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pu = sub.add_parser("upsert", help="create-or-update a document by title (idempotent)")
    pu.add_argument("--title", required=True)
    pu.add_argument("--project", default="", help="project id | key | name (omit for an org-level doc)")
    pu.add_argument("--parent", default="", help="parent document TITLE (must already exist)")
    pu.add_argument("--body", default="", help="markdown, or '-' to read stdin")
    pu.add_argument("--body-file", dest="body_file", default="", help="path to a .md file, or '-'")
    pu.add_argument("--allow-empty", action="store_true", help="permit an empty body on purpose")
    pu.add_argument("--apply", action="store_true")
    pu.set_defaults(func=cmd_upsert)

    pl = sub.add_parser("list", help="list documents as a tree (read-only)")
    pl.add_argument("--project", default="")
    pl.add_argument("--q", default="", help="server-side search term")
    pl.set_defaults(func=cmd_list)

    pg = sub.add_parser("get", help="print one document's markdown (read-only)")
    pg.add_argument("document", help="document TITLE or UUID")
    pg.add_argument("--project", default="")
    pg.add_argument("--out", default="", help="write to a file instead of stdout")
    pg.add_argument("--meta", action="store_true", help="print metadata instead of the body")
    pg.set_defaults(func=cmd_get)

    pa = sub.add_parser("activity", help="a task's activity feed / bitácora (read-only)")
    pa.add_argument("task", help="task UUID")
    pa.add_argument("--project", default="")
    pa.add_argument("--limit", type=int, default=30)
    pa.set_defaults(func=cmd_activity)

    pe = sub.add_parser("export", help="download the org-wide ZIP export")
    pe.add_argument("--out", default="organization-export.zip")
    pe.add_argument("--apply", action="store_true")
    pe.set_defaults(func=cmd_export)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    c = Client()
    if not c.org:
        raise SystemExit("✗ No org in context. Run ../pr/scripts/auth_check.sh + context_sync.sh first.")
    return args.func(args, c)


if __name__ == "__main__":
    sys.exit(main())
