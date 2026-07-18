#!/usr/bin/env bash
# http.sh — shared HTTP layer for every Projekt skill script.
#
# Source it:   source "$(dirname "$0")/lib/http.sh"
# Then call:   pj_req GET  /me
#              pj_req POST /issues '{"project_id":"…","title":"…"}'
#
# Auth precedence mirrors the Projekt MCP (mcp/index.js) exactly:
#   token    : $TREXA_API_TOKEN            > ~/.config/3xa-projekt/auth.json .token
#   api_base : $TREXA_API_BASE             > auth.json .api_base > https://projekt.3xa.es/api
#   org id   : $TREXA_ORG_ID               > .projekt-run/context.json .org_id > (resolved from /me)
#
# Every request carries:  Authorization: Bearer <t>  +  X-Auth-Token: <t> (LiteSpeed
# fallback)  +  X-Org-Id: <org>.  The token is NEVER printed — only a fingerprint.
# 429/5xx are retried with backoff driven by Retry-After / X-RateLimit-Reset.
set -uo pipefail

PJ_AUTH_FILE="${PJ_AUTH_FILE:-$HOME/.config/3xa-projekt/auth.json}"
PJ_RUN_DIR="${PJ_RUN_DIR:-.projekt-run}"
PJ_CONTEXT_FILE="$PJ_RUN_DIR/context.json"
PJ_MAX_RETRIES="${PJ_MAX_RETRIES:-5}"
PJ_LAST_STATUS=0   # set by pj_req after every call

pj_die() { echo "✗ $*" >&2; exit 1; }

_pj_jq() { command -v jq >/dev/null 2>&1 || pj_die "jq is required (brew install jq / apt install jq)"; jq "$@"; }

pj_token() {
  if [ -n "${TREXA_API_TOKEN:-}" ]; then printf '%s' "$TREXA_API_TOKEN"; return; fi
  if [ -f "$PJ_AUTH_FILE" ]; then _pj_jq -r '.token // empty' "$PJ_AUTH_FILE"; return; fi
  printf ''
}

pj_api_base() {
  if [ -n "${TREXA_API_BASE:-}" ]; then printf '%s' "${TREXA_API_BASE%/}"; return; fi
  if [ -f "$PJ_AUTH_FILE" ]; then
    local b; b=$(_pj_jq -r '.api_base // empty' "$PJ_AUTH_FILE")
    [ -n "$b" ] && { printf '%s' "${b%/}"; return; }
  fi
  printf 'https://projekt.3xa.es/api/v1'
}

pj_org_id() {
  [ -n "${TREXA_ORG_ID:-}" ] && { printf '%s' "$TREXA_ORG_ID"; return; }
  [ -f "$PJ_CONTEXT_FILE" ] && { _pj_jq -r '.org_id // empty' "$PJ_CONTEXT_FILE"; return; }
  printf ''
}

# Project id the PAT is scoped to (current API PATs are often project-scoped).
pj_project_id() {
  [ -n "${TREXA_PROJECT_ID:-}" ] && { printf '%s' "$TREXA_PROJECT_ID"; return; }
  [ -f "$PJ_CONTEXT_FILE" ] && { _pj_jq -r '.project_id // empty' "$PJ_CONTEXT_FILE"; return; }
  printf ''
}

# Safe-to-log identifier for a token: prefix + last 4, never the secret itself.
pj_fingerprint() {
  local t; t="$(pj_token)"
  [ -z "$t" ] && { printf '(none)'; return; }
  printf '%s…%s' "${t:0:9}" "${t: -4}"
}

# pj_req METHOD PATH [BODY_JSON]
# Prints the response body to stdout. Sets PJ_LAST_STATUS. Returns non-zero on 4xx/5xx.
pj_req() {
  local method="$1" path="$2" body="${3:-}"
  local token base org url hdr_file out code attempt=0 sleep_s
  token="$(pj_token)";  [ -z "$token" ] && pj_die "No token. Set TREXA_API_TOKEN or create $PJ_AUTH_FILE (see auth-setup.md)."
  base="$(pj_api_base)"; org="$(pj_org_id)"
  url="$base$path"
  hdr_file="$(mktemp)"; trap 'rm -f "$hdr_file"' RETURN

  while :; do
    attempt=$((attempt+1))
    local -a args=(-sS -X "$method" -D "$hdr_file" -o /dev/stdout -w '\n%{http_code}'
      -H "Authorization: Bearer $token" -H "X-Auth-Token: $token"
      -H 'Content-Type: application/json' -H 'Accept: application/json')
    [ -n "$org" ] && args+=(-H "X-Org-Id: $org")
    [ -n "$body" ] && args+=(--data "$body")
    out="$(curl "${args[@]}" "$url" 2>/dev/null)"
    code="${out##*$'\n'}"; out="${out%$'\n'*}"
    PJ_LAST_STATUS="$code"

    if [ "$code" = "429" ] || { [ "$code" -ge 500 ] 2>/dev/null && [ "$code" -le 599 ]; }; then
      if [ "$attempt" -gt "$PJ_MAX_RETRIES" ]; then break; fi
      sleep_s="$(_pj_backoff_seconds "$hdr_file" "$attempt")"
      echo "  ⏳ $code on $method $path — retry $attempt/$PJ_MAX_RETRIES in ${sleep_s}s" >&2
      sleep "$sleep_s"; continue
    fi
    break
  done

  printf '%s' "$out"
  [ "$code" -ge 200 ] 2>/dev/null && [ "$code" -lt 300 ] 2>/dev/null
}

# Decide how long to wait: Retry-After (s) > X-RateLimit-Reset (epoch) - now > exp backoff.
_pj_backoff_seconds() {
  local hdr="$1" attempt="$2" ra reset now diff
  ra="$(grep -i '^retry-after:' "$hdr" 2>/dev/null | tr -d '\r' | awk '{print $2}' | head -1)"
  if [ -n "$ra" ] && [ "$ra" -gt 0 ] 2>/dev/null; then echo "$(( ra > 120 ? 120 : ra ))"; return; fi
  reset="$(grep -i '^x-ratelimit-reset:' "$hdr" 2>/dev/null | tr -d '\r' | awk '{print $2}' | head -1)"
  now="$(date +%s)"
  if [ -n "$reset" ] && [ "$reset" -gt "$now" ] 2>/dev/null; then
    diff=$(( reset - now + 1 )); echo "$(( diff > 120 ? 120 : diff ))"; return
  fi
  echo "$(( attempt * attempt ))"   # 1,4,9,16,25
}

# Convenience: GET and pipe through a jq filter (default: pretty)
pj_get() { pj_req GET "$1" | _pj_jq "${2:-.}"; }
