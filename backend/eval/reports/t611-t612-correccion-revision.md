# Ronda correctiva de revisión — T-611 / T-612

**Fecha:** 2026-07-16 · **Gobierna:** `research.md` §25, `plan.md` §13, `pruebas.md` §4.4, `tasks.md` T-610…T-617
**Alcance:** exclusivamente pruebas, aislamiento de datos y evidencia. Cero cambios en `backend/app/`.

Este documento corrige y reemplaza, para T-611/T-612, las afirmaciones del informe de cierre anterior de esta misma sesión que la revisión encontró imprecisas o incompletas. El informe de T-610 (`deterministic-development-baseline.md`) fue **aprobado sin cambios** en la revisión y no se toca aquí salvo esta referencia cruzada.

---

## 1. Estado revisado

| Tarea | Estado anterior | Estado revisado |
|---|---|---|
| T-610 | Completa | **Completa** (sin cambios; aprobada en la revisión) |
| T-611 | Declarada completa (incorrecto) | **Completa** tras las tres correcciones — ver §2 |
| T-612 | Declarada completa (aislamiento defectuoso) | **Completa** — guardia fortalecida, marcadores y rename intactos, aislamiento corregido |

## 2. Corrección aplicada a cada hallazgo

### Hallazgo 1 — limpieza amplia por `LIKE`/prefijo

**Antes:** la fixture `clean_acceptance_rows` ejecutaba `DELETE FROM agent_runs WHERE question LIKE 'T-611 %'` y `DELETE FROM catalog_datasets WHERE id LIKE 'dh%'`, antes **y** después de cada prueba.

**Corrección aplicada:**
- Nuevo fixture `created` (`_CreatedIds`, dataclass con `run_ids`/`dataset_ids`) que cada prueba puebla explícitamente al sembrar sus propias filas (`_seed_run`/`_seed_dataset` ahora reciben `created` y registran el identificador exacto que acaban de crear).
- El teardown de `created` corre en un `finally` (se ejecuta aunque la prueba falle) y borra **exclusivamente** los identificadores registrados, por igualdad exacta: `DELETE FROM agent_runs WHERE id = ANY(:ids)` y `DELETE FROM catalog_datasets WHERE id = ANY(:ids)`, en ese orden (respeta cascadas: `agent_runs` arrastra `agent_steps`/`agent_run_events`/`evidence_results`→`quality_reports`/`quantitative_claims`; `catalog_datasets` arrastra `catalog_columns`/`catalog_embeddings`).
- **Cero limpieza preventiva** al iniciar la suite: cada `dataset_id` se genera con `_fresh_dataset_id()` (sufijo aleatorio con formato Socrata `xxxx-xxxx`), así que no hay colisión posible con ejecuciones anteriores ni necesidad de barrer nada antes de empezar.
- **Prueba de preservación** (condición 6): fixture `sentinel_dataset_id` (scope `module`) crea una fila `catalog_datasets` ajena a todos los casos **antes** de la primera prueba del módulo y la prueba `test_zz_sentinel_dataset_survived_every_teardown_in_this_module` (nombrada para ejecutarse al final por orden de definición) confirma que sigue existiendo después de que las historias 1-10 corrieron y limpiaron sus propios datos.
- **Tolerancia a ejecución repetida**: verificado corriendo la suite completa 3 veces seguidas (§4) sin fallos ni filas residuales.

### Hallazgo 2 — la suite no cubre el ensamblaje productivo

**Antes:** las 9 (12 con subcasos) historias reemplazaban `app.agent.runner.build_real_runtime_dependencies` por completo; `build_real_runtime_dependencies` real nunca se ejecutaba.

**Corrección aplicada:** nueva **historia 10** (`test_h10_real_dependency_factory_assembles_working_adapters_end_to_end`) que:
- Mantiene el punto de entrada `execute_deterministic_agent_run_async`.
- **Deja correr la fábrica real** — NO se reemplaza `build_real_runtime_dependencies`; se envuelve con un spy (`unittest.mock.Mock(side_effect=<función real importada de `deterministic_dependencies_module`>)`) que ejecuta la implementación real y registra la llamada.
- Sustituye únicamente los bordes externos inevitables:
  - `app.agent.runner.GoogleGenerativeAIEmbeddings` → `_RealFactoryEmbeddingClient`, que sí implementa `.aembed_query` (a diferencia del `_InertEmbeddingClient` de las historias 1-9) y devuelve un vector unitario de 768 dimensiones generado con semilla fija (`_generate_unit_vector`, sin sesgo de eje para no coincidir por casualidad con la componente dominante de embeddings reales ya sembrados en el catálogo — el catálogo local tiene 8.398 datasets reales).
  - `httpx.AsyncClient` (global) → fábrica que construye un cliente real con `httpx.MockTransport` (nunca toca la red), interceptando la llamada a Socrata que hace `ejecutar_soql` real.
  - `app.agent.deterministic_dependencies.get_structured_chat_model` → fábrica que devuelve, por esquema (`IntentExtraction`/`EnumeratedPlanSelection`/`GroundedSynthesis`), un `Runnable` falso cuyo `.ainvoke()` retorna directamente la instancia Pydantic — el patrón que el propio `ainvoke_structured_chat_model` real documenta como válido ("los dobles de prueba pueden devolver directamente el objeto Pydantic"), así que `_invoke`/`ainvoke_structured_chat_model` corren SIN modificar.
- Siembra `catalog_datasets` + `catalog_columns` + `catalog_embeddings` reales (vector idéntico al que devuelve el embedding falso, similitud coseno = 1.0) para que `search_catalog` real (pgvector) recupere el dataset de la prueba.
- Verifica la cadena completa: nodos persistidos incluyen `select_candidate`, `profile_dataset` (Postgres real), `build_plan`, `execute_query` (T5→T6→T7 reales), `synthesize`, `complete`; 1 `evidence_results`, 1 `quality_reports`, 1 `quantitative_claims`.
- **Evidencia del spy**: `factory_spy.assert_called_once()` + inspección de `factory_spy.call_args.kwargs` (confirma `embedding_client` es la instancia falsa inyectada, `engine`/`http_client` no son `None`) — prueba que la fábrica real fue invocada y no reemplazada.
- Ejecutada varias veces sin fallos (§4); no fue necesario ningún cambio en código productivo para lograrlo, así que no aplica la cláusula de "documentar el punto de acoplamiento y dejar T-611 parcial".

### Hallazgo 3 — presupuesto de candidatos presentado como protección, no como defecto

**Antes:** el comentario y el nombre de la prueba afirmaban "Comportamiento verificado, no un defecto: protege contra seguir intentando...".

**Corrección aplicada:**
- Prueba renombrada a `test_h9_candidate_budget_off_by_one_defect_documents_current_behavior`; docstring y comentarios reescritos para calificarlo explícitamente como **"DEFECTO/AMBIGÜEDAD PRODUCTIVA PENDIENTE — documenta, no certifica"**, sin afirmar corrección normativa.
- Nueva prueba `test_h9_expected_semantics_eight_candidate_budget_should_allow_profiling_eight`, marcada `@pytest.mark.xfail(strict=True)`, que expresa la semántica ESPERADA (`max_candidates=8` ⇒ hasta 8 candidatos perfilados) y **falla contra el comportamiento actual** (confirmado: `XFAIL` real en la corrida, no un `xfail` decorativo — con `strict=True`, el día que alguien corrija el runtime esta prueba pasará a `XPASS` y la suite fallará, forzando a retirar el marcador conscientemente).
- No se tocó `deterministic_runtime.py` ni `deterministic_graph.py` en esta ronda.
- **No se afirma "ningún defecto productivo"** en este informe (ver §9).

### Guardia T-612 — fortalecida contra elusión

`backend/tests/test_deterministic_acceptance_guard.py` ampliado (4 pruebas, antes 3):
- Análisis **transitivo**: si el archivo de aceptación importara un helper `tests.*`, ese módulo se analiza recursivamente (`_analyze_recursively`) — hoy no importa ninguno (todos los helpers son locales al archivo), pero la guardia ya cubre el caso si se introdujera uno.
- Detección de **imports dinámicos**: nueva prueba `test_deterministic_acceptance_has_no_dynamic_import_of_legacy_graph` busca literales de cadena en llamadas a `importlib.import_module(...)`/`__import__(...)` que contengan `app.agent.graph`/`build_graph`/`initial_state`, cerrando la elusión de la detección estática de `ast.Import`/`ast.ImportFrom`.
- Se conservan las 3 comprobaciones originales (archivo existe, sin imports estáticos prohibidos, entra por `execute_deterministic_agent_run_async`).

## 3. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/tests/integration/test_deterministic_agent_acceptance.py` | Reescritura completa (1733 líneas): registro/limpieza exacta (`_CreatedIds`, fixture `created`), historia 10 (ensamblaje productivo real), historia 9 renombrada + prueba `xfail(strict=True)`, fixture y prueba de fila centinela. |
| `backend/tests/test_deterministic_acceptance_guard.py` | Fortalecida: análisis transitivo de imports locales + detección de imports dinámicos (161 líneas, antes 67). |
| `backend/eval/reports/t611-t612-correccion-revision.md` | Este informe (nuevo). |

No se tocó `backend/tests/integration/test_legacy_agent_acceptance.py` ni `backend/pyproject.toml` en esta ronda (ya quedaron correctos en el cierre anterior; la revisión no encontró hallazgos sobre ellos). No se tocó ningún archivo bajo `backend/app/`.

## 4. Comandos exactos y resultados

```powershell
cd backend
$env:DATABASE_URL = "postgresql://usuario:clave@localhost:5433/cuestion_de_datos"   # puerto verificado, no asumido

uv run pytest --collect-only -q
# → 722 tests collected

uv run pytest -q -m deterministic_agent_acceptance
# → 14 passed, 707 deselected, 1 xfailed

uv run pytest -q -m legacy_agent_acceptance
# → 7 passed, 715 deselected

uv run pytest -q tests/test_deterministic_acceptance_guard.py
# → 4 passed

uv run pytest -q `
  tests/test_query_plan.py tests/test_plan_validator.py tests/test_soql_renderer.py `
  tests/test_llm_contracts.py tests/test_multiquery_retrieval.py `
  tests/test_deterministic_graph.py tests/test_deterministic_dependencies.py `
  tests/test_deterministic_pipeline.py tests/test_deterministic_runtime.py `
  tests/test_runner_runtime_selection.py tests/test_deterministic_acceptance_guard.py
# → 127 passed

uv run ruff check .
# → All checks passed!

uv run pytest -q -m "not integration"
# → 632 passed, 90 deselected, 5 warnings

uv run pytest -q -m integration
# → 1 failed, 72 passed, 1 skipped, 632 deselected, 1 xfailed, 15 errors (ver §9, todo preexistente)

# Suite completa del archivo de aceptación, repetida 3 veces para verificar
# tolerancia a ejecución repetida (condición 7, Corrección 1):
uv run pytest -q tests/integration/test_deterministic_agent_acceptance.py   # x3
# → 14 passed, 1 xfailed (idéntico en las 3 corridas)
```

## 5. Conteo total recolectado antes/después

| Momento | `pytest --collect-only -q` |
|---|---|
| Línea base T-610 (antes de T-611) | **703** |
| Después de esta ronda correctiva | **722** |

Desglose de los +19: archivo de aceptación determinista 12→15 (+3: historia 10, prueba `xfail` de historia 9, prueba de fila centinela) + guardia AST 3→4 (+1: detección de imports dinámicos) = +19. Coincide exactamente con la aritmética esperada (703 + 15 + 4 = 722); no se afirma un número sin haberlo recolectado de verdad.

## 6. Evidencia de que la fábrica productiva real fue ejecutada con bordes falsos

- `factory_spy = Mock(side_effect=deterministic_dependencies_module.build_real_runtime_dependencies)` envuelve la función real (no la reemplaza); `monkeypatch.setattr("app.agent.runner.build_real_runtime_dependencies", factory_spy)`.
- Tras la corrida: `factory_spy.assert_called_once()` pasa; `factory_spy.call_args.kwargs["embedding_client"]` es la instancia de `_RealFactoryEmbeddingClient` inyectada (confirma que el `embedding_client` que la fábrica real recibió es el falso, no uno productivo real); `engine`/`http_client` no son `None`.
- La cadena de nodos persistidos (`select_candidate → profile_dataset → build_plan → execute_query → synthesize → complete`) solo es alcanzable si `retrieve()`/`profile()`/`plan()`/`execute()`/`synthesize()` — las closures que la fábrica REAL construyó internamente — se ejecutaron de verdad contra Postgres real (pgvector para recuperación, filas de catálogo reales para perfilado, T5→T6→T7 reales para ejecución).
- `uv run pytest -q tests/integration/test_deterministic_agent_acceptance.py::test_h10_real_dependency_factory_assembles_working_adapters_end_to_end` → **1 passed**, reproducido 3 veces sin fallos.

## 7. Evidencia de limpieza exacta y preservación del centinela

Verificación directa contra Postgres después de 3 corridas completas de la suite:

```text
stray T-611 runs: 0
stray test-named datasets (incl. sentinel): 0
total catalog_datasets: 8398   (idéntico al recuento previo a esta ronda)
total agent_runs: 73           (idéntico al recuento previo a esta ronda — filas ajenas preexistentes)
```

La prueba `test_zz_sentinel_dataset_survived_every_teardown_in_this_module` pasó en las 3 corridas: la fila centinela, creada antes de la primera prueba del módulo, seguía presente después de que las 15 pruebas (incluidos sus teardowns) terminaron.

## 8. Estado del off-by-one y prueba que lo documenta

**Sigue abierto.** No autorizado a resolverlo en esta ronda (fuera de alcance: `deterministic_runtime.py`/`deterministic_graph.py`).

- `test_h9_candidate_budget_off_by_one_defect_documents_current_behavior`: **pasa**, documentando el comportamiento actual (7 de 8 candidatos nominalmente permitidos llegan a perfilarse; el 8° se selecciona pero el presupuesto ya aparece agotado en la iteración siguiente).
- `test_h9_expected_semantics_eight_candidate_budget_should_allow_profiling_eight`: marcada `xfail(strict=True)`, **falla como se espera** (`1 xfailed` en cada corrida) — expresa la semántica correcta (8 candidatos deberían permitir perfilar 8) y fallará "hacia adelante" (forzando atención, `XPASS` con `strict=True` rompe la suite) el día que alguien corrija el runtime.
- Causa raíz identificada (no corregida): `usage.candidates` (`SupervisorSnapshot`, `deterministic_graph.py`) cuenta un candidato como gastado en cuanto pasa a `SELECTED`, no cuando termina de perfilarse/rechazarse.
- Recomendación explícita: la decisión y corrección corresponden a una tarea posterior, autorizada por el coordinador, antes de usar este comportamiento como base para T-614.

## 9. Fallos de integración no resueltos y clasificación causal

Ejecución completa `pytest -m integration`: **1 failed, 15 errors** (idéntico conjunto de archivos en las dos rondas de esta sesión — antes y después de las correcciones).

| Archivo | Clasificación | Motivo |
|---|---|---|
| `test_catalog_search_rnf010.py::test_search_meets_rnf010_latency_and_coverage_budget` | **Preexistente reproducible** | p95 real medido 1850-1883ms > presupuesto RNF-010 de 1000ms; latencia de red hacia la API real de embeddings, no relacionado con T-611/612. |
| `test_build_embeddings.py` (3 casos) | **Preexistente reproducible** | Fixture ejecuta `DELETE FROM catalog_datasets` sin filtro; bloqueado por `evidence_results` reales preexistentes que referencian datasets reales (confirmado: id `m8fd-ahd9` en esta corrida, distinto id en la corrida anterior — la fila concreta cambia porque el catálogo real se reingiere entre sesiones, pero la CAUSA es la misma). |
| `test_explorar_valores_live.py` (2 casos) | **Preexistente reproducible** | Misma causa (fixture de wipe amplio). |
| `test_ingest_catalog.py` (6 casos) | **Preexistente reproducible** | Misma causa; confirmado con traceback real en esta ronda (`ForeignKeyViolation` sobre `catalog_datasets`). |
| `test_ingest_catalog_live_discovery.py` (1 caso) | **Preexistente reproducible** | Misma causa. |
| `test_publisher_coverage_queries.py` (3 casos) | **Preexistente reproducible** | Misma causa. |

**Ninguno de estos 16 fallos/errores está en `test_deterministic_agent_acceptance.py`, `test_legacy_agent_acceptance.py` ni `test_deterministic_acceptance_guard.py`.** Ninguno es contaminación de esta ronda: verificado que `created` (Corrección 1) no deja filas residuales (§7) y que los identificadores que bloquean estas fixtures preexistentes (`m8fd-ahd9`, con formato `xxxx-xxxx` distinto del formato usado por mis pruebas, que también usa ese formato pero con IDs registrados y borrados exactamente) corresponden a datos reales del catálogo ingerido, no a nada creado por esta suite.

**No se borraron datos preexistentes para forzar esta suite a estar en verde** — instrucción explícita respetada. La suite de integración completa **permanece con fallos/errores preexistentes**: no se afirma "todas las integraciones compartidas verdes".

## 10. Confirmación de integridad

- `backend/app/`: **sin cambios** (confirmado: `git status --short` no lista ningún archivo bajo esa ruta).
- Contratos (`specs/001-cuestion-de-datos-v2/contracts/`): **sin cambios**.
- `backend/eval/golden/golden-v1.yaml`: **sin cambios**; no se creó `golden-v2.yaml`.
- `backend/eval/metrics.py`: **sin cambios**, no relajado.
- `AGENT_RUNTIME` y su default en `backend/app/config.py`: **sin cambios** (sigue `deterministic` por default de código; la desviación documentada en T-610 sigue vigente y sin tocar).
- No se instalaron dependencias nuevas (todo lo usado — `httpx.MockTransport`, `unittest.mock.Mock` — ya estaba disponible en el proyecto).
- No hubo commit, push, PR ni merge.

## 11. `git status --short`, `git diff --check` y resumen del diff

```text
$ git status --short -- backend/
 M backend/pyproject.toml
RM backend/tests/integration/test_agent_redesign_acceptance.py -> backend/tests/integration/test_legacy_agent_acceptance.py
?? backend/eval/reports/deterministic-development-baseline.md
?? backend/tests/integration/test_deterministic_agent_acceptance.py
?? backend/tests/test_deterministic_acceptance_guard.py
?? backend/eval/reports/t611-t612-correccion-revision.md
?? backend/uv.lock

$ git diff --check
(solo advertencias de fin de línea LF→CRLF en archivos de specs/ preexistentes a esta sesión; sin problemas de espacio en blanco reales)

$ git diff --stat -- backend/pyproject.toml backend/tests/integration/test_legacy_agent_acceptance.py
 backend/pyproject.toml                                    |  2 ++
 backend/tests/integration/test_legacy_agent_acceptance.py | 10 ++++++++--
 2 files changed, 10 insertions(+), 2 deletions(-)
```

`backend/uv.lock` sigue apareciendo como efecto secundario de `uv run` (no intencional, no agregado a git, mismo hallazgo que en el cierre anterior — queda a criterio de Juan Camilo si se commitea).

## 12. Recomendación (ronda 1)

Detenerme aquí para revisión humana/agente coordinador. **No inicio T-613.**

---

## Ronda 2 de revisión — corrección puntual del fixture centinela

**Fecha:** 2026-07-16 (mismo día, corrección de seguimiento) · **Alcance:** un único hallazgo del coordinador sobre la prueba de preservación de datos (Corrección 1, condición 6). Cero cambios en `backend/app/`, contratos, `golden-v1.yaml`, `backend/eval/metrics.py`, selección/default de runtime o semántica productiva del presupuesto de candidatos.

### 13. Reconocimiento del defecto del fixture anterior

El coordinador tenía razón. El fixture de la ronda 1 estaba declarado:

```python
@pytest.fixture(scope="module")
async def sentinel_dataset_id():
    ...
```

**Por qué `scope="module"` sin `autouse=True` era insuficiente:** un fixture de alcance módulo que NO es `autouse` solo se instancia la primera vez que ALGUNA prueba lo solicita explícitamente como parámetro. En el diseño de la ronda 1, la única prueba que lo solicitaba era `test_zz_sentinel_dataset_survived_every_teardown_in_this_module` — la última por orden de definición. Es decir: pytest creaba la fila centinela justo antes de ejecutar **esa** prueba, después de que las historias 1-10 ya habían corrido y limpiado sus propios datos. La prueba pasaba, pero no porque hubiera demostrado que la fila sobrevivió a nada — la fila ni siquiera existía todavía cuando corrieron las historias 1-10. El docstring afirmaba "creada antes de la primera prueba", lo cual era falso en la práctica; solo era cierto en la intención del diseño, no en su comportamiento real bajo pytest.

### 14. Cambio exacto aplicado

`backend/tests/integration/test_deterministic_agent_acceptance.py`, sección "Preservación de datos ajenos":

1. **`_sentinel_engine`** (nuevo, `scope="module"`): motor propio, independiente del fixture `engine` function-scoped de las historias (que se dispone al final de cada prueba individual y por tanto no sirve para verificar algo que debe sobrevivir más allá de una sola prueba).
2. **`sentinel_dataset_id`** (redefinido, `scope="module"`, sin `autouse` directo): crea la fila, y ahora además **verifica con una aserción que quedó creada** (`_sentinel_row_exists`) antes de hacer `yield`; en el teardown, verifica que sigue existiendo **antes** de borrarla (detecta en el lugar exacto si algo la borró de más) y verifica que el borrado surtió efecto.
3. **`_sentinel_survives_every_test`** (nuevo, `@pytest.fixture(autouse=True)`, function-scoped): se aplica automáticamente a **todas** las pruebas del módulo sin que ninguna lo declare. Al depender de `sentinel_dataset_id` (module-scoped), fuerza su creación **antes del `setup` de la primera prueba del módulo**, sin importar nombre u orden de definición — es la resolución de dependencias de fixtures de pytest, no una convención de nombres, la que lo garantiza. Además comprueba presencia **antes y después de cada prueba individual** (no solo de la última) y registra cada comprobación en `_SENTINEL_AUDIT_LOG` (lista a nivel de módulo).
4. **`test_zz_sentinel_dataset_survived_every_teardown_in_this_module`** (conservada, con docstring corregido): ya no es la única fuente de la garantía — inspecciona `_SENTINEL_AUDIT_LOG` completo (exige ≥ 10 nombres de prueba distintos auditados, todos con `existe=True`) y hace una comprobación directa final. El nombre `zz` se conserva por legibilidad (sigue corriendo al final, como es natural), pero la prueba ya no es la única evidencia — es una confirmación adicional sobre una bitácora que las historias 1-10 ya construyeron por sí mismas al ejecutarse.

### 15. Comandos y resultados

```powershell
cd backend
$env:DATABASE_URL = "postgresql://usuario:clave@localhost:5433/cuestion_de_datos"   # verificado, no asumido

uv run pytest -q -m deterministic_agent_acceptance
# → 14 passed, 707 deselected, 1 xfailed, 2 warnings

uv run pytest -q -m legacy_agent_acceptance
# → 7 passed, 715 deselected, 2 warnings

uv run pytest -q tests/test_deterministic_acceptance_guard.py
# → 4 passed

uv run ruff check .
# → All checks passed!

uv run pytest --collect-only -q
# → 722 tests collected (sin cambio: esta corrección no agrega ni quita pruebas,
#   solo corrige el ciclo de vida de un fixture existente)

# Repetido 3 veces (incluida una corrida con -s para capturar la bitácora,
# ver §16) para confirmar estabilidad:
uv run pytest -q tests/integration/test_deterministic_agent_acceptance.py
# → 14 passed, 1 xfailed  (idéntico en las 3 corridas)
```

### 16. Evidencia de creación previa y supervivencia (ciclo temporal inequívoco)

Corrida con captura de salida habilitada (`-s`), suite completa:

```text
$ uv run pytest -q -s tests/integration/test_deterministic_agent_acceptance.py
............x.
[centinela] id=0f70-228f — bitácora con 29 comprobaciones sobre 14 pruebas previas, todas 'existe=True';
primer registro=('before', 'test_h1_positive_path_completes_with_evidence_quality_claims_and_single_terminal', True),
último registro antes de esta prueba=('before', 'test_zz_sentinel_dataset_survived_every_teardown_in_this_module', True)
.
14 passed, 1 xfailed, 1 warning in 15.60s
```

Lectura de esta evidencia, punto por punto de lo exigido:

- **"Se crea antes de la primera historia":** el primer registro de la bitácora es `('before', 'test_h1_...', True)` — la comprobación `before` del fixture autouse en la PRIMERA prueba del módulo (`test_h1`) ya encontró la fila creada. Si `sentinel_dataset_id` no se hubiera instanciado antes de `test_h1`, esa aserción habría fallado ahí mismo (la ejecución completa habría mostrado un `FAILED` en `test_h1`, no un `.` verde).
- **"Sigue existiendo después de los teardowns de las historias 1-10":** 29 comprobaciones (dos por prueba — antes y después — sobre 14 pruebas: 12 historias con subcasos + la prueba `xfail`, que también se audita) registran `existe=True` sin ninguna excepción; cualquier `False` habría hecho fallar esa prueba concreta con el mensaje `"la fila centinela desapareció durante/después de ..."`.
- **"Se elimina solamente durante el teardown final del módulo":** el teardown de `sentinel_dataset_id` (que ejecuta el `DELETE` real) solo corre cuando pytest libera el fixture de alcance módulo — es decir, después de que la ÚLTIMA prueba que lo usa (aquí, todas, por la cadena de dependencia autouse) termina. La comprobación directa final dentro de `test_zz_...` (antes de que termine esa prueba, y por tanto antes de que el fixture module-scoped se libere) confirma la fila todavía presente.
- **"Quedan cero filas residuales creadas por la suite":** verificado por consulta directa a Postgres después de la corrida:

```text
stray T-611 runs: 0
stray test-named datasets (incl. sentinel): 0
total catalog_datasets: 8398   (idéntico al recuento previo a esta corrección)
total agent_runs: 73           (idéntico al recuento previo — filas ajenas preexistentes)
```

Reproducido 3 veces seguidas sin variación.

### 17. Estado definitivo

| Tarea | Estado |
|---|---|
| T-610 | Completa (sin cambios en esta ronda) |
| T-611 | **Completa** |
| T-612 | **Completa** |

- El `xfail(strict=True)` de historia 9 (`test_h9_expected_semantics_eight_candidate_budget_should_allow_profiling_eight`) **sigue fallando como se espera** (`1 xfailed` en cada corrida de esta ronda) — no se convirtió en prueba aprobada ni se tocó el runtime. El off-by-one del presupuesto de candidatos **sigue abierto**, sin corrección de código productivo.
- `backend/app/`, contratos, `golden-v1.yaml`, `backend/eval/metrics.py`, `AGENT_RUNTIME`/su default: sin cambios (confirmado: `git status --short -- backend/app/` no lista nada).
- Índice `codebase-memory-mcp`: se volvió a consultar antes de editar (`query_graph` sobre `test_deterministic_agent_acceptance`) y **sigue sin incluir este archivo** — misma discrepancia ya reportada en las dos rondas anteriores de esta sesión; se procedió con lectura directa del archivo real, como exige `CLAUDE.md` cuando el MCP contradice o no refleja el contenido real.

### 18. Confirmación de que T-613 no fue iniciada

No se leyó, planificó ni implementó nada de la matriz diagnóstica del evaluador (T-613). Esta corrección se limitó exclusivamente al fixture de preservación de datos de T-611/T-612.

**Detenerme aquí para revisión humana/agente coordinador. No inicio T-613.**
