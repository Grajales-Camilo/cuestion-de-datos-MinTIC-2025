# T-617B-C10B — Preflight de capacidad textual en puertas formales

**Fecha:** 2026-07-20
**Baseline:** `e54ef2026df9ad60e3c1b682e46158407377a3c7`
**Estado:** `READY_FOR_COMMITTED_SMOKE_RETRY / FULL_GATE_BLOCKED`

## 1. Evidencia previa que sí pasó

La corrida formal `directed`
`aeac0584-c748-4ce3-9dd0-adaf8d800473` validó C10A sobre Gemini, Socrata y
PostgreSQL reales:

| Caso | Dataset | Filtros materiales | Resultado |
|---|---|---|---|
| `pilot-012` | `wasc-xi4h` | Regular, 2019, Contraloría General de Antioquia | 12 hallazgos |
| `pilot-021` | `52mk-e3ug` | Alcalá, enero, 2018 | 65 personas |

Ambos terminaron `completed`; cobertura y reproducibilidad de claims fueron
100%, sin fabricación ni cifras huérfanas. La métrica T5 fue observable y
registró `2/2` consultas exitosas. El modo `directed` no certificó smoke/full.

## 2. Smoke real y veredicto preservado

El smoke canónico real `21ea1576-3242-4a89-b2d7-4f5a3b87f1ac`, sobre el mismo
commit, persistió exactamente diez resultados:

- positivos: `5/8`;
- negativos: `2/2`;
- T5 observable: `7/7`;
- fabricaciones: `0`;
- cifras huérfanas: `0`;
- infraestructura: `0`;
- integridad de claims: completa;
- bloqueante mecánico: retroceso de `pilot-013-app-dnp`.

El reporte y su `gate_passed=false` se conservan sin reinterpretarlos ni
reescribirlos.

## 3. Causa raíz forense de `pilot-013`

No fallaron la recuperación, Gemini, Socrata ni el dataset esperado. En el
primer candidato (`tmk8-iihq`) el runtime:

1. observó el código `PRY00062`;
2. ejecutó una consulta con `WHERE codigo = 'PRY00062'`;
3. recibió una fila con:
   - `nombre_proyecto = IP Ibagué - Cajamarca`;
   - `tipo_app = Iniciativa Privada sin Recursos Públicos`;
4. no persistió esa evidencia porque la corrida tenía
   `DETERMINISTIC_TEXTUAL_FACTS_ENABLED=false`;
5. recorrió siete candidatos inferiores y terminó
   `CANDIDATE_BUDGET_EXCEEDED`.

El comportamiento del runtime fue seguro: con la capacidad textual apagada no
inventó claims ni revivió el antiguo surrogate `count=1`. El defecto estaba en
el arnés, que permitía iniciar una puerta formal con una capacidad necesaria
desactivada.

Esto contradice `pruebas.md` §4.4/T-615: después de implementar la capa textual,
`pilot-013` debe verificar los valores de nombre y tipo, no un conteo. Ambos
golden conservan exactamente esa pregunta y valores textuales.

## 4. Corrección

`eval.run._validate_eval_capabilities` ahora exige
`DETERMINISTIC_TEXTUAL_FACTS_ENABLED=true` para cualquier `--gate smoke` o
`--gate full` sobre las suites actuales, tanto v1 como v2. La validación ocurre:

- después de cargar la suite;
- antes de seleccionar/persistir casos;
- antes de crear el engine;
- antes de invocar Gemini o Socrata.

El mensaje indica el esquema, la puerta y el argumento correctivo
`--textual-facts-enabled`. El modo `directed` mantiene compatibilidad con el
flag encendido o apagado porque es diagnóstico y no certifica una puerta.

No se cambió el runtime, los presupuestos, los prompts, los golden, los
expected facts, los umbrales ni los contratos.

## 5. Verificación

- focalizadas `tests/test_eval_run_error_handling.py`: `30 passed`;
- `pytest -m "not integration" -q`:
  `1113 passed, 124 deselected`;
- `pytest -m deterministic_agent_acceptance -q` con PostgreSQL local:
  `21 passed, 1216 deselected`;
- integraciones compartidas con PostgreSQL local:
  `95 passed, 1 skipped, 1141 deselected`;
- aceptación legacy:
  `7 passed, 1230 deselected`;
- `ruff check .`: limpio;
- `ruff format --check` en archivos modificados: limpio;
- `git diff --check`: limpio.

Los primeros intentos de las suites PostgreSQL abortaron en setup porque la
sesión de PowerShell no exportaba `DATABASE_URL`; se repitieron de forma
secuencial inyectando únicamente el valor ya cargado por `Settings`, sin
modificar `.env`, y produjeron los resultados verdes anteriores. No fue un
fallo de código.

Hashes congelados:

- `golden-v1`:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`;
- `golden-v2`:
  `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`.

## 6. Siguiente paso

Crear un commit local con este preflight y su evidencia. Después ejecutar una
única repetición del smoke canónico de `golden-v1` con
`--textual-facts-enabled`. Si pasa, procede la suite completa `golden-v1` con
la misma capacidad y configuración; `full` sigue bloqueado hasta entonces.
