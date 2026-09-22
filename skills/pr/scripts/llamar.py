#!/usr/bin/env python3
"""llamar.py — call ANY of the API's 917 operations, safely and with a budget.

The catalogue says what exists; spec_lookup.sh says what shape it takes; this
calls it. Together they make the whole surface reachable without a wrapper
script per domain, and without hand-written curl that gets the path wrong.

    llamar.py GET  "«O»/crm/deals" --query limit=10
    llamar.py GET  "«O»/finance/invoices" --query status=sent --query limit=5
    llamar.py POST "«O»/crm/deals" --body '{"title":"Acme","value":1000}'          # dry-run
    llamar.py POST "«O»/crm/deals" --body @deal.json --apply
    llamar.py PATCH "«O»/crm/deals/{deal_id}" --path deal_id=… --body '{"stage":"won"}' --apply

Four things it does that a raw curl does not:

1. **Validates against the spec before sending.** An unknown path or an unknown
   method fails locally with a suggestion, instead of a 404 you then debug.
2. **Dry-run by default.** Anything that is not a GET prints the request and
   writes nothing until `--apply`.
3. **Refuses sensitive operations without `--admit`.** Sensitivity comes from the
   operation's own `x-tool.sensitive`, not from a list maintained here. Every
   DELETE needs `--admit` too, whatever the spec says about it.
4. **Caps the output.** A response is truncated to --max-bytes (default 4000) and
   says how much it cut. A full list of invoices dumped into a transcript is paid
   for on every later turn; see the context rules in the repo's CLAUDE.md.

`«O»` expands to /api/v1/organizations/{org_id}, and `{org_id}` / `{project_id}`
are filled from .projekt-run/context.json unless given with --path.

stdlib only · Python 3.10+ · never prints the token.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from projekt_api import Client, Ledger, eprint  # noqa: E402

ORG_PREFIX = "/api/v1/organizations/{org_id}"
VERBS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PHASE = "llamar"


def load_spec() -> dict:
    for c in (os.environ.get("PROJEKT_SPEC"),
              os.path.join(os.environ.get("PJ_SPEC_DIR",
                           os.path.expanduser("~/.cache/3xa-projekt")), "projekt.json")):
        if c and pathlib.Path(c).is_file():
            return json.loads(pathlib.Path(c).read_text())
    raise SystemExit("✗ No spec cached. Run: bash \"$(dirname $0)/fetch_spec.sh\"")


def resolve_template(spec: dict, raw: str) -> str:
    """Find the spec path this argument means. Accepts «O» and a missing /api/v1."""
    want = raw.replace("«O»", ORG_PREFIX)
    paths = spec.get("paths", {})
    for cand in (want, "/api/v1" + want, want.replace("/api/v1", "", 1)):
        if cand in paths:
            return cand
    tail = want.rstrip("/").split("/")[-1]
    near = [p for p in paths if tail and tail in p][:6]
    msg = "✗ No such path: %s" % raw
    if near:
        msg += "\n  Did you mean:\n" + "\n".join("    " + p.replace(ORG_PREFIX, "«O»") for p in near)
    msg += "\n  Search the catalogue: spec_lookup.sh --search %s" % (tail or "…")
    raise SystemExit(msg)


def fill(template: str, c: Client, overrides: dict[str, str]) -> str:
    """Substitute {placeholders} from --path, then from the cached context."""
    defaults = {"org_id": c.org, "organization_id": c.org, "project_id": c.project}
    out, missing = template, []
    for ph in re.findall(r"\{([a-zA-Z_]+)\}", template):
        val = overrides.get(ph) or defaults.get(ph)
        if not val:
            missing.append(ph)
        else:
            out = out.replace("{%s}" % ph, urllib.parse.quote(str(val), safe=""))
    if missing:
        raise SystemExit("✗ Missing path parameter(s): %s\n  Pass them: %s"
                         % (", ".join(missing), " ".join("--path %s=…" % m for m in missing)))
    return out


def read_body(raw: str | None):
    if raw is None:
        return None
    if raw == "-":
        raw = sys.stdin.read()
    elif raw.startswith("@"):
        raw = pathlib.Path(raw[1:]).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit("✗ --body is not valid JSON: %s" % e)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="llamar.py",
        description="Call any operation in the catalogue. Dry-run by default for writes.")
    ap.add_argument("method", choices=VERBS + tuple(v.lower() for v in VERBS))
    ap.add_argument("path", help="spec path, e.g. \"«O»/crm/deals\" or the full /api/v1/... form")
    ap.add_argument("--path", dest="path_params", action="append", default=[],
                    metavar="NAME=VALUE", help="fill a {placeholder}; repeatable")
    ap.add_argument("--query", action="append", default=[], metavar="K=V",
                    help="query parameter; repeatable")
    ap.add_argument("--body", help="JSON string, @file.json, or - for stdin")
    ap.add_argument("--apply", action="store_true", help="execute a write (default: dry-run)")
    ap.add_argument("--admit", action="store_true",
                    help="required for sensitive operations and every DELETE")
    ap.add_argument("--max-bytes", type=int, default=4000,
                    help="truncate the printed response (default 4000; 0 = no cap)")
    ap.add_argument("--out", help="write the full response to a file instead of truncating")
    args = ap.parse_args()

    method = args.method.upper()
    spec = load_spec()
    template = resolve_template(spec, args.path)
    op = spec["paths"][template].get(method.lower())
    if not isinstance(op, dict):
        have = ", ".join(k.upper() for k in spec["paths"][template] if k.upper() in VERBS)
        raise SystemExit("✗ %s has no %s. It has: %s" % (args.path, method, have or "nothing"))

    xt = op.get("x-tool") if isinstance(op.get("x-tool"), dict) else {}
    sensitive = bool(xt.get("sensitive"))
    c = Client()
    if not c.org:
        raise SystemExit("✗ No org in context. Run auth_check.sh + context_sync.sh first.")

    overrides = dict(p.split("=", 1) for p in args.path_params if "=" in p)
    path = fill(template, c, overrides)
    # Spec paths carry the /api/v1 prefix; Client.base already ends in it. Sending
    # both yields /api/v1/api/v1/... and a 404 that reads like a missing endpoint.
    base_tail = "/" + c.base.rstrip("/").split("/", 3)[-1] if c.base.count("/") > 2 else ""
    if base_tail and path.startswith(base_tail + "/"):
        path = path[len(base_tail):]
    qs = "&".join(urllib.parse.quote(k, safe="") + "=" + urllib.parse.quote(v, safe="")
                  for k, v in (q.split("=", 1) for q in args.query if "=" in q))
    if qs:
        path += ("&" if "?" in path else "?") + qs
    body = read_body(args.body)

    print("%s %s" % (method, template.replace(ORG_PREFIX, "«O»")))
    print("  summary:   %s" % (op.get("summary") or "—"))
    print("  domain:    %s%s" % (xt.get("domain") or "(no x-tool — not in the MCP catalogue)",
                                 "  ⚠ SENSITIVE" if sensitive else ""))
    print("  url:       %s%s" % (c.base, path))
    if body is not None:
        print("  body keys: %s" % ", ".join(sorted(body)) if isinstance(body, dict) else "  body: (not an object)")

    needs_admit = sensitive or method == "DELETE"
    if needs_admit and not args.admit:
        why = "marked sensitive in the spec" if sensitive else "a DELETE"
        raise SystemExit("\n✗ Refusing: this operation is %s. Re-run with --admit once the user "
                         "has confirmed, in their own words, what it will change." % why)

    if method != "GET" and not args.apply:
        print("\nDRY-RUN. Nothing was sent. Re-run with --apply%s."
              % (" --admit" if needs_admit else ""))
        return 0

    st, data = c.request(method, path, body)
    print("\nHTTP %s" % st)
    text = json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data

    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print("  %d chars → %s" % (len(text), args.out))
    elif args.max_bytes and len(text) > args.max_bytes:
        print(text[: args.max_bytes])
        print("\n  … truncated: %d of %d chars shown. Narrow it with --query limit=…, "
              "or pass --out FILE for the whole thing." % (args.max_bytes, len(text)))
    else:
        print(text)

    if method != "GET" and 200 <= st < 300:
        Ledger().add(PHASE, method.lower() + ":" + template, path, "ok")
    return 0 if 200 <= st < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
