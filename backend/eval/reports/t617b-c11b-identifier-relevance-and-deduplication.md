# T-617B-C11B — Relevancia y deduplicación de identificadores

**Fecha:** 2026-07-19 (America/Bogota)
**Baseline:** `e8c31afc9ebbddc3884839b5ede7a90f7db32388`
**Estado:** `READY_FOR_FINAL_DIRECTED_VALIDATION / FULL_GATE_BLOCKED`

## 1. Validación real de C11A

La corrida dirigida real `6100770b-080f-485a-a30c-f47ae1af1108`, sobre
`e8c31af`, ejecutó `pilot-016` y `pilot-020` con Gemini, Socrata y PostgreSQL
reales.

Resultados materiales:

- `pilot-020` respondió `Cod dpto: 05. Además, Cod mpio: 05001.`; los ceros
  iniciales se conservaron desde la evidencia hasta el texto final;
- `pilot-016` conservó literalmente los códigos postales `153.42` y
  `153.427`;
- ambos casos tuvieron integridad textual completa, cero fabricaciones, cero
  cifras huérfanas y ninguna falla de infraestructura;
- `pilot-016` siguió fallando su `expected_fact` histórico, que exige otra
  ancla y no representa la pregunta postal. No se modificó el golden.

C11A cerró la corrupción material. La auditoría humana encontró una advertencia
no bloqueante: al pedir un identificador postal, la narrativa también enumeró
códigos de departamento y municipio, y repitió la misma zona postal para las
dos filas. Todo estaba respaldado por la fuente, pero la respuesta era más
ruidosa de lo necesario.

## 2. Corrección genérica

La selección de identificadores ahora distingue calificadores estructurales:

- postal;
- NIT, SIGEP, radicado y consecutivo;
- municipio (`municipio`/`mpio`);
- departamento (`departamento`/`dpto`);
- DIVIPOLA, que admite códigos geográficos de municipio/departamento.

Si la intención contiene un calificador, solo se materializan columnas de esa
familia. Una solicitud genérica de código/identificador conserva la cobertura
anterior. La regla opera sobre tokens de la intención y nombres reales de
columna, nunca sobre valores, `case_id`, dataset o literales de golden.

Dentro de una misma columna, valores textuales idénticos se emiten una sola
vez, conservando determinísticamente la primera fila que los respalda. Valores
distintos, aunque sean muy parecidos (`153.42` frente a `153.427`), permanecen
separados.

## 3. Regresiones

La prueba multirregistro usa tres columnas:

- `codigo_postal`: dos valores distintos, ambos se preservan;
- `zona_postal`: el mismo valor en dos filas, se emite una vez;
- `codigo_departamento`: no se emite porque la intención pide códigos
  postales.

El control DIVIPOLA conserva `cod_dpto`/`cod_mpio`, y el camino de fallo seguro
con capacidad textual apagada permanece intacto.

Resultados:

- focalizadas: **88 aprobadas**;
- `pytest -m "not integration" -q`: **1.127 aprobadas**, 125 deseleccionadas;
- aceptación determinista con PostgreSQL real: **21 aprobadas**;
- Ruff y `git diff --check`: limpios;
- hashes golden sin cambios.

## 4. Siguiente paso

Una última validación real dirigida de `pilot-016` y `pilot-020` debe confirmar:

1. preservación byte a byte de todos los identificadores citados;
2. ausencia de códigos no solicitados;
3. ausencia de duplicados exactos por columna;
4. integridad textual completa y cero bloqueos reales.

El resultado mecánico de `pilot-016` seguirá interpretándose aparte del
`expected_fact` desalineado. No repetir smoke/full ni ejecutar golden-v2 hasta
cerrar también los defectos materiales independientes de `pilot-034` y
`pilot-036`.
