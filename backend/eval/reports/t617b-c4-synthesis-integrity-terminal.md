# T-617B-C4 — Terminal de integridad de síntesis y telemetría

**Fecha:** 2026-07-19
**Rama:** `feat/t617-gate-preflight`
**HEAD:** `597ef73e4e018ddba1a9d61faee6dcad97edce26`
**Requisitos:** Constitución Art. I.1/I.5/VII.1; RF-208, RF-602, RF-703; RNF-003, RNF-009.

## Veredicto

**IMPLEMENTADO_Y_VALIDADO_REALMENTE / PILOT-007_BLOQUEADO_CORRECTAMENTE**

Se conserva sin relajación el bloqueo de una síntesis con cifras huérfanas. El
fallo que persiste después del fallback determinista deja de escapar como
`INTERNAL`: ahora se convierte en `STRUCTURED_OUTPUT_INVALID`, código
contractual existente, bloqueante y atribuible al agente.

Antes de escribir el evento terminal se persisten `steps_used`, `latency_ms`,
proveedor/modelo, tokens de entrada/salida y costo estimado. La corrida
`failed` no persiste `final_answer` ni expone evidencia o claims.

## Evidencia causal de `pilot-007`

Corrida original: `657f0ebf-cd74-4750-b38f-94187922732a`, perteneciente al
eval run `b0d38f87-d2d3-4bc8-80ae-b197e278d328`.

- PostgreSQL conserva siete pasos y una consulta ejecutada.
- El paso final observado es `synthesize`.
- El evento terminal original contiene
  `síntesis contiene cifras huérfanas: ('16',)`.
- `agent_runs` tenía `terminal_error_code=INTERNAL`, tres llamadas LLM en la
  última traza, pero tokens, costo, `steps_used` y `final_answer` nulos.

La ruta de código intentaba validar la salida LLM, construía un fallback
determinista al primer `ValueError` y volvía a validarlo. El segundo
`ValueError` no estaba tipado y caía en el `except Exception` genérico del
runner.

## Cambios

- `app/agent/deterministic_runtime.py`
  - añade `SynthesisIntegrityError`;
  - convierte exclusivamente el segundo fallo de validación, después del
    fallback seguro, en ese error tipado.
- `app/agent/persistence.py`
  - añade `persist_run_telemetry`, escritura técnica sin `final_answer`.
- `app/agent/runner.py`
  - conserva el acumulador de uso durante toda la corrida;
  - captura `SynthesisIntegrityError`;
  - persiste telemetría y emite un único terminal
    `failed/STRUCTURED_OUTPUT_INVALID`.
- `tests/test_deterministic_runtime.py`
  - prueba que una cifra huérfana persistente produce el error tipado.
- `tests/integration/test_deterministic_agent_acceptance.py`
  - prueba con PostgreSQL real el terminal, la telemetría no nula, la ausencia
    de respuesta/evidencia/claims públicos y la unicidad del evento terminal.
- `eval/run.py`
  - proyecta hacia el resultado de evaluación la telemetría persistida en
    `agent_runs` cuando un terminal `failed` no tiene `final_answer`.
- `tests/test_eval_run_error_handling.py`
  - verifica que esa proyección conserva pasos, latencia, tokens, costo y
    código terminal.

No se cambiaron contratos, specs, métricas, umbrales ni golden. Se reutilizó
`STRUCTURED_OUTPUT_INVALID`, ya definido en `contracts/api-rest.md` y ya
clasificado por `eval/diagnostics.py` como `failure_owner=agent`.

## Validación

- Pruebas focalizadas unitarias/diagnóstico: `2 passed`.
- Aceptación focalizada con PostgreSQL real y dobles locales sin red:
  `1 passed`.
- Suite completa sin integración: `1057 passed, 123 deselected`.
- Ruff: limpio.
- Formato Ruff: limpio.
- `git diff --check`: limpio.
- `agent_runs.status='running'`: `0`.
- Hash `golden-v1`:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`.
- Hash `golden-v2`:
  `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`.

## Validación dirigida real

Eval run: `c53e4a96-c764-4e19-b13f-583a9575fdb1`.
Agent run: `1d8d8eeb-e780-4b4f-a6e4-c0404300dc7c`.

- dataset esperado `ji8i-4anb` recuperado en rango 1 e intentado;
- una consulta ejecutada y tres llamadas LLM;
- la síntesis y su fallback conservaron la cifra huérfana `16`;
- terminal `failed/STRUCTURED_OUTPUT_INVALID`;
- diagnóstico `failure_stage=synthesis`,
  `last_successful_stage=query_execution`, `failure_owner=agent`;
- `steps_used=7`, `latency_ms=18062`, `input_tokens=11305`,
  `output_tokens=2608`, `estimated_cost_usd=0.009912`;
- `final_answer` ausente y cero evidencia/claims públicos;
- un único evento terminal;
- `fabrication_count=0`, `orphan_figures_count=0`;
- modo `directed`: sin veredicto normativo de puerta.

La primera generación del reporte dirigido mostró costo vacío aunque la base
ya contenía USD 0,009912. Esto reveló que el arnés construía
`{"status": "failed"}` al faltar `final_answer` y descartaba la telemetría
persistida. La proyección descrita arriba corrige el defecto para corridas
posteriores sin reejecutar Gemini.

## Límites

Se ejecutó exclusivamente `pilot-007` en modo `directed`. No se ejecutaron
smoke, golden-v1 completo ni golden-v2. El caso no aprobó el hecho dorado
porque la respuesta fue bloqueada correctamente; el modo `directed` no
certifica una puerta normativa.

No se creó commit. Se preservaron todos los cambios rastreados de T-617B-C2/C3
y todos los archivos no rastreados preexistentes.
