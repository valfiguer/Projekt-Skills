#!/usr/bin/env python3
"""doc_generator.py — title-keyed UPSERT of Projekt project docs + issue bitácora + PDF export.

Three sub-commands, all DRY-RUN by default (print a plan, write nothing). Pass --apply to write.

  upsert    Title-keyed UPSERT of one project doc from markdown/text → EditorJS blocks.
            GET /projects/{pid}/docs to find a doc by title; PATCH if found, else POST.
            --parent <title|uuid> nests under an existing doc (resolved by title from the list).
  bitacora  POST /issues/{iid}/bitacora/regenerate (AI logbook). 503 = SOFT-SKIP: prior
            content is left intact, never overwritten with an error.
  pdf       POST /issues/export-pdf → save the binary stream to a file (never rendered in-model).

EditorJS wire format (confirmed against the spec, schema `ProjectDoc.blocks` / `EditorJsBlock`):
  blocks is EditorJS `OutputData` → { time, version, blocks: [ { type, data }, ... ] }.
  Both POST and PATCH accept it as `oneOf: [object, string]` — a parsed object OR a JSON-encoded
  string; reads always return the parsed object. This script sends the object form.
  Each block: { type, data } where data is tool-specific —
    header    { text, level }     paragraph { text }     list { style: ordered|unordered, items: [..] }

Idempotent: re-running `upsert` updates the same title (never duplicates); the Ledger dedupes writes.

  import resolution (install-location independent — DO NOT edit):
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "projekt" / "scripts" / "lib"))
from projekt_api import Client, Ledger, slim, eprint  # noqa: E402


# ── markdown / text → EditorJS OutputData ─────────────────────────────────────

def _list_block(items: list[str], ordered: bool) -> dict:
    return {"type": "list",
            "data": {"style": "ordered" if ordered else "unordered", "items": items}}


def md_to_editorjs(text: str) -> dict:
    """Convert markdown (or plain text) to a minimal EditorJS OutputData object.

    Supported: ATX headers (#..######), `-`/`*`/`+` bullet lists, `1.` ordered lists,
    blank-line-separated paragraphs. Anything else becomes a paragraph. No inline parsing
    (EditorJS stores inline HTML; we keep the raw line, which renders fine as plain text).
    """
    blocks: list[dict] = []
    bullets: list[str] = []
    ordered: list[str] = []
    para: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append({"type": "paragraph", "data": {"text": " ".join(para).strip()}})
            para.clear()

    def flush_bullets() -> None:
        if bullets:
            blocks.append(_list_block(list(bullets), ordered=False))
            bullets.clear()

    def flush_ordered() -> None:
        if ordered:
            blocks.append(_list_block(list(ordered), ordered=True))
            ordered.clear()

    def flush_all() -> None:
        flush_para()
        flush_bullets()
        flush_ordered()

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if stripped == "":
            flush_all()
            continue

        # ATX header: 1-6 '#' then a space.
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            if 1 <= hashes <= 6 and stripped[hashes:hashes + 1] in (" ", "\t"):
                flush_all()
                blocks.append({"type": "header",
                               "data": {"text": stripped[hashes:].strip(), "level": hashes}})
                continue

        # Unordered list item.
        if stripped[:2] in ("- ", "* ", "+ "):
            flush_para()
            flush_ordered()
            bullets.append(stripped[2:].strip())
            continue

        # Ordered list item: "<n>. " or "<n>) ".
        dot = _ordered_prefix(stripped)
        if dot is not None:
            flush_para()
            flush_bullets()
            ordered.append(dot)
            continue

        # Plain text → accumulate into a paragraph.
        flush_bullets()
        flush_ordered()
        para.append(stripped)

    flush_all()
    if not blocks:  # never emit an empty tree for non-empty input
        blocks.append({"type": "paragraph", "data": {"text": text.strip()}})

    return {"time": int(time.time() * 1000), "blocks": blocks, "version": "2.30.6"}


def _ordered_prefix(s: str) -> str | None:
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    if i == 0 or i >= len(s) or s[i] not in (".", ")"):
        return None
    rest = s[i + 1:]
    if not rest[:1].isspace():
        return None
    return rest.strip()


def _block_summary(doc: dict) -> str:
    types: dict[str, int] = {}
    for b in doc.get("blocks", []):
        types[b["type"]] = types.get(b["type"], 0) + 1
    return ", ".join("%s×%d" % (t, n) for t, n in types.items()) or "(empty)"


# ── doc listing / title resolution ────────────────────────────────────────────

def _norm(title: str) -> str:
    return " ".join(title.split()).casefold()


def list_docs(c: Client, pid: str) -> list[dict]:
    data = c.get_json("/projects/%s/docs?include_archived=1" % pid)
    return slim("doc", data)  # [{id,title,parent_doc_id,is_archived}]


def find_by_title(docs: list[dict], title: str) -> dict | None:
    want = _norm(title)
    hits = [d for d in docs if _norm(d.get("title") or "") == want]
    return hits[0] if hits else None


def resolve_parent(docs: list[dict], parent: str | None) -> tuple[str | None, str | None]:
    """Return (parent_id, error). `parent` may be a uuid (used as-is) or a title (looked up)."""
    if not parent:
        return None, None
    by_id = next((d for d in docs if d.get("id") == parent), None)
    if by_id:
        return by_id["id"], None
    by_title = find_by_title(docs, parent)
    if by_title:
        return by_title["id"], None
    return None, ("parent not found by title or id: %r" % parent)


# ── body source loading ───────────────────────────────────────────────────────

def load_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return pathlib.Path(args.body_file).read_text(encoding="utf-8")
    if args.body == "-":
        return sys.stdin.read()
    return args.body or ""


# ── sub-command: upsert ───────────────────────────────────────────────────────

def resolve_project_id(c: Client, raw: str) -> str:
    """Map a project id/key/name to its UUID via the cached context (falls back to raw)."""
    raw = (raw or "").strip()
    projects = c.context().get("projects", [])
    for p in projects:
        if raw in (p.get("id"), p.get("key"), p.get("name")):
            return p.get("id")
    low = raw.lower()
    for p in projects:
        if low in ((p.get("key") or "").lower(), (p.get("name") or "").lower()):
            return p.get("id")
    return raw  # assume it is already a UUID


def cmd_upsert(c: Client, led: Ledger, args: argparse.Namespace) -> int:
    pid = resolve_project_id(c, args.project)
    title = args.title.strip()
    if not title:
        eprint("✗ --title is required and must be non-empty.")
        return 2

    raw = load_body(args)
    editor = md_to_editorjs(raw)

    docs = list_docs(c, pid)
    existing = find_by_title(docs, title)
    parent_id, perr = resolve_parent(docs, args.parent)
    if perr:
        eprint("✗ %s" % perr)
        eprint("  Available doc titles: %s"
               % (", ".join(repr(d.get("title")) for d in docs[:20]) or "(none)"))
        return 2

    action = "UPDATE (PATCH)" if existing else "CREATE (POST)"
    print("Doc UPSERT plan  · org %s · project %s" % (c.org or "(none)", pid))
    print("  title   : %r" % title)
    print("  action  : %s%s" % (action, ("  → %s" % existing["id"]) if existing else ""))
    print("  parent  : %s" % (("%s → %s" % (args.parent, parent_id)) if parent_id else "(root)"))
    print("  blocks  : %d  [%s]" % (len(editor["blocks"]), _block_summary(editor)))

    dedupe_key = "%s|%s" % (pid, _norm(title))
    if led.seen("doc.upsert", dedupe_key):
        print("  ↩ already upserted this run-set (ledger) — skipping.")
        return 0

    if not args.apply:
        print("\nDRY-RUN — no write performed. Re-run with --apply to write.")
        return 0

    print("\nfingerprint %s" % c.fingerprint())
    if existing:
        body: dict = {"title": title, "blocks": editor}
        if args.parent is not None:
            body["parent_doc_id"] = parent_id  # explicit move (or null to lift to root)
        st, data = c.request("PATCH", "/projects/%s/docs/%s" % (pid, existing["id"]), body)
        op_status, ref = ("updated", existing["id"])
    else:
        body = {"title": title, "blocks": editor}
        if parent_id:
            body["parent_doc_id"] = parent_id
        if args.icon:
            body["icon"] = args.icon
        st, data = c.request("POST", "/projects/%s/docs" % pid, body)
        op_status, ref = ("created", _doc_id(data))

    if 200 <= st < 300:
        led.add("docs", "doc.upsert", dedupe_key, op_status, ref=ref)
        print("✓ %s — doc %s (HTTP %s)" % (op_status, ref, st))
        return 0

    led.add("docs", "doc.upsert", dedupe_key, "error", ref="HTTP %s" % st)
    eprint("✗ %s failed (HTTP %s): %s" % (action, st, _err(data)))
    if st == 403:
        eprint("  403 = no write permission on this project, or cross-org token. See references/errors.md.")
    return 1


def _doc_id(data) -> str | None:
    if isinstance(data, dict):
        return data.get("id") or (data.get("data") or {}).get("id")
    return None


# ── sub-command: bitacora ─────────────────────────────────────────────────────

def cmd_bitacora(c: Client, led: Ledger, args: argparse.Namespace) -> int:
    iids = _split_ids(args.issue_ids)
    if not iids:
        eprint("✗ pass at least one issue id (comma-separated).")
        return 2

    print("Bitácora regenerate plan · org %s · locale %s" % (c.org or "(none)", args.locale))
    print("  issues  : %d" % len(iids))
    for iid in iids:
        print("    - %s%s" % (iid, "  (done this run-set)" if led.seen("bitacora", iid) else ""))
    print("  policy  : 503 (AI quota) = SOFT-SKIP — prior content kept, never overwritten.")

    if not args.apply:
        print("\nDRY-RUN — no write performed. Re-run with --apply to regenerate.")
        return 0

    print("\nfingerprint %s" % c.fingerprint())
    ok = skipped = failed = 0
    for iid in iids:
        if led.seen("bitacora", iid):
            print("  ↩ %s already regenerated — skipping." % iid)
            continue
        path = "/issues/%s/bitacora/regenerate?locale=%s" % (iid, args.locale)
        st, data = c.request("POST", path, body={})
        if st == 503:
            led.add("docs", "bitacora", iid, "skipped", ref="503 AI quota")
            print("  ⚠ %s — 503 AI quota/unavailable; SOFT-SKIP (prior bitácora intact)." % iid)
            skipped += 1
        elif 200 <= st < 300:
            led.add("docs", "bitacora", iid, "ok", ref="regenerated")
            stale = isinstance(data, dict) and data.get("stale")
            print("  ✓ %s — regenerated%s." % (iid, " (still marked stale)" if stale else ""))
            ok += 1
        else:
            led.add("docs", "bitacora", iid, "error", ref="HTTP %s" % st)
            eprint("  ✗ %s — HTTP %s: %s" % (iid, st, _err(data)))
            failed += 1

    print("\nbitácora: %d ok · %d soft-skipped (503) · %d failed" % (ok, skipped, failed))
    return 0 if failed == 0 else 1


# ── sub-command: pdf (binary stream → file) ───────────────────────────────────

def cmd_pdf(c: Client, led: Ledger, args: argparse.Namespace) -> int:
    iids = _split_ids(args.issue_ids)
    if not iids:
        eprint("✗ pass at least one issue id (comma-separated).")
        return 2

    out = pathlib.Path(args.out or ("issues-export.%s" % args.format))
    body = {
        "issue_ids": iids,
        "mode": args.mode,
        "format": args.format,
        "include_comments": not args.no_comments,
        "include_attachments": not args.no_attachments,
        "title": args.title,
    }

    print("Issue export plan · org %s" % (c.org or "(none)"))
    print("  issues  : %d  %s" % (len(iids), iids if len(iids) <= 8 else "(%d ids)" % len(iids)))
    print("  format  : %s   mode: %s   title: %r" % (args.format, args.mode, args.title))
    print("  include : comments=%s attachments=%s"
          % (not args.no_comments, not args.no_attachments))
    print("  out     : %s  (binary artifact — saved to disk, NOT rendered in-model)" % out)

    if not args.apply:
        print("\nDRY-RUN — no request performed. Re-run with --apply to export.")
        return 0

    print("\nfingerprint %s" % c.fingerprint())
    # The shared Client decodes the body as text, which would corrupt a PDF. Issue a
    # dedicated request that keeps the raw bytes, reusing the client's token/org/base.
    raw, st, ctype = _request_bytes(c, "POST", "/issues/export-pdf", body)
    if st is None or not (200 <= st < 300):
        led.add("docs", "pdf.export", out.name, "error", ref="HTTP %s" % st)
        eprint("✗ export failed (HTTP %s): %s"
               % (st, raw.decode("utf-8", "replace")[:300] if raw else "(no body)"))
        return 1

    out.write_bytes(raw)
    led.add("docs", "pdf.export", out.name, "ok", ref="%d bytes" % len(raw))
    print("✓ wrote %s (%d bytes, %s)" % (out, len(raw), ctype or "?"))
    return 0


# ── shared helpers ────────────────────────────────────────────────────────────

def _split_ids(s: str) -> list[str]:
    return [x.strip() for x in (s or "").replace("\n", ",").split(",") if x.strip()]


def _err(data) -> str:
    if isinstance(data, dict):
        return data.get("message") or data.get("error") or json.dumps(data)
    return str(data)[:300]


def _request_bytes(c: Client, method: str, path: str, body):
    """Like Client.request but returns RAW bytes (for binary streams). Honors 429/5xx retry.

    Reuses the client's resolved token/org/base and the same dual auth headers.
    """
    url = c.base + path
    payload = json.dumps(body).encode() if body is not None else None
    from projekt_api import MAX_RETRIES, _backoff  # same backoff policy as the client
    for attempt in range(1, MAX_RETRIES + 2):
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Authorization", "Bearer " + c.token)
        req.add_header("X-Auth-Token", c.token)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/pdf, text/markdown, */*")
        if c.org:
            req.add_header("X-Org-Id", c.org)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), r.status, r.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            raw = e.read()
            if (e.code == 429 or 500 <= e.code <= 599) and attempt <= MAX_RETRIES:
                wait = _backoff(e.headers, attempt)
                eprint("  ⏳ %s on %s — retry %d/%d in %ds" % (e.code, path, attempt, MAX_RETRIES, wait))
                time.sleep(wait)
                continue
            return raw, e.code, e.headers.get("Content-Type")
        except urllib.error.URLError as e:
            if attempt > MAX_RETRIES:
                eprint("✗ Network error on %s %s: %s" % (method, path, e))
                return b"", None, None
            time.sleep(attempt * attempt)
    return b"", None, None


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="doc_generator.py",
        description="Title-keyed UPSERT of Projekt project docs + issue bitácora + PDF export. "
                    "DRY-RUN by default; pass --apply to write.")
    sub = p.add_subparsers(dest="cmd", required=True)
    # --apply lives on each sub-command (consistent with the other projekt-* skills:
    # `<cmd> … --apply`). Dry-run is the default everywhere.

    u = sub.add_parser("upsert", help="UPSERT a project doc by title (PATCH if exists, else POST).")
    u.add_argument("--project", required=True, help="Project id, key or name (resolved from cached context).")
    u.add_argument("--title", required=True, help="Doc title — the idempotency key.")
    src = u.add_mutually_exclusive_group()
    src.add_argument("--body", default="",
                     help="Markdown/plain text body. Use '-' to read from stdin.")
    src.add_argument("--body-file", help="Path to a markdown/text file for the body.")
    u.add_argument("--parent", help="Nest under this doc (title or UUID). Resolved from the doc list.")
    u.add_argument("--icon", help="Optional emoji/short id (≤8 chars), used on CREATE only.")
    u.add_argument("--apply", action="store_true", help="Execute writes (default: dry-run).")
    u.set_defaults(func=cmd_upsert)

    b = sub.add_parser("bitacora", help="Regenerate the AI bitácora for one or more issues.")
    b.add_argument("--issue-ids", required=True, dest="issue_ids",
                   help="Comma-separated issue UUIDs.")
    b.add_argument("--locale", default="es", help="Bitácora locale (default es).")
    b.add_argument("--apply", action="store_true", help="Execute writes (default: dry-run).")
    b.set_defaults(func=cmd_bitacora)

    d = sub.add_parser("pdf", help="Export issues as a PDF/markdown artifact saved to disk.")
    d.add_argument("--issue-ids", required=True, dest="issue_ids",
                   help="Comma-separated issue UUIDs.")
    d.add_argument("--format", choices=["pdf", "md"], default="pdf", help="Output format.")
    d.add_argument("--mode", choices=["report", "claude"], default="report",
                   help="report = human digest; claude = LLM-oriented.")
    d.add_argument("--out", help="Output file path (default issues-export.<format>).")
    d.add_argument("--title", default="Task Report", help="Document title in the export.")
    d.add_argument("--no-comments", action="store_true", help="Exclude comments.")
    d.add_argument("--no-attachments", action="store_true", help="Exclude attachments.")
    d.add_argument("--apply", action="store_true", help="Execute writes (default: dry-run).")
    d.set_defaults(func=cmd_pdf)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    c = Client()
    led = Ledger()
    return args.func(c, led, args)


if __name__ == "__main__":
    raise SystemExit(main())
