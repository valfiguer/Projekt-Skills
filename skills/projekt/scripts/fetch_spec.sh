#!/usr/bin/env bash
# fetch_spec.sh — download the Projekt OpenAPI spec into a user cache (ETag-cached)
# and (re)build the lightweight index. The 1.3 MB spec lives in ~/.cache, NEVER in
# the plugin dir or the model context. Run once; re-run only refreshes on change.
#
# Env: PROJEKT_SPEC (use a local spec, e.g. the monorepo, instead of downloading)
#      PJ_SPEC_DIR  (cache dir, default ~/.cache/3xa-projekt)
#      PROJEKT_SPEC_URL (default https://projekt.3xa.es/openapi.yaml)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PJ_SPEC_DIR="${PJ_SPEC_DIR:-$HOME/.cache/3xa-projekt}"
SPEC_URL="${PROJEKT_SPEC_URL:-https://projekt.3xa.es/api/openapi.json}"
mkdir -p "$PJ_SPEC_DIR"
DEST="$PJ_SPEC_DIR/projekt.json"
ETAG_FILE="$PJ_SPEC_DIR/.etag"

if [ -n "${PROJEKT_SPEC:-}" ] && [ -f "$PROJEKT_SPEC" ]; then
  echo "Using local spec: $PROJEKT_SPEC"
  ln -sf "$PROJEKT_SPEC" "$DEST"
else
  echo "Fetching $SPEC_URL …"
  etag=""; [ -f "$ETAG_FILE" ] && etag="$(cat "$ETAG_FILE")"
  code="$(curl -sS -o "$DEST.tmp" -w '%{http_code}' \
            ${etag:+-H "If-None-Match: $etag"} \
            -D "$PJ_SPEC_DIR/.hdr" "$SPEC_URL" 2>/dev/null || echo 000)"
  if [ "$code" = "304" ]; then
    echo "Spec unchanged (304) — keeping cached copy."; rm -f "$DEST.tmp"
  elif [ "$code" = "200" ] && [ -s "$DEST.tmp" ]; then
    mv "$DEST.tmp" "$DEST"
    grep -i '^etag:' "$PJ_SPEC_DIR/.hdr" 2>/dev/null | tr -d '\r' | awk '{print $2}' > "$ETAG_FILE"
    echo "Spec updated ($(wc -l < "$DEST") lines)."
  else
    rm -f "$DEST.tmp"
    [ -f "$DEST" ] && echo "Fetch failed (HTTP $code) — using existing cache." || { echo "✗ Could not fetch spec (HTTP $code) and no cache present." >&2; exit 1; }
  fi
fi

PJ_SPEC_DIR="$PJ_SPEC_DIR" PROJEKT_SPEC="$DEST" bash "$HERE/spec_index.sh"
