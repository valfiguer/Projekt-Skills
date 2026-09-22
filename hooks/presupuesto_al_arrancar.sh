#!/usr/bin/env bash
# presupuesto_al_arrancar.sh — SessionStart. Dice, en dos o tres líneas, lo que costó la
# sesión anterior de ESTE proyecto: lectura de caché por turno (el 97 % del gasto) y qué
# herramienta llenó más el contexto.
#
# Por qué un hook y no la skill: el gasto se decide en cada llamada, y una skill solo
# está en el contexto cuando alguien la invoca. Esto corre siempre, fuera del modelo, y
# no gasta un token en medir.
#
# Silencioso por diseño: si no hay python3, ni transcripciones, ni proyecto, no dice
# nada. Un hook que se queja en cada arranque acaba desinstalado.
#
# Se apaga con PROJEKT_TOKENS_SIN_AVISO=1.
set -uo pipefail

[ "${PROJEKT_TOKENS_SIN_AVISO:-0}" = "1" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

entrada="$(cat 2>/dev/null || true)"
cwd=""
if command -v jq >/dev/null 2>&1 && [ -n "$entrada" ]; then
  cwd="$(printf '%s' "$entrada" | jq -r '.cwd // empty' 2>/dev/null)"
fi
[ -z "$cwd" ] && cwd="$PWD"

medir="${CLAUDE_PLUGIN_ROOT}/skills/projekt-tokens/scripts/medir.py"
[ -f "$medir" ] || exit 0

# --max-mb: una transcripción enorme se salta en vez de hacer esperar al arranque.
salida="$(python3 "$medir" --proyecto "$cwd" --breve --max-mb 40 \
          --aviso "${PROJEKT_TOKENS_AVISO:-200000}" 2>/dev/null || true)"
[ -z "$salida" ] && exit 0

printf '%s\n' "$salida"
printf 'Las reglas de contexto de este repo están en su CLAUDE.md (bloque projekt-tokens); el detalle, con /projekt-tokens.\n'
exit 0
