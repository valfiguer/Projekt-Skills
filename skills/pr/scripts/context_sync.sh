#!/usr/bin/env bash
# context_sync.sh — fetch projects + team members ONCE and cache slim copies into
# .projekt-run/context.json. Everything downstream resolves name→uuid from this
# file instead of hitting the API again. Run after auth_check.sh.
#
# Rewrite API: org + project live in the PATH.
#   projects → GET /organizations/{org}/projects   (org-wide key only; a
#              project-scoped key gets 403 → we synthesize a 1-project list from
#              the self-discovered project_id + a /tasks probe instead).
#   members  → GET /organizations/{org}/members
#
# Usage: context_sync.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib/http.sh"

[ -f "$PJ_CONTEXT_FILE" ] || pj_die "Run auth_check.sh first (no $PJ_CONTEXT_FILE)."
ORG="$(pj_org_id)"; [ -n "$ORG" ] || pj_die "No org_id in context. Re-run auth_check.sh."
PROJECT_ID="$(jq -r '.project_id // empty' "$PJ_CONTEXT_FILE")"

echo "Syncing projects + members for org ${ORG}…"

# ── projects ──────────────────────────────────────────────────────────────────
PROJECTS="$(pj_req GET "/organizations/$ORG/projects?limit=200")"
PJ_STATUS="$(pj_last_status)"
if [ "$PJ_STATUS" = "403" ] && [ -n "$PROJECT_ID" ]; then
  # Project-scoped key: can't list org projects. Resolve just its own project by
  # probing the tasks endpoint (which returns the project id we already hold) and
  # naming it from whatever we can read. Fall back to a bare {id} entry.
  echo "  (project-scoped key — listing limited to project $PROJECT_ID)" >&2
  proj_slim="$(jq -nc --arg id "$PROJECT_ID" '[{id:$id, key:null, name:null}]')"
elif [ "${PJ_STATUS:0:1}" != "2" ]; then
  pj_die "GET /organizations/${ORG} projects failed (HTTP $PJ_STATUS): $(echo "$PROJECTS" | jq -r '.message // .error // .detail // .' 2>/dev/null)"
else
  # Check type=="array" FIRST — `.data` on a top-level array throws in jq.
  proj_slim="$(echo "$PROJECTS" | jq -c '[ (if type=="array" then . elif (.data|type=="array") then .data elif (.projects|type=="array") then .projects else [] end)[] | {id, key, name} ]' 2>/dev/null || echo '[]')"
fi

# ── members ───────────────────────────────────────────────────────────────────
MEMBERS="$(pj_req GET "/organizations/$ORG/members")"
PJ_STATUS="$(pj_last_status)"
if [ "${PJ_STATUS:0:1}" != "2" ]; then
  echo "  ⚠ GET /organizations/${ORG}/members → HTTP $PJ_STATUS (assignee resolution limited)" >&2
  mem_slim='[]'
else
  # MemberOut: {user_id,name,email,avatar_url,role,joined_at}. Tolerate array OR envelope.
  mem_slim="$(echo "$MEMBERS" | jq -c '[ (if type=="array" then . elif (.data|type=="array") then .data elif (.members|type=="array") then .members else [] end)[] | {user_id: (.user_id // .id), name: (.name // .email), email, role} ]' 2>/dev/null || echo '[]')"
fi

tmp="$(mktemp)"; cp "$PJ_CONTEXT_FILE" "$tmp"
jq --argjson p "$proj_slim" --argjson m "$mem_slim" --arg ts "$(date -u +%FT%TZ)" \
   '.projects=$p | .members=$m | .synced_at=$ts' "$tmp" > "$PJ_CONTEXT_FILE" && rm -f "$tmp"

echo "✓ Cached $(echo "$proj_slim" | jq length) project(s), $(echo "$mem_slim" | jq length) members → $PJ_CONTEXT_FILE"
echo "$proj_slim" | jq -r '.[] | "  · \(.key // "—")  \(.name // "(project-scoped)")  (\(.id))"' | head -50
