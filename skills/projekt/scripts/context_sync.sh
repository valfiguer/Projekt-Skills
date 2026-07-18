#!/usr/bin/env bash
# context_sync.sh — fetch projects + team members ONCE and cache slim copies into
# .projekt-run/context.json. Everything downstream resolves name→uuid from this
# file instead of hitting the API again. Run after auth_check.sh.
#
# Usage: context_sync.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib/http.sh"

[ -f "$PJ_CONTEXT_FILE" ] || pj_die "Run auth_check.sh first (no $PJ_CONTEXT_FILE)."
ORG="$(pj_org_id)"; [ -n "$ORG" ] || pj_die "No org_id in context; run auth_check.sh."
PROJECT="$(pj_project_id)"

echo "Syncing projects + members…"

# Org-scoped PAT: list all org projects. Project-scoped PAT gets 403 there → fall back to
# its single scoped project. NOTE: PJ_LAST_STATUS is set inside pj_req's subshell and does
# NOT propagate to a $()-assignment, so branch on the EXIT CODE, not on PJ_LAST_STATUS.
if PROJECTS="$(pj_req GET "/organizations/$ORG/projects?limit=200")"; then
  :
elif [ -n "$PROJECT" ] && ONE="$(pj_req GET "/organizations/$ORG/projects/$PROJECT")"; then
  PROJECTS="[$ONE]"
else
  pj_die "Could not read projects for org $ORG. The key may lack access to this org/project."
fi
# Org member roster (admin scope). A project-scoped key can't read it → empty, non-fatal.
MEMBERS="$(pj_req GET "/organizations/$ORG/members")" || MEMBERS="[]"
# Note: check type=="array" FIRST — `.data` on a top-level array throws in jq.
proj_slim="$(echo "$PROJECTS" | jq -c '[ (if type=="array" then . elif (.data|type=="array") then .data elif (.projects|type=="array") then .projects else [] end)[] | {id, key, name} ]' 2>/dev/null || echo '[]')"
mem_slim="$(echo "$MEMBERS"  | jq -c '[ (if type=="array" then . elif (.data|type=="array") then .data elif (.members|type=="array") then .members else [] end)[] | {user_id: (.user_id // .id), name: (.name // .email), email, role} ]' 2>/dev/null || echo '[]')"

tmp="$(mktemp)"; cp "$PJ_CONTEXT_FILE" "$tmp"
jq --argjson p "$proj_slim" --argjson m "$mem_slim" --arg ts "$(date -u +%FT%TZ)" \
   '.projects=$p | .members=$m | .synced_at=$ts' "$tmp" > "$PJ_CONTEXT_FILE" && rm -f "$tmp"

echo "✓ Cached $(echo "$proj_slim" | jq length) projects, $(echo "$mem_slim" | jq length) members → $PJ_CONTEXT_FILE"
echo "$proj_slim" | jq -r '.[] | "  · \(.key // "—")  \(.name)  (\(.id))"' | head -50
