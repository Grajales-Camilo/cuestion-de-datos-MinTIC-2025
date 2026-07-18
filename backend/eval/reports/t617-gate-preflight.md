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

## H. Decisión

**READY_FOR_T617B.**

Todas las precondiciones sin LLM de la puerta §4.4 están verdes y reproducibles;
el runner real está validado para aceptar ambas suites, seleccionar el smoke 10
de forma explícita/reproducible, exigir `EVAL_MODE=true`, registrar runtime/
modelo/commit/semilla/límites y no colisionar reportes. El rollback legado está
verde (diagnóstico anticipado). No hay bloqueos técnicos para autorizar las 110
corridas reales. La formalización del cambio de default y el cierre de T-617
quedan sujetos a la ejecución de T-617B y a la aprobación normativa de Juan
Camilo y del coordinador.
