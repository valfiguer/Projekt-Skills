---
name: pr-tokens
description: >-
  Measure and cut what a Claude Code session actually costs in tokens, read from the machine's
  own transcripts (no API call, no tokens spent): the four billing buckets, cache-read per turn,
  which tool filled the context, and the biggest dumps. Then install the context rules into the
  repo's CLAUDE.md and pick a domain-scoped Projekt MCP profile instead of the full catalogue.
  Use when a session is expensive, or to reduce token spend, optimize context, shrink the MCP
  tool catalogue, or set a context budget.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*)
---

# pr-tokens — medir el gasto, y bajarlo

`M="${CLAUDE_SKILL_DIR}/scripts"` — los tres comandos salen de ahí.

## Lo primero, porque cambia dónde se mira

En una sesión de programación **el 97,8 % de los tokens es lectura de caché**: la
conversación entera se reenvía en cada turno. Medido en 18 sesiones reales (30.319 turnos,
22/09/2026):

```
entrada                 106.209   0,0 %
escritura de caché  293.100.824   2,0 %
LECTURA DE CACHÉ 14.537.908.034  97,8 %
salida               34.913.098   0,2 %
```

Consecuencia: **lo que se paga no es lo que entra, es lo que entra multiplicado por los
turnos que quedan.** Un resultado de 8.000 caracteres en el turno 40 de una sesión de 400
se paga 360 veces. Por eso la cifra que hay que vigilar es *lectura por turno*, no el
total, y por eso el catálogo del MCP —que viaja una vez y va cacheado— casi nunca es el
problema que parece.

Quién llena ese contexto, medido sobre 16,77 M de caracteres de resultados: **`Bash`
82,6 %** (grep 10,2 · sed 17,4 · cat 4,2), `Read` 2,4 %, MCP ~6 %. Y no hay un monstruo:
los resultados de ≥10.000 caracteres son el 0,7 % de las llamadas y el 12,8 % de los
bytes. Son mil cortes.

## 1. medir — la línea base, de los ficheros de la máquina

Lee `~/.claude/projects/<proyecto>/*.jsonl`, que traen el `usage` exacto de cada turno.
No llama a ninguna API ni manda nada fuera.

```bash
python3 "$M/medir.py"                     # el proyecto del directorio actual, 10 sesiones
python3 "$M/medir.py" --todas             # todo el histórico
python3 "$M/medir.py" --proyecto ~/dev/x  # otro repo
python3 "$M/medir.py" --breve             # tres líneas (lo que imprime el hook)
python3 "$M/medir.py" --json              # para otro programa
```

Devuelve los cuatro cubos con su reparto, **lectura por turno**, la peor sesión, la
equivalencia en dólares a tarifa de API (`tarifas.json`, fechada), las cinco herramientas
que más contexto metieron, las familias de comando dentro de `Bash` y los tres volcados
más gordos con su comando.

Una sesión que pasa de **200.000 de lectura por turno** ya cuesta más por turno que el
trabajo que hace: cerrar y abrir (o `/compact`) antes de empezar algo largo.

## 2. instalar — las reglas donde SÍ se leen siempre

Una skill solo está en contexto cuando se invoca, y esto se decide en cada llamada. Así
que las ocho reglas medidas van al `CLAUDE.md` del repo, entre marcas, idempotentes:

```bash
python3 "$M/instalar.py" --repo .           # DRY-RUN: enseña el diff
python3 "$M/instalar.py" --repo . --apply
python3 "$M/instalar.py" --repo . --quitar --apply
```

El bloque está en `reglas-del-proyecto.md` y se puede leer antes de instalarlo. Correrlo
dos veces no duplica nada: reemplaza entre `<!-- projekt-tokens:inicio -->` y `:fin`.
**El marcador NO cambia con el renombrado de la skill**: es un contrato con los CLAUDE.md
que ya lo tienen instalado. Cambiarlo dejaría el bloque viejo huérfano y añadiría uno nuevo.

## 3. perfil — el catálogo del MCP que hace falta, y nada más

El servidor ya sabe exponer un subconjunto (`?tools=finance,crm`; `org` y `search` entran
siempre). Esto dice qué dominios pide una tarea y pone cifra a la diferencia:

```bash
python3 "$M/perfil_mcp.py" --tarea "registrar una factura de proveedor"
python3 "$M/perfil_mcp.py" --dominios finance,crm
python3 "$M/perfil_mcp.py" --dominios pm --desde-contrato <ruta>/openapi.json
```

`all` son ~140.000 tokens estimados en cada `tools/list`; `core`, ~31.000. **Ojo: pedir
dos dominios gordos puede salir MÁS caro que `core`**, y el script lo dice cuando pasa —
por eso existe, en vez de una recomendación fija.

## El hook, que es la parte que actúa sola

El plugin instala dos, y ninguno gasta tokens en decidir:

- **`presupuesto_al_arrancar.sh`** (`SessionStart`) — imprime la lectura por turno de la
  sesión anterior y avisa si pasó del umbral. Se apaga con `PROJEKT_TOKENS_SIN_AVISO=1`,
  y el umbral se mueve con `PROJEKT_TOKENS_AVISO`.
- **`aviso_de_tokens.sh`** (`PreToolUse` sobre `Bash`) — caza `cat` sin tope, búsquedas
  recursivas sin `-l`/`-c`, `git log` sin `-n`, `git diff` entero, `find`/`ls -R` sueltos.
  **Por defecto solo APUNTA** (una línea en `$TMPDIR/projekt-tokens-<usuario>/incumplimientos.log`)
  y deja pasar el comando: bloquear cuesta un turno, y un turno en una sesión cargada
  cuesta más que el volcado que evita. Con `PROJEKT_TOKENS_ESTRICTO=1` sí bloquea y dice
  la forma barata.

El orden correcto es ése: dejar que apunte unos días, mirar el registro
(`wc -l` y `cut -f2 … | sort | uniq -c`) y endurecer solo si la cuenta lo justifica.

## Lo que esta skill NO hace

- **No promete un porcentaje.** El veredicto es una segunda medición con el mismo
  comando una semana después, y se escribe aunque salga que no bajó.
- **No mide calidad.** La forma más eficaz de gastar menos es contestar peor; si un
  recorte obliga a pedir el dato dos veces, ha costado un turno y no ha ahorrado nada.
- **No es una factura.** En una suscripción los tokens se pagan en límite de uso; la
  equivalencia en dólares sirve para ordenar magnitudes y comparar semanas.
- **Las cifras de arriba son de un repo y una persona.** Reproducibles aquí; no son una
  afirmación sobre nadie más. Por eso el primer comando es `medir`, no `instalar`.

## Relación con las otras skills

- **`projekt-context`** guarda las memorias del repo como docs de Projekt y las carga de
  una vez: es la otra mitad del ahorro (no re-derivar lo que ya se sabe).
- **`projekt`** conecta el token y la organización; estos tres comandos no lo necesitan,
  porque no llaman a la API.
