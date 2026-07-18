#!/usr/bin/env bash
# spec_lookup.sh — print the OpenAPI block for ONE path (optionally search the
# index). The full spec is NEVER printed — only the ~20-60 lines you asked for.
#
# Usage:
#   spec_lookup.sh /issues/{issueId}          # print that path's full block
#   spec_lookup.sh /issues/{issueId} post     # (block, post highlighted at top)
#   spec_lookup.sh --search workload          # grep the index for matching paths
#   spec_lookup.sh --list finance             # list all paths whose tag/path ~ term
set -uo pipefail
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC="${PROJEKT_SPEC:-$PJ_SPEC_DIR/projekt.json}"
INDEX="$PJ_SPEC_DIR/.index.tsv"

_need_spec() { [ -f "$SPEC" ] || { echo "✗ Spec not cached. Run: bash \"$(dirname "$0")/fetch_spec.sh\"" >&2; exit 1; }; }
_need_index() { [ -f "$INDEX" ] || { echo "✗ Index missing. Run: bash \"$(dirname "$0")/spec_index.sh\"" >&2; exit 1; }; }

case "${1:-}" in
  --search|--list)
    _need_index; term="${2:-}"
    [ -z "$term" ] && { echo "usage: spec_lookup.sh --search <term>" >&2; exit 2; }
    awk -F'\t' -v t="$term" 'tolower($0) ~ tolower(t) { printf "%-48s %-22s %s\n", $1, $2, $3 }' "$INDEX"
    exit 0 ;;
  ""|-h|--help)
    echo "usage: spec_lookup.sh <path> [method] | --search <term> | --list <term>"; exit 0 ;;
esac

_need_spec
PATH_ARG="$1"; METHOD="${2:-}"
# Extract the exact path block: from the "  <path>:" key until the next col-0 or
# col-2 key. index()-based match avoids regex-escaping {} and /.
block="$(jq -r --arg p "$PATH_ARG" '
  (.paths[$p] // {}) | to_entries[]
  | select(.key | test("^(get|post|put|patch|delete|options|head)$"))
  | "\(.key|ascii_upcase) \($p) — \(.value.summary // "-")"
    + (if (.value.parameters|type)=="array" and (.value.parameters|length)>0
         then "\n  params: " + ([.value.parameters[] | "\(.name // "ref")\(if .required then "*" else "" end)"] | join(", "))
         else "" end)
    + (if .value.requestBody then "\n  requestBody: " + ((.value.requestBody.content["application/json"].schema["$ref"] // "inline") | sub(".*/";"")) else "" end)
' "$SPEC")"

[ -z "$block" ] && { echo "✗ Path not found: $PATH_ARG  (try: spec_lookup.sh --search ${PATH_ARG##*/})" >&2; exit 1; }
[ -n "$METHOD" ] && echo "# ── $PATH_ARG  (method asked: $(echo "$METHOD" | tr a-z A-Z)) ──"
printf '%s\n' "$block"
