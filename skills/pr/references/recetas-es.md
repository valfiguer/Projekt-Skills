# Recetas (español)

Flujos paso a paso. Todos empiezan conectando una vez y son **dry-run por defecto**: revisa el plan y
vuelve a ejecutar con `--apply` para escribir. `SK="${CLAUDE_SKILL_DIR}/scripts"`.

## 0. Conectar (siempre primero)
```bash
bash "$SK/auth_check.sh"      # resuelve usuario + organización + rol
bash "$SK/context_sync.sh"    # cachea proyectos + miembros en .projekt-run/context.json
```

## 1. Sembrar un backlog desde un CSV
1. Prepara el CSV con las columnas de `assets/import_template.csv`.
2. Vista previa (no escribe): el skill `pr` imprime una tabla con altas/duplicados.
3. Ejecuta: añade `--apply`. Reejecutar deduplica por `(proyecto,título)` + `external_ref`.

## 2. Planificar un sprint de punta a punta
`Conectar → estimar lo no estimado → asignar responsables → mover a "To Do" → documentar`.
- Estimar: skill `pr-informes` (puntos→horas vía `assets/points_hours.json`, marcado IA).
- Asignar y mover van en una misma llamada por lote (`op=set_assignee`, luego `op=set_status`).
  No existe la regla de «sin responsable no se mueve»: el 422 de un movimiento es el `wip_limit`
  de la columna destino, y solo en columnas que lo fijan.
- Las que no se puedan asignar se reportan como "necesita responsable", no se descartan en silencio.

## 3. Equilibrar la carga del equipo
```bash
# pr-informes usa agregados del servidor (sin gastar tokens en cálculo)
```
Genera un informe Markdown/CSV con sobre/infra-asignación y % de utilización a partir de
`/workforce/capacity` (semana en curso, sin parámetros), `/dashboard/stats` (contadores de
todo el histórico) y `/time-entries/summary` (el único que acepta `from`/`to`).

## 4. Cargar tiempos en lote
El skill `pr` registra entradas desde una hoja `{tarea, fecha, minutos, nota}`, rechaza
duraciones ≤0 y fechas futuras, y deduplica `(tarea,fecha,nota)` para reejecutar sin duplicar.

## 5. Documentar un proyecto
El skill `pr-docs` hace *upsert* de documentos (bloques EditorJS, anidados por `parent_doc_id`),
regenera la bitácora de incidencias (si la IA está agotada, 503 = se salta y conserva lo previo) y
exporta el PDF de una incidencia.

## 6. Llegar a cualquier endpoint (superficie completa)
```bash
bash "$SK/fetch_spec.sh"                       # una vez: cachea + indexa el spec
bash "$SK/spec_lookup.sh" --search "factura"    # busca rutas candidatas
bash "$SK/spec_lookup.sh" "/invoices" post       # imprime UN bloque del spec
```
🔒 Cualquier escritura en `admin / finance / payroll / tax / gdpr` exige confirmación extra: indica el
alcance del cambio antes de aplicar.
