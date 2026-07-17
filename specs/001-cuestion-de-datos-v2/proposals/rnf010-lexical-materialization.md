# Decisión SDD — T-614R2 materialización lexical RNF-010

**Estado:** DECIDIDA con medición local reversible (2026-07-16) ·
**Requisitos:** RF-301, RF-302, RF-304, RNF-010

## Problema y presupuesto

R1 redujo RNF-010 a p50 923,5 ms/p95 1293,6 ms, pero la rama lexical consume
~457 ms en un `Parallel Seq Scan` que recalcula `to_tsvector`. R2 debe recuperar
al menos 300 ms de p95 sin cambiar ranking, cobertura, modelo o contrato.

## Diseño aprobado

1. Añadir a `catalog_datasets` un `tsvector` normal, `NOT NULL`, mantenido e
   indexado con exactamente
   `name`, `publisher`, `category`, `description`, `embedding_text` y el texto
   de `catalog_columns(field_name, display_name, description)`.
2. Usar configuración PostgreSQL `spanish` sobre `concat_ws`, que conserva el
   tratamiento vigente de nulos y aplica stemming en español. Conservar
   normalización de la consulta, `ts_rank_cd`, boost
   máximo y sinónimos acotados existentes, sin IDs ni conocimiento golden.
3. Mantenerla en la base mediante un trigger `BEFORE INSERT OR UPDATE` de los
   cinco campos del dataset y tres triggers `AFTER ... REFERENCING ... TABLE`
   a nivel de sentencia para INSERT, UPDATE y DELETE de columnas. Los triggers
   de columnas recalculan cada dataset afectado una sola vez por sentencia.
   Esto cubre ingesta y escrituras fuera de la aplicación sin el coste de un
   trigger por fila. Una generated column se descarta porque PostgreSQL no
   permite agregar filas de `catalog_columns` en su expresión.
4. Elegir GIN. En el catálogo local real (8.398 filas), la tabla experimental
   reversible midió GIN 0,38 ms frente a GiST 6,17 ms para un término selectivo;
   GiST devolvió 8.398 entradas y descartó 8.321 en recheck. GIN tardó
   146–175 ms en construirse frente a 114–118 ms de GiST y ocupó
   3.056–3.352 KiB frente a 3.104 KiB. Actualizar 100 vectores costó ~2,7 ms
   con ambos. La carga es predominantemente de lectura y la ventaja de
   recuperación de GIN domina el pequeño ahorro de construcción de GiST.
5. En términos amplios (14–19 % del catálogo), PostgreSQL puede elegir un
   scan del `tsvector` ya almacenado (12–22 ms). Es correcto: desaparece el
   recálculo `to_tsvector` de ~545 ms; para términos selectivos el plan usa
   `Bitmap Index Scan` sobre GIN.
6. Backfill idempotente en una sola sentencia sobre el catálogo existente
   (~3,2 s medidos), sin tocar embeddings. Rollback: retirar triggers, función,
   índice y columna; el downgrade de aplicación vuelve al SQL anterior.

## Invariantes y compatibilidad

- El contrato HTTP, `k`, percentiles, muestras, modelo y dimensión no cambian.
- La rama vectorial y `vector_cosine_ops` no cambian.
- El vector materializado contiene los ocho campos acordados. El ranking final
  conserva su fórmula y se valida contra un corpus controlado y la búsqueda
  híbrida real antes de la puerta normativa.
- INSERT/UPDATE de dataset e INSERT/UPDATE/DELETE de columnas mantienen el
  vector dentro de la misma transacción.
- La ingesta existente no necesita una segunda operación de aplicación: sus
  escrituras activan los triggers; reejecutarla conserva idempotencia.
- `columns_preview` y `columns_all` permanecen en R2. Mover enriquecimiento
  después del top-10 queda reservado para T-614R3 solo si aún fuera necesario.

## Enriquecimiento de columnas

Hoy se ejecutan tres agregaciones laterales por ~117 candidatos. R2 comparará
seleccionar top-10 y enriquecer después. `columns_text` no puede salir del
ranking hasta que el vector materializado incluya exactamente su contenido.
`columns_preview` y `columns_all` sí pueden postergarse si pruebas demuestran
orden, filtros, elegibilidad, cobertura y contrato idénticos. Si amplía el
riesgo, se separará como T-614R3.

## Migración, pruebas y puerta

- Migración reversible; prueba de tipo, índice, backfill y mantenimiento ante
  INSERT/UPDATE/DELETE de columnas.
- Ranking idéntico sobre corpus fijo e ingesta idempotente.
- EXPLAIN debe usar el índice lexical y eliminar seq scan/cálculo por fila.
- Medir vector, lexical e híbrido con k=10; k=25 solo comparativo.
- RNF-010 una vez; si pasa, repetir. Puerta: dos corridas p95 <=1000 ms,
  cobertura 100 %, cero errores y sin regresión funcional.

Esta decisión autoriza únicamente la migración lexical mínima de T-614R2. No
autoriza cambios de contratos, golden, modelo de embeddings ni ranking amplio.
