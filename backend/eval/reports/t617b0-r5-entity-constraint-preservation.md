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

## Veredicto

**READY_FOR_T617B_PILOT005_RETRY**
