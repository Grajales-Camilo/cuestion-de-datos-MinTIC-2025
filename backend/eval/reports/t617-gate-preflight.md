# T-617A — Preflight reproducible de la puerta de migración

**Actividad:** T-617A (preflight de la puerta T-617). **No** ejecuta smoke 10,
golden-v1 ni golden-v2 con Gemini; **no** cambia el default de runtime; **no**
marca T-617 terminada; **no** retira el legado.
**Gobierna:** `research.md` §25, `plan.md` §13, `pruebas.md` §4.4, `tasks.md`
T-610…T-617. Documento **no normativo**.
**Fecha:** 2026-07-18, America/Bogota (UTC-5).

Distinción sostenida en todo el informe: **"el runner terminó"** (proceso
concluyó y persistió terminal) ≠ **"el agente resolvió"** (la respuesta coincidió
con lo esperado). Las suites de este preflight son deterministas/mockeadas: ambas
nociones coinciden por construcción. La segunda noción sólo se mide con LLM real
en T-617B.

---

## A. Punto de partida congelado

### A.1 Rama y commit

- **Rama base:** `v2`. **Rama del incremento:** `feat/t617-gate-preflight`
  (creada desde `v2` en este HEAD).
- **HEAD:** `44b2e9893ecc75c12b69c8426095b7a7d9561642`
  (`test(agent): close T-402 integrated quality gate`), que es exactamente el
  commit de cierre de T-402. `v2` ya estaba en ese commit.
- **Ancestro T-402:** `git merge-base --is-ancestor 44b2e98 HEAD` → exit `0`.
  Se cumple trivialmente porque `HEAD == 44b2e98`.

### A.2 Estado Git y archivos no rastreados preexistentes

- `git diff` y `git diff --cached`: **vacíos** (0 cambios rastreados).
- `git status --porcelain`: exactamente **18 archivos no rastreados
  preexistentes**, conservados intactos y no tocados:
  `backend/uv.lock`, `backend/eval/reports/019be4a6-…-763bb89d.md`, y 16
  documentos/figuras/prompts bajo `docs/`.
- Ningún archivo temporal quedó en el worktree (`backend/_t617a_preflight.py`
  usado para el preflight D se creó y eliminó dentro de esta sesión; no se
  commitea).

### A.3 Hashes de suites y métricas (antes y después de todas las corridas)

| Archivo | SHA-256 | Esperado | Estado |
|---|---|---|---|
| `backend/eval/golden/golden-v1.yaml` | `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72` | idéntico | intacto |
| `backend/eval/golden/golden-v2.yaml` (164535 bytes) | `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483` | idéntico | intacto |
| `backend/eval/metrics.py` | `bde462c2aaa5d91098442cc150f2e19a8330832db25fc6392140347ee51c079d` | — | intacto (no modificado) |

Reverificados tras ejecutar todas las suites: sin cambios byte a byte.

### A.4 Versiones de herramientas

- **Python (`backend/.venv`):** 3.13.14 (dentro de `>=3.12,<3.14`).
- **uv:** 0.11.24. **pytest:** 8.4.2. **ruff:** 0.15.20.

### A.5 PostgreSQL

- Contenedor `cuestion-de-datos-db`, imagen `pgvector/pgvector:0.8.0-pg16`,
  estado **`Up 2 hours (healthy)`**, puerto publicado `5433→5432`, 9 días de
  antigüedad. No fue levantado por esta sesión.
- `catalog_datasets = 8398` (catálogo sembrado intacto).
- Las pruebas de integración leen `os.environ["DATABASE_URL"]` directamente
  (no `Settings()`/`.env`), por lo que se exportó **solo** `DATABASE_URL`
  (`postgresql://<redacted>@localhost:5433/cuestion_de_datos`) en cada comando
  de integración.

### A.6 Configuración relevante (presencia/ausencia/origen, sin secretos)

- `EVAL_MODE`: presente y `=false` en `backend/.env` y en `backend/.env.example`.
- `AGENT_RUNTIME`: **ausente** en `backend/.env` y en `backend/.env.example`.
  No hay ninguna otra configuración versionada que lo fije.
- Claves API (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) y `DATABASE_URL`:
  presentes en `.env` (no versionado), **no** exportadas para las pruebas sin
  integración. Se verificó ausencia de las claves en el entorno del proceso
  antes de las suites no-integración (aprendizaje de la sesión anterior sobre
  contaminación por `source .env`).

---

## B. Auditoría del default prematuro

### B.1 Historia Git del default

- El default `deterministic` fue introducido por el commit
  **`120ce3cfd3fc6ae3cb9b5dad0a7c2ac2ae9debab`**
  (`feat(agent): make deterministic runtime the explicit default`,
  Juan Camilo Grajales B, **2026-07-12 23:13:46 -0500**).
- Ese mismo commit **creó** el `Literal` `AgentRuntime` y la línea
  `agent_runtime: AgentRuntime = Field(default="deterministic", …)` a la vez:
  el selector **nació** con default `deterministic`. **Nunca** existió en el
  código un default `legacy`.

### B.2 Cuatro planos, deliberadamente distintos

1. **Default del código:** `deterministic` (`backend/app/config.py:24`,
   confirmado por lectura directa).
2. **Configuración local efectiva (este checkout):** `deterministic`, porque
   `AGENT_RUNTIME` está **ausente** en `.env` y aplica el default de código.
3. **Configuración desplegada:** **sin evidencia verificable.** La Fase 7
   (T-701/T-702, despliegue) no está ejecutada y no existe manifiesto de entorno
   desplegado versionado que fije `AGENT_RUNTIME`. No se afirma que producción
   esté migrada ni que no lo esté: no hay dato.
4. **Política normativa (`pruebas.md` §4.4 / `plan.md` §13):** mientras la puerta
   esté abierta, los entornos de usuario/producción **deben** fijar
   `AGENT_RUNTIME=legacy` explícitamente; el default sólo pasa a `deterministic`
   **al superar T-617**.

**Desviación:** el plano (1) contradice al plano (4) desde `120ce3c`. Es la
"desviación documental conocida" registrada en la línea base T-610. T-617A la
**reconstruye y mide**; **no** la corrige (la corrección o formalización es
decisión de T-617B, de Juan Camilo y del coordinador).

### B.3 Despacho y opt-in

- `execute_agent_run_async` (`backend/app/agent/runner.py:688-695`): enruta a
  `execute_legacy_agent_run_async` **sólo si** `settings.agent_runtime ==
  "legacy"`; en cualquier otro caso, `execute_deterministic_agent_run_async`.
  **No hay fallback automático** entre runtimes.
- Prueba del opt-in explícito de legacy:
  `tests/test_runner_runtime_selection.py::test_legacy_runtime_requires_explicit_configuration`
  (legacy sólo se despacha con `_settings("legacy")`) y
  `::test_default_dispatches_only_to_deterministic_runtime`. Ambas **verdes** en
  el subconjunto determinista.
- **Capacidad de rollback real:** `legacy_agent_acceptance` = **7 passed**
  (diagnóstico anticipado, §C.7). El grafo legado (`app.agent.graph`) sigue
  ejecutable de punta a punta.
- `config_snapshot` de evaluación registra **`runtime`: settings.agent_runtime**
  (`eval/run.py:68`), de modo que las corridas reales de T-617B **sí** dejarán
  registrado el runtime efectivo por corrida — cerrando el vacío diagnóstico que
  la línea base T-610 no pudo resolver para la corrida histórica de 50 casos.

---

## C. Parte sin LLM real de la puerta (ejecutada en orden)

Todos los comandos desde `backend/` con `uv run`. Para las de integración se
exportó únicamente `DATABASE_URL`; las claves API se mantuvieron ausentes en las
no-integración.

### C.1 Recolección — `uv run pytest --collect-only -q`

| Selección | Comando | Resultado |
|---|---|---|
| Total | `--collect-only -q` | **991** recolectadas |
| No integración | `-m "not integration"` | **869** (122 deselected) |
| Integración | `-m "integration"` | **122** (869 deselected) |
| `deterministic_agent_acceptance` | idem | **19** |
| `legacy_agent_acceptance` | idem | **7** |
| Integración sin ambas aceptaciones | `-m "integration and not deterministic_agent_acceptance and not legacy_agent_acceptance"` | **96** |

Consistencia: 19 + 7 + 96 = 122 integración. ✅
Comparación con T-610: total 703 → 991 (+288 por T-611…T-615); no-integración
628 → 869 (+241); integración 75 → 122 (+47). El crecimiento corresponde a la
ruta determinista/textual T-611…T-615, no a cambios en T-617A.

### C.2 Unitarias deterministas dirigidas — **329 passed, 0 fallos** (5.50 s)

Inventario ejecutado = **10 archivos base de T-610** + **7 módulos deterministas
incorporados después** (T-613…T-615). Lista exacta:

Base T-610: `test_query_plan.py`, `test_plan_validator.py`,
`test_soql_renderer.py`, `test_llm_contracts.py`, `test_multiquery_retrieval.py`,
`test_deterministic_graph.py`, `test_deterministic_dependencies.py`,
`test_deterministic_pipeline.py`, `test_deterministic_runtime.py`,
`test_runner_runtime_selection.py`.
Ampliación determinista posterior: `test_deterministic_acceptance_guard.py`,
`test_deterministic_textual_planning.py`, `test_grounded_facts_contract.py`,
`test_grounded_synthesis_renderer.py`, `test_textual_fact_builder.py`,
`test_textual_facts.py`, `test_textual_integrity_metrics.py`.

**Clasificación de `test_deterministic_acceptance_guard.py`:** menciona
`app.agent.graph`/`build_graph`/`initial_state` **solo como literales de cadena**
en un análisis AST que **prohíbe** que la aceptación determinista los importe.
No importa ni ejecuta el grafo legado; es una meta-prueba de la separación de
runtimes, legítimamente determinista. Ningún otro archivo del inventario importa
símbolos legados (verificado con grep dirigido).

### C.3 Suite completa sin integración — `-m "not integration"`

**869 passed, 122 deselected, 5 warnings** en ~16 s. **0 fallos.** Coincide con
la evidencia de cierre de T-402 (869 passed). Advertencias: preexistentes
(`LangChainPendingDeprecationWarning`, `StarletteDeprecationWarning` por `httpx`/
`422`), ajenas al núcleo determinista.

### C.4 Aceptación determinista con PostgreSQL — `-m deterministic_agent_acceptance`

**18 passed, 1 xfailed, 972 deselected** en ~15 s. 18 + 1 = 19 recolectadas. El
`xfail(strict=True)` es el defecto documentado del **octavo candidato**
(seleccionado pero no perfilado), preexistente y fuera del alcance de T-615/617.

### C.5 Integraciones compartidas (sin ambas aceptaciones)

`-m "integration and not deterministic_agent_acceptance and not legacy_agent_acceptance"`
→ **95 passed, 1 skipped, 895 deselected** en **175.9 s** (~2:55). 95 + 1 = 96
recolectadas. El único skip es la prueba real de **RNF-010** cuando falta
configuración/índice apto (documentado en el cierre T-615). Las **2 pruebas
Socrata en vivo** (sin LLM, sin costo de modelo) pasaron dentro de esas 95;
la red hacia Socrata estuvo disponible.

### C.6 Validaciones estáticas

- `uv run ruff check .` → **All checks passed!**
- `uv run ruff format --check .` → **39 files would be reformatted, 150 already
  formatted.** Esta es **deuda de formato preexistente** ya registrada en el
  cierre de T-402 (§13: "~39 archivos históricos fuera de este incremento; no se
  reformatearon"). **No es introducida por T-617A** y **no se corrige** aquí
  (reformatear tocaría archivos ajenos al incremento). Afecta archivos históricos
  de tests y herramientas, no el comportamiento del runtime determinista. Se
  clasifica como **advertencia preexistente, no bloqueante**.

### C.7 Aceptación legacy — DIAGNÓSTICO ANTICIPADO (no escalón final)

`-m legacy_agent_acceptance` → **7 passed, 984 deselected** en ~18 s. Etiquetado
explícitamente como **diagnóstico anticipado**: prueba que el rollback existe y
está verde **hoy**. El orden normativo de T-617 exige ejecutar la aceptación
legacy **después** de smoke 10 + golden-v1 + golden-v2; por eso **no** se cuenta
todavía como cumplimiento final de la puerta. Se re-ejecutará como último escalón
en T-617B.

### C.8 Residuos de PostgreSQL tras las corridas

- `agent_runs` con `status='running'`: **0** (ninguna corrida huérfana).
- Bases temporales `t615ir_*`/`t617*`: **0**. Tablas de respaldo: **0**.
- `agent_runs` totales: 115; `worker_instances`: 17. Son **filas durables
  acumuladas de sesiones previas** (clase `eval`/técnica, gestionadas por el
  barrido de retención); las fixtures de aceptación borran exclusivamente sus
  propios UUID y preservan filas ajenas (regla `pruebas.md` §4.4 / T-615I-R). No
  son residuo de un fallo de este preflight.
- `catalog_datasets`: 8398 (intacto).

---

## D. Preflight del runner real (sin consumir Gemini)

Verificado con carga real de suites y análisis de `eval/run.py` / `eval/loader.py`
(sin ejecutar ningún caso):

| Condición | Resultado |
|---|---|
| `eval.run` acepta golden-v1 y golden-v2 | ✅ `default_suite_path` whitelist `{golden-v1, golden-v2}`; rechaza `golden-v3`, `../etc/passwd`, `golden-v1.yaml`, `""`. |
| Ambas suites cargan exactamente 50 casos | ✅ golden-v1 (v1.0.0, snapshot 2026-07-11) y golden-v2 (v2.0.0, snapshot 2026-07-18): **50 = 40 positivos + 10 negativos** cada una. |
| golden-v2 conserva su validación normativa | ✅ `load_golden_suite` aplica vocabulario cerrado de `acceptable_facts`, `allowed_datasets ⊆ expected`, `source_query` HTTPS, `tie_policy=reject` para extremos, cardinalidad de `canonical_text_set`, y huella `acceptable_facts_sha256` embebida en `notes`. |
| `config_snapshot` registra runtime, modelo, commit, semilla y límites | ✅ contiene `runtime`, `llm_provider`, `llm_model`, `agent_max_steps`, `embedding_model`, `eval_seed`, `git_commit`, `placeholder_min_ratio`, `run_max_duration_s`. |
| `EVAL_MODE=true` obligatorio en corridas reales | ✅ `run_suite` lanza `RuntimeError("EVAL_MODE=true es obligatorio…")` si `not settings.eval_mode`. Hoy `.env` tiene `EVAL_MODE=false`; T-617B debe fijarlo a `true`. |
| Smoke 10 seleccionable explícita y reproduciblemente | ✅ `_select_cases` soporta `--case-id` (repetible) y `--limit`; semilla fija (`--seed`, default 601000). Los **10 case_ids del smoke §4.4 existen en golden-v1 y en golden-v2** (0 faltantes en cada una). |
| Reportes no colisionan con históricos | ✅ el reporte de corrida se escribe en `eval/reports/{record.id}.md` con `record.id = uuid4`; el informe con nombre `t617-gate-preflight.md` no existía (sin colisión). |
| Se registran latencia, costo, claims, fabricaciones, negativos y diagnósticos por etapa | ✅ `_write_report` emite tablas "Recuperación", "Consumo y salida" (stop_reason, evidencias, claims, hechos, latencia ms, costo USD), "Fallos por etapa", "Motivos de fallo" e "Integridad textual"; `_finalize_eval_record` agrega `success_rate`, `recall_at_10`, `fabrication_count`, `orphan_figures_count`. |

Los 10 case_ids del smoke: `pilot-002-seguridad-homicidios`,
`pilot-003-salud-vigilancia`, `pilot-005-empleo-publico`, `pilot-013-app-dnp`,
`pilot-012-control-fiscal`, `pilot-021-sensibilizacion-valle`,
`pilot-022-red-vial`, `pilot-038-precipitacion`,
`pilot-045-negativo-dato-personal`, `pilot-046-negativo-tiempo-real`.

---

## E. Matriz de condiciones de la puerta `pruebas.md` §4.4

Estado tras T-617A. "Pendiente T-617B" = requiere LLM real y **no** está
autorizado en T-617A.

| # | Condición §4.4 | Estado T-617A | Evidencia |
|---|---|---|---|
| 1 | Unitarias deterministas y no integración verdes | ✅ cumplida | 329 dirigidas + 869 no-integración, 0 fallos |
| 2 | `deterministic_agent_acceptance` e integraciones compartidas verdes | ✅ cumplida | 18 passed +1 xfail; 95 passed +1 skip |
| 3 | Negativos 100% | ⏳ Pendiente T-617B | requiere smoke/golden con Gemini |
| 4 | `golden-v2` ≥ 80% con aprobación normativa | ⏳ Pendiente T-617B | golden-v2 materializado y validado (T-616B); ejecución y umbral aún no medidos; aprobación normativa a cargo de Juan Camilo/coordinador |
| 5 | Fabricaciones = 0 y cifras huérfanas = 0 | ⏳ Pendiente T-617B | métricas se calculan en la corrida real; instrumentación verificada (§D) |
| 6 | Persistencia, cancelación, durabilidad y terminal único | ✅ verificada por suites | historias de aceptación determinista 1–9 + integraciones (durabilidad, terminal único, cancelación); confirmación viva adicional llega con smoke/golden |
| 7 | Latencia y costo dentro de RNF-001/RNF-009 | ⏳ Pendiente T-617B | sólo medible con LLM real |
| 8 | `legacy_agent_acceptance` verde y rollback probado | ✅ diagnóstico verde (anticipado) | 7 passed; se re-ejecuta como escalón final en T-617B |

La puerta **no** es plenamente satisfacible dentro de T-617A por diseño: las
condiciones 3, 4, 5 y 7 dependen de las 110 corridas con LLM real que T-617A
tiene prohibido ejecutar. Todas las precondiciones sin LLM están **verdes**.

---

## F. Plan exacto y ordenado para T-617B

Sólo tras autorización explícita de Juan Camilo y del coordinador:

1. Partir de `v2` (o de esta rama tras revisión), reconfirmar prerrequisito
   (HEAD, hashes golden-v1/v2, worktree limpio).
2. Fijar `EVAL_MODE=true` en el entorno de evaluación controlado (no en backend
   público) y exportar `DATABASE_URL`. Confirmar `AGENT_RUNTIME` efectivo:
   para medir el runtime determinista, dejar el default o fijarlo explícito;
   registrar el valor efectivo (queda en `config_snapshot.runtime`).
3. Verificar Docker/PostgreSQL `healthy` y catálogo sembrado (8398).
4. **Smoke 10** (orden 1): `python -m eval.run --suite golden-v1 --provider
   google --model gemini-2.5-flash` con los 10 `--case-id` del §4.4 (o la suite
   que corresponda a la política). Puerta smoke: negativos 2/2, ningún positivo
   sólido retrocede, todo fallo con etapa/código, reporte persistido con commit/
   runtime/modelo/suite/semilla.
5. **golden-v1 50** (orden 2): corrida completa; archivar reporte
   `eval/reports/{uuid}.md`.
6. **golden-v2 50** (orden 3): corrida completa; medir `success_rate ≥ 80%`,
   fabricaciones = 0, cifras huérfanas = 0, cobertura de claims/hechos, latencia
   y costo.
7. **Aceptación legacy** (orden 4, escalón final): `pytest -m
   legacy_agent_acceptance` como cumplimiento normativo (no sólo diagnóstico) y
   probar rollback.
8. Contrastar con T-610 y archivar commit/config/reportes.
9. Sólo si **todas** las condiciones §4.4 se cumplen, y con aprobación
   normativa: formalizar el cambio de default a `deterministic`, medir tráfico,
   conservar `legacy` como rollback de emergencia por una versión. Marcar T-617.
   La eliminación del selector/código legado es una tarea posterior independiente.

**Estimación de las 110 corridas reales pendientes** (smoke 10 + golden-v1 50 +
golden-v2 50):

- **Costo:** RNF-009 exige `avg_cost_usd ≤ 0,05`/corrida ⇒ cota superior
  ~**5,50 USD** para 110 corridas (probablemente menor; casos simples cuestan
  menos).
- **Tiempo:** referencia histórica ~19 min por 50 casos ⇒ golden-v1 ~15–20 min,
  golden-v2 ~15–20 min, smoke ~4–6 min; total aproximado **35–50 min** de reloj
  más sobrecarga de arranque, dependiente de latencia de Gemini/Socrata.
- **Cuota:** consume cuota real de Gemini `gemini-2.5-flash` y llamadas a
  Socrata; ejecutar en entorno de evaluación con `EVAL_MODE=true`.

---

## G. No ejecutado / límites / riesgos

- **No** se ejecutaron Gemini, smoke 10, golden-v1 ni golden-v2 (prohibido en
  T-617A).
- **No** se cambió el default de runtime, ni se retiró/alteró el legado, ni se
  tocaron golden-v1/golden-v2/métricas/contratos/umbrales.
- **No** se marcó T-617 como terminada; **no** hubo push ni PR.
- Deuda preexistente reproducida y **no** tocada: 39 archivos con formato ruff
  pendiente (§C.6).
- Persiste el `xfail(strict=True)` del octavo candidato (fuera de alcance).
- No hay evidencia verificable de la configuración `AGENT_RUNTIME` desplegada
  (Fase 7 no ejecutada); la afirmación "producción migrada" **no** puede
  sostenerse ni refutarse con los datos disponibles.
- Los 115 `agent_runs` / 17 `worker_instances` durables preexistentes expiran
  por retención; no se borran en este preflight (borrar está fuera de alcance).

---

## H. Decisión (estado histórico T-617A, corregido)

**READY_FOR_T617B0.**

> Corrección T-617B0 (2026-07-18): la decisión histórica de T-617A decía
> "READY_FOR_T617B". Era prematura: el runner terminaba y mostraba valores
> crudos por caso, pero **no certificaba mecánicamente** varias condiciones de
> `pruebas.md` §4.2/§4.4 (ver §I). El estado correcto tras T-617A es
> **READY_FOR_T617B0** (cerrar instrumentación antes de gastar cuota). La
> decisión de pasar a T-617B corresponde a §I/§J de este informe y a la
> aprobación de Juan Camilo y del coordinador.

Todas las precondiciones sin LLM de la puerta §4.4 están verdes y reproducibles;
el runner real está validado para aceptar ambas suites, seleccionar el smoke 10
de forma explícita/reproducible, exigir `EVAL_MODE=true`, registrar runtime/
modelo/commit/semilla/límites y no colisionar reportes. El rollback legado está
verde (diagnóstico anticipado). La formalización del cambio de default y el
cierre de T-617 quedan sujetos a la ejecución de T-617B y a la aprobación
normativa de Juan Camilo y del coordinador.

---

## I. Corrección T-617B0 — huecos de instrumentación cerrados

**Aviso normativo:** mostrar por caso la latencia y el costo crudos **no
equivale** a medir los umbrales de `pruebas.md` §4.2. T-617A emitía tablas
por caso pero no calculaba p95/promedio ni los comparaba contra RNF-001/009,
y calculaba `success_rate` sobre los 50 casos (positivos + negativos). Los
cinco huecos reproducidos contra el código real y su corrección
(exclusivamente en `backend/eval/`, sin tocar runtime, contratos ni umbrales):

1. **`success_rate` sobre todos los casos, no solo positivos.** CIERTO.
   `_finalize_eval_record`/`run_suite` dividían `passed` entre `len(results)`
   (incluidos los 10 negativos). Un 30/40 positivos + 10/10 negativos se
   reportaba como 80%. **Corregido:** `success_rate` se calcula solo sobre
   positivos; los negativos se agregan aparte y exigen 100% para la puerta.
2. **Columnas agregadas sin poblar.** CIERTO. `EvalRun` tenía
   `socrata_success_rate`, `claims_coverage`, `claims_reproducible`, latencias
   p50/p95 (global/simple/multipaso) y `avg_cost_usd`, pero `_finalize` solo
   escribía `success_rate`, `recall_at_10`, `fabrication_count` y
   `orphan_figures_count`. **Corregido:** todas se calculan y persisten.
3. **Sin certificación de integridad cuantitativa completa (RF-208/RNF-003).**
   PARCIAL. `assess_case` validaba `expected_facts` y cifras huérfanas, pero no
   reejecutaba la fórmula DSL de cada claim ni reproducía `raw_value`/
   `display_value`/`source_hash` desde la evidencia. **Corregido:**
   `evaluate_claims_integrity` reejecuta cada claim de forma determinista
   (evidencia existe, filas/operandos existen, DSL, redondeo, presentación,
   `source_hash`, cifras huérfanas) sin usar `expected_facts` ni prosa del LLM.
4. **Latencia/costo crudos sin comparar contra umbrales.** CIERTO. Se
   imprimían por caso, pero no se calculaba `latency_simple_p95 <= 20 s`,
   `latency_multistep_p95 <= 75 s` ni `avg_cost_usd <= 0,05`. **Corregido:**
   percentiles deterministas (nearest-rank), partición simple/multipaso por
   señales estructuradas y comparación explícita en el veredicto.
5. **Cláusula "medir tráfico" sin despliegue verificable.** CIERTO. Ver §J.

Además, el **exit code** dependía solo de `success_rate < 80%`. Ahora depende
del **veredicto de puerta completo**: falla si incumple cualquier condición
normativa (negativos 100%, fabricaciones 0, cifras huérfanas 0, integridad de
claims, recall, latencia y costo). El smoke conserva su puerta específica
(`--gate smoke`), distinta del umbral completo de golden-v2.

**Limitación honesta de `socrata_success_rate`:** el runtime determinista
(`observe_transition` en `runner.py`) registra los pasos con `tool_output=None`
y un error de transporte Socrata se traduce en rechazo de candidato sin código
observable por paso; por tanto la métrica solo es medible cuando el resultado
crudo de T5 (`ok`/`error.code`) queda persistido (ruta legacy). Cuando no hay
llamada T5 observable, la métrica es `None` (no se inventa 100%). Hacerla
medible en el runtime determinista exigiría instrumentar `backend/app/agent/`,
que está **congelado** y fuera del alcance de este incremento; se reporta como
conflicto, no se implementa por iniciativa propia.

Evidencia: `tests/test_eval_gate.py` (28 casos, verdes), suite eval relacionada
(95 verdes), `pytest -m "not integration"` = 897 passed / 0 fallos, `ruff check
.` limpio, `ruff format --check` limpio sobre archivos modificados.
`golden-v1`/`golden-v2` intactos (SHA-256 sin cambios).

---

## J. Conflicto operativo pendiente — cláusula "medir tráfico" de T-617

`tasks.md` T-617 exige, al superar la puerta, "medir tráfico". No hay despliegue
verificable: la Fase 7 (T-701, despliegue del backend) sigue **pendiente**
(`[ ]`). Las 110 evaluaciones de T-617B (smoke 10 + golden-v1 50 + golden-v2 50)
son **tráfico de evaluación** contra Gemini/Socrata, **no tráfico de usuarios**
sobre un servicio desplegado; llamarlas "tráfico" en el sentido de T-617 sería
cambiar la norma en silencio.

Este incremento **no** modifica la norma. Se proponen dos salidas (sin
ejecutar ninguna; decisión de Juan Camilo y del coordinador):

1. **Mantener T-617 abierta** hasta medir un canary realmente desplegado
   (después de T-701), separando "puerta técnica superada" de "tráfico medido".
2. **Solicitar una enmienda humana** que traslade explícitamente la medición de
   tráfico a T-701/T-703 (monitoreo con tráfico real, RNF-001/009), dejando a
   T-617 solo la puerta técnica de migración.

---

## K. Corrección T-617B0-R — cuatro falsos positivos mecánicos remanentes

**Contexto:** tras T-617B0, Codex (revisor) encontró que la instrumentación de
`backend/eval/gate.py` todavía podía emitir un PASS espurio en cuatro bordes.
T-617B0-R los cierra **sin ejecutar Gemini, smoke ni golden**, exclusivamente en
`backend/eval/` (runtime, contratos, umbrales normativos y golden-v1/v2
intactos). Cada uno se reprodujo primero mecánicamente contra el código real
(script mínimo, sin LLM) y luego se cubrió con una prueba de regresión que falla
antes del fix. Los cuatro, con su causa raíz y su corrección:

1. **`None` aprobaba la puerta completa (latencia/costo sin medir).** CIERTO.
   `evaluate_full_gate` usaba `ls is None or ls <= umbral` (y análogamente para
   `latency_multistep_p95_ms` y `avg_cost_usd`): un p95 o un costo `None` —es
   decir, **no medido**— pasaba. Reproducción: 50 casos con `latency_ms=None` y
   `cost_usd=None` daban `passed=True`. **Corregido:** (a) dos métricas de
   completitud (`latencia_medida`, `costo_medido`) que exigen medición en
   `N/N` casos y registran el conteo medido/esperado; (b) el p95 simple y el
   multipaso exigen **muestra válida no vacía** (`ls is not None and ls <=
   umbral`), de modo que un `None` produce FAIL con razón explícita; (c)
   `avg_cost_usd` exige valor presente. `AggregateMetrics` añade
   `measured_total`, `latency_measured_count`, `cost_measured_count`,
   `simple_sample_count` y `multistep_sample_count`.
2. **`recall@10` excluía silenciosamente los positivos sin medir.** CIERTO.
   `aggregate_metrics` calculaba el recall sobre `recall_pool = [positivos con
   recall_hit is not None]`, sacando del denominador los positivos con
   `recall_hit=None`. Reproducción: un positivo `True` + uno `None` daba
   `recall_at_10=1.0` (100%). **Corregido:** el denominador es **todos** los
   positivos; `None` cuenta como miss (`recall_hits = positivos con recall_hit
   is True`). Ahora True+None = 0.5. Se añade `recall_measured_count` para
   exponer medido vs. total sin alterar el denominador.
3. **El smoke aprobaba con un subconjunto de casos.** CIERTO.
   `evaluate_smoke_gate` no verificaba qué casos se ejecutaron: correr solo los
   dos negativos daba `passed=True` (negativos 2/2, ningún sólido presente que
   retroceda, ningún fallo sin clasificar). **Corregido:** se definen los **10
   case_ids canónicos** de `pruebas.md` §4.4 (`SMOKE_CANONICAL_IDS` = 4 sólidos
   + 4 patrones diferenciados + 2 negativos) y una métrica de cobertura
   canónica que exige exactamente esos 10; **faltar o añadir** casos produce
   FAIL antes de cualquier otro veredicto.
4. **Una corrida con cero consultas se clasificaba como "simple".** CIERTO.
   `classify_run_complexity` usaba `<= 1`, de modo que `{evidence:0, query:0,
   exploration:0}` (abstención, fallo o caso no aplicable) caía en "simple" y
   contaminaba el p95 simple. **Corregido:** "simple" exige **exactamente** 1
   evidencia y **exactamente** 1 SoQL con 0 exploraciones; cualquier otra
   corrida —incluidas las de cero consultas— es "multipaso". Documentado en el
   módulo: las corridas no aplicables/fallidas caen en "multipaso" (cota de
   latencia más holgada) y las que no tienen latencia observable no entran en
   ninguna muestra p95.

**`socrata_success_rate` se mantiene** como en §I: `None` = "no observable", no
bloqueante para §4.4; no se instrumentó `backend/app/agent/` (congelado).

**Regresiones añadidas (los tres ejemplos de Codex, más bordes):**
`test_full_gate_fails_when_latency_and_cost_are_none`,
`test_full_gate_fails_when_multistep_sample_missing`,
`test_recall_true_plus_none_is_never_100_percent`,
`test_recall_counts_none_as_miss_over_all_positives`,
`test_smoke_gate_fails_with_only_two_negatives`,
`test_smoke_gate_passes_with_exactly_the_ten_canonical`,
`test_smoke_gate_fails_when_extra_noncanonical_case_present`,
`test_classify_zero_queries_is_not_simple`.

**Verificación (2026-07-18):**
`pytest tests/test_eval_gate.py tests/test_eval_run_error_handling.py` = **41
passed**; `pytest -m "not integration"` = **905 passed, 122 deselected, 0
fallos**; `ruff check .` = **All checks passed!**; `ruff format --check
eval/gate.py tests/test_eval_gate.py` = **2 files already formatted**.
`golden-v1`/`golden-v2` con SHA-256 sin cambios
(`ab546062…4630ff72` / `1c78264c…54e483`). Sin cambios en `backend/app/`; sin
push ni PR; `tasks.md` sin cerrar.

**Estado T-617B0-R:** los tres falsos positivos reproducidos por Codex (y el
cuarto de complejidad) ya **no** son reproducibles ⇒ **READY_FOR_REAL_T617B**.
La ejecución de las 110 corridas reales queda sujeta a la autorización de Juan
Camilo y del coordinador (plan §F).

---

## L. Corrección T-617B0-R2 — dos falsos positivos mecánicos remanentes

**Contexto:** tras T-617B0-R, Codex encontró **dos** bordes adicionales en los
que la instrumentación de `backend/eval/gate.py` todavía podía emitir un PASS
espurio: una **muestra parcial** certificada como puerta completa y una corrida
de smoke con un **resultado duplicado**. T-617B0-R2 los cierra **sin ejecutar
Gemini, Socrata real ni PostgreSQL real**, exclusivamente en `backend/eval/`
(runtime `backend/app/**`, contratos, umbrales normativos, `specs/**`,
`tasks.md` y golden-v1/v2 intactos). Cada uno se reprodujo primero
mecánicamente contra el código real (script mínimo, sin LLM) y luego se cubrió
con pruebas de regresión que fallan antes del fix.

### L.1 Defectos reproducidos (antes del fix)

1. **Puerta `full` con muestra parcial.** CIERTO. `evaluate_full_gate` no
   verificaba la cardinalidad de la suite: una muestra perfecta de solo **1
   positivo simple + 1 negativo multipaso** producía `passed=True` (2 casos,
   `success_rate=1.0`, negativos `1.0`, ambas particiones p95 pobladas). La
   puerta completa representa la ejecución COMPLETA de la suite golden y debe
   exigir exactamente **50 resultados, 40 positivos, 10 negativos y 50 case_ids
   únicos**.
2. **Smoke con resultado duplicado.** CIERTO. `evaluate_smoke_gate` calculaba la
   cobertura con un `set` de case_ids, de modo que los **10 canónicos más la
   repetición de uno** (11 resultados, 10 IDs únicos) daban `passed=True`. El
   smoke debe exigir exactamente los 10 `SMOKE_CANONICAL_IDS`, **una sola vez
   cada uno**.

### L.2 Corrección aplicada

- **Cardinalidad de suite completa (`eval/gate.py`).** `AggregateMetrics` gana
  `distinct_case_id_count`. `evaluate_full_gate` añade una métrica bloqueante
  `cardinalidad_suite`, evaluada **antes** de cualquier umbral de calidad, que
  exige `total==50`, `positivos==40`, `negativos==10` y `case_ids únicos==total`
  (constantes `FULL_GATE_TOTAL/POSITIVES/NEGATIVES`, que describen la
  composición fija de la suite, **no** relajan ni introducen umbrales
  normativos). Una muestra parcial —aunque sus métricas observadas sean
  perfectas— produce FAIL con razón explícita.
- **Unicidad en el smoke (`eval/gate.py`).** `evaluate_smoke_gate` detecta
  duplicados con `Counter`: la cobertura canónica ahora falla ante **faltantes,
  extras o duplicados**, exigiendo exactamente los 10 canónicos una sola vez.
- **Fail-fast del runner (`eval/run.py`).** Nuevo helper puro
  `validate_gate_selection(cases, gate_mode)` que se invoca en `run_suite`
  **inmediatamente después de `_select_cases` y antes de crear el engine, los
  registros de evaluación, abrir conexiones o invocar el agente/LLM**. Rechaza
  con `RuntimeError` claro (sin datos sensibles): selección `full` que no sea 50
  casos con distribución 40/10 e IDs únicos; selección `smoke` que no sean
  exactamente los 10 `SMOKE_CANONICAL_IDS` sin faltantes/extras/duplicados; y un
  `gate_mode` programático desconocido. Así, si `--limit`/`--case-id` dejan una
  selección incompatible, la corrida termina **antes de consumir cuota**.

Ningún umbral normativo se modifica; `socrata_success_rate` se mantiene como en
§I/§K (`None` = "no observable", no bloqueante; `backend/app/agent/` congelado,
no instrumentado).

### L.3 Reproducción antes/después

| Defecto | Antes | Después |
|---|---|---|
| `full` con 1 pos + 1 neg perfectos | `passed=True` | `passed=False` (razón: "selección incompatible con la puerta completa") |
| `smoke` 10 canónicos + 1 duplicado (11 resultados) | `passed=True` | `passed=False` (razón: "duplicados: …") |

### L.4 Regresiones añadidas

`tests/test_eval_gate.py`:
`test_full_gate_rejects_perfect_partial_sample` (parametrizada 2 y 10
resultados), `test_full_gate_cardinality_passes_with_exactly_40_positives_10_negatives`,
`test_full_gate_rejects_duplicated_case_ids_even_with_fifty_results`,
`test_smoke_gate_fails_with_duplicated_canonical_case`,
`test_validate_gate_selection_rejects_unknown_mode`,
`test_validate_gate_selection_full_rejects_incompatible` (parametrizada),
`test_validate_gate_selection_full_rejects_duplicates`,
`test_validate_gate_selection_full_accepts_complete_suite`,
`test_validate_gate_selection_smoke_rejects_missing_and_duplicate`,
`test_validate_gate_selection_smoke_accepts_exactly_ten_canonical`.
`tests/test_eval_run_error_handling.py`:
`test_run_suite_preflight_rejects_incompatible_selection_before_engine`
(parametrizada full/smoke, con espías que demuestran que **no** se creó el
engine ni se invocó el agente/LLM) y
`test_run_suite_preflight_rejects_unknown_gate_mode_before_engine`. Las dos
pruebas de resiliencia del bucle preexistentes neutralizan el preflight como un
colaborador más (aíslan el bucle, no la puerta), y su cobertura de puerta queda
en las pruebas dedicadas nuevas.

### L.5 Verificación (2026-07-18)

`pytest tests/test_eval_gate.py tests/test_eval_run_error_handling.py` = **57
passed**; `pytest -m "not integration"` = **921 passed, 122 deselected, 0
fallos**; `ruff check .` = **All checks passed!**; `ruff format --check
eval/gate.py eval/run.py tests/test_eval_gate.py
tests/test_eval_run_error_handling.py` = **4 files already formatted**;
`git diff --check` limpio. `golden-v1`/`golden-v2` con SHA-256 sin cambios
(`ab546062…4630ff72` / `1c78264c…54e483`). Sin cambios en `backend/app/`,
`specs/**` ni `tasks.md`; sin push ni PR; T-617 sigue abierta; no se ejecutaron
las 110 corridas reales ni se consumió cuota.

**Estado T-617B0-R2:** los dos falsos positivos remanentes (muestra parcial y
resultado duplicado) ya **no** son reproducibles ⇒ **READY_FOR_REAL_T617B**. La
ejecución de las 110 corridas reales queda sujeta a la autorización de Juan
Camilo y del coordinador (plan §F).

---

## M. Corrección T-617B0-R3 — falsa atribución de una falla de proveedor al agente

**Contexto:** tras la autorización de la ejecución real escalonada, el
**smoke real de 10 casos** (`eval run 9bebcb75-53d2-42f6-938f-bfbd45384128`,
`gemini-2.5-flash`, semilla `601000`, commit `b682332`) terminó con
`gate_passed=false` por "positivos sólidos que retroceden:
pilot-005-empleo-publico" (`success_rate=37.5%`, 3/8 positivos, 2/2
negativos). El reporte real queda **archivado como evidencia histórica, sin
reescribir**, en
[`backend/eval/reports/9bebcb75-53d2-42f6-938f-bfbd45384128.md`](9bebcb75-53d2-42f6-938f-bfbd45384128.md).
El smoke original **no pasó**; esta sección no revierte ese resultado, solo
corrige cómo se diagnostica su causa.

### M.1 Causa raíz reproducida contra el código real

`agent run 235466d2-a403-4c01-bc8e-817713ca3062` (caso
`pilot-005-empleo-publico`) terminó con `agent_runs.status="failed"` y
`agent_runs.terminal_error_code="LLM_PROVIDER_ERROR"` (504 del proveedor
durante `build_plan`, `app.agent.graph._llm_terminal_error`). El diagnóstico
de la corrida lo clasificó como `failure_stage="planning"`,
`failure_code="intent_mismatch"`, `failure_owner="agent"` — atribuyendo al
agente una falla que fue, en realidad, de infraestructura del proveedor. Dos
defectos independientes lo causaron, ambos en `backend/eval/`:

1. **`eval/run.py` nunca leía `run.status`/`run.terminal_error_code`.** El
   bucle por-caso llamaba `await execute_agent_run_async(...)` y luego solo
   leía `run.final_answer`; cuando el runtime determinista capturaba el error
   de proveedor internamente y persistía el terminal (sin relanzar la
   excepción hacia el arnés de evaluación), `error_code` quedaba en `None`.
   `EvalCaseResult.error_code` se persistía `null` pese a existir un código
   terminal tipado en `agent_runs`.
2. **`eval/diagnostics.build_stage_diagnostics` no tenía una rama para
   códigos terminales tipados de infraestructura/proveedor.** Con
   `infrastructure_error=None` (por el defecto anterior), la clasificación
   caía en la rama por defecto (`FailureCode.INTENT_MISMATCH`,
   `owner="agent"`) al no cumplirse ninguna de las condiciones semánticas
   anteriores (dataset esperado, plan_errors, zero_rows, etc.).

### M.2 Corrección aplicada

- **Propagación del terminal (`eval/run.py`).** Tras `get_run`, se leen
  `run.status`/`run.terminal_error_code` (con `getattr` defensivo, sin asumir
  el tipo del objeto retornado). Si `status=="failed"` y
  `terminal_error_code` es verdadero, se propaga como `provider_error_code` y
  como `error_code` persistido — **sin** depender del texto humano del
  error, solo del código tipado. Las observaciones parciales ya persistidas
  (`_stage_observations`) se conservan sin cambios.
- **Diagnóstico fiel (`eval/diagnostics.py`).** Nuevo
  `FailureCode.PROVIDER_ERROR` y constante
  `INFRASTRUCTURE_TERMINAL_ERROR_CODES` (`LLM_PROVIDER_ERROR`,
  `STRUCTURED_OUTPUT_INVALID`, `INTERNAL`, `RUN_TIMEOUT`,
  `HEARTBEAT_EXPIRED`, `WORKER_LOST`; excluye deliberadamente
  `RUN_INTERRUPTED`, que es cancelación con `status="interrupted"`, no
  `"failed"`). Nuevo parámetro `provider_error_code` en
  `build_stage_diagnostics`: cuando pertenece a ese conjunto, la
  clasificación es **siempre** `failure_code="provider_error"`,
  `failure_owner="infrastructure"`, conservando la última etapa observada
  ANTES del fallo (para este caso: `failure_stage="planning"` con
  `last_successful_stage="profiling"`, sin cambios respecto al reporte
  original). El snapshot diagnóstico gana `terminal_error_code` (el código
  original, siempre presente aunque sea `null`). El comportamiento previo de
  `infrastructure_error` (nombre de excepción Python del arnés) queda
  **intacto** para no romper la clasificación de fallos propios del arnés de
  evaluación (regresión de no-daño verificada).
- **Puertas smoke y full (`eval/gate.py`).** `CaseOutcome` gana
  `infrastructure_failure: bool = False`, poblado en `_build_case_outcome`
  desde `failure_owner=="infrastructure"`. `AggregateMetrics` gana
  `infrastructure_failure_count`/`infrastructure_failure_case_ids`. Ambas
  puertas añaden una métrica bloqueante `infraestructura` (0 corridas no
  evaluables) evaluada junto a la cardinalidad, **antes** de cualquier
  umbral de calidad: cualquier corrida con `infrastructure_failure=True`
  produce `verdict.passed=False`, sin excluirla de ningún denominador. En el
  smoke, `positivos_sólidos` excluye explícitamente los casos con
  `infrastructure_failure=True` de la lista de retrocesos semánticos (para
  no atribuirle al agente lo que no le pertenece), pero la puerta sigue
  bloqueada por la métrica `infraestructura`.
- **Reporte y configuración (`eval/run.py`).** Nueva tabla "Responsabilidad
  de fallos" (conteo por `failure_owner`: agente/golden/indeterminado/
  infraestructura) y "Fallos de infraestructura/proveedor" (caso,
  `terminal_error_code`, etapa de fallo, última etapa exitosa), separando
  explícitamente regresiones semánticas, fallos del contrato golden y fallos
  de infraestructura. `config_snapshot` gana
  `deterministic_textual_facts_enabled`. Se documenta en el propio código
  que `eval_seed` es metadata de reproducibilidad del experimento, no una
  garantía de determinismo de las respuestas de Gemini.

### M.3 Reproducción antes/después (sobre el hallazgo real)

| | Antes (reporte real archivado) | Después (mismo `terminal_error_code`, diagnóstico recalculado) |
|---|---|---|
| `EvalCaseResult.error_code` | `null` | `LLM_PROVIDER_ERROR` |
| `failure_code` | `intent_mismatch` | `provider_error` |
| `failure_owner` | `agent` | `infrastructure` |
| `failure_stage` / `last_successful_stage` | `planning` / `profiling` (sin cambio) | `planning` / `profiling` (sin cambio) |
| ¿Cuenta como retroceso semántico en `positivos_sólidos`? | Sí | No |
| ¿Bloquea la puerta smoke? | Sí (vía `positivos_sólidos`) | Sí (vía `infraestructura`) |

El smoke real **seguiría sin pasar** con la corrección aplicada (la métrica
`infraestructura` bloquea igual que antes bloqueaba `positivos_sólidos`);
lo que cambia es la atribución de responsabilidad, no el veredicto. No se
reinterpreta el resultado del smoke original como éxito.

### M.4 Límites respetados

Sin cambios en `backend/app/agent/**` (el runtime determinista/legado sigue
congelado); sin reglas específicas para `pilot-005`/`pilot-022`; sin cambios
en preguntas, `expected_facts`, `golden-v1`/`golden-v2`, umbrales,
cardinalidades ni contratos públicos. No se ejecutó ningún otro smoke real ni
las 100 corridas restantes (golden-v1 50 + golden-v2 50); esas corridas
quedan sujetas a nueva autorización explícita tras la auditoría de este
incremento. T-617 sigue **abierta**.

### M.5 Regresiones añadidas

`tests/test_eval_metrics.py`:
`test_diagnostics_classifies_provider_terminal_error_as_infrastructure`
(parametrizada `LLM_PROVIDER_ERROR`/`STRUCTURED_OUTPUT_INVALID`/
`RUN_TIMEOUT`),
`test_diagnostics_unrecognized_terminal_error_code_does_not_force_infrastructure`,
`test_diagnostics_harness_exception_keeps_prior_classification_unaffected`
(no-daño).
`tests/test_eval_gate.py`:
`test_smoke_gate_blocks_on_infra_failure_without_counting_it_as_semantic_regression`,
`test_full_gate_blocks_on_any_infrastructure_failure_even_with_perfect_metrics`,
`test_full_gate_passes_with_zero_infrastructure_failures_and_all_conditions_met`,
`test_smoke_gate_still_blocks_on_genuine_semantic_regression_of_a_solid`,
`test_smoke_gate_passes_cleanly_with_no_infrastructure_field_regression`.
`tests/test_eval_run_error_handling.py`:
`test_config_snapshot_registers_deterministic_textual_facts_enabled`.

Ninguna regresión ejecuta red, Gemini, Socrata ni PostgreSQL real: todas
operan sobre estructuras materializadas y dobles.

### M.6 Verificación (2026-07-18)

`pytest tests/test_eval_metrics.py tests/test_eval_gate.py
tests/test_eval_run_error_handling.py tests/test_eval_persistence.py
tests/test_eval_run_creation.py tests/test_eval_loader.py
tests/test_settings.py` = **114 passed**; `pytest -m "not integration"` =
**932 passed, 122 deselected, 0 fallos**; `ruff check .` = **All checks
passed!**; `ruff format --check` sobre los archivos modificados = limpio tras
un reformateo automático de `eval/run.py` (una línea larga, sin cambio
semántico); `git diff --check` limpio (solo advertencias de fin de línea
LF/CRLF, sin errores). `golden-v1`/`golden-v2` con SHA-256 sin cambios
(`ab546062…4630ff72` / `1c78264c…54e483`). Sin cambios en `backend/app/`,
`specs/**` ni `tasks.md` (salvo la nota operativa añadida al listado de
T-617); sin push ni PR; T-617 sigue abierta; no se ejecutó ningún LLM real en
este incremento.

**Estado T-617B0-R3:** la falsa atribución reproducida en el smoke real ya
**no** es reproducible ⇒ **READY_FOR_T617B_SMOKE_RETRY**. El reintento del
smoke real (y, si pasa, la continuación a golden-v1/golden-v2/aceptación
legacy) queda sujeto a nueva autorización explícita de Juan Camilo y del
coordinador.

---

## N. Corrección T-617B0-R3A — huecos de atribución cerrados por auditoría

**Contexto:** una auditoría posterior a T-617B0-R3 (baseline
`e74f3522853c75f6ae6ad984048bc327669602bb`) encontró que la corrección del 504
real quedaba bien resuelta, pero la taxonomía introducida tenía cinco huecos
adicionales. T-617B0-R3A los cierra **sin ejecutar Gemini, Socrata ni
PostgreSQL real**, exclusivamente en `backend/eval/` (sin tocar
`backend/app/agent/**`, golden-v1/v2, preguntas, `expected_facts`,
cardinalidades, umbrales ni contratos normativos). **R3 corrigió el 504
observado; R3A cierra los huecos que la auditoría encontró en esa misma
corrección** — ambos incrementos son necesarios y complementarios. El reporte
real `9bebcb75-53d2-42f6-938f-bfbd45384128.md` permanece **sin modificar**.

### N.1 Hallazgos de la auditoría y corrección aplicada

1. **`STRUCTURED_OUTPUT_INVALID` estaba incluido como infraestructura/
   proveedor.** CIERTO y contradecía `contracts/api-rest.md` §4: ese código
   distingue explícitamente una salida estructurada que sigue sin cumplir el
   esquema tras agotar el repair loop de una falla real del proveedor (`NO`
   es `retryable`; el problema es de esquema/prompt del agente, no de red,
   cuota, 5xx ni timeout). **Corregido:** se retira de
   `_INFRASTRUCTURE_TERMINAL_ERROR_CODE_TO_FAILURE_CODE` y se clasifica
   aparte con `failure_code="structured_output_invalid"`,
   `failure_owner="agent"`; si afecta un positivo sólido del smoke, sigue
   contando como regresión semántica bloqueante en `positivos_sólidos`
   (distinto de `provider_error`, que se excluye de esa lista).
2. **Las excepciones del arnés (`infrastructure_error`) conservaban
   `failure_owner="agent"`.** CIERTO: una excepción propia de
   `run_suite`/`create_eval_run`/persistencia/dependencias caía en un mapeo
   por etapa (`profile_failed`, `plan_invalid`, `value_not_resolved`,
   `query_failed`) con `owner="agent"` implícito — la misma clase de falsa
   atribución que R3 corrigió para el terminal de `agent_runs`, pero para el
   arnés mismo. **Corregido:** toda excepción del arnés se clasifica ahora
   con `failure_code="harness_error"`, `failure_owner="infrastructure"`
   (nunca regresión semántica), conservando el nombre de la excepción en
   `EvalCaseResult.error_code` (no en `failure_code`) para diagnóstico.
3. **`build_stage_diagnostics` evaluaba `golden_ambiguous` antes que la falla
   de infraestructura/proveedor.** CIERTO: un `LLM_PROVIDER_ERROR` sobre un
   caso con golden ambiguo podía terminar clasificado como
   `ambiguous_golden`/`owner="golden"`. **Corregido:** el orden de prioridad
   ahora es (1) terminal de infraestructura/proveedor/ejecución tipado, (2)
   `STRUCTURED_OUTPUT_INVALID`, (3) excepción del arnés, y **solo después**
   (4) `golden_ambiguous` y el resto de clasificaciones semánticas. Los
   fallos que impiden evaluar el caso nunca terminan como `ambiguous_golden`,
   `intent_mismatch` ni `plan_invalid`.
4. **`INTERNAL` se etiquetaba junto con "proveedor".** CIERTO: todos los
   códigos de infraestructura compartían el mismo `FailureCode.PROVIDER_ERROR`
   genérico, de modo que un error interno del runtime se leía como si Gemini
   hubiera fallado externamente. **Corregido:** cada código terminal tiene su
   propio `FailureCode` inequívoco: `LLM_PROVIDER_ERROR→provider_error`,
   `RUN_TIMEOUT→run_timeout`, `HEARTBEAT_EXPIRED→heartbeat_expired`,
   `WORKER_LOST→worker_lost`, `INTERNAL→internal_error`. Todos con
   `failure_owner="infrastructure"` y bloqueo idéntico por la métrica de
   puerta; solo cambia el código expuesto para diagnóstico.
5. **`HEARTBEAT_EXPIRED`/`WORKER_LOST` estaban documentados como soportados
   pero eran inalcanzables.** CIERTO: `run.py` solo leía
   `run.status == "failed"`, pero `app.agent.heartbeat_sweep` persiste ambos
   códigos con `status="interrupted"` (igual que `RUN_INTERRUPTED`, que se
   mantiene deliberadamente excluido por ser cancelación, no falla).
   **Corregido (opción 1 de las dos ofrecidas):** se propagan los terminales
   no evaluables tanto para `status="failed"` como para
   `status="interrupted"` (`eval.diagnostics.NON_EVALUABLE_RUN_STATUSES`),
   sin ampliar qué códigos se consideran infraestructura — solo qué
   `agent_runs.status` puede llevar uno.
6. **No existía una prueba integral del punto originalmente defectuoso
   dentro de `run_suite`.** CIERTO: las pruebas previas cubrían
   `build_stage_diagnostics` y `evaluate_smoke_gate`/`evaluate_full_gate` por
   separado, nunca la lectura y propagación real de
   `run.status`/`run.terminal_error_code` dentro del bucle de
   `run_suite`. **Corregido:** nueva prueba parametrizada
   `test_run_suite_propagates_provider_terminal_from_agent_run` que mockea
   `get_run` devolviendo `status`/`terminal_error_code`/`final_answer=None`
   directamente (sin invocar diagnósticos ni puerta por separado) y verifica
   de punta a punta `EvalCaseResult.error_code`, `failure_code`,
   `failure_owner`, `AggregateMetrics.infrastructure_failure_count` y el
   veredicto de puerta bloqueado por la métrica `infraestructura`.

### N.2 Verificación de que las pruebas fallan contra el baseline sin la corrección

Se creó un worktree temporal en `e74f3522853c75f6ae6ad984048bc327669602bb`
(`git worktree add`, eliminado después con `git worktree remove --force`; no
afectó este worktree) y se copiaron únicamente los tres archivos de prueba
modificados/nuevos, ejecutándolos con el mismo entorno virtual contra el
código de R3 sin R3A:

```
9 failed, 87 passed
FAILED test_diagnostics_classifies_harness_exception_as_infrastructure
FAILED test_diagnostics_classifies_provider_terminal_error_as_infrastructure[RUN_TIMEOUT-run_timeout]
FAILED test_diagnostics_classifies_provider_terminal_error_as_infrastructure[HEARTBEAT_EXPIRED-heartbeat_expired]
FAILED test_diagnostics_classifies_provider_terminal_error_as_infrastructure[WORKER_LOST-worker_lost]
FAILED test_diagnostics_classifies_provider_terminal_error_as_infrastructure[INTERNAL-internal_error]
FAILED test_diagnostics_structured_output_invalid_is_not_infrastructure
FAILED test_diagnostics_provider_error_outranks_golden_ambiguous
FAILED test_run_suite_propagates_provider_terminal_from_agent_run[interrupted-HEARTBEAT_EXPIRED-heartbeat_expired]
FAILED test_run_suite_persists_a_failed_case_and_still_finalizes
```

La variante `[failed-LLM_PROVIDER_ERROR-provider_error]` de
`test_run_suite_propagates_provider_terminal_from_agent_run` **ya pasaba** en
el baseline (R3 la había corregido); las nueve fallas restantes son
exactamente los huecos de esta auditoría. Todas pasan tras aplicar R3A.

### N.3 Tabla código terminal → owner → failure_code → efecto en smoke

| `agent_runs.status` | `terminal_error_code` | `failure_owner` | `failure_code` | ¿Cuenta como regresión semántica de un sólido? | ¿Bloquea la puerta? |
|---|---|---|---|---|---|
| `failed` | `LLM_PROVIDER_ERROR` | `infrastructure` | `provider_error` | No | Sí (métrica `infraestructura`) |
| `failed` | `RUN_TIMEOUT` | `infrastructure` | `run_timeout` | No | Sí (métrica `infraestructura`) |
| `failed` | `INTERNAL` | `infrastructure` | `internal_error` | No | Sí (métrica `infraestructura`) |
| `failed` | `STRUCTURED_OUTPUT_INVALID` | `agent` | `structured_output_invalid` | **Sí** | Sí (vía `positivos_sólidos`, si aplica) |
| `interrupted` | `HEARTBEAT_EXPIRED` | `infrastructure` | `heartbeat_expired` | No | Sí (métrica `infraestructura`) |
| `interrupted` | `WORKER_LOST` | `infrastructure` | `worker_lost` | No | Sí (métrica `infraestructura`) |
| `interrupted` | `RUN_INTERRUPTED` | *(sin cambio, clasificación previa)* | *(sin cambio)* | Según clasificación semántica previa | Según clasificación semántica previa |
| n/a (excepción del arnés) | *(nombre de excepción Python en `error_code`)* | `infrastructure` | `harness_error` | No | Sí (métrica `infraestructura`) |

### N.4 Regresiones añadidas/actualizadas

Nuevas: `test_diagnostics_structured_output_invalid_is_not_infrastructure`,
`test_diagnostics_provider_error_outranks_golden_ambiguous`,
`test_run_suite_propagates_provider_terminal_from_agent_run` (parametrizada
`failed`/`LLM_PROVIDER_ERROR` e `interrupted`/`HEARTBEAT_EXPIRED`),
`test_smoke_gate_structured_output_invalid_still_blocks_as_semantic_regression`.
Actualizadas (comportamiento intencionalmente cambiado, ya no "no-daño"):
`test_diagnostics_classifies_harness_exception_as_infrastructure` (antes
`..._classifies_profile_failure_from_last_observed_stage`/
`..._harness_exception_keeps_prior_classification_unaffected`),
`test_diagnostics_classifies_provider_terminal_error_as_infrastructure`
(ahora parametrizada con `failure_code` esperado por código,
`STRUCTURED_OUTPUT_INVALID` retirado de esta parametrización),
`test_run_suite_persists_a_failed_case_and_still_finalizes` (la excepción del
arnés ahora persiste `failure_code="harness_error"`/
`failure_owner="infrastructure"`, antes `"query_failed"`).

### N.5 Verificación (2026-07-18)

`pytest tests/test_eval_metrics.py tests/test_eval_gate.py
tests/test_eval_run_error_handling.py` = **96 passed**; `pytest -m "not
integration"` = **938 passed, 122 deselected, 0 fallos**; `ruff check .` =
**All checks passed!** (tras corregir `UP037` en `eval/diagnostics.py` y
`E501` en `tests/test_eval_run_error_handling.py`); `ruff format --check`
sobre los archivos modificados = **5 files already formatted**; `git diff
--check` limpio (solo advertencia LF/CRLF, sin errores). `golden-v1`/
`golden-v2` con SHA-256 sin cambios (`ab546062…4630ff72` /
`1c78264c…54e483`). Sin cambios en `backend/app/`; sin push ni PR; T-617
sigue abierta; cero llamadas LLM/Socrata/PostgreSQL reales en este
incremento (worktree temporal de verificación usó únicamente pruebas
deterministas con dobles, sin red).

**Estado T-617B0-R3A:** los cinco huecos de atribución encontrados por la
auditoría ya **no** son reproducibles ⇒ **READY_FOR_T617B_SMOKE_RETRY**. El
reintento del smoke real (y, si pasa, la continuación a
golden-v1/golden-v2/aceptación legacy) queda sujeto a nueva autorización
explícita de Juan Camilo y del coordinador.
