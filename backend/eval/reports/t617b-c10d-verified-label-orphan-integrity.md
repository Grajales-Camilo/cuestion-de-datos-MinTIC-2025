# T-617B-C10D — Integridad de cifras en etiquetas estructurales verificadas

**Fecha:** 2026-07-19 (America/Bogota)
**Baseline:** `ef9cde0ca420bcf539ce5ef8f685a4ec4197cbf2`
**Estado:** `ORPHAN_FALSE_POSITIVE_CLOSED / FULL_GATE_BLOCKED`

## 1. Evidencia real que motivó el incremento

Después de C10C se ejecutaron, sin modificar los golden:

1. evaluación real dirigida de `pilot-002` y `pilot-003`,
   UUID `845a1c48-93c4-4b66-a590-1f986b4b14fb`;
2. smoke canónico, UUID `d5ee908e-abe9-49fa-989a-1630818b8f85`;
3. puerta full de golden-v1, UUID
   `1b405332-aa8c-4870-a35c-a62875ecd599`.

La validación dirigida confirmó categoría y cifra consultables en ambos casos.
El smoke pasó: 10/10 canónicos, positivos 6/8, negativos 2/2, T5 7/7,
cero fabricaciones, cifras huérfanas o fallos de infraestructura e integridad
cuantitativa completa.

La puerta full ejecutó 50/50 casos únicos (40 positivos y 10 negativos) y
falló. Sus resultados principales fueron:

- positivos 15/40 (37,5 %);
- negativos 10/10 (100 %);
- fabricaciones 0;
- recall@10 100 %;
- Socrata observable 36/36;
- claims reproducibles 100 %;
- tres fallos de infraestructura;
- p95 simple 44.058 ms y p95 multipaso 95.138 ms;
- dos supuestas cifras huérfanas y cobertura de claims 99,58 %.

Golden-v2 no se ejecutó.

## 2. Causa raíz de las dos cifras huérfanas

Las dos observaciones pertenecían a `pilot-007` y `pilot-026`. En ambos casos
la síntesis citó una etiqueta derivada de la columna real
`tasa_matriculacion_5_16`:

> Tasa matriculacion 5 16: ...

El detector auxiliar interpretaba `5` y `16` como cantidades independientes.
No eran cifras fabricadas: formaban parte del nombre estructural de una
columna real, y la etiqueta pública se había derivado mecánicamente de esa
columna conforme a RF-212.

Este falso positivo es independiente de que `pilot-026` seleccionara un
dataset materialmente incorrecto. La corrección no convierte ese caso en
éxito ni modifica `expected_facts`.

## 3. Corrección acotada y defensa antimanipulación

`eval.metrics._collect_orphan_figures` admite una etiqueta como texto
respaldado únicamente cuando:

1. `claims[].columns` es una lista no vacía de nombres reales;
2. `derive_claim_label(columns)` reproduce exactamente la etiqueta;
3. el estado derivado es `verified`;
4. `claims[].label` y `claims[].label_status` coinciden exactamente con el
   resultado recalculado.

Una etiqueta ambigua, ausente o alterada no añade sus números a la lista
permitida. Por tanto, un payload no puede declarar por sí solo
`label_status="verified"` para blanquear una cifra inventada.

No se modificaron el runtime productivo, el DSL/hash de claims, los golden,
`expected_facts`, presupuestos, umbrales, contratos ni cardinalidades.

## 4. Pruebas y recálculo sin cuota

Regresión contra el baseline, antes del cambio:

- `test_eval_gate.py`: 1 fallo y 76 aprobadas;
- falló exactamente la etiqueta estructural legítima;
- los controles de etiqueta ambigua y etiqueta manipulada ya se rechazaban.

Después del cambio:

- `pytest tests/test_eval_gate.py -q`: 77 aprobadas;
- `pytest -m "not integration" -q`: 1.119 aprobadas, 124 deseleccionadas;
- `ruff check` sobre archivos tocados: limpio;
- `ruff format --check` sobre archivos tocados: limpio;
- `git diff --check`: limpio.

Recálculo de solo lectura sobre los 50 `final_answer` persistidos del UUID
`1b405332-aa8c-4870-a35c-a62875ecd599`, sin Gemini, Socrata ni nueva corrida:

- 50 resultados;
- 25 casos con integridad cuantitativa aplicable;
- 2.530/2.530 claims reproducibles;
- 298 cifras observadas;
- cifras huérfanas: 2 → 0;
- cobertura ponderada: 99,58 % → 100 %;
- casos con integridad rota: 0.

## 5. Veredicto y siguiente frontera

El falso positivo del evaluador queda cerrado. La puerta full continúa
bloqueada por resultados reales distintos: 15/40 positivos, tres fallos de
infraestructura y latencias p95 por encima de los umbrales, además de fallos
semánticos que requieren clasificación causal.

El siguiente incremento debe diagnosticar patrones comunes de los fallos
`budget_exceeded`, `evidence_not_eligible` y selecciones materialmente
incorrectas. No debe relajar los umbrales ni convertir automáticamente
`expected_fact_not_found` en un fallo del agente, porque varios golden
permiten más de una respuesta útil y verificable. Golden-v2 permanece
bloqueado hasta resolver o acotar los fallos sistémicos de golden-v1.
