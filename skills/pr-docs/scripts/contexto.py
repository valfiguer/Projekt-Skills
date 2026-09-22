#!/usr/bin/env python3
"""contexto.py — use Projekt Republic as an AI-context store (memories ↔ documents).

Mirror a codebase's memory/context `.md` files into Projekt documents (one per
file, idempotent UPSERT keyed on the filename stem) and load them back as ONE
markdown bundle, so any AI reads repo context over the API instead of crawling
the repository and burning tokens. Same idea as Serena's `.serena/memories/`,
but stored in Projekt and shared across providers and machines.

Endpoints (/api/v1 — documents are ORG-scoped and hold PLAIN MARKDOWN):
    GET   /organizations/{org}/documents?project_id&parent_id&limit&offset
    POST  /organizations/{org}/documents   {title*, content, project_id, parent_id}
    PATCH /organizations/{org}/documents/{id} {title, content, parent_id}
    GET   /organizations/{org}/documents/{id}   → content is the markdown, as written

There is no EditorJS block format and no `?format=markdown` round-trip: what you
write is what you read back.

Commands:
    sync  local *.md → documents (DRY-RUN first, --apply to write)
    load  documents → one markdown bundle on stdout or a file (always read-only)
    diff  which local files would create / update / are unchanged (read-only)

stdlib only · Python 3.10+.
"""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pr" / "scripts" / "lib"))
from projekt_api import Client, Ledger, eprint  # noqa: E402
from docs import list_documents, find_by_title, project_id, _norm  # noqa: E402

PHASE = "context"
DEFAULT_PARENT = "Claude Memory"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter fields we surface, body). Only description/type are kept."""
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip().strip("'\"")
    return fields, text[m.end():]


def render(path: pathlib.Path) -> str:
    """Markdown for one memory: a lead blockquote from frontmatter, then the body."""
    raw = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(raw)
    lead = ""
    desc, typ = fm.get("description"), fm.get("type")
    if desc:
        lead = "> %s%s\n\n" % (desc, " _(%s)_" % typ if typ else "")
    return lead + body.lstrip("\n")


def ensure_parent(c: Client, docs: list[dict], pid: str | None, title: str,
                  index_body: str, icon: str, applying: bool) -> tuple[str | None, str]:
    """Find or create the parent document. Returns (id, action)."""
    parent = find_by_title(docs, title)
    if parent:
        if index_body and applying:
            c.request("PATCH", "/organizations/%s/documents/%s" % (c.org, parent["id"]),
                      {"content": index_body})
        return parent["id"], "found"
    if not applying:
        return None, "would create"
    payload = {"title": title, "content": index_body or "%s %s" % (icon, title)}
    if pid:
        payload["project_id"] = pid
    st, data = c.request("POST", "/organizations/%s/documents" % c.org, payload)
    if not (200 <= st < 300):
        raise SystemExit("✗ could not create parent %r → HTTP %s" % (title, st))
    return data.get("id"), "created"


def collect(memory_dir: pathlib.Path, index_name: str) -> tuple[list[pathlib.Path], pathlib.Path | None]:
    files = sorted(p for p in memory_dir.glob("*.md") if p.is_file())
    index = None
    if index_name:
        for p in list(files):
            if p.name == index_name:
                index, files = p, [f for f in files if f is not p]
                break
    return files, index


def cmd_sync(args, c: Client) -> int:
    memory_dir = pathlib.Path(args.memory_dir).expanduser()
    if not memory_dir.is_dir():
        raise SystemExit("✗ %s is not a directory." % memory_dir)
    files, index = collect(memory_dir, args.index)
    if not files:
        raise SystemExit("✗ No *.md files in %s." % memory_dir)

    pid = project_id(c, args.project)
    docs = list_documents(c, pid)
    index_body = render(index) if index else ""
    parent_id, parent_action = ensure_parent(c, docs, pid, args.parent, index_body,
                                             args.icon, args.apply)
    children = [d for d in docs if d.get("parent_id") == parent_id] if parent_id else []

    plan = []
    for f in files:
        body = render(f)
        hit = find_by_title(children, f.stem)
        if hit and (hit.get("content") or "") == body:
            plan.append((f, hit, "unchanged", body))
        else:
            plan.append((f, hit, "update" if hit else "create", body))

    counts = {"create": 0, "update": 0, "unchanged": 0}
    print("Context sync — org=%s  project=%s  parent=%r (%s)"
          % (c.org, args.project or "(org-level)", args.parent, parent_action))
    print("  %-9s  %-40s  %s" % ("ACTION", "TITLE (= filename stem)", "CHARS"))
    print("  " + "-" * 66)
    for f, hit, action, body in plan:
        counts[action] += 1
        print("  %-9s  %-40.40s  %d" % (action, f.stem, len(body)))
    print("\n  %d create · %d update · %d unchanged%s"
          % (counts["create"], counts["update"], counts["unchanged"],
             "  · index: %s" % index.name if index else ""))
    print("  Mode: %s" % ("APPLY (writing)" if args.apply else "DRY-RUN (no writes)"))

    stale = [d for d in children if _norm(d.get("title")) not in {_norm(f.stem) for f in files}]
    if stale:
        print("\n  ⚠ %d document(s) under the parent have no local file any more "
              "(NOT deleted — this syncs one way):" % len(stale))
        for d in stale[:10]:
            print("      · %s" % d.get("title"))

    if not args.apply:
        print("\nDRY-RUN. Re-run with --apply.")
        return 0

    led = Ledger()
    ok = bad = 0
    for f, hit, action, body in plan:
        if action == "unchanged":
            continue
        payload = {"title": f.stem, "content": body}
        if pid:
            payload["project_id"] = pid
        if parent_id:
            payload["parent_id"] = parent_id
        if hit:
            st, data = c.request("PATCH", "/organizations/%s/documents/%s" % (c.org, hit["id"]), payload)
            did = hit["id"]
        else:
            st, data = c.request("POST", "/organizations/%s/documents" % c.org, payload)
            did = data.get("id") if isinstance(data, dict) else None
        if 200 <= st < 300:
            led.add(PHASE, "memory.sync", _norm(f.stem), "updated" if hit else "created", ref=did)
            ok += 1
            print("  ✓ %-9s %s" % (action, f.stem))
        elif st == 403:
            eprint("  ✗ 403 — no write permission on this org/project. Stopping.")
            return 2
        else:
            led.add(PHASE, "memory.sync", _norm(f.stem), "error", ref=str(st))
            bad += 1
            eprint("  ✗ %-9s %s → HTTP %s" % (action, f.stem, st))
    print("\ndone  written=%d  failed=%d  unchanged=%d" % (ok, bad, counts["unchanged"]))
    return 0 if not bad else 1


def cmd_load(args, c: Client) -> int:
    pid = project_id(c, args.project)
    docs = list_documents(c, pid)
    parent = find_by_title(docs, args.parent)
    if not parent:
        raise SystemExit("✗ Parent %r not found. Run `sync` first." % args.parent)
    full = c.get_json("/organizations/%s/documents/%s" % (c.org, parent["id"]))
    children = [d for d in docs if d.get("parent_id") == parent["id"]]

    parts = ["# %s — AI context bundle" % args.parent, ""]
    if full.get("content"):
        parts += [full["content"].strip(), ""]
    for d in sorted(children, key=lambda x: (x.get("position") or 0, _norm(x.get("title")))):
        body = c.get_json("/organizations/%s/documents/%s" % (c.org, d["id"])).get("content") or ""
        parts += ["## %s" % (d.get("title") or d["id"]), "", body.strip(), ""]
    bundle = "\n".join(parts)

    if args.out:
        pathlib.Path(args.out).write_text(bundle, encoding="utf-8")
        eprint("✓ %d document(s), %d chars → %s" % (len(children) + 1, len(bundle), args.out))
    else:
        print(bundle)
    return 0


def cmd_diff(args, c: Client) -> int:
    args.apply = False
    return cmd_sync(args, c)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="contexto.py",
        description="Mirror local AI memories into Projekt Republic documents and read them back.")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = lambda sp: (
        sp.add_argument("--project", default="", help="project id | key | name (omit for org-level)"),
        sp.add_argument("--parent", default=DEFAULT_PARENT, help="parent document title"))

    ps = sub.add_parser("sync", help="local *.md → documents (dry-run by default)")
    ps.add_argument("--memory-dir", dest="memory_dir", required=True)
    common(ps)
    ps.add_argument("--index", default="MEMORY.md", help="this file becomes the PARENT body")
    ps.add_argument("--icon", default="🧠", help="used only in a created parent's placeholder body")
    ps.add_argument("--apply", action="store_true")
    ps.set_defaults(func=cmd_sync)

    pd = sub.add_parser("diff", help="what sync WOULD do (read-only alias)")
    pd.add_argument("--memory-dir", dest="memory_dir", required=True)
    common(pd)
    pd.add_argument("--index", default="MEMORY.md")
    pd.add_argument("--icon", default="🧠")
    pd.set_defaults(func=cmd_diff)

    pl = sub.add_parser("load", help="documents → one markdown bundle (read-only)")
    common(pl)
    pl.add_argument("--out", default="", help="write to a file instead of stdout")
    pl.set_defaults(func=cmd_load)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    c = Client()
    if not c.org:
        raise SystemExit("✗ No org in context. Run ../pr/scripts/auth_check.sh + context_sync.sh first.")
    return args.func(args, c)


if __name__ == "__main__":
    sys.exit(main())
