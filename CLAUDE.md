# Instrucciones para agentes

Antes de escribir o modificar código, leer en este orden:

1. `specs/constitution.md`
2. `specs/README.md`
3. `specs/001-cuestion-de-datos-v2/spec.md`
4. `specs/001-cuestion-de-datos-v2/research.md`
5. `specs/001-cuestion-de-datos-v2/plan.md`
6. `specs/001-cuestion-de-datos-v2/contracts/`
7. `specs/001-cuestion-de-datos-v2/data-model.md`
8. `specs/001-cuestion-de-datos-v2/pruebas.md`
9. `specs/001-cuestion-de-datos-v2/tasks.md`
10. `specs/001-cuestion-de-datos-v2/quickstart.md`
11. `specs/001-cuestion-de-datos-v2/checklists/requirements.md`, si existe

Este archivo refleja instrucciones operativas del repositorio. No altera la
jerarquía normativa definida por `specs/constitution.md`.

## Jerarquía

`constitution.md` > `spec.md` > `research.md` > `plan.md` >
`contracts/` > `data-model.md` > `pruebas.md` > `tasks.md` >
`quickstart.md` > código.

Si dos documentos se contradicen:

1. No asumir.
2. No modificar silenciosamente la especificación.
3. Reportar el conflicto.
4. Aplicar el documento de mayor jerarquía.

## Navegación del repositorio con MCP

- Este repositorio debe navegarse primero con `codebase-memory-mcp`.
- Antes de leer archivos de forma amplia, hacer búsquedas recursivas o inspeccionar directorios completos, consultar el grafo MCP para ubicar módulos, símbolos, rutas, dependencias, pruebas y hotspots relacionados.
- Abrir solo los archivos necesarios para verificar, implementar o probar el cambio solicitado.
- Si el índice MCP no existe, está desactualizado o no responde, indexar o actualizar el repositorio antes de continuar.
- Si el resultado del MCP contradice el contenido real de los archivos, prevalece el contenido real y se debe reportar la discrepancia.
- No usar el MCP para alterar la jerarquía documental definida en este archivo.

## Desarrollo

- Toda implementación debe mencionar los requisitos `RF-###` o `RNF-###`
  que satisface.
- Los contratos son la fuente de verdad de las interfaces.
- Las decisiones marcadas como `PENDIENTE` en `research.md` bloquean las
  tareas dependientes; no se deben resolver implícitamente en código.
- No cambiar contratos para adaptar código existente sin autorización.
- Ejecutar las pruebas relacionadas después de cada cambio.
- No marcar una tarea de `tasks.md` como terminada hasta verificar sus
  criterios de aceptación.
- No incluir secretos ni archivos `.env` reales.
- Trabajar en incrementos pequeños y revisables.

## Rediseño del núcleo determinista

La migración vigente está definida en:

- `specs/001-cuestion-de-datos-v2/research.md` §25.
- `specs/001-cuestion-de-datos-v2/plan.md` §13.
- `specs/001-cuestion-de-datos-v2/pruebas.md` §4.4.
- `specs/001-cuestion-de-datos-v2/tasks.md` T-610…T-617.

Reglas obligatorias:

- `legacy` y `deterministic` son runtimes, no proveedores o modelos LLM.
- El runtime legado está congelado: puede recibir cambios mínimos de
  clasificación, nombres, fixtures o compatibilidad necesarios para conservar
  el rollback, pero no nuevas heurísticas, prompts ni comportamiento.
- No atribuir al determinista pruebas que importen o ejecuten
  `app.agent.graph`, `build_graph` o `initial_state`.
- No modificar `backend/eval/golden/golden-v1.yaml`.
- `backend/eval/golden/GOLDEN_V2_PROPOSAL.md` es informativo y no autoriza
  crear `golden-v2.yaml`.
- No relajar `backend/eval/metrics.py` ni introducir IDs, cifras, filtros o
  respuestas de casos golden en runtime, prompts, fixtures de producción o
  ranking.
- Respetar estrictamente T-610 → T-611 → T-612 → T-613 → T-614 → T-615 →
  T-616 → T-617. No iniciar una tarea si la puerta anterior no tiene evidencia.
- T-611/T-612 son un incremento exclusivamente de pruebas y clasificación:
  no cambian recuperación, planificación, síntesis ni comportamiento
  productivo.
- Los cambios de contratos, modelo de datos, semántica de claims o suite
  normativa requieren aprobación previa de Juan Camilo y del agente
  coordinador; Claude Code no los decide ni implementa por iniciativa propia.
- Al superar la puerta final, `deterministic` pasa inmediatamente a ser el
  default; `legacy` queda solo como rollback administrativo durante una versión
  y después se elimina en una tarea independiente.

## Herramientas y evidencia

- Usar primero `codebase-memory-mcp`: indexar o actualizar, `search_graph`,
  `trace_path`, `get_code_snippet`, `query_graph` y arquitectura. Usar búsqueda
  textual solo para literales, configuración y documentación.
- Verificar el worktree antes y después de cada incremento. Preservar cambios y
  archivos ajenos; no usar `git reset --hard`, `git checkout --` ni borrar
  trabajo no reconocido.
- En Windows usar PowerShell 7 y los comandos documentados por el proyecto.
- Antes de instalar algo, comprobar `backend/pyproject.toml`, el entorno virtual
  y las herramientas ya disponibles. No agregar dependencias para resolver
  trabajo que puede hacerse con el stack existente.
- Para pruebas de integración comprobar Docker/PostgreSQL local y distinguir
  claramente “no ejecutada por ambiente” de “falló por código”.
- Empezar con la prueba dirigida, después el subconjunto relacionado y
  finalmente la puerta completa correspondiente.
- Todo cierre debe informar: archivos modificados, comandos exactos, resultados,
  pruebas no ejecutadas, limitaciones ambientales, riesgos y diff pendiente.

## Coordinación

Claude Code implementa la carpintería técnica y reúne evidencia. Juan Camilo y
el agente coordinador revisan arquitectura, alcance, resultados y autorización
de la siguiente puerta.

- Detenerse al completar el incremento autorizado y entregar el reporte.
- No continuar automáticamente a la siguiente tarea de `tasks.md`.
- Si aparece una contradicción normativa, un cambio de contrato, una mutación
  de `golden-v1`, una necesidad de relajar métricas o una decisión metodológica,
  detenerse y reportarla sin implementar una solución implícita.
