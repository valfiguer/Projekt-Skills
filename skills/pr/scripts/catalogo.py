#!/usr/bin/env python3
"""catalogo.py — build the catalogue of everything the API offers, from the spec.

The point is that this is GENERATED. The previous hand-written endpoint notes
drifted until five of eight skills pointed at endpoints that no longer existed.
A catalogue that regenerates from the spec cannot drift: re-run it and the
numbers are today's.

Two artifacts, deliberately different in size and purpose:

  --md   A human map: the domains, what is in each, how many operations, how
         many are sensitive, and which pr-* script already covers them.
         Small enough to read (~8 KB) and meant for `references/catalogo.md`.

  --tsv  The full index, one line per operation:
             METHOD <tab> path <tab> domain <tab> profile <tab> S|- <tab> tags <tab> summary
         ~917 lines. This is meant to be GREPPED, never read into a model
         context. It lands in the spec cache next to the spec itself and is what
         `spec_lookup.sh --search/--domain/--sensitive` reads.

Domains come from each operation's `x-tool` extension, which is the product's
own taxonomy (the same one that decides what the MCP connector exposes). Note
that the spec SERVED by FastAPI strips `x-tool`; the portal bundle keeps it, so
fetch_spec.sh pulls from the portal on purpose.

stdlib only · Python 3.10+.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter, defaultdict

VERBS = ("get", "post", "put", "patch", "delete")
ORG = "/api/v1/organizations/{org_id}"

# Which pr-* script already drives a path. Patterns are matched against the path
# with the org prefix collapsed to «O». Order matters: first match wins.
COVERAGE = [
    (r"^/api/v1/auth/me$",                      "pr · auth_check.sh"),
    (r"^/api/v1/organizations$",                "pr · auth_check.sh"),
    (r"^«O»/projects$",                         "pr · context_sync.sh"),
    (r"^«O»/members$",                          "pr · context_sync.sh"),
    (r"^«O»/projects/\{project_id\}/tasks/bulk$", "pr · mover.py"),
    (r"^«O»/projects/\{project_id\}/tasks/by-number", "pr · tiempo.py, mover.py"),
    (r"^«O»/projects/\{project_id\}/tasks/\{task_id\}/activity$", "pr-docs · docs.py"),
    (r"^«O»/projects/\{project_id\}/tasks",     "pr · tareas.py, mover.py"),
    (r"^«O»/time-entries",                      "pr · tiempo.py"),
    (r"^«O»/workforce/capacity$",               "pr-informes · cargas.py"),
    (r"^«O»/dashboard/stats$",                  "pr-informes · cargas.py"),
    (r"^«O»/projects/\{project_id\}/sprints",   "pr-informes · estimaciones.py"),
    (r"^«O»/sprints/",                          "pr-informes · estimaciones.py"),
    (r"^«O»/roadmap$",                          "pr-informes · estimaciones.py"),
    (r"^«O»/documents",                         "pr-docs · docs.py, contexto.py"),
    (r"^«O»/export$",                           "pr-docs · docs.py"),
]

# One line each, so the map says what a domain IS rather than only naming it.
DOMAIN_BLURB = {
    "pm":          "Projects, tasks, sprints, boards, tags, roadmap — the core of the product.",
    "finance":     "Invoices, quotes, expenses, suppliers, contracts, profitability, fiscal export.",
    "crm":         "Leads, deals, pipelines, clients, activities and the funnel analytics.",
    "hr":          "Employees, departments, leave, absences, payroll and workforce capacity.",
    "support":     "Support requests, SLAs and the client-facing portal.",
    "crossorg":    "Shared projects and channels between organizations.",
    "context":     "The Context Fabric surface: capsules, projections and retrieval.",
    "docs":        "Documents, folders, templates, versions and publication.",
    "admin":       "Organization settings, roles, API keys, members and invites.",
    "calendar":    "Calendars, events and meetings.",
    "okr":         "Objectives and key results.",
    "org":         "Organization identity and the caller's own membership.",
    "bi":          "Dashboards and widgets built on the org's data.",
    "automations": "Rules that fire on events.",
    "search":      "Cross-domain search.",
    "attachments": "File upload and download on tasks and other records.",
}


def load_spec(path: str | None) -> dict:
    candidates = [path] if path else []
    candidates += [os.environ.get("PROJEKT_SPEC"),
                   os.path.join(os.environ.get("PJ_SPEC_DIR",
                                os.path.expanduser("~/.cache/3xa-projekt")), "projekt.json")]
    for c in candidates:
        if c and pathlib.Path(c).is_file():
            return json.loads(pathlib.Path(c).read_text())
    raise SystemExit("✗ No spec found. Run fetch_spec.sh first, or pass --spec <file>.")


def short(path: str) -> str:
    return path.replace(ORG, "«O»")


def covered_by(path: str) -> str:
    s = short(path)
    for pat, who in COVERAGE:
        if re.search(pat, s):
            return who
    return ""


def operations(spec: dict):
    for path, item in sorted(spec.get("paths", {}).items()):
        if not isinstance(item, dict):
            continue
        for verb in VERBS:
            op = item.get(verb)
            if not isinstance(op, dict):
                continue
            xt = op.get("x-tool") if isinstance(op.get("x-tool"), dict) else {}
            yield {
                "method": verb.upper(),
                "path": path,
                "short": short(path),
                "domain": xt.get("domain") or "",
                "profile": xt.get("profile") or "",
                "tool": xt.get("name") or "",
                "sensitive": bool(xt.get("sensitive")),
                "tags": op.get("tags") or [],
                "summary": (op.get("summary") or "").replace("\t", " ").replace("\n", " "),
                "covered": covered_by(path),
            }


def emit_tsv(ops, out) -> int:
    n = 0
    for o in ops:
        out.write("\t".join([
            o["method"], o["short"], o["domain"] or "-", o["profile"] or "-",
            "S" if o["sensitive"] else "-", ",".join(o["tags"]) or "-",
            o["covered"] or "-", o["summary"],
        ]) + "\n")
        n += 1
    return n


def emit_md(ops) -> str:
    ops = list(ops)
    total = len(ops)
    tooled = [o for o in ops if o["domain"]]
    sens = [o for o in tooled if o["sensitive"]]
    cov = [o for o in ops if o["covered"]]
    paths = len({o["path"] for o in ops})

    by_dom: dict[str, list] = defaultdict(list)
    for o in tooled:
        by_dom[o["domain"]].append(o)
    untooled: Counter = Counter()
    for o in ops:
        if not o["domain"]:
            for t in (o["tags"] or ["(untagged)"]):
                untooled[t] += 1

    L = [
        "# The catalogue — everything the API offers",
        "",
        "**Generated** by `scripts/catalogo.py` from the cached spec. Do not edit by hand: "
        "re-run `bash scripts/fetch_spec.sh && python3 scripts/catalogo.py --md` and the numbers "
        "are today's. The previous hand-written notes drifted until five of eight skills pointed "
        "at endpoints that no longer existed.",
        "",
        f"**{paths} paths · {total} operations · {len(by_dom)} domains.** "
        f"{len(tooled)} operations carry an `x-tool` (these are the ones the MCP connector can "
        f"expose), of which **{len(sens)} are marked sensitive**. The remaining "
        f"**{total - len(tooled)} have no `x-tool`**: they work over HTTP exactly like the rest, "
        f"but they are invisible to the MCP catalogue, to profile selection and to Kern.",
        "",
        f"A `pr-*` script already drives **{len(cov)}** of them. Everything else is reachable "
        "today with `spec_lookup.sh` + `pj_req` — being uncovered means there is no convenience "
        "wrapper, not that it is out of reach.",
        "",
        "## Domains",
        "",
        "| Domain | Ops | Sensitive | Covered | What is in it |",
        "|---|--:|--:|--:|---|",
    ]
    for dom, rows in sorted(by_dom.items(), key=lambda kv: -len(kv[1])):
        s = sum(1 for r in rows if r["sensitive"])
        c = sum(1 for r in rows if r["covered"])
        L.append(f"| `{dom}` | {len(rows)} | {s} | {c} | {DOMAIN_BLURB.get(dom, '—')} |")
    L += ["", "## Outside the `x-tool` taxonomy", "",
          f"{total - len(tooled)} operations have no `x-tool`, grouped by their OpenAPI tag. "
          "`platform` is the superadmin surface and `auth` is the login flow the cookie session "
          "uses — neither belongs in an automation catalogue. The rest are candidates for an "
          "`x-tool` if they should become reachable from the MCP.", "",
          "| Tag | Ops |", "|---|--:|"]
    for t, c in untooled.most_common(18):
        L.append(f"| `{t}` | {c} |")
    rest = sum(c for _, c in untooled.most_common()[18:])
    if rest:
        L.append(f"| _{len(untooled) - 18} more tags_ | {rest} |")

    L += [
        "", "## Drilling in", "",
        "The full index — one line per operation, with domain, profile, sensitivity, tags and "
        "the covering script — lives in the spec cache and is meant to be **grepped, never "
        "read into context**:",
        "",
        "```bash",
        'bash scripts/fetch_spec.sh                  # cache the spec + rebuild the index',
        'bash scripts/spec_lookup.sh --domain finance   # every finance operation',
        'bash scripts/spec_lookup.sh --sensitive        # everything flagged sensitive',
        'bash scripts/spec_lookup.sh --search invoice   # free-text over the index',
        'bash scripts/spec_lookup.sh "«O»/invoices" post  # ONE operation, in full',
        "```",
        "",
        "`«O»` abbreviates `/api/v1/organizations/{org_id}` in the index and in this page.",
        "",
        "## Before calling something uncovered",
        "",
        "Read the one operation with `spec_lookup.sh` first — the shapes are not guessable, and "
        "guessing is how the previous catalogue went wrong. Anything marked sensitive, plus every "
        "`DELETE`, needs the user's explicit confirmation; the guard hook blocks `admin/*`, "
        "`finance/*` and `payroll/*` without `--admit`.",
        "",
    ]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the API catalogue from the cached spec.")
    ap.add_argument("--spec", help="path to an OpenAPI JSON (default: the spec cache)")
    ap.add_argument("--md", action="store_true", help="write the human map to stdout")
    ap.add_argument("--tsv", action="store_true", help="write the full index to stdout")
    ap.add_argument("--out", help="write to this file instead of stdout")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    if args.tsv:
        text_fn = lambda buf: emit_tsv(operations(spec), buf)
        if args.out:
            with open(args.out, "w") as f:
                n = text_fn(f)
            print("✓ %d operations → %s" % (n, args.out), file=sys.stderr)
        else:
            text_fn(sys.stdout)
        return 0

    if args.md:
        text = emit_md(operations(spec))
        if args.out:
            pathlib.Path(args.out).write_text(text + "\n")
            print("✓ catalogue → %s (%d bytes)" % (args.out, len(text)), file=sys.stderr)
        else:
            print(text)
        return 0

    ops = list(operations(spec))
    doms = Counter(o["domain"] for o in ops if o["domain"])
    print("%d paths · %d operations · %d domains · %d with x-tool · %d sensitive · %d covered"
          % (len({o["path"] for o in ops}), len(ops), len(doms),
             sum(doms.values()), sum(1 for o in ops if o["sensitive"]),
             sum(1 for o in ops if o["covered"])))
    for d, c in doms.most_common():
        print("  %-12s %3d" % (d, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
