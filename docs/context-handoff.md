# Prompt de contexto — sesión de revisión, Cuestión de Datos v2

Continúas como la sesión de **revisión/coordinación** del backend v2 de
"Cuestión de Datos" (tesis/investigación vinculada a MinCiencias/MinTIC).
El usuario, Juan Camilo Grajales B., corre en paralelo otra sesión de
Claude Code que **implementa** siguiendo prompts muy detallados; tu rol es
auditar ese trabajo con rigor real, no confiar en los reportes de PR sin
verificar, y coordinar los siguientes pasos. Un hilo anterior muy largo con
este mismo contexto se cerró por longitud — esta es la continuación.

## Primero: carga tu memoria persistente

Ya existe memoria guardada de la sesión anterior en
`C:\Users\graja\.claude\projects\D--Usuario-AppWebs-cuestion-de-datos-MinTIC\memory\`
(debería cargarse automáticamente vía `MEMORY.md`, pero verifica que la
tienes disponible). Contiene: quién es el usuario y cómo coordina el
trabajo, la lección de proceso más importante de la sesión anterior (no
cerrar tareas sin ejecución real — T-303 se reabrió DOS veces por esto), y
convenciones del repositorio que no son obvias leyendo el código (usar
`AGENTS.md` no `CLAUDE.md`, el reindexado incremental de
`codebase-memory-mcp` queda stale con frecuencia, el `.env` local ya tiene
claves reales configuradas). Léela antes de asumir nada.

## Reindexar antes de navegar

`codebase-memory-mcp` (proyecto `D-Usuario-AppWebs-cuestion-de-datos-MinTIC`)
puede estar desactualizado. Si buscas un símbolo reciente y no aparece, o
los conteos de nodos/aristas no cambian tras una edición real, usa
`delete_project` + `index_repository(mode="full")` desde cero — el
incremental no siempre detecta cambios en este entorno.

## Estado real verificado al cierre de la sesión anterior (2026-07-11)

- **`v2`** tiene mergeado hasta T-303 (PR #22, grafo real del agente
  LangGraph). Fase 3 del backend (T-300→T-301→T-302→T-401→T-403→T-303)
  completa y verificada con ejecución real contra Postgres+Socrata+Gemini.
- **PR #23** (`feat/t304-agent-endpoints` → `v2`, título "Implementar
  endpoints reales del agente T-304") está **abierto, en draft**, CI
  Backend/Frontend en verde, `mergeable`. Lo construyó la sesión
  implementadora siguiendo `docs/prompt-t304.md` (el prompt completo que se
  le dio, con firmas exactas verificadas de `runner.py`/`durability.py`/
  `main.py`/`schemas.py`/`config.py` — léelo para entender qué se le pidió
  exactamente). El PR reporta: `POST/GET/DELETE /v2/agent/...` con Bearer,
  `create_public_run` (interfaz nueva, separada de `create_run` del PoC —
  documentada en `research.md` §16), pruebas de contrato + integración,
  verificación manual con `curl`. **Esto NO fue auditado a fondo por la
  sesión anterior** — es tu primera tarea real.
- `research.md` llegaba hasta §16 (revísalo completo antes de asumir que un
  tema no tiene contexto previo — cada hallazgo real de esta fase quedó
  documentado ahí con problema/decisión/consecuencias).

## Tu primera tarea concreta

Audita el PR #23 con el mismo rigor que la sesión anterior tuvo que
aprender a aplicarse a sí misma (ver memoria "Rigor de verificación"):

1. `gh pr view 23` / `gh pr diff 23` para ver el estado actual (puede haber
   cambiado desde este snapshot).
2. Lee el diff completo, no solo el resumen del PR body.
3. Verifica los 4 endpoints contra un servidor local real
   (`uvicorn app.main:app --reload` + `curl`/PowerShell, comandos ya
   escritos en `quickstart.md` §5 puntos 4 y 4b) — el criterio de
   aceptación literal de T-304 en `tasks.md` exige esto explícitamente, no
   basta con que las pruebas mockeadas pasen.
4. Presta especial atención a: el manejo del `run_access_token` (¿se
   entrega en claro solo una vez? ¿se guarda solo el hash? ¿comparación en
   tiempo constante?), el rate limiting (`MAX_CONCURRENT_RUNS`), CORS, y
   que `retention_class` sea verdaderamente inaceptable desde el JSON
   público (RF-801).
5. Corre `ruff check .` y la suite completa (`pytest -m "not integration"`
   y, si tienes credenciales, `pytest -m integration`). El único fallo
   esperable y no bloqueante es
   `test_llm_factory.py::test_get_chat_model_from_settings_sin_key_falla_claro`
   (contaminación conocida de `.env` local, no es tuyo que arreglar).
6. Si encuentras problemas reales (como pasó con T-303: un bug de
   `base_url` y uno de sintaxis SQL que los mocks no detectaban), revierte
   el estado de cierre inmediatamente (PR a draft si no lo está, checkbox
   de `tasks.md` desmarcado) antes de investigar — no dejes el repositorio
   afirmando algo no verificado mientras trabajas.

## Lectura previa recomendada (si no la tienes ya en contexto)

`AGENTS.md` (no `CLAUDE.md`) → `specs/constitution.md` → `spec.md` Grupo 800
(RF-801-804) → `research.md` completo (especialmente §13-§16) → `plan.md`
§11 → `contracts/api-rest.md` completo → `pruebas.md` §2.2 → `tasks.md`
(estado de T-303/T-304/T-306/T-305).
