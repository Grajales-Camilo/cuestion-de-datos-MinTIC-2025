# T-617B-C7 — Capacidad textual, corte de observación y observabilidad T4

**Fecha:** 2026-07-19  
**Baseline:** `0781ee5b07e355539de2ec6fa1c7edf0dcea6b60`  
**Disparador:** smoke `a2f6d778-87f8-45e5-a674-1b705dbd4732`  
**Veredicto:** `READY_FOR_DIRECTED_PILOT003_PILOT013 / FULL_GATE_BLOCKED`

## 1. Resultado real que motivó el incremento

El primer smoke posterior a C6 mejoró de `0/8` a `2/8` positivos:

- `pilot-002-seguridad-homicidios` y `pilot-005-empleo-publico` pasaron;
- los dos negativos se abstuvieron correctamente;
- Socrata dejó de aparecer como `0/0`: se observaron `5/5` llamadas T5;
- no hubo infraestructura, fabricaciones, cifras huérfanas ni claims no
  reproducibles.

La puerta siguió en `FAIL` por dos positivos sólidos:

1. `pilot-003-salud-vigilancia`: el plan trató «fuente observada al 17 de
   octubre de 2024» como periodo estadístico de las filas y agregó
   `ano=2024 AND semana<=42`. La fuente esperada sí fue recuperada y
   consultada, pero el filtro artificial produjo cero filas. El golden
   verificado pide el ranking acumulado de toda la instantánea observada, no
   restringir sus filas a la fecha en que se consultó la fuente.
2. `pilot-013-app-dnp`: el dataset esperado fue consultado y devolvió la fila
   textual correcta (`codigo`, `nombre_proyecto`, `tipo_app` y entidad). La
   corrida se ejecutó con
   `DETERMINISTIC_TEXTUAL_FACTS_ENABLED=false`; por ello el planificador no
   podía producir hechos textuales y el gate de relevancia rechazó el único
   claim cuantitativo auxiliar. `pruebas.md` §4.5 exige explícitamente que
   este caso pruebe valores textuales, no un conteo.

Los restantes `pilot-012`, `pilot-021` y `pilot-038` siguen requiriendo
diagnóstico antes de una puerta full, pero no justifican ampliar presupuestos.
`pilot-022` permanece como `expected_fact_not_found` para lectura cualitativa
separada.

## 2. Correcciones genéricas

### 2.1 Fecha de observación de la fuente no es periodo de filas

Se añadió `normalize_source_observation_cutoff_filters`, una regla
determinista y conservadora que solo actúa cuando una fecha está ligada
gramaticalmente a una `fuente`, `datos`, `dataset` o `portal` observados,
consultados, actualizados o disponibles.

La normalización elimina filtros de año, semana, mes, día o fecha únicamente
cuando:

- su valor coincide con la fecha de observación o su semana ISO; y
- ese mismo periodo no fue pedido explícitamente fuera de la cláusula de
  observación.

Una fecha o periodo solicitado normalmente conserva su semántica. No existen
condiciones por `case_id`, `dataset_id`, fecha concreta, valor esperado ni
texto completo de una pregunta.

Esto implementa RF-211: una fecha que describe cuándo se observó la fuente no
debe convertir por sí sola evidencia útil en `no_evidence`.

### 2.2 `golden-v2` no puede certificarse con su capacidad textual apagada

El runner incorpora un preflight de capacidades antes de seleccionar casos,
crear el engine o invocar LLM:

- `golden-v2` con puerta `smoke` o `full` exige
  `deterministic_textual_facts_enabled=true`;
- el CLI expone `--textual-facts-enabled`;
- una corrida `directed` puede mantener el flag apagado para diagnósticos que
  no certifican ninguna puerta;
- `golden-v1` conserva su comportamiento previo.

No se cambió el default productivo ni `.env.example`. La capacidad se activa
explícitamente en la evaluación y queda registrada en `config_snapshot`.
La barrera no endurece el golden: evita declarar válida una evaluación que
desactiva una capacidad requerida por su propio contrato.

### 2.3 Observabilidad de exploración separada de Socrata

El paso `explore_value` ahora persiste, en el mismo `AgentStep`:

- dataset, columna, valores propuestos y saldo de llamadas;
- resultado y valores observados;
- término efectivo, número de llamadas y latencia;
- error tipado `EXPLORATION_ERROR` cuando la exploración controlada falla.

`socrata_success_rate` cuenta exclusivamente observaciones cuyo nodo es
`execute_query`. Por tanto, la nueva salida T4 no infla ni contamina la tasa
T5/Socrata.

## 3. Límites preservados

No se modificaron:

- `golden-v1`, `golden-v2`, preguntas ni `expected_facts`;
- tolerancias, cardinalidades o umbrales;
- presupuestos de candidatos, exploraciones, consultas, reparaciones, LLM o
  duración;
- contratos públicos, migraciones o schemas;
- defaults productivos;
- reglas de privacidad, integridad o abstención.

No se añadió una excepción por caso, dataset o respuesta esperada.

## 4. Pruebas

| Control | Resultado |
|---|---|
| Focalizadas contratos/eval | `139 passed` |
| Suite `-m "not integration"` | `1083 passed, 122 deselected` |
| Aceptación determinista PostgreSQL | `19 passed` |
| Integración compartida | `95 passed, 1 skipped` |
| Aceptación legacy | `7 passed` |
| `ruff check .` | limpio |
| `ruff format --check` en 10 archivos modificados | limpio |
| `git diff --check` | limpio; solo advertencias LF/CRLF de Windows |
| SHA-256 golden-v1 | `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72` |
| SHA-256 golden-v2 | `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483` |

La prueba focal inicial falló únicamente porque un fixture nuevo usó un
`dataset_id` que no cumplía el patrón contractual `xxxx-xxxx`; se corrigió el
fixture y las mismas pruebas quedaron verdes. La primera prueba PostgreSQL
falló en setup porque `DATABASE_URL` no estaba exportada; se repitió cargando
solo esa variable desde `.env`, sin imprimirla ni modificar el archivo.

## 5. Próxima decisión

Este incremento no certifica el smoke ni autoriza `full`. El siguiente gasto
real debe ser una única evaluación `directed` de
`pilot-003-salud-vigilancia` y `pilot-013-app-dnp`, con
`--textual-facts-enabled`, desde un commit limpio:

- `pilot-003` debe usar la fuente correcta sin convertir la fecha de
  observación en filtro de filas;
- `pilot-013` debe producir hechos textuales persistidos y reproducibles sobre
  el nombre y tipo solicitados, no aprobar por un conteo auxiliar.

Solo si ambos resultados son materialmente útiles, verificables y sin
bloqueos reales corresponde repetir una vez el smoke canónico de diez casos.
La puerta `full` permanece bloqueada hasta que ese smoke pase.
