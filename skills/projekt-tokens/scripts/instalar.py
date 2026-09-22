#!/usr/bin/env python3
"""instalar.py — mete (y actualiza) el bloque de reglas de contexto en un CLAUDE.md.

Una skill solo está en el contexto cuando alguien la invoca, y el gasto se decide en
CADA llamada. Así que la parte de `projekt-tokens` que de verdad ahorra no es su prosa:
es este bloque, que vive en el `CLAUDE.md` del repo y por tanto se lee entero en todas
las sesiones.

Idempotente por marcas: el bloque va entre `<!-- projekt-tokens:inicio -->` y
`<!-- projekt-tokens:fin -->`. Si ya está, se REEMPLAZA; si no, se añade al final. Correr
esto dos veces deja el fichero igual que correrlo una.

DRY-RUN por defecto: imprime qué haría y no escribe nada hasta que se pasa `--apply`.

Uso:
    python3 instalar.py                       # dry-run sobre ./CLAUDE.md
    python3 instalar.py --apply
    python3 instalar.py --repo ~/dev/otro --apply
    python3 instalar.py --quitar --apply      # retira el bloque y deja el resto intacto
"""
from __future__ import annotations

import argparse
import difflib
import pathlib
import re
import sys

INICIO = "<!-- projekt-tokens:inicio"
FIN = "<!-- projekt-tokens:fin -->"
BLOQUE = pathlib.Path(__file__).resolve().parent.parent / "reglas-del-proyecto.md"
PATRON = re.compile(re.escape(INICIO) + r".*?" + re.escape(FIN) + r"\n?", re.DOTALL)


def nuevo_texto(actual: str, bloque: str, quitar: bool) -> str:
    if quitar:
        return PATRON.sub("", actual).rstrip() + "\n"
    if PATRON.search(actual):
        return PATRON.sub(lambda _: bloque, actual)
    separador = "" if actual.endswith("\n\n") or not actual else "\n"
    return actual + separador + bloque


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".", help="repo destino (por defecto, el directorio actual)")
    ap.add_argument("--fichero", default="CLAUDE.md", help="fichero de instrucciones del repo")
    ap.add_argument("--quitar", action="store_true", help="retira el bloque en vez de ponerlo")
    ap.add_argument("--apply", action="store_true", help="escribe de verdad")
    a = ap.parse_args()

    destino = (pathlib.Path(a.repo).expanduser() / a.fichero).resolve()
    bloque = BLOQUE.read_text(encoding="utf-8")
    if not bloque.endswith("\n"):
        bloque += "\n"

    actual = destino.read_text(encoding="utf-8") if destino.exists() else ""
    if a.quitar and not PATRON.search(actual):
        print(f"no hay bloque que quitar en {destino}")
        return 0

    resultado = nuevo_texto(actual, bloque, a.quitar)
    if resultado == actual:
        print(f"{destino}: ya está al día, no toco nada")
        return 0

    if a.quitar:
        verbo, hecho = "quitaría", "quitado"
    elif PATRON.search(actual):
        verbo, hecho = "actualizaría", "actualizado"
    else:
        verbo, hecho = "añadiría", "añadido"
    diff = list(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            resultado.splitlines(keepends=True),
            fromfile=str(destino),
            tofile=str(destino) + " (nuevo)",
            n=1,
        )
    )
    if not a.apply:
        print(f"DRY-RUN · {verbo} el bloque en {destino} ({len(diff)} líneas de diff)")
        print("".join(diff[:40]), end="")
        if len(diff) > 40:
            print(f"… y {len(diff) - 40} líneas más")
        print("\nvuelve a lanzarlo con --apply para escribir")
        return 0

    if not destino.parent.is_dir():
        print(f"no existe el directorio {destino.parent}", file=sys.stderr)
        return 1
    destino.write_text(resultado, encoding="utf-8")
    print(f"escrito: {hecho} el bloque en {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
