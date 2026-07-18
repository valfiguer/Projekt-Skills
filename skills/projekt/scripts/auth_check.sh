#!/usr/bin/env bash
# auth_check.sh — MANDATORY first call of every run. Resolves the token, calls
# /me ONCE, pins the org, and seeds .projekt-run/context.json with {org_id,user_id}.
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

ME="$(pj_req GET /auth/me)" || pj_die "GET /auth/me failed (HTTP $PJ_LAST_STATUS): $(echo "$ME" | jq -r '.error.message // .message // .' 2>/dev/null). Token invalid/expired/revoked?"

# /auth/me shape (current API): FLAT user { id, name, email, … } plus the calling key's
# scope in .api_key { organization_id, project_id }. A pjk_live_ PAT is scoped to ONE org
# (and usually ONE project) — pin both from api_key. Env overrides win.
USER_ID="$(echo "$ME" | jq -r '.id // .user.id // empty')"
USER_NAME="$(echo "$ME" | jq -r '.name // .email // .user.name // empty')"
ORG_ID="${TREXA_ORG_ID:-$(echo "$ME" | jq -r '.api_key.organization_id // empty')}"
PROJECT_ID="${TREXA_PROJECT_ID:-$(echo "$ME" | jq -r '.api_key.project_id // empty')}"
ROLE=""

[ -n "$ORG_ID" ] || pj_die "Authenticated as $USER_NAME but no organization resolved from the key scope.
  Fix: set TREXA_ORG_ID=<uuid>. (A pjk_live_ PAT is scoped to one org — see Projekt -> Integraciones.)"

# Org name isn't in /auth/me; resolve it from the (user-level) org list.
ORG_NAME="$(pj_req GET /organizations 2>/dev/null | jq -r --arg o "$ORG_ID" '(if type=="array" then . else (.data // .organizations // []) end)[] | select(.id==$o) | .name' 2>/dev/null | head -1)"

mkdir -p "$PJ_RUN_DIR"
tmp="$(mktemp)"
[ -f "$PJ_CONTEXT_FILE" ] && cp "$PJ_CONTEXT_FILE" "$tmp" || echo '{}' > "$tmp"
jq --arg o "$ORG_ID" --arg on "$ORG_NAME" --arg u "$USER_ID" --arg un "$USER_NAME" \
   --arg r "$ROLE" --arg b "$(pj_api_base)" --arg pid "$PROJECT_ID" \
   '.org_id=$o | .org_name=$on | .user_id=$u | .user_name=$un | .role=$r | .api_base=$b | .project_id=$pid' \
   "$tmp" > "$PJ_CONTEXT_FILE" && rm -f "$tmp"

echo "User:     $USER_NAME ($USER_ID)"
echo "Org:      ${ORG_NAME:-?} ($ORG_ID)"
echo "Project:  ${PROJECT_ID:-<org-wide key>}"
echo "✓ Connected. Context → $PJ_CONTEXT_FILE"
echo "Next: run context_sync.sh to cache projects + members."
