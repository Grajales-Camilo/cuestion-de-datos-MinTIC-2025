# T-617B-C10C — Etiquetas textuales en agregados de una fila

**Fecha:** 2026-07-19
**Baseline:** `95ecb5dbb21b22bec8becfe78c13efa5b9fa5767`
**Estado:** `READY_FOR_DIRECTED_REAL_VALIDATION / FULL_GATE_BLOCKED`

## 1. Hallazgo real

El smoke canónico `43e3cac4-5939-48ab-96d5-e00f46a0b9ed` pasó
mecánicamente:

- 10/10 casos canónicos y sin duplicados;
- positivos `7/8`, negativos `2/2`;
- cero fabricaciones, cifras huérfanas o fallos de infraestructura;
- claims con cobertura y reproducibilidad del 100%;
- T5 observable `8/8`;
- `gate_passed=true`.

La auditoría humana posterior encontró dos respuestas materialmente
insuficientes bajo RF-211, aunque sus cifras y fuentes eran correctas:

| Caso | Pregunta material | Fila respaldada | Respuesta emitida |
|---|---|---|---|
| `pilot-002` | departamento con mayor concentración | `VALLE DEL CAUCA`, `66.723` | `Cantidad: 66.723.` |
| `pilot-003` | evento con mayor volumen | `AGRESIONES POR ANIMALES POTENCIALMENTE TRANSMISORES DE RABIA`, `1.470.739` | `Conteo: 1.470.739.` |

En ambos casos el plan produjo un agregado agrupado, ordenado y limitado a
una fila. La dimensión textual estaba en la evidencia (`dim_1`), pero no
existía ningún `textual_fact`; la síntesis solo recibió el claim cuantitativo
y omitió precisamente la categoría que respondía la pregunta.

Por tanto, el PASS mecánico se conserva como evidencia del arnés, pero no
autoriza todavía la puerta `full`.

## 2. Causa raíz

`deterministic_pipeline._prepare_single_row_lookup_textual_fallback` ya
derivaba `direct_text` de forma segura cuando:

1. el resultado tenía exactamente una fila;
2. el LLM no había producido `textual_requests`;
3. la dimensión era `TEXT`;
4. su nombre real estaba explícitamente solicitado por la intención;
5. el alias no estaba representado por un claim cuantitativo.

La misma garantía no se aplicaba a agregados agrupados de una fila. No era un
problema de Socrata, evidencia, claims ni síntesis: la etiqueta verificable se
descartaba antes de llegar a cualquiera de las dos rutas de síntesis.

## 3. Corrección genérica

El helper se generaliza como `_prepare_single_row_textual_fallback` y conserva
las cinco condiciones anteriores para cualquier operación validada. No
inspecciona valores para elegir una columna, ni usa `case_id`, `dataset_id`,
preguntas o cifras codificadas.

El hecho derivado es `direct_text`: certifica únicamente que el valor textual
aparece en la única fila devuelta. No añade la afirmación de que sea un
ganador único ni debilita la detección de empates de `argmax_label` o
`first_by_validated_order`. Si regresan dos o más filas, no elige ninguna
etiqueta.

La seguridad previa permanece:

- columnas PII `high/unknown` no superan el validador del plan;
- PII `medium` exige agregación y tamaño de grupo;
- evidencia no elegible se rechaza antes de construir texto;
- dimensiones no solicitadas no se promueven;
- solicitudes textuales explícitas siguen por la ruta cerrada normal.

## 4. Regresiones deterministas

Se agregaron tres comportamientos:

1. un agregado de una fila deriva la dimensión textual explícitamente pedida;
2. una dimensión no pedida no se promueve;
3. dos filas no permiten elegir automáticamente una categoría.

El caso positivo falló contra el baseline (`1 failed, 33 passed`) y pasa con
la corrección.

Verificación final:

- focalizadas: `34 passed`;
- `pytest -m "not integration" -q`:
  `1116 passed, 124 deselected`;
- aceptación determinista con PostgreSQL local:
  `21 passed, 1219 deselected`;
- `ruff check .`: limpio;
- formato de los dos archivos modificados: limpio;
- `git diff --check`: limpio.

Hashes congelados sin cambios:

- `golden-v1`:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`;
- `golden-v2`:
  `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`.

## 5. Siguiente paso

Crear un commit local y ejecutar una única evaluación real `directed` de
`pilot-002` y `pilot-003`, con capacidad textual habilitada. La aceptación
requiere que cada respuesta incluya su categoría y su cifra respaldadas, sin
fabricaciones, cifras huérfanas ni pérdida de trazabilidad. Solo después de
esa auditoría procede repetir el smoke canónico; `full` permanece bloqueado.
