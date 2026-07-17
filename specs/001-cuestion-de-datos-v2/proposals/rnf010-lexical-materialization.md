# Propuesta PENDIENTE — T-614R2 materialización lexical RNF-010

**Estado:** PENDIENTE de aprobación SDD · **Requisitos:** RF-302, RNF-010

## Problema y presupuesto

R1 redujo RNF-010 a p50 923,5 ms/p95 1293,6 ms, pero la rama lexical consume
~457 ms en un `Parallel Seq Scan` que recalcula `to_tsvector`. R2 debe recuperar
al menos 300 ms de p95 sin cambiar ranking, cobertura, modelo o contrato.

## Diseño por validar

1. Añadir a `catalog_datasets` un `tsvector` mantenido e indexado con exactamente
   `name`, `publisher`, `category`, `description`, `embedding_text` y el texto
   de `catalog_columns(field_name, display_name, description)`.
2. Usar configuración `spanish`; conservar normalización, `ts_rank_cd`, boost
   máximo y sinónimos acotados existentes, sin IDs ni conocimiento golden.
3. Candidato inicial: columna normal actualizada por la ingesta en la misma
   transacción. Una generated column no agrega filas de `catalog_columns`; un
   trigger cruzado agrega complejidad. Ambos mecanismos deben medirse.
4. Comparar GIN y GiST con datos reales. GIN parte como candidato por lectura
   de términos; GiST solo si tamaño/escritura/latencia lo justifican. No son
   equivalentes.
5. Backfill idempotente de datasets existentes, lotes acotados y sin borrar
   embeddings. Rollback: retirar índice y columna/trigger y volver al SQL actual.

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

Esta propuesta no autoriza todavía la migración. Mantenimiento y GIN/GiST se
cierran con planes y tiempos reales antes del código.
