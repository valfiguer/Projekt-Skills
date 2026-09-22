#!/usr/bin/env bash
# aviso_de_tokens.sh — PreToolUse (Bash). Caza los comandos que vuelcan el contexto sin
# tope: un `cat` de un fichero entero, un `grep` recursivo sin `-l`/`-c`/`head`, un
# `git log` sin `-n`, un `find` o un `ls -R` sueltos.
#
# ── Por qué NO bloquea por defecto ───────────────────────────────────────────────────
#
# Bloquear cuesta un turno, y un turno en una sesión cargada cuesta más que el volcado
# que evita (medido: 450k-550k tokens de lectura de caché por turno, frente a los ~2k
# tokens de un volcado de 8.000 caracteres). Así que por defecto este hook sólo APUNTA:
# escribe una línea por incidencia en
#
#     ${TMPDIR:-/tmp}/projekt-tokens-<usuario>/incumplimientos.log
#
# y deja pasar el comando. Con esa cuenta delante se decide si merece la pena endurecer,
# que es lo que hace PROJEKT_TOKENS_ESTRICTO=1: entonces sí devuelve 2 y el comando no
# corre, con la forma barata escrita en el motivo.
#
#   PROJEKT_TOKENS_ESTRICTO=1   bloquea (exit 2) en vez de apuntar
#   PROJEKT_TOKENS_SIN_AVISO=1  apaga el hook entero
set -uo pipefail

[ "${PROJEKT_TOKENS_SIN_AVISO:-0}" = "1" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

entrada="$(cat)"
cmd="$(printf '%s' "$entrada" | jq -r '.tool_input.command // ""' 2>/dev/null)"
[ -z "$cmd" ] && exit 0

# Un comando que ya acota, escribe o cuenta no vuelca nada al contexto.
case "$cmd" in
  *"| head"*|*"|head"*|*"| tail"*|*"|tail"*|*"| wc"*|*"|wc"*|*"> /dev/null"*|*">/dev/null"*) exit 0 ;;
  *" -c "*|*" -l "*|*" -q "*|*"--stat"*|*"--oneline"*|*"--name-only"*|*"--quiet"*) exit 0 ;;
  *"<<'EOF'"*|*"<<EOF"*|*" > "*|*" >> "*) exit 0 ;;
esac

motivo=""
case "$cmd" in
  *"cat "*.json*|*"cat "*.lock*|*"cat "*.jsonl*|*"cat "*.map*)
    motivo="un \`cat\` de un fichero generado (json/lock/jsonl/map). Saca sólo lo que buscas: \`jq -r '.campo'\`, o \`grep -m5\`." ;;
  "cat "*|*" cat "*|*"&& cat "*)
    motivo="un \`cat\` sin tope. Si sabes dónde mirar, \`sed -n '40,90p' fichero\`; si no, \`grep -n patron fichero | head -20\`." ;;
esac
case "$cmd" in
  *"grep -r"*|*"grep -R"*|*"rg "*)
    [ -z "$motivo" ] && motivo="una búsqueda recursiva sin tope. Primero \`grep -rln patron\` (sólo ficheros) o \`grep -rc\` (cuántos), y sólo luego el contenido de uno." ;;
esac
case "$cmd" in
  *"git log"*)
    case "$cmd" in *" -n"*|*" -[0-9]"*) : ;; *) motivo="un \`git log\` sin \`-n\`. Usa \`git log --oneline -n 10\`." ;; esac ;;
  *"git diff"*)
    motivo="un \`git diff\` entero. Mira antes \`git diff --stat\` y baja al fichero que importe." ;;
esac
case "$cmd" in
  *"ls -R"*|*"find "*)
    [ -z "$motivo" ] && motivo="un listado recursivo sin tope. Acótalo con \`-maxdepth\` y \`| head -40\`." ;;
esac

[ -z "$motivo" ] && exit 0

registro="${TMPDIR:-/tmp}/projekt-tokens-$(id -un 2>/dev/null || echo anon)"
mkdir -p "$registro" 2>/dev/null || true
printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "${motivo%%.*}" "$(printf '%s' "$cmd" | tr '\n' ' ' | cut -c1-160)" \
  >> "$registro/incumplimientos.log" 2>/dev/null || true

if [ "${PROJEKT_TOKENS_ESTRICTO:-0}" = "1" ]; then
  echo "⛔ projekt-tokens: $motivo" >&2
  echo "(Modo estricto. Se apaga con PROJEKT_TOKENS_ESTRICTO=0.)" >&2
  exit 2
fi
exit 0
