#!/usr/bin/env bash
# run_ledger.sh — append-only audit + resume log shared by every mutating script.
#
#   source lib/run_ledger.sh
#   pj_ledger_init                       # picks/creates .projekt-run/<ts>.jsonl
#   pj_ledger_add create issue PJKT-12 ok '{"id":"…"}'
#   pj_ledger_seen create issue "title-key"   # -> 0 if already done (skip), 1 if new
#   pj_ledger_summary                    # prints created/updated/skipped/blocked counts
#
# One JSONL line per op: {"ts","phase","op","target","key","status","ref"}.
# NEVER write a token here — only ids/keys. The dir is gitignored.
set -uo pipefail

PJ_RUN_DIR="${PJ_RUN_DIR:-.projekt-run}"
PJ_LEDGER="${PJ_LEDGER:-}"

pj_ledger_init() {
  mkdir -p "$PJ_RUN_DIR"
  if [ -z "$PJ_LEDGER" ]; then
    # Reuse the most recent ledger of the day if resuming, else start a new one.
    local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
    PJ_LEDGER="${PJ_LEDGER_OVERRIDE:-$PJ_RUN_DIR/$stamp.jsonl}"
  fi
  touch "$PJ_LEDGER"
  echo "$PJ_LEDGER"
}

# pj_ledger_add PHASE OP TARGET STATUS [REF_JSON]
pj_ledger_add() {
  [ -z "$PJ_LEDGER" ] && pj_ledger_init >/dev/null
  local phase="$1" op="$2" target="$3" status="$4" ref="${5:-null}"
  jq -cn --arg ts "$(date -u +%FT%TZ)" --arg phase "$phase" --arg op "$op" \
        --arg target "$target" --arg status "$status" --argjson ref "$ref" \
     '{ts:$ts,phase:$phase,op:$op,target:$target,status:$status,ref:$ref}' \
     >> "$PJ_LEDGER"
}

# pj_ledger_seen OP KEY  -> exit 0 if a prior ok/created/updated line matches (skip it)
pj_ledger_seen() {
  local op="$1" key="$2"
  [ -z "$PJ_LEDGER" ] && return 1
  # Search ALL ledgers in the run dir so resumes across files still dedupe.
  grep -h . "$PJ_RUN_DIR"/*.jsonl 2>/dev/null \
    | jq -e --arg op "$op" --arg key "$key" \
        'select(.op==$op and .target==$key and (.status|test("ok|created|updated")))' \
    >/dev/null 2>&1
}

pj_ledger_summary() {
  [ -z "$PJ_LEDGER" ] && { echo "(no ledger)"; return; }
  echo "Ledger: $PJ_LEDGER"
  jq -rs 'group_by(.status)[] | "\(.[0].status): \(length)"' "$PJ_LEDGER" 2>/dev/null
}
