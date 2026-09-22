#!/usr/bin/env python3
"""perfil_mcp.py — qué catálogo de tools del MCP hace falta, y qué cuesta el que sobra.

El servidor MCP de Projekt ya sabe exponer un subconjunto: `?tools=finance,crm` en la URL
del conector (o `MCP_TOOLS=finance,crm` en stdio). `org` y `search` entran SIEMPRE, sin
pedirlos: sin el primero el modelo no sabe en qué organización está y sin el segundo no
puede convertir un nombre en un id.

Este script hace dos cosas: decir qué dominios pide una tarea y poner cifra a la
diferencia. No llama a nadie — la cuenta sale del catálogo declarado.

── De dónde salen los números ────────────────────────────────────────────────────────

Bytes por tool del `tools/list` serializado, medidos el 21/09/2026 en el repo del
producto (`apps/mcp/src/presupuesto-medido.ts`, vigilados por un guardián):

    perfil `core`   1.418 bytes por tool   (las de escritura tienen el esquema más gordo)
    perfil `all`    1.146 bytes por tool

Y el factor de 3,0 bytes por token, que `copilot/seleccion.py` fijó contra el consumo
real del proveedor. Los bytes son exactos; los tokens van rotulados como estimación
porque eso es lo que son.

El reparto por dominio se contó sobre `packages/api-contract/openapi/openapi.json` el
22/09/2026 (367 tools con `x-tool`). Como crece con cada ola, se puede volver a contar
con `--desde-contrato <ruta a openapi.json>` en vez de fiarse de la tabla de abajo.

Uso:
    python3 perfil_mcp.py --dominios finance,crm
    python3 perfil_mcp.py --tarea "registrar una factura de proveedor y cobrar"
    python3 perfil_mcp.py --dominios pm --url https://app.projektrepublic.com/mcp
    python3 perfil_mcp.py --desde-contrato ~/dev/projekt/packages/api-contract/openapi/openapi.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import unicodedata

BYTES_POR_TOOL_ALL = 1146
BYTES_POR_TOOL_CORE = 1418
BYTES_POR_TOKEN = 3.0

#: Los dos que entran siempre, decididos en el servidor (`DOMINIOS_SIEMPRE`).
SIEMPRE = ("org", "search")

#: Contado el 22/09/2026 sobre el contrato. `--desde-contrato` lo recalcula.
DOMINIOS = {
    "pm": 74,
    "finance": 67,
    "crm": 42,
    "hr": 41,
    "support": 29,
    "crossorg": 27,
    "context": 15,
    "docs": 15,
    "org": 11,
    "admin": 10,
    "calendar": 8,
    "okr": 8,
    "bi": 6,
    "automations": 6,
    "search": 4,
    "attachments": 4,
}
TOTAL_CORE = 66

#: Palabras → dominio. Salen de para qué se usa cada cajón, en los dos idiomas. No
#: pretende acertar siempre: es un atajo para no tener que recordar los dieciséis
#: nombres, y por eso imprime lo que ha entendido para poder corregirlo a mano.
PISTAS = {
    "pm": "tarea tareas issue issues proyecto proyectos sprint backlog tablero milestone hito time tiempo fichaje task project",
    "finance": "factura facturas gasto gastos cobro pago presupuesto invoice expense payment iva impuesto nomina payroll contabilidad tesoreria banco",
    "crm": "cliente clientes lead leads oportunidad deal pipeline presupuesto-comercial quote contacto customer",
    "hr": "empleado empleados vacaciones ausencia baja contrato rrhh nomina personal employee leave",
    "support": "ticket tickets soporte incidencia sla helpdesk support",
    "crossorg": "organizaciones compartido externo cross-org colaboracion shared",
    "context": "contexto memoria ingesta recuperacion retrieval kern",
    "docs": "documento documentos doc wiki pagina runbook documentation",
    "calendar": "reunion reuniones calendario evento meeting agenda",
    "okr": "okr objetivo objetivos key-result",
    "bi": "informe informes metrica metricas dashboard analitica report",
    "automations": "automatizacion automatizaciones regla trigger webhook automation",
    "admin": "administracion ajustes permisos roles miembros settings admin",
    "attachments": "adjunto adjuntos fichero ficheros subir upload attachment",
}


def normalizar(t: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def dominios_de(tarea: str) -> list[str]:
    palabras = set(normalizar(tarea).replace(",", " ").replace(".", " ").split())
    elegidos = [d for d, pistas in PISTAS.items() if palabras & set(pistas.split())]
    return sorted(elegidos)


def contar_desde_contrato(ruta: pathlib.Path) -> tuple[dict[str, int], int]:
    spec = json.loads(ruta.read_text(encoding="utf-8"))
    cuenta: dict[str, int] = {}
    core = 0
    for operaciones in spec.get("paths", {}).values():
        for op in operaciones.values():
            if not isinstance(op, dict):
                continue
            x = op.get("x-tool")
            if not x:
                continue
            for t in x if isinstance(x, list) else [x]:
                d = t.get("domain", "?")
                cuenta[d] = cuenta.get(d, 0) + 1
                if t.get("profile") == "core":
                    core += 1
    return cuenta, core


def tokens(bytes_: int) -> int:
    return int(bytes_ / BYTES_POR_TOKEN)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dominios", help="lista separada por comas")
    ap.add_argument("--tarea", help="una frase; de ella se deducen los dominios")
    ap.add_argument("--url", default="https://app.projektrepublic.com/mcp", help="base del conector remoto")
    ap.add_argument("--desde-contrato", help="ruta a un openapi.json para recontar los dominios")
    a = ap.parse_args()

    dominios_totales, total_core = DOMINIOS, TOTAL_CORE
    origen = "tabla contada el 22/09/2026"
    if a.desde_contrato:
        dominios_totales, total_core = contar_desde_contrato(pathlib.Path(a.desde_contrato).expanduser())
        origen = f"contado ahora en {a.desde_contrato}"

    total_all = sum(dominios_totales.values())

    if a.tarea and not a.dominios:
        elegidos = dominios_de(a.tarea)
        if not elegidos:
            print("no he sabido deducir ningún dominio de esa frase; pásalos con --dominios")
            print("disponibles: " + ", ".join(sorted(d for d in dominios_totales if d not in SIEMPRE)))
            return 1
        print(f"de «{a.tarea}» deduzco: {', '.join(elegidos)}")
    elif a.dominios:
        elegidos = sorted({d.strip() for d in a.dominios.split(",") if d.strip()})
    else:
        ap.error("hace falta --dominios o --tarea")

    desconocidos = [d for d in elegidos if d not in dominios_totales]
    if desconocidos:
        print(f"dominios que el catálogo no conoce: {', '.join(desconocidos)}", file=sys.stderr)
        return 1

    pedidos = sorted(set(elegidos) | set(SIEMPRE))
    n = sum(dominios_totales.get(d, 0) for d in pedidos)
    b = n * BYTES_POR_TOOL_ALL
    b_all = total_all * BYTES_POR_TOOL_ALL
    b_core = total_core * BYTES_POR_TOOL_CORE

    print(f"\ndominios ({origen}): {', '.join(pedidos)}   ({', '.join(SIEMPRE)} entran siempre)")
    print(f"\n{'perfil':<26}{'tools':>7}{'bytes':>12}{'tokens (est.)':>16}")
    print(f"{'?tools=' + ','.join(elegidos):<26}{n:>7}{b:>12,}{tokens(b):>16,}")
    print(f"{'core (por defecto)':<26}{total_core:>7}{b_core:>12,}{tokens(b_core):>16,}")
    print(f"{'all':<26}{total_all:>7}{b_all:>12,}{tokens(b_all):>16,}")
    print(f"\nfrente a `all`: {tokens(b_all) - tokens(b):,} tokens menos EN CADA `tools/list`")
    if b > b_core:
        print(f"frente a `core`: {tokens(b) - tokens(b_core):,} tokens MÁS — para esta tarea, `core` sale más barato")

    print(f"\n  remoto:  {a.url}?tools={','.join(elegidos)}")
    print(f"  stdio:   MCP_TOOLS={','.join(elegidos)}")
    print("\nSe cambia en la configuración del conector, y hace falta reiniciar el cliente")
    print("para que vuelva a pedir el catálogo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
