#!/usr/bin/env bash
# spec_lookup.sh — find operations in the index, or print ONE operation in full.
# The whole spec is NEVER printed: only the lines or the block you asked for.
#
# Search the index (cheap — a few KB of a 130 KB TSV):
#   spec_lookup.sh --search invoice        free text over path, tags and summary
#   spec_lookup.sh --domain finance        every operation in one x-tool domain
#   spec_lookup.sh --tag payroll           every operation carrying one OpenAPI tag
#   spec_lookup.sh --sensitive [term]      everything flagged sensitive
#   spec_lookup.sh --uncovered [term]      operations no pr-* script drives yet
#   spec_lookup.sh --domains               the domain list with counts
#
# Read one operation (the shapes are not guessable — always do this first):
#   spec_lookup.sh "«O»/invoices" post
#   spec_lookup.sh /api/v1/organizations/{org_id}/invoices post
#
# «O» abbreviates /api/v1/organizations/{org_id}. A leading /api/v1 is optional.
set -uo pipefail
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC="${PROJEKT_SPEC:-$PJ_SPEC_DIR/projekt.json}"
INDEX="$PJ_SPEC_DIR/.index.tsv"

_need_spec()  { [ -f "$SPEC" ]  || { echo "✗ Spec not cached. Run: bash \"$(dirname "$0")/fetch_spec.sh\"" >&2; exit 1; }; }
_need_index() { [ -f "$INDEX" ] || { echo "✗ Index missing. Run: bash \"$(dirname "$0")/spec_index.sh\"" >&2; exit 1; }; }

# $1 = awk condition over the TSV fields, $2 = free-text term ("" = all)
_filter() {
  _need_index
  awk -F'\t' -v t="${2:-}" -v cond="$1" '
    function match_term(  hay) { if (t=="") return 1; hay=tolower($2 FS $6 FS $8); return index(hay, tolower(t))>0 }
    {
      keep = 0
      if (cond=="all")            keep = 1
      else if (cond=="sensitive") keep = ($5=="S")
      else if (cond=="uncovered") keep = ($7=="-")
      if (keep && match_term()) printf "%-7s %-52s %-11s %-5s %s %s\n", $1, $2, ($3=="-"?"":$3), ($4=="-"?"":$4), ($5=="S"?"⚠":" "), $8
    }' "$INDEX"
}

case "${1:-}" in
  --search|--list)
    term="${2:-}"; [ -z "$term" ] && { echo "usage: spec_lookup.sh --search <term>" >&2; exit 2; }
    _filter all "$term"; exit 0 ;;
  --domain)
    d="${2:-}"; [ -z "$d" ] && { echo "usage: spec_lookup.sh --domain <domain>   (--domains to list them)" >&2; exit 2; }
    _need_index
    awk -F'\t' -v d="$d" '$3==d { printf "%-7s %-52s %-5s %s %s\n", $1, $2, ($4=="-"?"":$4), ($5=="S"?"⚠":" "), $8 }' "$INDEX"
    exit 0 ;;
  --tag)
    t="${2:-}"; [ -z "$t" ] && { echo "usage: spec_lookup.sh --tag <tag>" >&2; exit 2; }
    _need_index
    awk -F'\t' -v t="$t" '{ n=split($6,a,","); for(i=1;i<=n;i++) if(a[i]==t) { printf "%-7s %-52s %-11s %s %s\n", $1, $2, ($3=="-"?"":$3), ($5=="S"?"⚠":" "), $8; break } }' "$INDEX"
    exit 0 ;;
  --sensitive) _filter sensitive "${2:-}"; exit 0 ;;
  --uncovered) _filter uncovered "${2:-}"; exit 0 ;;
  --domains)
    _need_index
    awk -F'\t' '$3!="-" { d[$3]++; if($5=="S") s[$3]++ } END { for (k in d) printf "%-13s %3d ops  %3d sensitive\n", k, d[k], s[k]+0 }' "$INDEX" | sort -k2 -rn
    exit 0 ;;
  ""|-h|--help)
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

_need_spec
python3 - "$SPEC" "$1" "${2:-}" <<'PY'
import json, sys
spec_path, want, method = sys.argv[1], sys.argv[2], (sys.argv[3] or "").lower()
ORG = "/api/v1/organizations/{org_id}"
want = want.replace("«O»", ORG)
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
        have = ", ".join(k.upper() for k in item if k.lower() in
                         ("get", "post", "put", "patch", "delete"))
        print("✗ %s has no %s. It has: %s" % (want, method.upper(), have), file=sys.stderr)
        raise SystemExit(1)
    item = {method: op}

print("# ── %s ──" % want)
print(json.dumps(item, indent=2, ensure_ascii=False))
PY
