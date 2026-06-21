#!/usr/bin/env python3
"""context_store.py — mirror a memory directory into Projekt docs, and load it back as ONE
markdown bundle.

The AI-context store (Serena-style): keep a codebase's context memories (architecture, gotchas,
conventions, runbooks) as Projekt docs so any AI provider (Claude Code, Codex, …) reads them
cheaply over the API — `?format=markdown` — instead of crawling the whole repo and burning tokens.

  sync   Title-keyed UPSERT of every *.md in a directory as a doc under a parent (default
         "Claude Memory"), one doc per file. Idempotent: re-running PATCHes the same titles,
         never duplicates. Markdown is sent as-is (the server converts it to rich EditorJS
         blocks); YAML frontmatter is parsed and rendered cleanly instead of flattened.
  load   Fetch the parent's child docs as one concatenated markdown bundle — the cheap
         onboarding read an agent does once at the start of a session.

`sync` is DRY-RUN by default (prints a plan, writes nothing); pass --apply to write. `load` is
read-only and always runs.

  import resolution (install-location independent — DO NOT edit):
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "projekt" / "scripts" / "lib"))
from projekt_api import Client, eprint  # noqa: E402

CONTEXT_JSON = pathlib.Path(".projekt-run/context.json")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ── helpers ───────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a leading `--- … ---` YAML block off the body. Returns (meta, body).

    Frontmatter is intentionally NOT sent to the doc verbatim (EditorJS has no concept of it,
    so it would flatten into an ugly paragraph). The useful keys are rendered as a clean lead
    blockquote instead.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[m.end():].lstrip("\n")


def render_body(meta: dict, body: str) -> str:
    """Prepend a clean one-line context header (type · description) to the body."""
    bits = []
    if meta.get("description"):
        bits.append(meta["description"])
    type_ = meta.get("type") or (meta.get("metadata", {}) or {}).get("type")
    if isinstance(type_, str) and type_:
        bits.append("_(%s)_" % type_)
    header = ("> " + " ".join(bits) + "\n\n") if bits else ""
    return header + body


def doc_title(path: pathlib.Path, meta: dict) -> str:
    """Idempotency key: the filename stem — stable, unique, 1:1 with the file. (The
    frontmatter `name:` slug is intentionally NOT used: it may differ in case/separators
    and would split the same memory across two docs on re-sync.)"""
    return path.stem


def resolve_project_id(raw: str) -> str:
    """Resolve a project id|key|name to its id via the cached context, else pass through."""
    if CONTEXT_JSON.exists():
        try:
            ctx = json.loads(CONTEXT_JSON.read_text())
            for p in ctx.get("projects", []) or []:
                if raw in (p.get("id"), p.get("key"), p.get("name")):
                    return p.get("id")
        except Exception:
            pass
    return raw


def list_docs(c: Client, pid: str) -> list[dict]:
    st, data = c.request("GET", "/projects/%s/docs?include_archived=1" % pid)
    if not (200 <= (st or 0) < 300):
        eprint("✗ could not list docs (HTTP %s)" % st)
        return []
    if isinstance(data, list):
        return data
    for k in ("data", "docs"):
        if isinstance(data, dict) and isinstance(data.get(k), list):
            return data[k]
    return []


def find_by_title(docs: list[dict], title: str) -> dict | None:
    t = title.strip().lower()
    for d in docs:
        if (d.get("title") or "").strip().lower() == t:
            return d
    return None


def upsert(c: Client, pid: str, title: str, markdown: str, parent_id: str | None,
           docs: list[dict], icon: str | None = None) -> tuple[str, str | None, int]:
    existing = find_by_title(docs, title)
    body: dict = {"title": title, "markdown": markdown}
    if parent_id:
        body["parent_doc_id"] = parent_id
    if existing:
        st, data = c.request("PATCH", "/projects/%s/docs/%s" % (pid, existing["id"]), body)
        return "updated", existing["id"], st
    if icon:
        body["icon"] = icon
    st, data = c.request("POST", "/projects/%s/docs" % pid, body)
    did = data.get("id") if isinstance(data, dict) else None
    return "created", did, st


# ── sync ──────────────────────────────────────────────────────────────────────

def cmd_sync(c: Client, args: argparse.Namespace) -> int:
    pid = resolve_project_id(args.project)
    mem = pathlib.Path(args.memory_dir).expanduser()
    if not mem.is_dir():
        eprint("✗ --memory-dir not a directory: %s" % mem)
        return 2

    index_name = args.index.lower()
    files = sorted(p for p in mem.glob("*.md") if p.name.lower() != index_name)
    index_file = next((p for p in mem.glob("*.md") if p.name.lower() == index_name), None)

    print("Context SYNC plan · org %s · project %s" % (c.org or "(none)", pid))
    print("  memory dir : %s" % mem)
    print("  parent     : %r" % args.parent)
    print("  index→parent body : %s" % (index_file.name if index_file else "(none)"))
    print("  memories   : %d .md files" % len(files))

    if not args.apply:
        print("\nDRY-RUN — no write performed. Re-run with --apply to write.")
        return 0

    print("\nfingerprint %s" % c.fingerprint())
    docs = list_docs(c, pid)

    # 1. Ensure the parent exists; seed/refresh its body from the index file.
    parent = find_by_title(docs, args.parent)
    parent_md = index_file.read_text() if index_file else "# %s\n\nAI context store." % args.parent
    pstatus, parent_id, pst = upsert(c, pid, args.parent, parent_md, None, docs, icon=args.icon)
    if not (200 <= pst < 300) or not parent_id:
        eprint("✗ parent upsert failed (HTTP %s)" % pst)
        return 1
    print("  parent %s → %s" % (pstatus, parent_id))
    if not parent:  # newly created — add it so children resolve against a fresh list
        docs.append({"id": parent_id, "title": args.parent})

    # 2. UPSERT one child per memory file.
    created = updated = failed = 0
    for f in files:
        meta, body = parse_frontmatter(f.read_text())
        title = doc_title(f, meta)
        status, ref, st = upsert(c, pid, title, render_body(meta, body), parent_id, docs)
        if 200 <= st < 300:
            created += status == "created"
            updated += status == "updated"
        else:
            failed += 1
            eprint("  ✗ %s (HTTP %s)" % (title, st))
    print("\n✓ sync done — created=%d updated=%d failed=%d (under %r)"
          % (created, updated, failed, args.parent))
    return 1 if failed else 0


# ── load ──────────────────────────────────────────────────────────────────────

def cmd_load(c: Client, args: argparse.Namespace) -> int:
    pid = resolve_project_id(args.project)
    docs = list_docs(c, pid)
    parent = find_by_title(docs, args.parent)
    if not parent:
        eprint("✗ parent doc %r not found in project %s" % (args.parent, pid))
        return 2
    children = [d for d in docs if d.get("parent_doc_id") == parent["id"]
                and not d.get("is_archived")]
    children.sort(key=lambda d: (d.get("title") or "").lower())

    out: list[str] = ["# %s — AI context bundle" % args.parent,
                      "> %d memories · read this once to skip crawling the repo\n" % len(children)]
    # parent body (the index) first
    st, pdoc = c.request("GET", "/projects/%s/docs/%s?format=markdown" % (pid, parent["id"]))
    if isinstance(pdoc, dict) and pdoc.get("markdown"):
        out.append(pdoc["markdown"].strip() + "\n")
    for d in children:
        st, full = c.request("GET", "/projects/%s/docs/%s?format=markdown" % (pid, d["id"]))
        md = full.get("markdown", "") if isinstance(full, dict) else ""
        out.append("\n---\n\n## %s\n\n%s" % (d.get("title") or "(untitled)", md.strip()))
    bundle = "\n".join(out)
    if args.out:
        pathlib.Path(args.out).write_text(bundle)
        print("✓ wrote %d chars to %s (%d memories)" % (len(bundle), args.out, len(children)))
    else:
        sys.stdout.write(bundle + "\n")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="context_store.py",
        description="Mirror a memory dir into Projekt docs (sync) and read it back as one "
                    "markdown bundle (load). sync is DRY-RUN by default; pass --apply.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync", help="UPSERT every *.md in a dir as a doc under a parent.")
    s.add_argument("--project", required=True, help="Project id, key or name.")
    s.add_argument("--memory-dir", required=True, dest="memory_dir",
                   help="Directory of *.md memory files.")
    s.add_argument("--parent", default="Claude Memory", help="Parent doc title (default 'Claude Memory').")
    s.add_argument("--index", default="MEMORY.md",
                   help="Filename used as the parent body instead of a child (default MEMORY.md).")
    s.add_argument("--icon", default="🧠", help="Parent icon on CREATE (default 🧠).")
    s.add_argument("--apply", action="store_true", help="Execute writes (default: dry-run).")
    s.set_defaults(func=cmd_sync)

    l = sub.add_parser("load", help="Concatenate the parent's child docs into one markdown bundle.")
    l.add_argument("--project", required=True, help="Project id, key or name.")
    l.add_argument("--parent", default="Claude Memory", help="Parent doc title (default 'Claude Memory').")
    l.add_argument("--out", help="Write the bundle to a file instead of stdout.")
    l.set_defaults(func=cmd_load)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(Client(), args)


if __name__ == "__main__":
    raise SystemExit(main())
