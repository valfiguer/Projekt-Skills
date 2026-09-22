#!/usr/bin/env bash
# guard.sh — PreToolUse guard (belt-and-suspenders on top of each script's own
# dry-run/confirm). Blocks a Bash command ONLY when it is a Projekt API call that
# hits a sensitive surface (DELETE, or admin/finance/payroll/tax/gl/consolidation/
# gdpr) WITHOUT an explicit --admit. Everything else passes untouched.
#
# Reads the PreToolUse JSON on stdin; exit 2 = block (reason on stderr).
set -uo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // ""' 2>/dev/null)"
[ -z "$cmd" ] && exit 0

# Only consider Projekt API traffic.
case "$cmd" in
  *projektrepublic.com/api*|*pj_req*|*'request("DELETE"'*|*"request('DELETE'"*) : ;;
  *) exit 0 ;;
esac

# Already explicitly admitted by the user.
case "$cmd" in *--admit*) exit 0 ;; esac

sensitive_re='(-X[[:space:]]*DELETE|request\(["'"'"']DELETE|/admin/|/admin"|/finance/|/payroll|/tax-multi|/gl/|/consolidation|/gdpr)'
if printf '%s' "$cmd" | grep -Eq "$sensitive_re"; then
  echo "⛔ Projekt guard: this looks like a DESTRUCTIVE or SENSITIVE Projekt API write (DELETE / admin / finance / payroll / tax / gdpr)." >&2
  echo "State the blast radius to the user and re-run with the script's second-confirmation flag (--admit) once approved." >&2
  exit 2
fi
exit 0
