#!/usr/bin/env bash
# spec_lookup.sh — print the OpenAPI block for ONE path (or search the index).
# The full spec is NEVER printed — only the operation you asked for.
#
# Usage:
#   spec_lookup.sh /api/v1/organizations/{org_id}/documents        # whole path block
#   spec_lookup.sh /api/v1/organizations/{org_id}/documents post   # just that operation
#   spec_lookup.sh --search workload      # grep the index for matching paths
#   spec_lookup.sh --list finance         # same, alias
#
# A leading /api/v1 is optional: `--search` and a bare path both work.
set -uo pipefail
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC="${PROJEKT_SPEC:-$PJ_SPEC_DIR/projekt.json}"
INDEX="$PJ_SPEC_DIR/.index.tsv"

_need_spec()  { [ -f "$SPEC" ]  || { echo "✗ Spec not cached. Run: bash \"$(dirname "$0")/fetch_spec.sh\"" >&2; exit 1; }; }
_need_index() { [ -f "$INDEX" ] || { echo "✗ Index missing. Run: bash \"$(dirname "$0")/spec_index.sh\"" >&2; exit 1; }; }

case "${1:-}" in
  --search|--list)
    _need_index; term="${2:-}"
    [ -z "$term" ] && { echo "usage: spec_lookup.sh --search <term>" >&2; exit 2; }
    awk -F'\t' -v t="$term" 'tolower($0) ~ tolower(t) { printf "%-62s %-22s %s\n", $1, $2, $3 }' "$INDEX"
    exit 0 ;;
  ""|-h|--help)
    echo "usage: spec_lookup.sh <path> [method] | --search <term> | --list <term>"; exit 0 ;;
esac

_need_spec
python3 - "$SPEC" "$1" "${2:-}" <<'PY'
import json, sys
spec_path, want, method = sys.argv[1], sys.argv[2], (sys.argv[3] or "").lower()
with open(spec_path) as f:
    paths = (json.load(f).get("paths") or {})

item = paths.get(want)
if item is None:  # tolerate a path written without the /api/v1 prefix
    for cand in ("/api/v1" + want, want.replace("/api/v1", "", 1)):
        if cand in paths:
            want, item = cand, paths[cand]
            break
if item is None:
    tail = want.rstrip("/").split("/")[-1]
    print("✗ Path not found: %s  (try: spec_lookup.sh --search %s)" % (want, tail), file=sys.stderr)
    raise SystemExit(1)

if method:
    op = item.get(method)
    if op is None:
        print("✗ %s has no %s. It has: %s"
              % (want, method.upper(),
                 ", ".join(k.upper() for k in item if k.lower() in
                           ("get", "post", "put", "patch", "delete"))), file=sys.stderr)
        raise SystemExit(1)
    item = {method: op}

print("# ── %s ──" % want)
print(json.dumps(item, indent=2, ensure_ascii=False))
PY
