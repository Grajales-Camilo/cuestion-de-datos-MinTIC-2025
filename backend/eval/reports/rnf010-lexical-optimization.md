# T-614R2 — Optimización lexical RNF-010

**Fecha:** 2026-07-16 · **rama:** `feat/deterministic-agent-core` ·
**Requisitos:** RF-301, RF-302, RF-304, RNF-010 ·
**veredicto:** RNF-010 resuelto; dos corridas normativas consecutivas pasan.

## 1. Estado inicial

Después de T-614R1, 100 consultas reales obtenían p50/p95/p99
`923,5/1293,6/1696,2 ms`, cobertura 100 % (8394/8394) y cero errores.
`EXPLAIN ANALYZE` medía ~498,6 ms: ~457,5 ms correspondían a un
`Parallel Seq Scan` que recalculaba `to_tsvector`; HNSW tardaba ~0,7 ms.

## 2. Decisión SDD y campos lexicales

`catalog_datasets.lexical_search_vector` es `tsvector NOT NULL`, configuración
`spanish`, e incluye exactamente:

1. `name`;
2. `description`;
3. `publisher`;
4. `category`;
5. `embedding_text`;
6. `catalog_columns.field_name`;
7. `catalog_columns.display_name`;
8. `catalog_columns.description`.

Un segundo `lexical_rank_vector`, sin índice, conserva exactamente la expresión
histórica de ranking: `name`, `publisher`, `category`, `description` y texto de
columnas ordenado por `field_name`. En las 8.398 filas reales hubo cero
diferencias entre ambos vectores y sus expresiones fuente.

## 3. Mantenimiento, backfill y rollback

- Trigger `BEFORE INSERT OR UPDATE` mantiene ambos vectores ante cambios del
  dataset.
- Tres triggers por sentencia con transition tables mantienen ambos vectores
  ante INSERT, UPDATE y DELETE de columnas; cada dataset se recalcula una vez
  por sentencia.
- La ingesta activa los triggers dentro de su propia transacción. Dos upserts
  consecutivos conservaron idempotencia.
- Backfill idempotente: ~3,2 s para el catálogo real; 8.398/8.398 poblados,
  cero vacíos y cero cambios semánticos al repetir la expresión.
- Rollback probado: downgrade `0005→0004` y `0004→0003`, seguido de upgrade a
  head; quedaron 8.398 datasets y 8.394 embeddings.
- Generated column descartada: no puede agregar filas hijas de
  `catalog_columns`. Mantenimiento solo en aplicación descartado: no cubre
  escrituras SQL externas.

## 4. Comparación GIN frente a GiST

Prueba reversible en tabla experimental con 8.398 datasets reales:

| Métrica | GIN | GiST |
|---|---:|---:|
| construcción | 146–175 ms | 114–118 ms |
| tamaño experimental | 3.056–3.352 KiB | 3.104 KiB |
| búsqueda selectiva `acueducto:*` | 0,38 ms | 6,17 ms |
| bloques de índice | 3 | 389 |
| filas devueltas por índice | 77 | 8.398 |
| rechecks descartados | 0 | 8.321 |
| actualización de 100 vectores | ~2,7 ms | ~2,7 ms |

Se eligió GIN: la búsqueda selectiva fue ~16 veces más rápida y evitó los
rechecks de GiST. El menor tiempo de construcción de GiST no compensa en una
carga predominantemente de lectura. El índice productivo usa `gin` +
`tsvector_ops`; su tamaño observado tras migraciones/pruebas es 17 MiB.

Para términos muy amplios PostgreSQL puede preferir scan del `tsvector`
almacenado (~51 ms en el diagnóstico final). Esto no recalcula `to_tsvector`
y no reproduce el seq scan dominante anterior. Para consultas selectivas y
para el diagnóstico indexado se observó `Bitmap Index Scan` GIN.

## 5. Consulta, ranking y enriquecimiento

La rama de candidatos usa `lexical_search_vector`; HNSW y
`vector_cosine_ops` no cambiaron. `lexical_rank_vector` reemplaza únicamente
la expresión histórica equivalente. La fórmula final sigue siendo:

`similarity + LEAST(0.25, lexical_rank * 0.02)`, con desempate por similarity.

`columns_preview` y `columns_all`, que solo forman la respuesta, se calculan
después del top-10. Las agregaciones laterales bajaron de 384 (3 × 128) a 20
(2 × 10). Pruebas controladas conservaron orden híbrido, cobertura, columnas
y contrato. No hubo boosts por ID, mapas pregunta→dataset ni conocimiento
golden.

## 6. EXPLAIN y componentes antes/después

Consulta diagnóstica: `estadísticas de educación en Colombia`, k=10.

| Componente | Después R1 | T-614R2 final |
|---|---:|---:|
| embedding reutilizado p50/p95 | 323,7/426,0 ms | 345,9/372,6 ms |
| SQL+Python con vector fijo p50/p95 | 568,3/810,1 ms | 125,5/144,4 ms |
| EXPLAIN ejecución | 498,6 ms | 67,5 ms |
| lexical | ~457,5 ms, recálculo + seq scan | ~51 ms scan almacenado; GIN selectivo 0,38 ms |
| HNSW | ~0,7 ms | ~0,75 ms |
| ruta directa p50/p95 | 833,3/1094,4 ms | 389,2/433,7 ms |
| candidatos híbridos | ~118 | 128 |
| agregaciones laterales | 357–384 | 20 |

Otro diagnóstico posterior al primer vector, antes del rank materializado,
observó GIN en el plan: `Bitmap Index Scan` ~1,1 ms, rama lexical ~37,8 ms,
EXPLAIN 123,8 ms y SQL+Python p95 242,1 ms.

El bloque final de una corrida diagnóstica sufrió throttling remoto (máximo
~30 s); por ello sus percentiles de plataforma no se usan como prueba
normativa. Las corridas de 100 consultas sí son la puerta.

## 7. Corridas RNF-010

Todas usaron 100 consultas representativas, Gemini real, k=10, el cálculo
normativo de percentiles y el contrato HTTP real.

| Corrida | Diseño | p50 | p95 | p99 | cobertura | errores | resultado |
|---|---|---:|---:|---:|---:|---:|---|
| R1 referencia | lifecycle | 923,5 | 1293,6 | 1696,2 | 100 % | 0 | falla |
| R2-1 | GIN + vector búsqueda | 427,4 | 1003,3 | 2074,2 | 100 % | 0 | falla |
| R2-2 | preview/all post top-10 | 435,2 | 1094,8 | 1345,9 | 100 % | 0 | falla |
| R2-3 | rank exacto materializado | 376,8 | 828,0 | 1635,5 | 100 % | 0 | pasa |
| R2-4 consecutiva | mismo diseño | 359,5 | 482,0 | 771,4 | 100 % | 0 | pasa |

Las dos últimas son consecutivas y cumplen p95 <= 1000 ms, cobertura completa
y cero errores. La mejora frente a R1 es -465,6 ms (-36,0 %) en el peor p95
de las dos corridas estables.

## 8. Pruebas y validaciones

- 25 pruebas dirigidas iniciales: pasan.
- Pruebas de materialización/ingesta/búsqueda: 11 pasan.
- Suite no integración: 653 pasan, 95 deseleccionadas.
- Aceptación determinista: 14 pasan, 1 xfail esperado.
- Aceptación legacy: 7 pasan.
- Ruff completo: pasa.
- `git diff --check`: pasa.
- Downgrade/upgrade de ambas migraciones: pasa.
- Dos corridas normativas consecutivas: pasan.

Las suites históricas `test_ingest_catalog.py` y `test_build_embeddings.py`
no pudieron aislar la base compartida: sus fixtures intentan borrar todo el
catálogo y `evidence_results` contiene FKs activas. Fueron nueve errores de
setup previos al código probado. La ingesta relevante quedó cubierta por el
upsert doble específico de T-614R2.

## 9. Limitaciones e impacto

- El p99 de la primera corrida verde (1635,5 ms) muestra variabilidad remota,
  pero RNF-010 norma p95 y la segunda corrida confirmó estabilidad.
- Términos amplios pueden usar scan del vector almacenado en vez de GIN; el
  coste es decenas, no cientos de milisegundos.
- Las escrituras pagan el recálculo de dos vectores. La comparación midió
  ~2,7 ms por 100 actualizaciones de vector y la ingesta es semanal.
- El índice productivo de 17 MiB es mayor que el experimental limpio; no afecta
  el presupuesto de lectura y debe vigilarse tras ingestiones completas.
- No se ejecutó una reescritura concurrente embedding/SQL ni caché de consultas.

## 10. Estado, archivos y commits

T-614 queda cerrada por evidencia. T-615 permanece bloqueada y no se inició.
No hace falta T-614R3: el enriquecimiento post top-10 ya quedó incorporado sin
cambiar ranking.

Commits:

- `073efb5` — `docs(sdd): define RNF-010 lexical materialization`
- `c8401a9` — `perf(catalog): materialize and index lexical search vector`
- `0e3b173` — `perf(catalog): use indexed lexical retrieval`
- `8023cf7` — `perf(catalog): materialize exact lexical ranking`
- commit de este informe — `docs(eval): report RNF-010 lexical optimization`

Archivos productivos: `app/catalog/search.py`, `app/db/models.py`, migraciones
`0004`/`0005`. Pruebas: `test_catalog_lexical_materialization.py` y
`test_catalog_search_sql.py`. SDD: `research.md`, `plan.md`, `data-model.md` y
la propuesta lexical. No cambiaron contratos, `golden-v1`, modelo/dimensión,
muestras, percentiles, k ni límites.

**Recomendación:** revisar y fusionar T-614R2 como cierre independiente. No
autorizar T-615 automáticamente; requiere su enmienda contractual separada.
