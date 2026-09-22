#!/usr/bin/env bash
# check_drift.sh — assert the cheatsheet's core endpoints still exist in the live
# OpenAPI spec, so references/endpoints.md never silently rots. Run by CI; also
# usable locally. Exits non-zero (lists the missing paths) on drift.
set -uo pipefail
SPEC_URL="${PROJEKT_SPEC_URL:-https://developers.projektrepublic.com/openapi.json}"
SPEC="$(mktemp)"
trap 'rm -f "$SPEC"' EXIT

echo "Fetching $SPEC_URL …"
code="$(curl -sS -o "$SPEC" -w '%{http_code}' "$SPEC_URL" || echo 000)"
[ "$code" = "200" ] && [ -s "$SPEC" ] || { echo "✗ Could not fetch spec (HTTP $code)"; exit 1; }
echo "Spec: $(wc -l < "$SPEC" | tr -d ' ') lines."

CORE_PATHS=(
  "/me"
  "/projects"
  "/team"
  "/issues"
  "/issues/{issueId}"
  "/issues/bulk"
  "/issues/{issueId}/comments"
  "/issues/export-pdf"
  "/workload"
  "/workload/capacity"
  "/capacity"
  "/ai/suggest-estimation"
  "/projects/{projectId}/docs"
  "/projects/{projectId}/roadmap"
  "/projects/{projectId}/issues/{issueId}/time-entries"
  "/projects/{projectId}/issues/{issueId}/time-summary"
)

missing=0
for p in "${CORE_PATHS[@]}"; do
  # path keys in the spec appear as two-space-indented "  <path>:"
  if grep -qE "^  ${p//\//\\/}:" "$SPEC"; then
    echo "  ✓ $p"
  else
    echo "  ✗ MISSING: $p"; missing=$((missing+1))
  fi
done

if [ "$missing" -gt 0 ]; then
  echo ""; echo "✗ Drift: $missing core path(s) no longer match the spec. Update references/endpoints.md."
  exit 1
fi
echo ""; echo "✓ No drift — all ${#CORE_PATHS[@]} core paths present."
