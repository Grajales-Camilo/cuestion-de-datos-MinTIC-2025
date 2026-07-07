# Plan de Implementación — Cuestión de Datos v2.0

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Implementa:** [`spec.md`](./spec.md) bajo las reglas de [`constitution.md`](../constitution.md)

> Este documento define **CÓMO** se construye lo especificado. Decisiones ya tomadas con el responsable del proyecto: backend **Python (FastAPI + LangGraph)**, vectores en **PostgreSQL + pgvector**, LLM **Gemini por defecto con capa multi-proveedor**.

---

## 1. Arquitectura general

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│  FRONTEND (Vercel)          │  SSE/  │  BACKEND AGENTE (Railway/Render) │
│  Next.js 14 + Tailwind      │  REST  │  FastAPI + LangGraph (Python 3.12)│
│  · Policy Canvas (Tiptap)   │───────▶│  · Grafo del agente (ReAct)      │
│  · Copiloto (pasos en vivo) │◀───────│  · Herramientas (tools)          │
│  · Panel de trazabilidad    │        │  · Capa validación de calidad    │
└─────────────────────────────┘        │  · Capa multi-proveedor LLM      │
                                       └───────┬──────────────┬───────────┘
                                               │              │
                              ┌────────────────▼───┐   ┌──────▼─────────────┐
                              │ PostgreSQL+pgvector│   │ APIs externas      │
                              │ dev: Docker local  │   │ · datos.gov.co     │
                              │ prod: gestionado   │   │                    │
                              │ · catálogo+embeds  │   │   (SODA + Discovery)│
                              │ · trazas agente    │   │ · Gemini API       │
                              │ · corridas eval    │   │ · (Claude/otros)   │
                              └────────▲───────────┘   └────────────────────┘
                                       │
                              ┌────────┴───────────┐
                              │ INGESTA (cron/CLI) │
                              │ scripts/ingest_*   │
                              └────────────────────┘
```

**Decisión clave:** el bucle ReAct manual de v1.0 (`pages/api/consultar_v2.js`) se reemplaza por un grafo LangGraph en un servicio Python independiente. El frontend Next.js se conserva y evoluciona. **El navegador se conecta DIRECTAMENTE al backend** (`NEXT_PUBLIC_BACKEND_URL`), sin proxy en Next.js: FastAPI expone CORS restringido al dominio del frontend, y el SSE se consume con `fetch()` + stream de lectura (nunca `EventSource` nativo, que no admite el encabezado `Authorization`). Un proxy serverless introduce límites de duración, posible buffering y comportamiento dependiente del runtime/plan, inadecuado para un SSE durable con corridas de hasta 75 s (RNF-008, RF-209) — decisión registrada en research.md §6.

### Grafo del agente (LangGraph)

```
entrada ─▶ planificador ─▶ enrutador ─┬─▶ buscar_catalogo ──┐
                             ▲        ├─▶ perfilar_dataset ─┤
                             │        ├─▶ resolver_geografia┤ (observación
                             │        ├─▶ explorar_valores ─┤  vuelve al
                             │        └─▶ ejecutar_soql ────┘  enrutador)
                             │
                    (máx. 10 pasos, RF-201)
                             │
                             ▼
        validador_calidad ─▶ constructor_afirmaciones ─▶ sintetizador ─▶ respuesta + trazas
```

- **planificador:** descompone la pregunta (RF-202) y decide la primera acción.
- **enrutador (LLM):** nodo de decisión con *structured output*; elige herramienta o terminar.
- **validador_calidad:** nodo determinista (sin LLM) que aplica `contracts/validacion-calidad.md` (RF-401).
- **constructor_afirmaciones:** nodo determinista (sin LLM) que materializa las **afirmaciones cuantitativas** (claims, RF-208): calcula toda cifra derivada (porcentajes, sumas, promedios) con la herramienta T7 de `contracts/agent-tools.md` y las registra en `quantitative_claims`.
- **sintetizador:** redacta la respuesta final y la narrativa citable usando EXCLUSIVAMENTE los `display_value` de claims validados y evidencia cualitativa trazable; NO PUEDE calcular ni introducir cifras propias (RNF-003, RF-208).
- Cada transición emite un evento SSE (RF-204) con número de secuencia persistente y se persiste como `agent_step` + `agent_run_events` (RF-703, RF-209).
- El grafo usa el **checkpointer PostgreSQL de LangGraph**: el estado de la corrida sobrevive a reinicios del proceso (§11).

## 2. Stack y dependencias

### Backend (`backend/`)
| Componente | Elección | Justificación |
|---|---|---|
| Lenguaje | Python 3.12 | Ecosistema de agentes/embeddings; alineado con la maestría y los libros guía. |
| API | FastAPI + Uvicorn | Estándar de la industria, tipado con Pydantic, SSE nativo. |
| Orquestación | LangGraph (+ LangChain Core) | Grafo de estados con checkpoints; patrón recomendado por los libros guía. |
| Capa LLM | `langchain-google-genai` (default) + `langchain-anthropic` (comparativa OE3) | RF-206: intercambio por configuración `LLM_PROVIDER`/`LLM_MODEL`. |
| Embeddings | **DECISIÓN PENDIENTE** (ver [`research.md`](./research.md) §1). Candidatos: `intfloat/multilingual-e5-large` (local), `gemini-embedding-2` (gestionado) u otro modelo multilingüe actual justificado en research.md | La selección DEBE salir del benchmark reproducible de T-205; ningún candidato es ganador todavía. La dimensión vectorial y la migración definitiva dependen de esta decisión (T-104B). |
| Validación datos | Pydantic + módulo propio `quality/` | La capa de calidad es lógica determinista propia (Art. I.4); no requiere framework pesado. |
| HTTP externo | `httpx` (async, timeouts, retries) | Consultas Socrata concurrentes. |
| Pruebas | pytest + pytest-asyncio + respx (mocks HTTP) | Ver `pruebas.md`. |
| Lint/formato | ruff | Un solo binario para lint+format. |

### Frontend (`frontend/` — evolución del código actual)
| Componente | Elección | Justificación |
|---|---|---|
| Framework | Next.js 14 (Pages Router, el actual) | No migrar a App Router en v2.0: costo sin beneficio para el alcance (Art. III). |
| Estilos | Tailwind CSS + tokens de diseño (§7) | Ya presente en v1.0. |
| Editor | Tiptap (actual) | Se conserva; se añade extensión de "cita de evidencia" (RF-103). |
| Streaming | `fetch()` con stream de lectura (SSE), directo al backend con CORS | Pasos del agente en vivo (RF-204); permite header `Authorization` y reconexión `Last-Event-ID`. NO usar `EventSource` nativo. |
| Gráficas | Chart.js (ya instalada) | RF-503 sin dependencias nuevas. |
| Pruebas | Playwright (E2E mínimo) | RNF-007, RNF-008. |

### Base de datos
- **PostgreSQL 15+ con `pgvector`**, en dos modalidades (Constitución Art. II.2):
  - **Desarrollo local:** contenedor Docker definido en `compose.yaml` (raíz del repo, tarea T-105): PostgreSQL + pgvector, volumen persistente, healthcheck y variables por `.env`. `DATABASE_URL=postgresql://usuario:clave@localhost:5432/cuestion_de_datos`.
  - **Despliegue:** servicio gestionado compatible (Supabase, Neon u otro; tier gratuito suficiente para el piloto). `DATABASE_URL=postgresql://usuario:clave@host-remoto:5432/base`.
- Esquema completo en [`data-model.md`](./data-model.md). Migraciones con **Alembic**. La migración definitiva de `catalog_embeddings` se crea DESPUÉS del benchmark de embeddings (orden T-104A → T-205 → T-104B, ver tasks.md).
- Índice vectorial HNSW sobre `catalog_embeddings.embedding` (RNF-010: búsqueda ≤ 1 s p95), creado en T-104B con la dimensión seleccionada.

### Plataformas externas
| Servicio | Uso | Plan |
|---|---|---|
| datos.gov.co (SODA 2.1 + Discovery API `api.us.socrata.com/api/catalog/v1`) | Datos y metadatos | Gratuito con App Token |
| Google AI Studio (Gemini) | LLM por defecto + embeddings alternativos | Tier gratuito → pago según uso |
| Anthropic API (Claude) | Configuración comparativa OE3 | Pago por uso (solo evaluación) |
| Supabase o Neon | PostgreSQL + pgvector — SOLO despliegue; el desarrollo local usa `compose.yaml` | Tier gratuito |
| Vercel | Frontend | Tier gratuito (actual) |
| Railway o Render | Backend FastAPI | Tier básico (~USD 5/mes) |
| GitHub Actions | CI + cron de ingesta semanal (RF-701) | Gratuito |
| UptimeRobot (u similar) | Monitor RNF-006 | Gratuito |

## 3. Estructura del repositorio (objetivo)

Adaptada de `Sugerencia_EstructuraRepositorio_Avanzado.txt` a la realidad del proyecto (dos servicios + specs). Se toma lo útil (docs/, tests/, notebooks/, CI) y se descarta lo sobredimensionado (Kubernetes, Spark, serverless múltiple — Art. III).

```
cuestion-de-datos/
├── specs/                        # ← este paquete SDD (fuente de verdad)
├── frontend/                     # Next.js (migrado desde la raíz actual)
│   ├── components/  pages/  styles/  public/  data/
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI, rutas, SSE
│   │   ├── agent/                # grafo LangGraph, nodos, prompts
│   │   ├── tools/                # buscar_catalogo, ejecutar_soql, etc.
│   │   ├── quality/              # capa de validación (4 dimensiones)
│   │   ├── llm/                  # capa multi-proveedor
│   │   ├── db/                   # modelos SQLAlchemy + repositorios
│   │   └── config.py             # settings Pydantic (env vars)
│   ├── scripts/
│   │   ├── ingest_catalog.py     # ingesta Discovery API → Postgres
│   │   └── build_embeddings.py   # embeddings de metadatos
│   ├── eval/                     # batería OE3: golden set + runner + reportes
│   ├── migrations/               # Alembic
│   ├── tests/                    # unit / integration / eval smoke
│   ├── pyproject.toml
│   └── .env.example
├── docs/                         # documentación pública (arquitectura, working paper)
├── notebooks/                    # análisis exploratorio del catálogo y resultados eval
├── .github/workflows/
│   ├── ci.yml                    # lint + tests + auditoría accesibilidad
│   └── ingest-cron.yml           # ingesta semanal del catálogo
├── README.md   LICENSE   CHANGELOG.md
```

> **Nota de migración:** el código v1.0 vive hoy en la raíz. La tarea T-101 (tasks.md) mueve el frontend a `frontend/` sin cambios funcionales antes de empezar el backend, para que la estructura quede limpia desde el inicio.

## 4. Contratos e interfaces

- **REST + SSE entre frontend y backend:** [`contracts/api-rest.md`](./contracts/api-rest.md)
- **Herramientas del agente (entradas/salidas JSON):** [`contracts/agent-tools.md`](./contracts/agent-tools.md)
- **Validación de calidad (dimensiones, puntaje, umbrales):** [`contracts/validacion-calidad.md`](./contracts/validacion-calidad.md)

## 5. Pipeline de ingesta del catálogo (RF-301…RF-304)

1. **Descubrimiento:** paginar la Discovery API de Socrata filtrando dominio `www.datos.gov.co`, tipo `dataset`.
2. **Filtrado:** conservar datasets tabulares con API activa; descartar mapas/archivos sin API (quedan fuera del alcance RNF-010).
3. **Normalización:** limpiar HTML de descripciones, truncar a 2.000 caracteres, extraer columnas (nombre, tipo, descripción), entidad, categoría, `rowsUpdatedAt`.
4. **Texto de embedding por dataset:** `título + descripción + entidad + categoría + nombres de columnas` (estrategia de compensación de metadatos pobres: si la descripción < 100 caracteres, se pesa más el título y las columnas).
5. **Embeddings por lotes** → upsert en `catalog_datasets` + `catalog_embeddings` (idempotencia por `dataset_id`, RF-304).
6. **Reporte:** filas nuevas/actualizadas/fallidas → tabla `ingest_runs` (RF-701).
7. **Programación:** GitHub Actions cron semanal + ejecución manual por CLI.
8. **Ventana de obsolescencia (RF-303):** un dataset cuyo `metadata_synced_at` sea más antiguo que `CATALOG_STALE_AFTER_DAYS` (default 8 días = ingesta semanal + 1 de margen) se marca `index_stale = true` en las respuestas de búsqueda (`/v2/catalog/search`) y se lista en `/v2/admin/metrics`.

## 6. Rendimiento y presupuesto de latencia (RNF-001)

| Fase | Presupuesto p95 |
|---|---|
| Búsqueda semántica (pgvector HNSW) | ≤ 1 s |
| Llamada LLM por paso (Gemini Flash) | ≤ 6 s |
| Consulta Socrata | ≤ 5 s (timeout 10 s, 1 reintento) |
| Validación de calidad | ≤ 500 ms (determinista) |
| Investigación completa (≤ 10 pasos, típica 4–6) | ≤ 75 s |

Mitigaciones: consultas Socrata paralelas cuando el plan lo permita; `LIMIT` obligatorio (máx. 1.000 filas por consulta); streaming SSE para percepción de progreso (RNF-008).

## 7. Diseño visual (Constitución Art. V)

**Tokens de color (Tailwind):** paleta única de azules + neutros fríos.

| Token | Hex | Uso |
|---|---|---|
| `blue-900` | `#0C2D57` | Titulares, navegación, botón primario hover |
| `blue-700` | `#1D4E89` | Botones primarios, enlaces |
| `blue-500` | `#2E7CD6` | Acentos, foco, elementos activos del agente |
| `blue-100` | `#DBEAFE` | Fondos de tarjetas de evidencia, chips |
| `blue-50`  | `#EFF6FF` | Fondos de sección |
| `slate-900/600/400` | — | Texto principal / secundario / deshabilitado |
| `white` | `#FFFFFF` | Fondo base |
| Semánticos | éxito `#15803D`, advertencia `#B45309`, error `#B91C1C` | SOLO estados de validación/errores |

**Reglas:** tipografía única sans-serif (Inter o similar del sistema); máximo 2 pesos por pantalla; espaciado en escala 4/8; sin sombras duras ni degradados; iconografía de una sola familia (Lucide). Layout de 3 zonas: navegación mínima superior, lienzo central, copiloto lateral colapsable. Todo estado del agente visible con texto, no solo spinner (RNF-008).

## 8. Fases de implementación (resumen — detalle en tasks.md)

| Fase | Contenido | Resultado verificable |
|---|---|---|
| 0 | Cuentas, claves, base de datos, esqueleto de repos | `quickstart.md` ejecutable hasta "hola mundo" de ambos servicios |
| 1 | Reorganización del repo + migración frontend | v1.0 funcionando igual desde `frontend/` |
| 2 | Ingesta del catálogo + índice semántico | Búsqueda semántica ≥ 90% del catálogo tabular (RNF-010) |
| 3 | Grafo del agente + herramientas + capa LLM | ESC-01/02/03 pasan manualmente |
| 4 | Capa de validación de calidad | Contrato de validación cumplido con pruebas |
| 5 | Frontend v2: SSE, panel de trazabilidad, rediseño azul | ESC-04/05 + RNF-007/008 |
| 6 | Batería de evaluación OE3 + golden set | Reporte comparativo entre ≥ 2 modelos |
| 7 | Endurecimiento, CI/CD, despliegue, documentación | Todos los RNF verificados; v2.0 en producción |

## 9. Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Metadatos pobres en el catálogo degradan la recuperación | Alta | Alto | Estrategia de texto de embedding ponderado (§5.4); perfilado de dataset como herramienta del agente; medición temprana con golden set (Fase 2). |
| Límites de tarifa del tier gratuito de Gemini | Media | Medio | Capa multi-proveedor (RF-206); caché de respuestas de catálogo; presupuesto de pasos. |
| Cambios en la API de Socrata/Discovery | Baja | Alto | Adaptador aislado en `tools/`; pruebas de integración marcadas que detectan drift. |
| Latencia total > 75 s en preguntas complejas | Media | Medio | Paralelización de consultas, límites de filas, streaming de progreso. |
| Costo de servicio backend excede presupuesto personal | Media | Bajo | Railway/Render tier básico; escalado a cero fuera de horas si el proveedor lo permite. |
| Embeddings locales (e5-large) demasiado pesados para el server barato | Media | Medio | El benchmark de T-205 incluye capacidad de ejecución local y latencia como criterios; si un modelo local resulta inviable, un modelo gestionado (p. ej. `gemini-embedding-2`) puede seleccionarse justificadamente en `research.md`. |

## 10. Criterios de cierre de v2.0

v2.0 se declara terminada cuando: (1) todos los RF de spec.md están implementados o formalmente diferidos con enmienda; (2) todos los RNF medidos cumplen su umbral; (3) la batería OE3 corre en CI y produce el reporte comparativo; (4) el despliegue productivo en cuestiondedatos.com sirve la nueva versión; (5) el registro en el directorio de herramientas del MinTIC puede actualizarse con la documentación de los nuevos componentes.

## 11. Durabilidad, acceso y recuperación de corridas (RF-209, RF-801…804)

*Arquitectura mínima para el piloto — sin Celery, Redis ni colas externas (Art. III). Decisión registrada en [`research.md`](./research.md) §2–4.*

**Durabilidad (un solo worker):**
- El backend corre como **un único worker** durante el piloto; las corridas se ejecutan como tareas asíncronas dentro del proceso, pero TODO estado relevante vive en PostgreSQL, nunca solo en memoria.
- **Estado de corrida** en `agent_runs.status` (+ `heartbeat_at` actualizado periódicamente por la corrida activa).
- **Checkpoints de LangGraph** persistidos en PostgreSQL (checkpointer oficial): se usan para inspección y diagnóstico del estado de una corrida. En el piloto NO existe reanudación automática del trabajo del agente.
- **Eventos numerados:** cada evento SSE se persiste en `agent_run_events` con secuencia monotónica por corrida ANTES de emitirse. Los eventos terminales (`answer`/`error`) se conservan siempre.
- **Reconexión SSE:** el cliente reanuda enviando el encabezado estándar `Last-Event-ID` con el último `seq` recibido; el servidor reenvía los eventos persistidos con `seq` mayor y continúa en vivo. Sin pérdida ni duplicación (prueba de integración en pruebas.md §2.3). El token de acceso viaja SIEMPRE por encabezado `Authorization`, nunca en la URL.
- **Corridas huérfanas:** un barrido periódico detecta corridas `running` con `heartbeat_at` vencido (> `RUN_HEARTBEAT_TIMEOUT`, default 120 s) o duración > `RUN_MAX_DURATION` (default 10 min) y las transiciona a `interrupted` o `failed`, emitiendo el evento terminal correspondiente.
- **Semántica única de recuperación (sin ambigüedad):**
  1. La desconexión del navegador NO interrumpe la ejecución: la corrida continúa en el servidor.
  2. Los eventos ya emitidos se recuperan siempre con `Last-Event-ID`.
  3. Un reinicio del proceso SÍ interrumpe la corrida activa: al arrancar, el backend marca `interrupted` (estado TERMINAL) toda corrida `running` sin heartbeat vigente y persiste el evento terminal `RUN_INTERRUPTED`.
  4. Los eventos y resultados parciales de una corrida `interrupted` permanecen disponibles vía `GET /v2/agent/runs/{run_id}`.
  5. No hay reanudación automática: el usuario simplemente vuelve a ejecutar la consulta (una investigación cuesta centavos y < 75 s; reanudar un grafo a mitad de camino no justifica su complejidad en el piloto).
- **Idempotencia:** todas las herramientas del agente son de solo lectura; repetir un paso tras recuperación es seguro por diseño (contracts/agent-tools.md, reglas comunes).

**Acceso a corridas (RF-801):**
- Al crear la corrida se genera un `run_access_token` aleatorio (≥ 256 bits), se entrega UNA vez en la respuesta `202` y se almacena solo su hash (SHA-256). **El token vive exactamente lo que viven los datos:** su expiración es igual a la retención de la clase `user` (`RUN_TOKEN_TTL_DAYS = RETENTION_USER_DAYS`, default 90 días) y al vencer la retención la corrida se elimina (data-model.md §7). Sin cuentas de usuario no existe mecanismo seguro de renovación, así que no se ofrece.
- Toda lectura, streaming, reanudación o borrado exige `Authorization: Bearer <run_access_token>`; la comparación de hashes es en tiempo constante. El `run_id` solo identifica, no autoriza.
- Como `EventSource` nativo no admite encabezados, el frontend consume SSE mediante **fetch con stream de lectura** (patrón estándar), enviando el header. Los tokens NUNCA van en URLs ni en logs.
- **CORS:** FastAPI (`CORSMiddleware`) con orígenes tomados de la variable `CORS_ALLOWED_ORIGINS` (lista separada por comas). Valores base: producción (`https://cuestiondedatos.com`, `https://www.cuestiondedatos.com`) y desarrollo (`http://localhost:3000`). **Previews de Vercel:** se añade temporalmente el origen EXACTO del preview a la variable durante las pruebas; PROHIBIDO el comodín `*.vercel.app` o `*`. Métodos permitidos: `GET, POST, DELETE`; encabezados permitidos: `Authorization`, `Content-Type`, `Last-Event-ID`. La conexión navegador→backend es directa; no hay proxy en Next.js.

**Consentimiento y borrado (RF-802/803):** la UI informa antes de la primera investigación qué se almacena (pregunta, contexto acotado, trazas), con qué fin (funcionamiento y evaluación técnica), por cuánto tiempo (según `retention_class`, data-model.md §7) y cómo borrarlo (`DELETE /v2/agent/runs/{run_id}`).
