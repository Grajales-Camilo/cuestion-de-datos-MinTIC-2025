# Instrucciones para evaluar el agente después de los ajustes de diseño

## Objetivo y alcance

Estas instrucciones permiten decidir, con evidencia reproducible, si los ajustes al agente satisfacen RF-201, RF-205, RF-208, RF-401..404, RNF-001..005 y ESC-01..03.

El evaluador NO debe asumir que una suite verde demuestra por sí sola que el agente funciona. Debe verificar, en este orden, contratos aislados, mecánica completa con LLM guionado, integración real focalizada y finalmente el golden set. No debe modificar `backend/eval/` ni editar `golden-v1.yaml`.

Ejecutar comandos desde `backend/`. En Windows, toda ejecución async directa contra SQLAlchemy/psycopg debe usar `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)`. Antes de una corrida que escriba trazas, consultar `pg_stat_activity` y confirmar que no existe otra evaluación activa.

## 1. Puerta estática y regresión general

### Pruebas existentes que deben conservarse

- `backend/tests/test_agent_graph.py`: contratos básicos del grafo, presupuesto, correcciones SoQL, T6, T7 y síntesis.
- `backend/tests/test_claims.py`: semántica y reproducibilidad de claims.
- `backend/tests/test_soql_guard.py`: gramática, seguridad y canonicalización SoQL.
- `backend/tests/test_llm_factory.py`: adaptación de salida estructurada, errores y uso del proveedor.

### Ejecución

```powershell
Set-Location D:\Usuario\AppWebs\cuestion-de-datos-MinTIC\backend
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q
```

### Criterio de aprobación

- Ruff sin errores.
- Cero fallos en pruebas no marcadas como integración.
- No aceptar `xfail`, `skip` nuevo o relajación de asserts para ocultar una regresión.

## 2. Schema estructurado del router y de los inputs de herramientas

### Cobertura existente útil

En `backend/tests/test_agent_graph.py` ya funcionan y deben seguir pasando:

- `test_claim_spec_payload_accepts_every_real_dsl_shape`.
- `test_claim_spec_payload_rejects_invented_dsl_shapes`.
- `test_unknown_tool_is_controlled_graph_error`.

Estas pruebas validan Pydantic localmente, pero NO prueban que el schema enviado al proveedor exija los campos correctos para cada acción.

### Pruebas nuevas requeridas

Crear un archivo nuevo: `backend/tests/test_agent_router_contracts.py`.

Implementar, como mínimo:

1. `test_each_router_action_has_a_discriminated_input_schema`
   - Verificar que cada acción solo acepta su tipo de input.
   - Rechazar campos pertenecientes a otra herramienta.

2. `test_explorar_valores_requires_termino_busqueda_before_tool_execution`
   - Una salida con `action="explorar_valores"` sin `termino_busqueda` debe fallar en la validación del router.
   - La herramienta y Socrata no deben ser llamados.

3. `test_ejecutar_soql_requires_dataset_soql_and_purpose`
   - Cada campo debe ser obligatorio.

4. `test_finish_does_not_require_or_accept_tool_input`
   - Evitar inputs fantasma que confundan diagnóstico y persistencia.

5. `test_provider_tool_schema_contains_required_fields_per_action`
   - Inspeccionar el JSON Schema realmente entregado a `with_structured_output`/function calling.
   - Confirmar discriminador, `required` y `additionalProperties=false`.

6. `test_formula_schema_exposed_to_provider_supports_all_supported_shapes`
   - Verificar el schema convertido para Gemini, no solo `model_validate()`.
   - Si se conserva recursión, comprobar explícitamente la profundidad admitida.

### Criterio de aprobación

- Cero `INVALID_INPUT` por campos obligatorios omitidos en una corrida con LLM guionado.
- El schema del proveedor y el contrato Pydantic deben aceptar exactamente las mismas formas comprometidas.

## 3. Reparación de salidas estructuradas

### Cobertura existente útil

En `backend/tests/test_llm_factory.py`:

- `test_recovers_from_string_too_long_by_truncating_the_field` funciona para límites de longitud.
- `test_does_not_recover_missing_required_field` y `test_does_not_recover_mixed_errors_including_non_length_ones` documentan el comportamiento actual. Si se implementa reparación general, no deben sobrescribirse: agregar casos nuevos y revisar si esos tests siguen describiendo la capa de bajo nivel.

### Pruebas nuevas requeridas

Crear `backend/tests/test_agent_structured_repair.py`.

1. `test_router_repairs_invalid_formula_once_with_validation_feedback`.
2. `test_router_repairs_missing_required_tool_field`.
3. `test_structured_repair_is_bounded_to_two_attempts`.
4. `test_structured_repair_does_not_consume_semantic_step_budget`.
5. `test_structured_repair_preserves_usage_and_attempt_trace`.
6. `test_unrepairable_output_ends_with_specific_error_not_generic_provider_error`.

Usar un LLM guionado que primero devuelva JSON inválido y luego una salida válida. Verificar el feedback de validación entregado al segundo intento y la persistencia de ambos intentos.

### Criterio de aprobación

- Una salida reparable no termina la corrida.
- Una salida no reparable termina de forma acotada y observable.
- Nunca hay bucle infinito ni consumo silencioso de pasos.

## 4. Herramienta `explorar_valores` y recuperación de errores

### Pruebas existentes que funcionan

En `backend/tests/test_tools_explorar_valores.py`:

- sanitización de comillas, `%`, `_` y backslash;
- input/columna inválida;
- timeout y error Socrata 400;
- rechazo de columnas numéricas y temporales sin llamar a Socrata;
- columna desconocida.

En `backend/tests/integration/test_explorar_valores_live.py`:

- `test_explorar_valores_finds_known_value_against_real_socrata`;
- `test_explorar_valores_no_match_returns_empty_not_error`.

### Pruebas nuevas requeridas

Agregar un archivo nuevo `backend/tests/test_agent_tool_recovery.py`:

1. `test_invalid_input_returns_to_repair_path_not_general_router_loop`.
2. `test_corrected_explorar_valores_input_executes_once`.
3. `test_repeated_invalid_input_stops_with_input_repair_exhausted`.
4. `test_non_text_column_error_causes_direct_soql_strategy`.

### Criterio de aprobación

- El error corregible produce una corrección focalizada.
- El mismo input inválido no puede repetirse indefinidamente.
- La corrida todavía puede alcanzar T5 después de una corrección exitosa.

## 5. Guardia y generación de SoQL

### Pruebas existentes que funcionan

En `backend/tests/test_soql_guard.py` ya se cubren:

- SELECT, GROUP BY, ORDER BY y funciones permitidas;
- rechazo de `FROM` con mensaje accionable;
- lista negra de escritura;
- columnas desconocidas;
- límites, canonicalización y PII.

En `backend/tests/test_tools_ejecutar_soql.py` ya se cubren:

- éxito y vista acotada para el LLM;
- input inválido sin llamar a Socrata;
- `SELECT *`, dataset/columna inválidos;
- mapeo de 400 y timeout después de un reintento.

En `backend/tests/test_agent_graph.py` ya existen:

- `test_soql_syntax_allows_only_two_corrections_after_initial_attempt`;
- `test_soql_forbidden_also_allows_only_two_corrections`;
- `test_at_most_four_soql_calls_per_run`.

### Pruebas nuevas requeridas si se introduce un renderer determinista

Crear `backend/tests/test_soql_renderer.py`:

1. Render de selección simple, agregación, filtros, agrupación y orden.
2. El renderer nunca emite `FROM` ni una segunda sentencia.
3. Literales se escapan correctamente.
4. La salida siempre pasa `validate_and_canonicalize`.
5. Property-based/fuzz ligero: ninguna estructura válida produce escritura o columnas no declaradas.

### Criterio de aprobación

- Cero `SOQL_FORBIDDEN` atribuible a sintaxis generada por el propio renderer.
- Los rechazos maliciosos de la guardia continúan funcionando.

## 6. Construcción de claims

### Pruebas existentes que funcionan

En `backend/tests/test_claims.py` funcionan:

- claim directo desde una celda;
- rechazo de múltiples filas/columnas en claim directo;
- fórmulas derivadas y agregaciones;
- operandos inválidos, nulos y división por cero;
- formato es-CO, `source_hash` y cifras huérfanas.

En `backend/tests/test_agent_graph.py` funcionan:

- `test_claim_builder_builds_claims_for_eligible_alta_evidence`;
- `test_claim_builder_skips_eligible_no_recomendada_evidence`;
- `test_real_graph_runs_t6_t7_and_blocks_orphans`.

### Pruebas nuevas requeridas

Crear `backend/tests/test_agent_claim_planning.py` si se separa el planeador de claims; si no se separa, mantener igualmente el archivo para probar el contrato del componente responsable.

1. `test_numeric_cell_becomes_direct_claim_with_one_row_and_one_column`.
2. `test_dimension_text_is_context_not_second_numeric_column`.
3. `test_top_n_aggregated_rows_produce_one_claim_per_numeric_value`.
4. `test_derived_claim_uses_formula_only_when_computation_is_required`.
5. `test_claim_plan_references_only_available_evidence_rows_and_columns`.
6. `test_rejected_claims_trigger_claim_repair_before_synthesis`.
7. `test_valid_high_quality_evidence_cannot_silently_finish_with_zero_claims`.

Caso obligatorio de regresión: filas con `nombre_evento` y `total_casos`. Debe producir claims sobre `total_casos`, conservando `nombre_evento` como contexto, sin intentar un claim directo de dos columnas.

### Criterio de aprobación

- Evidencia elegible y de calidad alta que contiene la respuesta produce al menos un claim aceptado.
- Todo valor cuantitativo mostrado se reproduce desde sus filas y fórmula.

## 7. Presupuesto y razones de terminación

### Prueba existente que funciona parcialmente

`backend/tests/test_agent_graph.py::test_step_budget_forces_no_evidence_without_exceeding_limit` debe conservarse. Prueba el límite general, pero debe complementarse para distinguir agotamiento real de reserva preventiva.

### Pruebas nuevas requeridas

Crear `backend/tests/test_agent_budget_semantics.py`:

1. `test_steps_used_never_exceeds_configured_max_on_every_route`.
2. `test_exact_budget_exhaustion_uses_step_budget_exceeded`.
3. `test_action_rejected_by_reservation_uses_insufficient_budget_for_action`.
4. `test_termination_records_requested_action_remaining_and_required_steps`.
5. `test_structured_and_input_repairs_use_separate_repair_budget`.
6. `test_happy_path_t1_t5_t6_t7_synthesis_fits_default_budget`.

Parametrizar rutas: sin evidencia, herramienta normal, T5 exitoso, T5 corregido, claim reparado y síntesis reintentada.

### Criterio de aprobación

- `steps_used <= max_steps` en todas las rutas.
- Cada razón de terminación describe la condición real.
- El camino feliz estándar cabe en la configuración por defecto.

## 8. Integración completa con Postgres y LLM guionado

### Prueba existente que funciona

`backend/tests/integration/test_t303_agent_graph.py::test_t303_persists_complete_trace` valida persistencia integral y debe seguir pasando.

### Pruebas nuevas requeridas

Crear `backend/tests/integration/test_agent_redesign_acceptance.py`:

1. Camino positivo: T1 → T5 → T6 → claims → síntesis → `completed`.
2. Recuperación de input inválido → corrección → `completed`.
3. Recuperación de schema inválido → corrección → `completed`.
4. SoQL con `FROM` inicial → corrección → `completed`.
5. Evidencia alta con claim inicialmente inválido → reparación → `completed`.
6. Dataset no elegible → `no_evidence`, cero cifras y explicación clara.
7. Verificar filas en `agent_runs`, `agent_steps`, `evidence_results`, `quality_reports` y `quantitative_claims`.

### Criterio de aprobación

- Todos los positivos guionados terminan `completed`.
- Los negativos terminan `no_evidence`, nunca `failed`, salvo falla externa definitiva simulada.
- La traza permite reconstruir acción, reparación y razón terminal.

## 9. Smoke real focalizado con Gemini, catálogo y Socrata

No ejecutar todavía los 50 casos. Usar primero entre 5 y 8 casos representativos de `backend/eval/golden/golden-v1.yaml`, sin modificar el archivo:

1. `pilot-003-salud-vigilancia` / dataset `4hyg-wa9d`: agregación, top-N y claims directos con contexto textual.
2. Un caso que requiera `explorar_valores`.
3. Un caso territorial con `resolver_geografia`.
4. Un caso con fórmula derivada.
5. Un caso que históricamente generó `SOQL_FORBIDDEN`.
6. Un caso negativo de abstención.

Para cada corrida registrar `run_id` real y consultar `agent_steps` en orden. No aceptar solo el JSON final.

### Criterio de aprobación

- Positivos: al menos 5/5 `completed`, dataset esperado presente, T5 y T6 ejecutados, al menos un claim aceptado y cero cifras huérfanas.
- Negativo: `no_evidence`, cero evidencia/claims/cifras inventadas.
- Cero `INVALID_INPUT`, cero schema inválido no recuperado y cero `SOQL_FORBIDDEN` definitivo.
- Cada `run_id` existe en Postgres y coincide con la traza reportada.

## 10. Golden set y puerta final de release

### Infraestructura existente que debe usarse

- Suite: `backend/eval/golden/golden-v1.yaml`.
- Runner: `backend/eval/run.py`.
- Métricas: `backend/eval/metrics.py`.
- Persistencia: `backend/eval/persistence.py`.
- Umbrales: `specs/001-cuestion-de-datos-v2/pruebas.md` §4.2.

No modificar el harness para hacer pasar los resultados. Si una métrica parece incorrecta, detenerse y reportar la discrepancia por separado.

Ejecución final, solo después de aprobar las puertas 1–9:

```powershell
$env:DATABASE_URL='postgresql://usuario:clave@localhost:5433/cuestion_de_datos'
.\.venv\Scripts\python.exe -m eval.run --suite golden-v1 --provider google --model gemini-2.5-flash --seed 601002
```

### Criterio de aprobación

- `success_rate >= 80%`.
- `recall_at_10 >= 85%`.
- `fabrication_count = 0`.
- `orphan_figures_count = 0`.
- claims: cobertura y reproducibilidad 100%.
- Umbrales de latencia y costo de `pruebas.md` §4.2.
- Analizar por separado positivos y negativos: no aceptar una tasa agregada favorecida por abstenciones.
- Entregar una tabla para los 40 positivos con `case_id`, `run_id`, último nodo, T1 hit, T5 intentado, T6 completado, claims aceptados/rechazados, estado final y razón terminal.

## 11. Orden de decisión del evaluador

1. Si falla lint o una prueba determinista: rechazar los ajustes; no gastar cuota real.
2. Si falla el schema por acción o la reparación estructurada: rechazar; no ejecutar smoke real.
3. Si una evidencia alta termina sin claims: rechazar aunque el resto de pruebas esté verde.
4. Si los smokes positivos no terminan `completed`: diagnosticar por traza; no ejecutar los 50.
5. Solo si todas las puertas anteriores pasan, ejecutar el golden completo.
6. Declarar que el agente funciona como debería únicamente si cumple los umbrales normativos y conserva cero fabricaciones/cifras huérfanas.

## 12. Evidencia mínima del informe final

El agente evaluador debe entregar:

- commit y rama evaluados;
- comandos exactos;
- conteos de passed/failed/skipped;
- `run_id` reales de los smokes;
- consultas SQL usadas para verificar trazas;
- tabla de los 40 positivos de la corrida final;
- métricas del golden y comparación contra umbrales;
- fallos clasificados como diseño, regresión, proveedor o fuente externa;
- conclusión inequívoca: aprobado, rechazado o bloqueado por infraestructura.

