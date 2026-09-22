#!/usr/bin/env python3
"""medir.py — lo que cuesta de verdad una sesión de Claude Code, medido en esta máquina.

Lee las transcripciones locales (`~/.claude/projects/<proyecto>/*.jsonl`), que traen el
`usage` exacto de cada turno, y saca los cuatro cubos que se pagan a precios distintos:

    entrada            1x el precio de entrada del modelo
    escritura de caché 1,25x
    LECTURA de caché   0,1x   ← casi siempre el 95-98 % de los tokens
    salida             su propio precio

No llama a ninguna API, no gasta un token y no manda nada a ningún sitio: todo sale de
ficheros que ya están en el disco.

── Por qué la lectura de caché es la cifra que manda ─────────────────────────────────

Cada turno reenvía la conversación entera. Lo que ya viajó se cobra como lectura de
caché, barato por token pero multiplicado por TODOS los turnos que quedan. O sea: un
resultado de 8.000 caracteres en el turno 40 de una sesión de 400 no se paga una vez,
se paga 360 veces. Por eso este script no rotula «tokens totales» sino **lectura por
turno**, que es la única cifra que se puede comparar entre sesiones de distinto largo.

── Lo medido al escribir esto (22/09/2026, proyecto Next Projekt, 18 sesiones) ───────

    entrada                 106.209   0,0 %
    escritura de caché  293.100.824   2,0 %
    LECTURA DE CACHÉ 14.537.908.034  97,8 %
    salida               34.913.098   0,2 %

    lectura por turno en las cinco sesiones grandes: 489k - 550k

Y de los 16,77 M de caracteres que devolvieron las herramientas, el 82,6 % los devolvió
`Bash` (sed 17,4 % · grep 10,2 % · cat 4,2 %). Los resultados de ≥10.000 caracteres son
el 0,7 % de las llamadas y solo el 12,8 % de los bytes: no hay un monstruo al que culpar,
son mil cortes.

Uso:
    python3 medir.py                      # el proyecto del directorio actual
    python3 medir.py --proyecto ~/dev/x   # otro proyecto
    python3 medir.py --sesiones 5         # solo las 5 más recientes (por defecto 10)
    python3 medir.py --todas              # todas las que haya
    python3 medir.py --breve              # 4 líneas: lo que imprime el hook
    python3 medir.py --json               # para otro programa
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import re
import sys

RAIZ = pathlib.Path.home() / ".claude" / "projects"
TARIFAS = pathlib.Path(__file__).resolve().parent.parent / "tarifas.json"

#: Por encima de esto, un resultado de herramienta deja de ser un dato y es un volcado.
#: Sale de la medición: el 2,7 % de las llamadas que pasan de aquí llevan el 26,5 % de
#: los bytes, así que es el corte con más recorrido por regla escrita.
VOLCADO = 5_000

#: Lectura por turno a partir de la cual conviene abrir sesión nueva. No es un límite
#: del producto: es el punto donde CADA turno siguiente cuesta ya más que el trabajo que
#: hace. Se puede mover con --aviso.
AVISO_POR_TURNO = 200_000


def carpeta_del_proyecto(ruta: str | None) -> pathlib.Path:
    """`/Users/x/dev/Mi Repo` → `~/.claude/projects/-Users-x-dev-Mi-Repo`."""
    p = pathlib.Path(ruta).expanduser().resolve() if ruta else pathlib.Path.cwd()
    return RAIZ / re.sub(r"[^A-Za-z0-9]", "-", str(p))


def tarifas() -> dict:
    return json.loads(TARIFAS.read_text(encoding="utf-8"))


def texto(c) -> str:
    """El contenido de un bloque, venga como venga (str, lista o dict anidado)."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(texto(x) for x in c)
    if isinstance(c, dict):
        if c.get("text"):
            return str(c["text"])
        if c.get("content"):
            return texto(c["content"])
    return ""


#: Verbos que no dicen nada de lo que devolvió el comando: son el andamio con el que
#: empieza casi toda línea (`cd …`, `export …`, un `echo` de cabecera, una asignación).
#: Sin esta lista la familia más gorda de cualquier medición es `cd`, que no se puede
#: arreglar porque no es el que vuelca.
ANDAMIO = frozenset({"cd", "export", "echo", "printf", "set", "source", ".", "true", "cat<<"})


def familia(cmd: str) -> str:
    """El primer verbo que DEVUELVE algo, saltándose el andamio del principio.

    Un comando real aquí es `export X=…; cd "…" && grep -rn foo | head`. El verbo que
    llena el contexto es `grep`, no `export` ni `cd`, así que se parten los segmentos y
    se devuelve el primero que no sea andamio.
    """
    segmentos = re.split(r"&&|\|\||[;|\n]", cmd)
    ultimo = "?"
    for seg in segmentos:
        trozos = seg.strip().split()
        while trozos and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", trozos[0]):
            trozos = trozos[1:]  # `S=/tmp/x && …`
        if not trozos:
            continue
        verbo = trozos[0].split("/")[-1]
        ultimo = verbo
        if verbo not in ANDAMIO:
            return verbo
    return ultimo


def leer(fichero: pathlib.Path, con_detalle: bool) -> dict:
    """Los cubos de una sesión, y (si se pide) qué herramienta llenó el contexto."""
    cubos = collections.Counter()
    por_modelo = collections.defaultdict(collections.Counter)
    turnos = 0
    por_tool = collections.Counter()
    por_familia = collections.Counter()
    volcados: list[tuple[int, str, str]] = []
    nombre_de_id: dict[str, tuple[str, str]] = {}

    with fichero.open(errors="replace") as f:
        for linea in f:
            try:
                d = json.loads(linea)
            except Exception:
                continue
            m = d.get("message") or {}
            uso = m.get("usage")
            if uso:
                turnos += 1
                modelo = re.sub(r"\[.*\]$", "", str(m.get("model") or "?"))
                for clave, campo in (
                    ("entrada", "input_tokens"),
                    ("escritura", "cache_creation_input_tokens"),
                    ("lectura", "cache_read_input_tokens"),
                    ("salida", "output_tokens"),
                ):
                    n = uso.get(campo) or 0
                    cubos[clave] += n
                    por_modelo[modelo][clave] += n
            if not con_detalle:
                continue
            contenido = m.get("content")
            if not isinstance(contenido, list):
                continue
            if m.get("role") == "assistant":
                for b in contenido:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        e = b.get("input") or {}
                        pista = e.get("command") or e.get("file_path") or e.get("pattern") or ""
                        nombre_de_id[b.get("id")] = (str(b.get("name")), str(pista))
            elif m.get("role") == "user":
                for b in contenido:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        nombre, pista = nombre_de_id.get(b.get("tool_use_id"), ("?", ""))
                        n = len(texto(b.get("content")))
                        por_tool[nombre] += n
                        if nombre == "Bash":
                            por_familia[familia(pista)] += n
                        if n >= VOLCADO:
                            volcados.append((n, nombre, pista[:70]))
    return {
        "fichero": fichero.name,
        "turnos": turnos,
        "cubos": cubos,
        "por_modelo": por_modelo,
        "por_tool": por_tool,
        "por_familia": por_familia,
        "volcados": volcados,
    }


def coste(por_modelo: dict, tarifa: dict) -> tuple[float, set[str]]:
    """Equivalencia en dólares y los modelos sin precio conocido."""
    mult = tarifa["multiplicadores"]
    total, sin_precio = 0.0, set()
    for modelo, c in por_modelo.items():
        p = tarifa["modelos"].get(modelo)
        if not p:
            if c.total():
                sin_precio.add(modelo)
            continue
        lectura = p.get("lectura_de_cache", p["entrada"] * mult["lectura_de_cache"])
        escritura = p.get("escritura_de_cache", p["entrada"] * mult["escritura_de_cache"])
        total += (
            c["entrada"] * p["entrada"]
            + c["escritura"] * escritura
            + c["lectura"] * lectura
            + c["salida"] * p["salida"]
        ) / 1e6
    return total, sin_precio


def recoger(carpeta: pathlib.Path, limite: int | None, con_detalle: bool) -> list[dict]:
    ficheros = sorted(carpeta.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if limite:
        ficheros = ficheros[:limite]
    return [r for r in (leer(f, con_detalle) for f in ficheros) if r["turnos"]]


def resumen(sesiones: list[dict], tarifa: dict) -> dict:
    cubos = collections.Counter()
    por_modelo = collections.defaultdict(collections.Counter)
    por_tool = collections.Counter()
    por_familia = collections.Counter()
    volcados: list[tuple[int, str, str]] = []
    turnos = 0
    for s in sesiones:
        cubos.update(s["cubos"])
        turnos += s["turnos"]
        for modelo, c in s["por_modelo"].items():
            por_modelo[modelo].update(c)
        por_tool.update(s["por_tool"])
        por_familia.update(s["por_familia"])
        volcados.extend(s["volcados"])
    dolares, sin_precio = coste(por_modelo, tarifa)
    peor = max(sesiones, key=lambda s: s["cubos"]["lectura"] / max(s["turnos"], 1), default=None)
    return {
        "sesiones": len(sesiones),
        "turnos": turnos,
        "cubos": dict(cubos),
        "total": sum(cubos.values()),
        "lectura_por_turno": cubos["lectura"] // max(turnos, 1),
        "peor_sesion": {
            "fichero": peor["fichero"],
            "turnos": peor["turnos"],
            "lectura_por_turno": peor["cubos"]["lectura"] // max(peor["turnos"], 1),
        }
        if peor
        else None,
        "dolares_equivalentes": round(dolares, 2),
        "modelos_sin_precio": sorted(sin_precio),
        "por_tool": por_tool.most_common(5),
        "por_familia": por_familia.most_common(5),
        "volcados": sorted(volcados, reverse=True)[:3],
        "chars_de_tools": sum(por_tool.values()),
        "chars_en_volcados": sum(v[0] for v in volcados),
    }


def imprimir(r: dict, aviso: int) -> None:
    total = max(r["total"], 1)
    c = r["cubos"]
    print(f"{r['sesiones']} sesiones · {r['turnos']:,} turnos")
    print(f"  entrada            {c.get('entrada', 0):>15,}  {c.get('entrada', 0)/total*100:5.1f} %")
    print(f"  escritura de caché {c.get('escritura', 0):>15,}  {c.get('escritura', 0)/total*100:5.1f} %")
    print(f"  LECTURA DE CACHÉ   {c.get('lectura', 0):>15,}  {c.get('lectura', 0)/total*100:5.1f} %")
    print(f"  salida             {c.get('salida', 0):>15,}  {c.get('salida', 0)/total*100:5.1f} %")
    print(f"\nlectura por turno: {r['lectura_por_turno']:,}" + ("  ⚠ pasa del aviso" if r["lectura_por_turno"] > aviso else ""))
    p = r["peor_sesion"]
    if p:
        print(f"peor sesión: {p['fichero'][:8]} · {p['turnos']:,} turnos · {p['lectura_por_turno']:,} por turno")
    print(f"equivalencia: ${r['dolares_equivalentes']:,.2f} a tarifa de API (una suscripción lo paga en límite de uso, no en dólares)")
    if r["modelos_sin_precio"]:
        print(f"  sin precio en tarifas.json: {', '.join(r['modelos_sin_precio'])}")
    if r["chars_de_tools"]:
        print(f"\nlo que llenó el contexto ({r['chars_de_tools']:,} caracteres de resultados):")
        for nombre, n in r["por_tool"]:
            print(f"  {nombre[:28]:<30}{n:>12,}  {n/r['chars_de_tools']*100:5.1f} %")
        if r["por_familia"]:
            fam = " · ".join(f"{v} {n:,}" for v, n in r["por_familia"])
            print(f"  dentro de Bash: {fam}")
        pct = r["chars_en_volcados"] / r["chars_de_tools"] * 100
        print(f"  resultados de ≥{VOLCADO:,} chars: {pct:.1f} % de los bytes")
        for n, nombre, pista in r["volcados"]:
            print(f"    {n:>8,}  {nombre[:16]:<18}{pista}")


def imprimir_breve(r: dict, aviso: int) -> None:
    total = max(r["total"], 1)
    pct = r["cubos"].get("lectura", 0) / total * 100
    print(
        f"Tokens de la última sesión: {r['turnos']:,} turnos · "
        f"{r['lectura_por_turno']:,} de lectura de caché por turno ({pct:.0f} % del gasto)."
    )
    if r["lectura_por_turno"] > aviso:
        print(
            f"⚠ Por encima de {aviso:,}: cada turno nuevo cuesta ya más que el trabajo que hace. "
            "Cierra y abre sesión (o /compact) antes de arrancar algo largo."
        )
    if r["por_tool"]:
        peor = r["por_tool"][0]
        print(f"Lo que más llenó el contexto: {peor[0]} ({peor[1]:,} caracteres).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--proyecto", help="ruta del repo (por defecto, el directorio actual)")
    ap.add_argument("--sesiones", type=int, default=10, help="cuántas transcripciones, de la más reciente hacia atrás")
    ap.add_argument("--todas", action="store_true", help="todas las transcripciones del proyecto")
    ap.add_argument("--breve", action="store_true", help="tres líneas sobre la última sesión (lo que usa el hook)")
    ap.add_argument("--json", action="store_true", dest="como_json")
    ap.add_argument("--aviso", type=int, default=AVISO_POR_TURNO, help="lectura por turno a partir de la cual avisar")
    ap.add_argument("--max-mb", type=float, default=0, help="salta las transcripciones mayores que esto (0 = sin límite)")
    a = ap.parse_args()

    carpeta = carpeta_del_proyecto(a.proyecto)
    if not carpeta.is_dir():
        print(f"sin transcripciones para este proyecto ({carpeta})", file=sys.stderr)
        return 1

    limite = 1 if a.breve else (None if a.todas else a.sesiones)
    if a.max_mb:
        # El tope mira SOLO las transcripciones que se van a leer, no las que hay. Una
        # sesión vieja de 100 MB no tiene por qué callar la medición de la de hoy.
        candidatas = sorted(carpeta.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
        if limite:
            candidatas = candidatas[:limite]
        grandes = [f for f in candidatas if f.stat().st_size > a.max_mb * 1e6]
        if grandes:
            mayor = max(f.stat().st_size for f in grandes) / 1e6
            print(f"({len(grandes)} transcripción/es de hasta {mayor:.0f} MB: medición omitida, súbelo con --max-mb)")
            return 0
    sesiones = recoger(carpeta, limite, con_detalle=True)
    if not sesiones:
        print("sin turnos medibles todavía", file=sys.stderr)
        return 1

    r = resumen(sesiones, tarifas())
    if a.como_json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=list))
    elif a.breve:
        imprimir_breve(r, a.aviso)
    else:
        imprimir(r, a.aviso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
