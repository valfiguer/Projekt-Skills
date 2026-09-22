#!/usr/bin/env bash
# spec_index.sh — build a tiny TSV index of the OpenAPI spec (path, methods,
# summary) so the skill can DISCOVER any of the 685 endpoints by grepping a few
# KB instead of loading the multi-MB spec into context.
#
# The spec served by Projekt Republic is JSON, so this parses JSON with python3
# (already required by the skill's scripts) rather than awk over YAML.
#
# Output: $PJ_SPEC_DIR/.index.tsv  (one line: <path>\t<METHODS>\t<summary>)
set -uo pipefail
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC="${PROJEKT_SPEC:-$PJ_SPEC_DIR/projekt.json}"
INDEX="$PJ_SPEC_DIR/.index.tsv"
[ -f "$SPEC" ] || { echo "✗ Spec not found at $SPEC — run fetch_spec.sh first." >&2; exit 1; }

python3 - "$SPEC" "$INDEX" <<'PY'
import json, sys
spec_path, index_path = sys.argv[1], sys.argv[2]
with open(spec_path) as f:
    spec = json.load(f)
VERBS = ("get", "post", "put", "patch", "delete", "options", "head")
rows = 0
with open(index_path, "w") as out:
    for path, item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(item, dict):
            continue
        methods, summary = [], ""
        for verb in VERBS:
            op = item.get(verb)
            if isinstance(op, dict):
                methods.append(verb.upper())
                if not summary:
                    summary = (op.get("summary") or "").replace("\t", " ").replace("\n", " ")
        if not summary:
            summary = (item.get("summary") or "").replace("\t", " ")
        out.write("%s\t%s\t%s\n" % (path, ",".join(methods), summary))
        rows += 1
print("✓ Indexed %d paths → %s" % (rows, index_path))
PY
