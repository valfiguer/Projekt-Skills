#!/usr/bin/env bash
# spec_index.sh — build a tiny TSV index of the OpenAPI spec (path, methods,
# summary) so the skill can DISCOVER any of the 800+ endpoints by grepping a few
# KB instead of loading the 1.3 MB YAML. Pure awk — no yq/python needed.
#
# Output: $PJ_SPEC_DIR/.index.tsv  (one line: <path>\t<METHODS>\t<summary>)
set -uo pipefail
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC="${PROJEKT_SPEC:-$PJ_SPEC_DIR/projekt.json}"
INDEX="$PJ_SPEC_DIR/.index.tsv"
[ -f "$SPEC" ] || { echo "✗ Spec not found at $SPEC — run fetch_spec.sh first." >&2; exit 1; }

# JSON spec (current API serves /api/openapi.json) → TSV index via jq.
command -v jq >/dev/null 2>&1 || { echo "✗ jq is required to index the JSON spec." >&2; exit 1; }
jq -r '
  (.paths // {}) | to_entries[]
  | .key as $p
  | ( .value | to_entries
      | map(select(.key | test("^(get|post|put|patch|delete|options|head)$"))) ) as $ops
  | ( [ $ops[].key | ascii_upcase ] | join(",") ) as $m
  | ( [ $ops[].value.summary? // empty ] | (.[0] // "") ) as $s
  | "\($p)\t\($m)\t\($s)"
' "$SPEC" > "$INDEX"

echo "✓ Indexed $(wc -l < "$INDEX" | tr -d ' ') paths → $INDEX"
