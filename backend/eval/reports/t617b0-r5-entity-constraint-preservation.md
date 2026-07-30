# T-617B0-R5 — Preservación de restricción de entidad explícita

## Punto de partida

- Repositorio: `D:\Usuario\AppWebs\cuestion-de-datos-MinTIC`
- Rama: `feat/t617-gate-preflight`
- HEAD base: `41a7b7c5ba6137fc55ba421d0fe43707d994272b`
- Evidencia disparadora: corrida `8ab794ac-50e6-453d-a7b7-3d8a1b95f973` (smoke T-617B0-R4A),
  caso `pilot-005-empleo-publico`.

## Causa raíz

`materialize_query_plan` (`backend/app/agent/llm_contracts.py`) construye el `QueryPlan`
final a partir de la `EnumeratedPlanSelection` propuesta por el LLM y de la `IntentExtraction`
ya validada. Antes de esta corrección, la función solo comprobaba que
`selection.operation == intent.operation` y que los índices de columna existieran
(`context.validate_references`). No existía ninguna comprobación que exigiera que, si la
intención había identificado una **entidad explícita** (`intent.entity`), el plan final
conservara un filtro sobre la columna de entidad del dataset seleccionado.

En `pilot-005-empleo-publico`, la intención extrajo correctamente
`entity="Ministerio de Relaciones Exteriores"`, pero el LLM planificador propuso una
`EnumeratedPlanSelection` sin filtro sobre `nombre_de_la_entidad`. Ningún paso posterior
(`normalize_lookup_filters`, `validate_query_plan`, renderer Socrata) rechaza un plan
`lookup` sin filtro de entidad cuando la intención sí la exige: `normalize_lookup_filters`
solo *elimina* filtros no fundamentados, nunca *exige* uno que falte. El plan se ejecutó,
Socrata devolvió la primera fila del dataset ordenada por `genero_hombre DESC` (INPEC:
9.943/3.082) y esa fila se atribuyó a la entidad solicitada. Esto es una contradicción
material (fuente vinculada a una entidad, cifras atribuidas a otra), no una imperfección
de optimización.

## Invariante implementado

Nueva función `_require_entity_constraint_preserved(plan, *, intent, context)` en
`backend/app/agent/llm_contracts.py`, invocada al final de `materialize_query_plan` justo
después de `context.validate_references(plan)` y antes de devolver el `QueryPlan`:

1. Si `intent.entity` es `None` o vacío tras `strip()` → no hace nada (la pregunta no
   especifica entidad; no se activa ninguna restricción).
2. Si no es vacío, localiza las columnas del candidato seleccionado
   (`context.candidates[plan.dataset_index]`) cuyo `field_name`/`display_name` normalizado
   interseca el vocabulario genérico `{"entidad", "empresa", "institucion", "organismo",
   "nombre"}` (reutiliza `_semantic_tokens`, ya usado por `normalize_lookup_filters` con el
   mismo vocabulario de dominio — no es nuevo para esta corrección).
3. Si el dataset no tiene ninguna columna de ese tipo → no hace nada (no hay forma
   determinista de vincular la entidad a ese dataset; no se bloquea).
4. Si existe columna de entidad:
   - Si el plan no tiene ningún filtro `EQ`/`IN` sobre esa columna → `ValueError`
     ("el plan omite la restricción de entidad requerida por la intención").
   - Si tiene filtro(s) pero ningún valor es equivalente a `intent.entity`
     (comparación normalizada por `_normalized_phrase`/`_semantic_tokens`: substring o
     inclusión de conjunto de tokens en cualquier dirección, tolerando mayúsculas, acentos
     y orden) → `ValueError` ("el plan contradice la entidad solicitada por la intención").
   - Si algún valor es equivalente → continúa sin cambios.

`materialize_query_plan` es una función pura (sin I/O, sin LLM, sin Socrata, sin
PostgreSQL); el `ValueError` que lanza ya era manejado por el bucle del grafo determinista
en `backend/app/agent/deterministic_runtime.py:530-536`, que lo convierte en
`PlanValidationError(UNKNOWN_REFERENCE, ...)`, incrementa `repairs` y vuelve a
`BUILD_PLAN` — el mismo mecanismo de **replanteamiento acotado** que ya existía para el
chequeo `operation != intent.operation`. No se creó ningún mecanismo nuevo de control de
flujo; solo se amplió una comprobación determinista ya presente en el mismo punto de la
tubería. Si los reintentos se agotan, el caso termina como fallo clasificado (no como
ejecución silenciosa contra Socrata con datos de otra entidad).

## Comportamiento ante los tres escenarios pedidos

- **Omisión**: intención con entidad explícita + plan sin ningún filtro sobre columna de
  entidad → `ValueError` antes de llegar a `validate_query_plan`/Socrata.
- **Contradicción**: intención con entidad explícita + plan con filtro de entidad hacia un
  valor distinto (no equivalente) → `ValueError`.
- **Ausencia de entidad**: intención sin `entity` → la función retorna de inmediato; el
  plan se materializa exactamente igual que antes de esta corrección.
- **Vinculación válida y equivalente**: intención con entidad + filtro `EQ`/`IN` cuyo valor
  normalizado coincide (aunque difiera en mayúsculas/acentos/orden de palabras) → el plan
  continúa sin cambios.

## Por qué no endurece respuestas parciales legítimas

- El chequeo solo mira **filtros de entidad**, nunca periodo, territorio, selección
  temporal ni cobertura de columnas. Una consulta que omite el filtro de mes/año más
  óptimo, pero preserva correctamente la entidad, no se ve afectada
  (`test_materialization_does_not_block_suboptimal_temporal_selection_with_entity`).
- Preguntas genéricas sin entidad (la mayoría del golden set) nunca activan la
  comprobación (`test_materialization_does_not_require_entity_filter_when_intent_has_no_entity`).
- Datasets sin ninguna columna que designe entidades tampoco la activan: no se inventa una
  restricción donde no hay forma determinista de vincularla.
- La comparación de equivalencia es tolerante a formas estilísticas (mayúsculas, acentos,
  orden), para no exigir una coincidencia literal byte a byte.
- No se referencia ningún `dataset_id`, `case_id`, cifra ni condición particular de
  `pilot-005` en el código de producción; el vocabulario de columnas de entidad ya existía
  en `normalize_lookup_filters` para otros propósitos.

## Archivos modificados

- `backend/app/agent/llm_contracts.py` — nueva función `_require_entity_constraint_preserved`
  y helper `_entity_grounded_in_value`; una línea añadida al final de
  `materialize_query_plan`.
- `backend/tests/test_llm_contracts.py` — 6 pruebas nuevas con dobles (`EnumeratedPlanningContext`,
  `DatasetOption`, `ColumnOption` construidos a mano; ninguna llama a Gemini, Socrata ni
  PostgreSQL):
  - `test_materialization_rejects_plan_that_omits_explicit_entity_filter`
  - `test_materialization_accepts_plan_with_equivalent_entity_filter`
  - `test_materialization_rejects_plan_that_contradicts_entity_filter`
  - `test_materialization_does_not_require_entity_filter_when_intent_has_no_entity`
  - `test_materialization_does_not_block_suboptimal_temporal_selection_with_entity`
  - (fixtures) `_entity_context`, `_entity_intent`
- `backend/eval/reports/t617b0-r5-entity-constraint-preservation.md` — este informe.

No se modificaron `golden-v1.yaml`, `golden-v2.yaml`, contratos, prompts, `timeout`,
`max_retries` ni el `thinking_budget` de Gemini 2.5 Flash.

## Pruebas y resultados exactos

1. **Reproducción de fallo en worktree temporal baseline** (`git worktree add
   %TEMP%/t617b0-r5-baseline 41a7b7c5ba6137fc55ba421d0fe43707d994272b`, copiando solo el
   archivo de pruebas nuevo, sin la corrección de producción):
   ```
   uv run python -m pytest tests/test_llm_contracts.py -q -k "entity"
   F.F..                                                                    [100%]
   2 failed, 3 passed, 22 deselected in 0.32s
   FAILED test_materialization_rejects_plan_that_omits_explicit_entity_filter — DID NOT RAISE
   FAILED test_materialization_rejects_plan_that_contradicts_entity_filter — DID NOT RAISE
   ```
   Los 3 casos que no dependen de la corrección (equivalencia, sin entidad, temporal
   subóptimo) ya pasaban en baseline, confirmando que la prueba es específica al defecto.
   Worktree eliminado con `git worktree remove --force` tras la comprobación.

2. **Con la corrección, en el árbol principal**:
   ```
   uv run python -m pytest tests/test_llm_contracts.py -q
   ...........................                                              [100%]
   27 passed in 0.21s / 0.32s
   ```

3. **Suite completa no-integración**:
   ```
   uv run python -m pytest -m "not integration" -q
   953 passed, 122 deselected, 5 warnings in 17.60s
   ```

4. **Aceptación determinista focalizada** (afecta al runtime `deterministic`):
   ```
   uv run python -m pytest tests/test_deterministic_acceptance_guard.py \
     tests/test_deterministic_runtime.py tests/test_deterministic_pipeline.py \
     tests/test_deterministic_graph.py tests/test_deterministic_dependencies.py \
     tests/test_deterministic_textual_planning.py -q
   90 passed, 1 warning in 6.04s
   ```

5. **Lint y formato**:
   ```
   uv run ruff check .
   All checks passed!

   uv run ruff format --check backend/app/agent/llm_contracts.py backend/tests/test_llm_contracts.py
   → 1 archivo requería reformateo (tests/test_llm_contracts.py); se aplicó
     `ruff format` y se reejecutaron las pruebas (27 passed). Verificación final:
   uv run ruff format --check ...
   2 files already formatted
   ```

6. **`git diff --check`** sobre los archivos modificados: sin salida (limpio).

## Hashes golden (antes y después)

- `golden-v1.yaml`: `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72` (sin cambio)
- `golden-v2.yaml`: `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483` (sin cambio)

No se ejecutó `pilot-005`, ningún smoke, golden completa ni aceptación legacy con proveedor
real durante este incremento; toda la verificación usó dobles deterministas en memoria.

## Estado final del worktree

`git status --porcelain` antes del commit mostraba únicamente:
- `M backend/app/agent/llm_contracts.py`
- `M backend/tests/test_llm_contracts.py`
- Los 7 documentos preexistentes de `specs/` modificados por el coordinador (no tocados,
  no incluidos en el commit de este incremento).
- Los archivos no rastreados preexistentes (reportes de eval anteriores, `docs/*`,
  `backend/uv.lock`), preservados intactos.

El commit de este incremento incluye únicamente los dos archivos de código/pruebas y este
informe. No hubo `push`, no hubo `amend`, no se tocó ningún archivo no rastreado ni ninguno
de los 7 documentos de specs señalados como fuera de alcance.

## Veredicto R5

**READY_FOR_T617B_PILOT005_RETRY**

---

# T-617B0-R5A — Corrección de bordes residuales

## Punto de partida

- HEAD base para esta ronda: `7dbcf50f93e4961f86b55775ba8a915630153256` (R5).
- Disparador: auditoría independiente que confirmó que la protección principal de R5
  funciona pero reprodujo tres bordes residuales.

## Bordes residuales encontrados (auditoría)

1. Un filtro `IN` con `("MINISTERIO DE RELACIONES EXTERIORES", "INPEC")` se aceptaba
   porque `_require_entity_constraint_preserved` usaba `any()` sobre **todos los valores
   de todos los filtros combinados**, en vez de exigir que un único filtro fuera
   inequívoco: bastaba un valor correcto dentro de una lista que mezclaba dos entidades
   distintas.
2. `_entity_grounded_in_value` aceptaba coincidencia por subcadena literal
   (`entity_norm in value_norm`), así que `"Ministerio"` se consideraba equivalente a
   `"Ministerio de Relaciones Exteriores"` — un término genérico de tipo institucional no
   identifica una entidad específica.
3. `_ENTITY_COLUMN_TOKENS` incluía el token suelto `"nombre"`, así que cualquier columna
   con `nombre` en el nombre (`nombre_producto`, `nombre_proyecto`, `nombre_indicador`,
   nombres personales) se clasificaba como columna de entidad y activaba la protección
   sin que el dataset tuviera semántica institucional real.

## Corrección

Todo el cambio vive en `backend/app/agent/llm_contracts.py`, sin tocar la firma pública de
`materialize_query_plan` ni el punto de integración con `deterministic_runtime.py`:

1. **Columna de entidad** (`_is_entity_designating_column`): se retira `"nombre"` de
   `_ENTITY_COLUMN_TOKENS`, que ahora es
   `{"entidad", "empresa", "institucion", "organismo", "organizacion"}`. Una columna sólo
   cuenta como de entidad si sus tokens semánticos intersecan directamente ese conjunto.
   `nombre_de_la_entidad` y `nombre_empresa` siguen reconociéndose porque contienen
   `"entidad"`/`"empresa"`; `nombre_producto` ya no interseca nada del conjunto.

2. **Equivalencia entre valores** (`_entity_grounded_in_value`): se elimina el atajo por
   subcadena de texto y se compara exclusivamente por conjuntos de tokens semánticos.
   Dos frases se consideran equivalentes si sus conjuntos de tokens son iguales, o si uno
   es subconjunto propio del otro (frase más específica que añade calificadores, p. ej.
   *"... de Colombia"*) — **salvo** que el conjunto más pequeño tenga un solo token y ese
   token esté en `_GENERIC_ENTITY_TOKENS` (`ministerio`, `instituto`, `entidad`,
   `empresa`, `organismo`, `institucion`, `organizacion`, `direccion`, `secretaria`,
   `agencia`, `fondo`, `unidad`, `superintendencia`, `corporacion`, `comision`,
   `consejo`): en ese caso se rechaza por ser un fragmento genérico de un solo término, no
   una identificación inequívoca.

3. **Unanimidad en `IN`** (`_filter_unambiguously_grounds_entity` +
   `_require_entity_constraint_preserved`): en vez de recolectar todos los valores de
   todos los filtros de entidad y usar `any()`, ahora se evalúa **filtro por filtro**: un
   filtro sólo cuenta como grounding si **todos** sus valores son equivalentes a la
   entidad solicitada (`all(...)`). El plan se acepta si **existe** al menos un filtro de
   entidad que sea inequívoco en su totalidad; si ningún filtro lo es (incluyendo un `IN`
   que mezcla la entidad correcta con otra), se rechaza como contradicción/ambigüedad.

Ninguno de estos cambios depende de `case_id`, `dataset_id` ni cifras de `pilot-005`; los
conjuntos de tokens son vocabulario genérico de tipos institucionales en español,
consistente con el ya usado en `normalize_lookup_filters` para filtros de `lookup`.

## Comportamiento verificado

- `IN` con entidad correcta + entidad distinta → rechazado (unanimidad falla).
- `IN` con solo variantes de la misma entidad (mayúsculas distintas) → aceptado.
- `"Ministerio"` solo → rechazado (token genérico único).
- `"Ministerio de Relaciones Exteriores de Colombia"` (superset específico) → aceptado.
- `nombre_producto` → no se clasifica como columna de entidad; el plan no requiere ningún
  filtro sobre ella.
- `nombre_de_la_entidad` y `nombre_empresa` → sí se clasifican como columnas de entidad.
- Los 5 comportamientos originales de R5 (omisión, equivalencia simple, contradicción
  total, ausencia de entidad en la intención, selección temporal subóptima no bloqueada)
  siguen verdes sin modificar sus aserciones de comportamiento (solo se actualizó el
  texto de una expresión regular de una prueba existente para que siga coincidiendo con
  el mensaje de error, ahora compartido entre contradicción y ambigüedad).

## Archivos modificados (R5A)

- `backend/app/agent/llm_contracts.py` — reescritura de `_ENTITY_COLUMN_TOKENS`,
  `_entity_grounded_in_value`, nuevas `_is_entity_designating_column`,
  `_GENERIC_ENTITY_TOKENS`, `_filter_unambiguously_grounds_entity`; reescritura de
  `_require_entity_constraint_preserved` para evaluar filtro por filtro.
- `backend/tests/test_llm_contracts.py` — 6 pruebas nuevas + 1 ajuste de regex en una
  prueba existente de R5 (mismo comportamiento, mensaje de error actualizado):
  - `test_materialization_rejects_in_filter_mixing_correct_and_other_entity`
  - `test_materialization_accepts_in_filter_with_only_equivalent_entity_variants`
  - `test_materialization_rejects_single_generic_word_as_entity_equivalence`
  - `test_materialization_accepts_sufficiently_specific_normalized_variant`
  - `test_product_name_column_is_not_classified_as_institutional_entity`
  - `test_institutional_name_columns_are_recognized_as_entity_columns`
- Esta sección del informe existente (sin crear archivo nuevo).

## Pruebas y resultados exactos (R5A)

1. **Reproducción de fallo en worktree temporal sobre R5** (`git worktree add
   %TEMP%/t617b0-r5a-baseline 7dbcf50f93e4961f86b55775ba8a915630153256`, copiando sólo el
   archivo de pruebas con los 6 casos nuevos, sin la corrección de producción R5A):
   ```
   uv run python -m pytest tests/test_llm_contracts.py -q
   3 failed, 30 passed in 0.36s
   FAILED test_materialization_rejects_in_filter_mixing_correct_and_other_entity
   FAILED test_materialization_rejects_single_generic_word_as_entity_equivalence
   FAILED test_product_name_column_is_not_classified_as_institutional_entity
   ```
   Los 3 fallos corresponden exactamente a los 3 bordes residuales reportados por la
   auditoría; los otros 3 casos nuevos (IN con variantes equivalentes, forma específica
   aceptada, columnas institucionales reconocidas) y los 5 originales de R5 ya pasaban en
   baseline. Worktree eliminado con `git worktree remove --force`.

2. **Con la corrección R5A, en el árbol principal**:
   ```
   uv run python -m pytest tests/test_llm_contracts.py -q
   .................................                                        [100%]
   33 passed in 0.16s / 0.34s
   ```

3. **Suite completa no-integración**:
   ```
   uv run python -m pytest -m "not integration" -q
   959 passed, 122 deselected, 5 warnings in 17.18s
   ```

4. **Aceptación determinista focalizada**:
   ```
   uv run python -m pytest tests/test_deterministic_acceptance_guard.py \
     tests/test_deterministic_runtime.py tests/test_deterministic_pipeline.py \
     tests/test_deterministic_graph.py tests/test_deterministic_dependencies.py \
     tests/test_deterministic_textual_planning.py -q
   90 passed, 1 warning in 6.01s
   ```

5. **Lint y formato**:
   ```
   uv run ruff check .
   All checks passed!

   uv run ruff format --check app/agent/llm_contracts.py tests/test_llm_contracts.py
   → app/agent/llm_contracts.py requería reformateo; se aplicó `ruff format` y se
     reejecutaron las pruebas (33 passed). Verificación final: 2 files already formatted.
   ```

6. **`git diff --check`** sobre los archivos modificados: sin salida (limpio).

## Hashes golden (antes y después de R5A)

- `golden-v1.yaml`: `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72` (sin cambio)
- `golden-v2.yaml`: `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483` (sin cambio)

No se ejecutó Gemini, Socrata, PostgreSQL, `pilot-005` ni el smoke durante este
incremento; toda la verificación usó dobles deterministas en memoria.

## Estado final del worktree (R5A)

`git status --porcelain` antes del commit mostraba únicamente:
- `M backend/app/agent/llm_contracts.py`
- `M backend/tests/test_llm_contracts.py`
- Los mismos 7 documentos preexistentes de `specs/` modificados por el coordinador (no
  tocados, no incluidos en el commit).
- Los mismos archivos no rastreados preexistentes, preservados intactos.

El commit de esta ronda incluye únicamente los dos archivos de código/pruebas y esta
sección del informe existente. No hubo `push`, no hubo `amend`, no se tocó ningún archivo
no rastreado ni ninguno de los 7 documentos de specs señalados como fuera de alcance.

## Veredicto R5A

**READY_FOR_T617B_PILOT005_RETRY**
