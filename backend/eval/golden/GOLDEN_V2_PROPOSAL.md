# Propuesta de `golden-v2`: contrato de hechos derivables

## Estado y alcance

Este documento no modifica ni relaja `golden-v1`, `eval/metrics.py` ni el
umbral RNF-002. Registra incompatibilidades observadas al ejecutar el runtime
determinista contra Socrata real y propone un contrato nuevo, versionado y
auditable. Satisface RF-208 y RNF-002: la evaluación debe premiar respuestas
fundamentadas en la pregunta, no el uso de filtros ocultos del evaluador.

`golden-v1` continúa siendo inmutable y útil como línea histórica. No debe
reemplazarse ni reinterpretarse silenciosamente.

## Evidencia reproducible

- `eval/reports/a4cc79c8-d011-4de7-83e2-2b3770205e38.md`: el caso
  `pilot-013-app-dnp` pasa cuando el identificador `PRY00062`, explícito en la
  pregunta, se conserva como filtro y los campos textuales se representan como
  presencia verificable.
- `eval/reports/152bce74-8e21-42e9-83f3-18251b0ffd81.md`: de nueve casos lookup,
  ocho consultan o intentan consultar fuentes reales, pero solo uno coincide
  con la fila exacta congelada.
- `eval/reports/f80dbf19-61d5-4973-93a6-653494b05b79.md`: 038 y 039 consultan el
  dataset esperado con rango diario explícito y seleccionan fecha, estación y
  sensor, pero no coinciden con la observación horaria oculta del golden.

Consultas persistidas para la última corrida:

```sql
SELECT fechaobservacion, codigoestacion, codigosensor, descripcionsensor,
       nombreestacion, departamento, municipio
WHERE fechaobservacion >= '2019-02-11'
  AND fechaobservacion < '2019-02-12'
LIMIT 100 OFFSET 0
```

La misma forma se ejecutó para 2020-01-21. Ambos días devuelven al menos 100
observaciones. La pregunta no contiene la hora, la estación ni una regla de
orden que seleccione de manera única el registro congelado.

## Incompatibilidades confirmadas

| Caso | Pregunta observable | Hecho congelado no determinado |
|---|---|---|
| `pilot-022-red-vial` | solicita el tramo `55ST02` | la URL esperada filtra `administrador=1`, `calzada=1`, `categoria=2`, pero no filtra el identificador solicitado |
| `pilot-037-calidad-aire` | pregunta qué estación de AMVA figura | congela la estación `9020 / I.E. COL. COLOMBIA` sin criterio para escogerla entre varias |
| `pilot-038-precipitacion` | especifica solo 2019-02-11 | exige estación `0054050010`, sensor `0240` y hora `13:50` |
| `pilot-039-temperatura` | especifica solo 2020-01-21 | exige estación `0026195501`, sensor `0068` y hora `03:35` |

Estos casos no pueden convertirse en pruebas de exactitud determinista sin una
de estas dos correcciones: hacer explícita la restricción en la pregunta o
evaluar un conjunto de respuestas válidas. Incorporar los valores congelados
al runtime sería sobreajuste al benchmark y violaría la prohibición de
hardcodear preguntas, IDs o cifras piloto.

## Contrato propuesto

Cada caso positivo de `golden-v2` debe declarar:

1. `input_constraints`: restricciones literales presentes en la pregunta.
2. `selection_rule`: agregación, orden y desempate necesarios para obtener una
   respuesta única; puede ser nulo solo si las restricciones identifican una
   única fila.
3. `acceptable_facts`: uno o más hechos válidos cuando la pregunta admite
   varias respuestas equivalentes.
4. `source_urls`: consultas de verificación que aplican únicamente
   `input_constraints` y `selection_rule`; no filtros de la respuesta esperada.
5. `observed_at` y `data_cutoff_at`: corte usado para congelar el caso.

El evaluador debe comprobar que la evidencia contiene un hecho aceptable y que
la consulta ejecutada respeta las restricciones explícitas. Los casos con
respuesta no única deben usar pertenencia a `acceptable_facts`, no igualdad con
una fila arbitraria.

## Migración y puertas

1. Auditar los 40 casos positivos de `golden-v1` sin cambiar ese archivo.
2. Reescribir únicamente los casos incompatibles en un archivo nuevo
   `golden-v2.yaml`, con revisión humana de sus fuentes y cortes.
3. Ejecutar ambos suites durante una versión: v1 informativo y v2 como candidato
   de aceptación.
4. Autorizar el cambio de suite normativa de forma explícita en la
   especificación antes de usar v2 para RNF-002.
5. No retirar el runtime legado hasta alcanzar la puerta contractual aplicable
   y conservar `AGENT_RUNTIME=legacy` como rollback durante una versión.

Hasta esa autorización, el resultado honesto es: runtime determinista activo y
mejorado, pero Gate 6 no aprobado; la retirada del legado permanece bloqueada.
