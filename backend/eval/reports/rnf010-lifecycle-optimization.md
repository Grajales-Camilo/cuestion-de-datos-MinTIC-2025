# T-614R1 — Reutilización lifecycle para RNF-010

**Fecha:** 2026-07-16 · **rama:** `feat/deterministic-agent-core`
**Commit de implementación:** `fba0a92` · **Requisitos:** RF-302, RNF-010

## Veredicto

R1 está implementada y validada funcionalmente: cliente Gemini y engine/pool
se crean una vez por worker, se reutilizan y se cierran una vez. La mediana
normativa bajó 264,1 ms, pero RNF-010 continúa en rojo: p95 1293,6 ms. T-614
permanece abierta, T-615 bloqueada y se requiere T-614R2 lexical.

## Estado inicial

Sobre `bb5b8cf`: 100 consultas, cobertura 100 %, p50 1187,6 ms, p95 1659,3
ms, p99 1770,2 ms. La medición anterior de referencia también había obtenido
p95 1828,8 ms, confirmando variabilidad sin cambiar el veredicto.

## Propiedad y lifecycle

Cada proceso/worker FastAPI posee un `CatalogSearchResources` en `app.state`:
un `AsyncEngine` con pool y una instancia `GoogleGenerativeAIEmbeddings`. Se
crean durante `lifespan` cuando la configuración está completa. ASGI sin
lifespan usa inicialización lazy protegida por `asyncio.Lock`. Un fallo parcial
dispone el engine; shutdown cierra recursos en `finally`. Sin credenciales, la
aplicación conserva startup degradado y el endpoint responde 503.

## Threads y event loops

En Windows se instala `WindowsSelectorEventLoopPolicy` antes de iniciar
FastAPI. Endpoint y recursos viven en el mismo Selector loop. Se eliminó para
esta ruta el thread y `asyncio.run` por solicitud, porque compartir el engine
desde loops efímeros sería inseguro. Linux usa igualmente el loop principal.
Cada worker crea recursos propios; no se comparten entre procesos.

## Cambios y pruebas

- `app/main.py`: lifecycle, factory inyectable, lock y ruta directa.
- `tests/test_catalog_search_lifecycle.py`: creación/cierre idempotente,
  limpieza parcial, concurrencia, uso tras cierre, inyección, shutdown vacío y
  fallo de startup.
- `tests/test_catalog_search_endpoint.py`: dependencia falsa explícita.
- script diagnóstico actualizado para medir recursos reutilizados.

Resultados: 18 pruebas unitarias/contrato y 2 de integración pasaron; Ruff
dirigido y `git diff --check` pasaron.

## Comparación antes/después

| Métrica | Antes | Después R1 | Cambio |
|---|---:|---:|---:|
| RNF p50 | 1187,6 ms | 923,5 ms | -264,1 ms (-22,2 %) |
| RNF p95 | 1659,3 ms | 1293,6 ms | -365,7 ms (-22,0 %) |
| RNF p99 | 1770,2 ms | 1696,2 ms | -74,0 ms (-4,2 %) |
| cobertura | 100 % | 100 % | igual |
| errores HTTP | 0 | 0 | igual |

Diagnóstico limitado posterior (10 muestras): embedding reutilizado p50 323,7
ms/p95 426,0 ms; SQL+Python con vector fijo p50 568,3/p95 810,1 ms; ruta
completa p50 833,3/p95 1094,4 ms. EXPLAIN: 498,6 ms; rama lexical ~457,5 ms
y HNSW ~0,7 ms.

## Limitaciones y estado

La prueba normativa ASGI usa el fallback lazy y reutiliza después de la primera
solicitud. No hubo segunda corrida porque la primera falló. No se ejecutaron
suite no integración ni aceptaciones, exigidas solo si RNF pasaba. Quedan por
reducir al menos ~294 ms del p95 observado. T-614R2 debe materializar/indexar
la representación lexical y evaluar después el enriquecimiento top-10. T-614
sigue abierta; T-615 no se inició. No cambiaron contratos, golden, modelo, k,
percentiles, muestras ni cobertura.
