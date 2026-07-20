# T-617B-C10A — Cantidades publicadas y diagnóstico terminal de Socrata

**Fecha:** 2026-07-19
**Rama:** `feat/t617-gate-preflight`
**Baseline:** `d4bf73a0db9dbb3fa532ca6dfa9a70f41bd160c1`
**Estado:** `READY_FOR_DIRECTED_PILOT012_PILOT021 / FULL_GATE_BLOCKED`

## 1. Disparador real

La evaluación dirigida real `f0d780fe-6514-4ede-9085-8aa677e3e1f4`
ejecutó `pilot-012`, `pilot-021` y `pilot-038` después de T-617B-C10.
Los tres alcanzaron planificación; los dos primeros ejecutaron Socrata y
persistieron evidencia, mientras el tercero terminó con
`terminal_error_code=SOCRATA_TIMEOUT`.

La corrida permitió separar tres defectos:

1. `pilot-012` preguntaba por hallazgos administrativos, pero el plan usó
   `count(*)=66` en lugar de leer `hallazgos_administrativos=12`.
2. `pilot-021` preguntaba cuántas personas participaron, pero el plan usó
   `count(*)=1` en lugar de leer la columna publicada `cantidad=65`.
3. El arnés degradaba el terminal de `pilot-038` a
   `intent_mismatch`, responsabilidad del agente, aunque la fila real de
   `agent_runs` conservaba `SOCRATA_TIMEOUT`.

En `pilot-012`, la extracción había dejado `entity=null`, pero conservaba
literalmente `Contraloría General de Antioquia` dentro de
`administrative_terms`. El esquema observado ofrecía
`sujeto_auditado`; omitir ese filtro podía mezclar sujetos.

## 2. Causa raíz

La normalización existente entendía que algunas preguntas cuantitativas debían
ser `LOOKUP`, pero no cubría el caso general donde el dataset ya publica la
cantidad solicitada como una columna numérica. Por ello el contrato superior
`COUNT` seguía materializándose como cardinalidad de filas.

La protección de entidad solo operaba si `IntentExtraction.entity` estaba
presente. No había una recuperación acotada desde términos institucionales ya
extraídos por el modelo, aunque fueran literales de la pregunta y el esquema
identificara una columna institucional.

Finalmente, `eval/diagnostics.py` todavía documentaba
`SOCRATA_TIMEOUT`/`SOCRATA_ERROR` como exclusivamente recuperables y no los
incluía entre los terminales de infraestructura, pese a que C10 ya puede
persistirlos como terminales reales conforme a `plan.md` §11 y
`contracts/api-rest.md`.

## 3. Corrección genérica

### 3.1 Cantidad directa

Se añadió una resolución determinista basada exclusivamente en la pregunta y
el esquema observado:

- requiere una pregunta explícita de cantidad;
- conserva `count(*)` cuando el objeto pedido son filas, registros, datasets,
  columnas o variables;
- selecciona una columna numérica solo cuando su concepto coincide de forma
  inequívoca con el objeto cuantificado;
- admite una columna puramente genérica (`cantidad`, `total` o `numero`) solo
  cuando es la única candidata;
- ante empate, ambigüedad o ausencia de objetivo cuantificado, no transforma
  la operación.

Cuando la normalización segura convierte la intención en `LOOKUP`, esa misma
columna se incorpora a la selección antes de materializar el plan. No se
modificaron presupuestos, prompts, schemas, golden ni tolerancias.

### 3.2 Entidad institucional

Si `entity` está ausente, solo puede recuperarse un término que cumpla a la vez:

- ya fue emitido por el modelo en `administrative_terms`;
- aparece literalmente en la pregunta;
- contiene al menos dos tokens y una cabeza institucional reconocible;
- el esquema observado tiene una columna que designa entidad, incluida
  `sujeto_auditado`.

La recuperación no interpreta texto libre ni contiene literales de los pilotos.
La protección existente exige después que el plan preserve esa entidad mediante
un filtro inequívoco; de lo contrario activa el replanteamiento acotado.

### 3.3 Diagnóstico Socrata

`SOCRATA_TIMEOUT` y `SOCRATA_ERROR`, cuando aparecen como
`agent_runs.terminal_error_code` de una corrida no evaluable, se clasifican
como infraestructura con `failure_code=socrata_timeout` o `socrata_error`.
Una observación intermedia recuperable no se promueve por sí sola.

El recálculo de solo lectura sobre el `agent_run` real de `pilot-038` produjo:

```json
{
  "run_status": "failed",
  "terminal_error_code": "SOCRATA_TIMEOUT",
  "failure_stage": "value_exploration",
  "failure_code": "socrata_timeout",
  "failure_owner": "infrastructure",
  "last_successful_stage": "planning"
}
```

No se reescribió la base ni el reporte histórico.

## 4. Controles de sobreajuste

Una auditoría offline, de solo lectura, cruzó las preguntas cuantificadas y los
esquemas reales del catálogo para ambos golden congelados:

- `golden-v1`: solo `pilot-021` se convierte a lectura directa de `cantidad`;
- `golden-v2`: solo `pilot-012` y `pilot-021` se convierten;
- casos sobre puestos, calzadas, registros de venta y cardinalidad explícita
  permanecen `COUNT`;
- “cuánto se pagó” no activa la regla porque no tiene un sustantivo
  cuantificado;
- una columna no relacionada como `cantidad_elecciones` no se elige por el
  solo hecho de contener “cantidad”.

Las pruebas también cubren columnas ambiguas, preguntas sin entidad, esquemas
sin columna institucional y filtros de entidad omitidos.

## 5. Evidencia fallo → pasa y regresiones

Antes de la implementación, las pruebas nuevas de contrato no podían
recolectarse porque `normalize_direct_quantity_lookup` no existía. Con la
implementación:

- pruebas focalizadas: `151 passed`;
- suite `pytest -m "not integration" -q`: `1109 passed, 124 deselected`;
- aceptación determinista con PostgreSQL local:
  `21 passed, 1212 deselected`;
- integraciones compartidas:
  `95 passed, 1 skipped, 1137 deselected`;
- aceptación legacy: `7 passed, 1226 deselected`;
- `ruff check`: limpio;
- `ruff format --check` en archivos modificados: limpio;
- `git diff --check`: limpio.

Hashes congelados:

- `golden-v1`:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`;
- `golden-v2`:
  `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`.

## 6. Alcance y siguiente puerta

No se cambiaron golden, expected facts, presupuestos, umbrales, contratos,
cardinalidades ni reglas por caso/dataset. T-617 permanece abierta.

La validación real mínima siguiente es una corrida `directed` de
`pilot-012` y `pilot-021`. Debe comprobar, sin exigir perfección de redacción:

- fuente y entidad correctas;
- lectura de `hallazgos_administrativos` y `cantidad`, no `count(*)`;
- cifras trazables y sin fabricación;
- respuesta útil y materialmente correcta, con limitaciones transparentes.

`pilot-038` no requiere otra corrida dirigida para atribuir el hallazgo
histórico: ya quedó demostrado como infraestructura. El próximo smoke canónico
volverá a ejecutarlo. Solo si los dos casos dirigidos cumplen el criterio
anterior procede un smoke de 10; la puerta `full` continúa bloqueada hasta que
ese smoke pase.
