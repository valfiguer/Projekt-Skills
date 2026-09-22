#!/usr/bin/env bash
# auth_check.sh — MANDATORY first call of every run. Resolves the token, calls
# GET /auth/me ONCE, and self-discovers the org (+ project) from the PAT's own
# scope, seeding .projekt-run/context.json with {org_id, project_id, user_id, …}.
#
# The rewritten /api/v1 puts org + project in the PATH. A PAT authenticating via
# `Authorization: Bearer pjk_live_…` gets an `api_key` object back on /auth/me
# carrying { id, name, organization_id, project_id } — that's how a project-scoped
# key discovers WHICH org + project it may touch (project_id is null for org-wide
# keys). Falls back to GET /organizations for the org when api_key is absent.
#
# Prints a human summary + the token FINGERPRINT (never the token). Non-zero exit
# with a remediation hint if no token or no org resolves.
#
# Usage: auth_check.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib/http.sh"

[ -n "$(pj_token)" ] || pj_die "No token found.
  Fix: export TREXA_API_TOKEN=\"pjk_live_…\"  (or create ~/.config/3xa-projekt/auth.json)
  Mint one at Projekt → Organization → Settings → General → Integraciones. See references/auth-setup.md"

echo "Token:    $(pj_fingerprint)"
echo "API base: $(pj_api_base)"

ME="$(pj_req GET /auth/me)" || pj_die "GET /auth/me failed (HTTP $(pj_last_status)): $(echo "$ME" | jq -r '.message // .error // .detail // .' 2>/dev/null). Token invalid/expired/revoked?"

# /auth/me (rewrite): { id, email, name, …, api_key:{ id, name, organization_id,
# project_id } | null }. With a PAT, api_key carries the key's org + project scope.
USER_ID="$(echo "$ME" | jq -r '.id // .user_id // empty')"
USER_NAME="$(echo "$ME" | jq -r '.name // .email // empty')"
ORG_ID="${TREXA_ORG_ID:-$(echo "$ME" | jq -r '.api_key.organization_id // empty')}"
PROJECT_ID="${TREXA_PROJECT_ID:-$(echo "$ME" | jq -r '.api_key.project_id // empty')}"
KEY_NAME="$(echo "$ME" | jq -r '.api_key.name // empty')"

# Fallback: no api_key scope (cookie-style / older key) → resolve org from /organizations.
if [ -z "$ORG_ID" ]; then
  ORGS="$(pj_req GET /organizations)" || pj_die "GET /organizations failed (HTTP $(pj_last_status)). Token invalid or no org access?"
  ORG_ID="$(echo "$ORGS" | jq -r 'if type=="array" then .[0].id else (.data[0].id // .organizations[0].id) end // empty')"
  ORG_NAME="$(echo "$ORGS" | jq -r 'if type=="array" then .[0].name else (.data[0].name // .organizations[0].name) end // empty')"
  ROLE="$(echo "$ORGS" | jq -r 'if type=="array" then .[0].role else (.data[0].role // .organizations[0].role) end // empty')"
fi

[ -n "$ORG_ID" ] || pj_die "Authenticated as ${USER_NAME:-?} but no organization resolved.
  A project-scoped PAT self-discovers its org via /auth/me api_key.organization_id.
  Fix: set TREXA_ORG_ID=<uuid>, or mint a fresh key. See references/auth-setup.md"

# Enrich org name/role from /organizations when we only had an id from api_key.
if [ -z "${ORG_NAME:-}" ]; then
  ORGS="${ORGS:-$(pj_req GET /organizations 2>/dev/null)}"
  ORG_NAME="$(echo "$ORGS" | jq -r --arg o "$ORG_ID" 'if type=="array" then . else (.data // .organizations // []) end | map(select(.id==$o)) | .[0].name // empty' 2>/dev/null)"
  ROLE="$(echo "$ORGS" | jq -r --arg o "$ORG_ID" 'if type=="array" then . else (.data // .organizations // []) end | map(select(.id==$o)) | .[0].role // empty' 2>/dev/null)"
fi

mkdir -p "$PJ_RUN_DIR"
tmp="$(mktemp)"
[ -f "$PJ_CONTEXT_FILE" ] && cp "$PJ_CONTEXT_FILE" "$tmp" || echo '{}' > "$tmp"
jq --arg o "$ORG_ID" --arg on "${ORG_NAME:-}" --arg p "$PROJECT_ID" --arg kn "$KEY_NAME" \
   --arg u "$USER_ID" --arg un "$USER_NAME" --arg r "${ROLE:-}" --arg b "$(pj_api_base)" \
   '.org_id=$o | .org_name=$on | .project_id=$p | .key_name=$kn
    | .user_id=$u | .user_name=$un | .role=$r | .api_base=$b' \
   "$tmp" > "$PJ_CONTEXT_FILE" && rm -f "$tmp"

echo "User:     ${USER_NAME:-?} (${USER_ID:-?})"
echo "Org:      ${ORG_NAME:-?} ($ORG_ID)${ROLE:+  role=$ROLE}"
if [ -n "$PROJECT_ID" ]; then
  echo "Scope:    project-scoped key${KEY_NAME:+ '$KEY_NAME'} → project $PROJECT_ID"
else
  echo "Scope:    org-wide key${KEY_NAME:+ '$KEY_NAME'} (all projects)"
fi
echo "✓ Connected. Context → $PJ_CONTEXT_FILE"
echo "Next: run context_sync.sh to cache projects + members."
