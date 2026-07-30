# T-617B-C9 — Diagnóstico de la frontera de salida estructurada

## Estado

`SMOKE_FAILED` / `FULL_GATE_BLOCKED` /
`READY_FOR_STRUCTURED_OUTPUT_BOUNDARY_FIX`

- Smoke: `1aca0753-0db3-4b7c-81e6-3a46e8a101f5`
- Commit evaluado: `fd6cc70b595dad31862d8ca296c1edc1728491ff`
- Suite: `golden-v2`
- Runtime: `deterministic`
- Proveedor/modelo: `google/gemini-2.5-flash`
- Hechos textuales: habilitados

## Resultado verificable

- 10/10 casos canónicos, sin duplicados.
- Positivos: 2/8 (`pilot-003` y `pilot-013`).
- Negativos: 2/2.
- `pilot-013` confirma C8/C8A en el smoke formal.
- Fabricaciones: 0.
- Cifras huérfanas: 0.
- Integridad de claims/hechos aplicables: 100%.
- Socrata observable: 3/3.
- Corridas `running` al finalizar: 0.
- Cinco casos quedaron reportados como infraestructura:
  `pilot-002`, `pilot-005`, `pilot-012`, `pilot-021` y `pilot-038`.
- `pilot-022` ejecutó consulta pero no coincidió con `expected_facts`;
  permanece indeterminado para revisión separada.

El primer intento de lanzar el smoke no ejecutó casos ni gastó cuota: PowerShell
no transmitió los `--case-id` repetidos al proceso hijo y el preflight rechazó
la selección completa de 50. El comando formal corregido sí ejecutó exactamente
los diez canónicos.

## Causa raíz de los cinco falsos fallos de infraestructura

Las cinco corridas tienen `terminal_error_code=LLM_PROVIDER_ERROR`, pero sus
eventos terminales prueban que Gemini sí respondió. El error real fue validar
su respuesta contra `EnumeratedPlanSelection`:

- cuatro respuestas incluyeron texto explicativo libre dentro de
  `textual_requests`, que solo admite objetos `TextualSelection`;
- `pilot-005` propuso tres métricas con `operation="lookup"`, representación
  rechazada porque un `LOOKUP` debe usar `dimension_column_indexes`.

`ainvoke_structured_chat_model` agotó su reparación y lanzó
`LLMStructuredOutputError`, subclase de `LLMProviderError`. El runner
determinista captura la clase padre y persiste siempre
`LLM_PROVIDER_ERROR`. Esto contradice el contrato ya documentado:
`STRUCTURED_OUTPUT_INVALID` es fallo del contrato de ejecución del agente, no
caída de red/cuota/5xx del proveedor.

Por tanto:

1. el arnés no inventó la clasificación; leyó fielmente un terminal mal
   tipado por el runtime;
2. corregir solo la clasificación hará el reporte honesto, pero no permitirá
   que los casos completen;
3. habilitar hechos textuales expuso una incompatibilidad sistemática entre el
   esquema ampliado y salidas frecuentes del planificador.

## Incremento siguiente acotado

1. En el runner determinista, capturar `LLMStructuredOutputError` antes que
   `LLMProviderError` y persistir `STRUCTURED_OUTPUT_INVALID`,
   `owner=agent`, no reintentable como infraestructura.
2. En la frontera del contrato del planificador, tolerar únicamente
   representaciones opcionales semánticamente recuperables:
   - descartar entradas no estructuradas de `textual_requests` sin convertir su
     texto en hechos;
   - para operación superior `LOOKUP`, trasladar índices de métricas
     `operation="lookup"` a `dimension_column_indexes`, sin inventar columnas,
     filtros, valores ni operaciones.
3. Mantener rechazo estricto para cualquier otra forma inválida.
4. Probar ambos caminos con payloads reales anonimizados/dobles, sin red, y
   demostrar fallo contra `fd6cc70`.
5. Ejecutar primero validaciones dirigidas de los cinco casos afectados; solo
   si no hay bloqueos reales, repetir una vez el smoke canónico.

No cambiar golden, `expected_facts`, presupuestos, umbrales, cardinalidades,
contratos públicos ni el criterio de suficiencia RF-211. No ejecutar `full`
antes de un smoke formal verde.

## C9A — implementación

Se implementó el incremento acotado:

1. `EnumeratedPlanSelection` incorpora un preprocesamiento previo a Pydantic
   que solo recupera las dos formas demostradas por el smoke:
   - dentro de una lista `textual_requests`, descarta elementos que no son
     objetos/modelos; nunca interpreta su texto ni lo convierte en un hecho;
   - cuando la operación superior es `LOOKUP`, mueve a
     `dimension_column_indexes` únicamente métricas `lookup` que contienen
     solo `operation` y un `column_index` integral no negativo.
2. Objetos textuales con campos extra, `textual_requests` fuera de una lista,
   métricas lookup con datos adicionales y métricas lookup bajo otra operación
   siguen fallando estrictamente.
3. El runner determinista captura `LLMStructuredOutputError` antes que su clase
   padre y persiste `STRUCTURED_OUTPUT_INVALID`, no
   `LLM_PROVIDER_ERROR`. Los fallos reales de red/cuota/5xx conservan la ruta
   de proveedor.

No se alteraron prompts, golden, filtros, valores, presupuestos, contratos
públicos, umbrales ni cardinalidades.

### Prueba fallo→pasa

Worktree temporal sobre `7ac6b18`, con las pruebas nuevas copiadas:

- normalización: `2 failed, 4 passed` (los dos defectos reales fallaron);
- atribución terminal: `1 failed` porque el baseline persistía
  `LLM_PROVIDER_ERROR`;
- con la implementación: todos esos casos pasan;
- el worktree temporal fue eliminado.

### Verificación

- `tests/test_llm_contracts.py`: `47 passed`.
- `pytest -m "not integration" -q`:
  `1091 passed, 123 deselected`.
- aceptación determinista con PostgreSQL:
  `20 passed, 1194 deselected`.
- integraciones compartidas:
  `95 passed, 1 skipped, 1118 deselected`.
- aceptación legacy: `7 passed, 1207 deselected`.
- Ruff check/formato y `git diff --check`: limpios.
- hashes de `golden-v1` y `golden-v2`: intactos.

Estado: `READY_FOR_FIVE_CASE_DIRECTED_VALIDATION` /
`SMOKE_AND_FULL_BLOCKED`.

## C9B — validación dirigida real

La evaluación `54f9e4df-eb31-4f89-9999-7a2eae311aa9` sobre `ff5b5f9`
ejecutó una vez los cinco casos afectados:

- `pilot-002`: aprobado;
- `pilot-005`: aprobado;
- `pilot-012`: `LLM_BUDGET_EXCEEDED`, sin consulta;
- `pilot-021`: `CANDIDATE_BUDGET_EXCEEDED`, sin consulta;
- `pilot-038`: `CANDIDATE_BUDGET_EXCEEDED`, sin consulta.

No ocurrió ningún `LLM_PROVIDER_ERROR`, `STRUCTURED_OUTPUT_INVALID` ni terminal
de infraestructura. Esto confirma que C9A recuperó las formas observadas y
corrigió la atribución. No basta para repetir el smoke: tres casos siguen sin
llegar a T5.

La traza identifica dos hallazgos genéricos nuevos:

1. La exploración construye como máximo tres términos en este orden:
   frase original, frase sin tildes, tokens sin tildes. Por el corte a tres,
   `"Auditoría Regular"` nunca prueba `"Regular"` y `"Alcalá (Valle)"` nunca
   prueba el token original `"Alcalá"`. Los dos datasets esperados estaban en
   primer lugar, pero fueron descartados por esa política de variantes.
2. En el dataset esperado de `pilot-038` (`s54a-sgyg`), T4 devolvió un error
   definitivo de transporte Socrata después del reintento interno. El runtime
   determinista lo redujo a `ValueError`, rechazó el candidato y terminó
   contabilizándolo como agotamiento semántico. `plan.md` §11 y
   `contracts/api-rest.md` exigen que `SOCRATA_TIMEOUT`/`SOCRATA_ERROR` sean
   terminales de infraestructura, no rechazo silencioso del candidato.

Además, el agregado dirigido registra `orphan_figures_count=1` pese a que
`pilot-002`/`pilot-005` aprobaron; debe localizarse y auditarse antes de una
puerta formal.

Estado: `READY_FOR_EXPLORATION_BOUNDARY_FIX` /
`SMOKE_AND_FULL_BLOCKED`.
