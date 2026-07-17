# T-614R — Diagnóstico de latencia RNF-010

**Fecha:** 2026-07-16 · **commit:** `bb5b8cf` · **rama:** `feat/deterministic-agent-core`
**Requisitos:** RF-302, RNF-010 · **estado:** diagnóstico completo; RNF-010 no resuelto

## Resumen ejecutivo

RNF-010 se reproduce en el entorno normativo: 100 consultas, cobertura 100 %
(8394/8394), p50 1187,6 ms, p95 1659,3 ms y p99 1770,2 ms. La causa es
compuesta. El endpoint crea por solicitud un cliente Gemini, un engine/pool,
un thread y un event loop; crear el cliente duplica aproximadamente la fase
remota. En paralelo, la búsqueda lexical recalcula `to_tsvector` sobre todo
`catalog_datasets` y domina PostgreSQL (~579 de 622 ms). El HNSW sí se usa y
tarda ~1 ms; T-614 `per_query=25` no participa porque RNF-010 llama `k=10` y
`search_catalog` fija 300 candidatos tanto para k=10 como para k=25.

## Estado y entorno

- Docker `pgvector/pgvector:0.8.0-pg16`, sano, puerto host 5433.
- Base efectiva: `localhost:5433/cuestion_de_datos` (sin registrar credenciales).
- `gemini-embedding-2`, 768 dimensiones; `CATALOG_STALE_AFTER_DAYS=8`.
- Worktree inicial contenía archivos no rastreados ajenos, incluidos
  `backend/uv.lock`; fueron preservados y no se incluyen en esta investigación.
- MCP fue reindexado en modo fast: 2773 nodos/10253 aristas. Excluyó por diseño
  migraciones, scripts, integración, reportes y `app/tools`; por ello esos
  artefactos se verificaron en archivos reales. Sus líneas de símbolos de
  `search.py` y `main.py` coincidieron con el worktree.

## Configuración y reproducción

La prueba usa ASGITransport, 100 consultas secuenciales únicas generadas desde
categorías y departamentos reales y `k=10`. Mide correctamente la experiencia
completa (HTTP interno + embedding externo + PostgreSQL), aunque no expone
componentes. No hay concurrencia ni pipelining.

| Métrica | Resultado | Norma |
|---|---:|---:|
| p50 | 1187,6 ms | informativa |
| p95 | 1659,3 ms | <= 1000 ms |
| p99 | 1770,2 ms | informativa |
| cobertura | 100,00 % | >= 90 % |
| errores HTTP | 0/100 | — |

## Arquitectura real

`GET /v2/catalog/search` -> `catalog_search_with_platform_loop` -> en Windows
`asyncio.to_thread` -> `asyncio.run(SelectorEventLoop)` ->
`_catalog_search_async` -> cliente `GoogleGenerativeAIEmbeddings` nuevo +
engine SQLAlchemy nuevo -> `search_catalog` -> embedding remoto -> una consulta
híbrida SQL -> construcción Pydantic de respuesta. El endpoint no usa el
runtime determinista ni `multiquery_retrieval`.

## Descomposición y experimentos

Experimento controlado, 10 muestras por variante, consulta repetida; valores ms:

| Componente/variante | p50 | p95 | media |
|---|---:|---:|---:|
| embedding, cliente reutilizado | 341,1 | 438,0 | 338,1 |
| embedding, cliente nuevo | 672,5 | 1157,3 | 707,9 |
| vector fijo + engine reutilizado (SQL+Python) | 654,0 | 857,3 | 688,0 |
| ruta directa completa, cliente+engine nuevos | 1110,7 | 1443,1 | 1158,6 |
| puente Windows completo | 989,1 | 1447,2 | 1102,8 |

El puente no mostró penalización consistente: su p95 difiere ~4 ms de la ruta
directa en 10 muestras. La primera llamada de calentamiento no se mezcló con
las diez muestras; aun calientes, cliente nuevo y SQL siguen dominando. Una
segunda corrida corta (3 muestras) confirmó SQL p50 546 ms y `EXPLAIN`
622,4 ms. Las consultas repetidas no eliminan el coste, por lo que una caché
no es condición necesaria para explicar ni resolver el defecto.

Distribución aproximada sobre la mediana normativa: embedding con cliente
nuevo ~55-60 %, SQL híbrido ~45-55 %; se solapan variabilidad y overhead de
creación, por lo que no deben sumarse como percentiles independientes. La
normalización, validación, reranking Python, respuesta y puente quedan en el
residuo, menor frente a esas dos fases. Esto explica más del 90 % de la mediana.

## Auditoría SQL y pgvector

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, k=10, consulta representativa:

- planificación 1,156 ms; ejecución 622,427 ms;
- HNSW `ix_catalog_embeddings_embedding_hnsw` con `vector_cosine_ops`: usado,
  ~0,919 ms, 40 filas observadas (el filtro/join impide alcanzar siempre 300);
- búsqueda lexical: `Parallel Seq Scan catalog_datasets` + cálculo repetido de
  `to_tsvector(concat_ws(...))`, ~573,6 ms por worker y ~579 ms hasta top 100;
- join posterior hace un `Seq Scan` de 8394 embeddings (~1 ms), secundario;
- 119 candidatos ejecutan tres agregaciones laterales sobre
  `catalog_columns` (preview, todas, texto), cada una indexada. Son 357
  subconsultas correlacionadas: patrón N+1 dentro de una sola sentencia,
  contribuyente (~33 ms hasta el nested loop), no causa principal;
- el sort/fusión final trabaja sobre 119 candidatos, no sobre toda la tabla.

Clasificación SQL: **causa principal compartida**, específicamente la rama
lexical sin índice materializado. La recuperación vectorial es adecuada. El
enriquecimiento lateral es mejorable y secundario. k=25 conserva
`candidate_limit=max(300,k*20)=500`, mientras k=10 usa 300; esto puede aumentar
trabajo del runtime determinista, pero no causa esta medición k=10.

## Hipótesis

| Hipótesis | Evidencia a favor / en contra | Impacto | Veredicto |
|---|---|---:|---|
| H1 Gemini domina | cliente nuevo p50 672 ms | alto | confirmada, causa compartida |
| H2 cliente recreado | código y diferencia 672 vs 341 ms | ~331 ms p50 | confirmada |
| H3 puente Windows | p95 1447 vs 1443 ms | despreciable medido | descartada |
| H4 engine/pool por solicitud | creado/dispuesto por request; SQL con engine caliente sigue alto | secundario no aislado completamente | contribuyente |
| H5 pgvector no usa índice | EXPLAIN usa HNSW ~1 ms | nulo | descartada |
| H6 varias rutas secuenciales | embedding y SQL son secuenciales; SQL combina vector+lexical | alto | confirmada |
| H7 N+1 | 3 laterales x 119 candidatos, todas indexadas | ~33 ms | contribuyente |
| H8 Python/serialización | residuo pequeño frente a embedding+EXPLAIN | bajo | descartada como principal |
| H9 frío contamina | fallo persiste en muestras calientes | variable | contribuyente, no causal principal |
| H10 variabilidad proveedor | cliente nuevo p95 1157 vs min 355 | alta dispersión | confirmada |
| H11 benchmark no descompone | solo cronometra endpoint | diagnóstico ciego | confirmada metodológica |
| H12 tráfico distinto | secuencial ASGI, conservador; endpoint real idéntico | no invalida norma | contribuyente metodológica |

## Propuestas priorizadas (no implementadas)

1. **Reutilizar por lifecycle el cliente de embeddings y el engine/pool.**
   Cambiaría `app/main.py` y lifecycle/config; reducción observada del cliente
   ~331 ms p50, además elimina negociación/transporte y churn de pool. Riesgo
   bajo-medio (loops en Windows, cierre ordenado); reversible. Probar lifecycle,
   concurrencia, shutdown y RNF-010 completo. No cambia contratos/modelo.
2. **Indexar la representación lexical y reescribir la rama textual para usarla.**
   Cambiaría migración/modelo/search e ingesta; potencial ~500-570 ms por
   solicitud según EXPLAIN. Requiere decisión SDD y migración reversible sobre
   cómo mantener un `tsvector` materializado/GiST o GIN. Probar plan real,
   relevancia/cobertura e ingesta idempotente. No crear el índice en diagnóstico.
3. **Eliminar agregaciones laterales redundantes antes del top-k.** Recuperar
   columnas solo para los 10 finales o agregarlas una vez; potencial observado
   ~20-40 ms. Cambiaría `search.py`; riesgo medio por ranking lexical que hoy usa
   texto de columnas. Probar orden, contrato y ausencia de N+1.

No se recomienda elevar umbral, reducir muestras, omitir Gemini, cambiar modelo,
degradar cobertura ni introducir caché. Una caché exigiría antes semántica de
invalidación, privacidad, cardinalidad y consultas nuevas.

## Comandos, pruebas y limitaciones

- `docker compose ps`; inspección de configuración sin secretos.
- `uv run pytest -q tests/test_catalog_search_benchmark.py`: 8 passed.
- `uv run pytest -q tests/test_catalog_search_endpoint.py`: 3 passed.
- integración inicial sin `DATABASE_URL`: 2 errores de entorno; relanzada
  exportando desde Settings sin imprimirla: 2 passed.
- RNF-010 aislada: 1 failed por p95 1659,3 ms; cobertura pasa.
- `uv run python scripts/diagnose_catalog_search_latency.py --samples 10` y
  `--samples 3`: completados.
- No se ejecutó suite completa ni se midió carga concurrente; no eran necesarias
  para la puerta diagnóstica. Los percentiles de 10 muestras son diagnósticos,
  no sustituyen los 100 normativos.

## Estado y siguiente tarea

T-614 continúa abierta y T-615 no se inicia. No se modificaron contratos,
`golden-v1`, runtime, proveedor/modelo ni comportamiento productivo. Siguiente
tarea exacta: implementar en un incremento separado la reutilización lifecycle
del cliente Gemini y engine/pool, medir otra vez los componentes y RNF-010; si
el p95 sigue >1000 ms, abrir la migración SDD del índice lexical materializado.
