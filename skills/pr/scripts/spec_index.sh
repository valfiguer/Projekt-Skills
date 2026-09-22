#!/usr/bin/env bash
# spec_index.sh — build the greppable index of every operation in the spec.
#
# One line per operation, tab-separated:
#   METHOD <tab> path <tab> domain <tab> profile <tab> S|- <tab> tags <tab> covered-by <tab> summary
#
# ~917 lines / ~130 KB. It is meant to be GREPPED by spec_lookup.sh, never read
# into a model context. The heavy lifting is in catalogo.py (the spec is JSON, so
# this is a python job, not an awk-over-YAML one — the previous awk version
# returned nothing at all, silently).
#
# Output: $PJ_SPEC_DIR/.index.tsv
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC="${PROJEKT_SPEC:-$PJ_SPEC_DIR/projekt.json}"
INDEX="$PJ_SPEC_DIR/.index.tsv"
[ -f "$SPEC" ] || { echo "✗ Spec not found at $SPEC — run fetch_spec.sh first." >&2; exit 1; }

python3 "$HERE/catalogo.py" --spec "$SPEC" --tsv --out "$INDEX" || exit 1
echo "✓ Indexed $(wc -l < "$INDEX" | tr -d ' ') operations → $INDEX"
