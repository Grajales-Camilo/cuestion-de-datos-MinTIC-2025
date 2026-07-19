# T-617B-C6 — Límites accionables y observabilidad T5 determinista

**Fecha:** 2026-07-19
**Baseline auditado:** `597ef73e4e018ddba1a9d61faee6dcad97edce26`
**Disparador:** smoke `706bd396-c07e-408a-a163-d8eb4cafebc8`
**Veredicto:** `READY_FOR_COMMITTED_SMOKE_RETRY / FULL_GATE_STILL_BLOCKED`

## 1. Qué significaba realmente el 0/8

El smoke no demostró que los ocho positivos fueran falsos ni que Socrata
estuviera caído. Los dos negativos se abstuvieron correctamente; no hubo
fabricaciones, cifras huérfanas ni fallos de infraestructura. Los positivos
se repartieron así:

- `pilot-002`, `pilot-003` y `pilot-013`: agotamiento de reparaciones de plan;
- `pilot-005`, `pilot-012` y `pilot-021`: agotamiento de llamadas LLM;
- `pilot-038`: agotamiento de candidatos;
- `pilot-022`: consulta y evidencia completadas, pero
  `expected_fact_not_found`, pendiente de lectura cualitativa separada.

La inspección de pasos y estado persistido confirmó que varios presupuestos
se evaluaban globalmente al comienzo de cada transición. Por eso el runtime
podía rechazar trabajo ya producido por la última acción permitida:

- el octavo candidato se seleccionaba, pero se detenía antes de perfilarlo;
- un plan válido producido por la última llamada LLM no alcanzaba validación
  ni ejecución;
- una consulta exitosa que consumía la última llamada T5 no alcanzaba calidad
  ni claims;
- agotar reparaciones impedía pasar a otro candidato todavía disponible.

Esto era un error de frontera, no evidencia para aumentar presupuestos.

## 2. Correcciones genéricas

### 2.1 Presupuestos aplicados antes de la acción que consumen

`deterministic_graph.py` conserva el límite duro global de duración, pero
aplica los demás límites únicamente antes de iniciar otra acción del tipo que
consume el presupuesto:

- candidato: antes de seleccionar uno nuevo;
- LLM: antes de construir o reparar otro plan;
- consulta: antes de ejecutar otra consulta;
- reparación: antes de pedir otra reparación.

El resultado válido de la última acción permitida puede continuar por pasos
deterministas. Si ya no hay presupuesto LLM para síntesis, el runtime usa el
fallback determinista basado exclusivamente en claims verificados; no inventa
otra llamada ni otra cifra. Si se agotan reparaciones y existe otro candidato,
continúa con ese candidato; si no existe, se abstiene con el código tipado
correspondiente.

No cambiaron `max_candidates=8`, `max_explorations=6`, `max_queries=6`,
`max_plan_repairs=2`, `max_llm_calls=10` ni la duración máxima.

### 2.2 Exploraciones sin sobrepasar el saldo

El adaptador real de exploración podía probar hasta tres variantes de texto en
una sola transición. Una transición iniciada con una llamada disponible podía
terminar consumiendo tres y rebasar el máximo. Ahora el supervisor entrega el
saldo exacto y el adaptador limita sus llamadas reales a
`min(3, saldo_disponible)`.

Además, la validación categórica quedó alineada con la decisión de exploración:
solo `EQ` e `IN` textuales requieren comprobar el valor contra lo observado.
Un filtro textual `NE`, `LT`, `LTE`, `GT` o `GTE` ya no consume una reparación
por no tener un diccionario categórico que nunca se le pidió explorar.

### 2.3 Identificadores institucionales

La protección de entidad sigue impidiendo consultas a una institución
distinta, pero reconoce que una entidad puede quedar inequívocamente
preservada mediante una columna institucional o mediante una columna
identificadora (`codigo`, `id`, `identificador`). Esto resuelve de forma
genérica preguntas como una APP identificada por código, sin aceptar un código
ajeno como sustituto de una institución explícita.

No existe condición por `case_id`, `dataset_id`, pregunta completa ni valor
esperado.

### 2.4 Observabilidad real de T5

El runtime determinista ya creaba el paso `execute_query`, pero descartaba el
resultado crudo de `ejecutar_soql`. Ahora completa ese mismo paso —sin crear un
paso duplicado— con:

- `tool_input`: `dataset_id` y hash del plan;
- `tool_output_summary`: resultado real con `ok`/`error` y filas resumidas;
- latencia de la herramienta;
- error, cuando corresponde.

Los fallos deterministas posteriores a la llamada (calidad no elegible o
claims rechazados) conservan el resultado T5 que los precedió. Con ello,
`eval.gate.socrata_success_rate` puede medir llamadas reales en vez de informar
`0/0` cuando sí hubo consulta.

## 3. Relación con el criterio de producto

Las correcciones no endurecen la respuesta ni exigen una consulta perfecta.
Permiten que una respuesta útil, verificable y suficientemente correcta
continúe después de usar el último recurso permitido. Se mantienen como
bloqueos las cifras fabricadas, fuentes equivocadas, contradicciones
materiales, falta de evidencia, privacidad y fallos sistemáticos.

No se modificaron:

- `golden-v1`, `golden-v2` ni `expected_facts`;
- preguntas, tolerancias, cardinalidades o umbrales;
- contratos públicos o migraciones;
- presupuestos del runtime;
- reglas por caso/dataset.

`pilot-022` permanece sin reinterpretar: la corrección de ejecución no decide
si su respuesta parcial era cualitativamente aceptable.

## 4. Verificación

| Control | Resultado |
|---|---|
| Focalizadas de runtime/dependencias | `78 passed` |
| Runtime/grafo/contratos | `119 passed` |
| Suite `-m "not integration"` | `1071 passed, 122 deselected` |
| Aceptación determinista con PostgreSQL local | `19 passed` |
| Integración local, excluyendo aceptación legacy | `114 passed, 1 skipped` |
| Aceptación legacy | `7 passed` |
| `ruff check .` local | limpio con Ruff `0.15.20` |
| `git diff --check` | limpio; solo advertencias LF/CRLF de Windows |
| SHA-256 golden-v1 | `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72` |
| SHA-256 golden-v2 | `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483` |

La primera invocación de aceptación de esta sesión no contó como prueba de
código: falló en setup porque `DATABASE_URL` no estaba exportada. Se repitió
cargando únicamente esa variable desde `.env`, sin imprimir ni exportar claves
de proveedores, y produjo los 19 casos verdes registrados arriba.

## 5. Ruff y CI

CI no fija una versión exacta: `backend/pyproject.toml` declara
`ruff>=0.12,<1`, el workflow instala `.[dev]` con pip y ejecuta
`ruff check .`. El último workflow completo exitoso consultado directamente en
GitHub Actions fue el run `29159413025` (commit `7d8a8814…`, 2026-07-11); sus
logs muestran que instaló y ejecutó Ruff `0.15.21`.

El entorno local actual usa Ruff `0.15.20`. El `backend/uv.lock` local no
versionado resolvería Ruff `0.15.22`, pero CI no usa ese archivo. Por tanto,
el único dato histórico confirmado para el último check remoto limpio es
`0.15.21`; una ejecución nueva puede tomar otra versión mientras el rango siga
flotante.

## 6. Decisión siguiente

El código queda apto para ser consolidado en un commit local reproducible. El
siguiente gasto real permitido es un único smoke canónico de diez casos desde
ese commit limpio. Solo si ese smoke pasa corresponde ejecutar `golden-v1`
completa; luego `golden-v2`; después la aceptación legacy final y el cierre
documental de T-617. Este informe no certifica ninguna puerta real nueva:
`full` continúa bloqueada hasta completar esa secuencia.
