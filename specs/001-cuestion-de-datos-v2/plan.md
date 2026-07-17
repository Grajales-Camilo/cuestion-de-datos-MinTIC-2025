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
                    (máx. 14 pasos por defecto, RF-201, research.md §19)
                             │
                             ▼
        validador_calidad ─▶ planificador_claims ─▶ constructor_afirmaciones
                                                     │
                                                     ▼
                                              sintetizador ─▶ respuesta + trazas
```

- **planificador:** descompone la pregunta (RF-202) y decide la primera acción.
- **enrutador (LLM):** nodo de decisión con *structured output*; elige herramienta o terminar.
- **validador_calidad:** nodo determinista (sin LLM) que aplica `contracts/validacion-calidad.md` (RF-401).
- **planificador_claims (LLM):** nodo especializado que propone filas,
  columnas, unidades y la DSL T7 después de existir evidencia validada. Para
  conservar operaciones anidadas sin exponer un JSON Schema recursivo que el
  proveedor no puede convertir, transporta la fórmula como JSON textual y el
  backend la parsea y valida recursivamente antes de T7.
- **constructor_afirmaciones:** nodo determinista (sin LLM) que materializa las **afirmaciones cuantitativas** (claims, RF-208): calcula toda cifra derivada (porcentajes, sumas, promedios) con la herramienta T7 de `contracts/agent-tools.md` y las registra en `quantitative_claims`.
- **sintetizador:** redacta la respuesta final y la narrativa citable usando EXCLUSIVAMENTE los `display_value` de claims validados y evidencia cualitativa trazable; NO PUEDE calcular ni introducir cifras propias (RNF-003, RF-208).
- Cada transición emite un evento SSE (RF-204) con número de secuencia persistente y se persiste como `agent_step` + `agent_run_events` (RF-703, RF-209).
- El grafo usa el **checkpointer PostgreSQL de LangGraph** solo para inspección y diagnóstico: ante reinicio del proceso, la corrida activa termina como `interrupted`; no hay reanudación automática del grafo (§11).

## 2. Stack y dependencias

### Backend (`backend/`)
| Componente | Elección | Justificación |
|---|---|---|
| Lenguaje | Python 3.12 | Ecosistema de agentes/embeddings; alineado con la maestría y los libros guía. |
| API | FastAPI + Uvicorn | Estándar de la industria, tipado con Pydantic, SSE nativo. |
| Orquestación | LangGraph (+ LangChain Core) + `langgraph-checkpoint-postgres` | Grafo de estados con checkpoints PostgreSQL; `thread_id = run_id`, `.setup()` idempotente y borrado con `adelete_thread(run_id)` (research.md §10). |
| Capa LLM | `langchain-google-genai` (default) + `langchain-anthropic` (comparativa OE3) | RF-206: intercambio por configuración `LLM_PROVIDER`/`LLM_MODEL`. |
| Embeddings | `gemini-embedding-2` (Google, gestionado), 768 dimensiones — decidido en T-205 (ver [`research.md`](./research.md) §1, 2026-07-09) | Empata en recall@10 con el candidato local (94,12%/90,91%) pero gana en latencia real (p95 41,8ms vs 120,2ms) y evita el costo de infraestructura del local: su pico de RAM medido (2,43 GB) excede el tier gratuito de Railway y consumiría de forma permanente parte del tier Hobby presupuestado. `langchain-google-genai` y `httpx` ya son dependencias de runtime (RF-206); no se agrega ninguna dependencia nueva. `sentence-transformers`/`torch` quedan solo en el extra opcional `benchmark-embeddings`, para reproducir el benchmark si hace falta reabrir la decisión. |
| Validación datos | Pydantic + módulo propio `quality/` | La capa de calidad es lógica determinista propia (Art. I.4); no requiere framework pesado. |
| HTTP externo | `httpx` (async, timeouts, retries) | Consultas Socrata concurrentes. |
| Persistencia | SQLAlchemy async + `psycopg[binary,pool]` | Una sola estrategia asíncrona para FastAPI, repositorios y jobs; evita mezclar drivers. |
| Pruebas | pytest + pytest-asyncio + respx (mocks HTTP) | Ver `pruebas.md`. `pytest -m "not integration"` ejecuta pruebas deterministas sin red; `pytest -m integration` ejecuta las pruebas con PostgreSQL/Socrata reales. |
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
  - **Desarrollo local:** contenedor Docker definido en `compose.yaml` (raíz del repo, tarea T-105): PostgreSQL + pgvector, volumen persistente, healthcheck y variables por `.env`. La imagen debe fijarse con tag completo o digest, no `latest` ni un alias flotante. Las extensiones `vector` y `pg_trgm` se crean mediante script `init` del contenedor local; no por comando manual ni por Alembic. `DATABASE_URL=postgresql://usuario:clave@localhost:5432/cuestion_de_datos`.
  - **CI:** el job backend de GitHub Actions usa un servicio PostgreSQL+pgvector equivalente al local cuando ejecute pruebas de contrato o integración con DB. Exporta un `DATABASE_URL` de CI y valida extensiones antes de correr migraciones/pruebas. Las pruebas unitarias puras no necesitan el servicio.
  - **Despliegue:** servicio gestionado compatible (Supabase, Neon u otro; tier gratuito suficiente para el piloto). `DATABASE_URL=postgresql://usuario:clave@host-remoto:5432/base`.
- Esquema completo en [`data-model.md`](./data-model.md). Migraciones con **Alembic**. La base local se crea y levanta en T-105; luego T-102 puede inicializar backend/checkpointer, T-104A configura Alembic y crea las tablas iniciales sin `catalog_embeddings`; la migración definitiva de `catalog_embeddings` se crea DESPUÉS del benchmark de embeddings (orden T-105 → T-102 → T-104A → T-106 → T-201 → T-201A → T-202 → T-205 → T-104B, ver tasks.md).
- T-205 decidió `gemini-embedding-2` a 768 dimensiones (`research.md` §1, 2026-07-09; `768 <= 2000`). T-104B queda desbloqueada: crea `vector(768)` + HNSW con `vector_cosine_ops` (no requiere `halfvec`).

### Benchmark de embeddings (T-205)

El benchmark usa un entorno reproducible instalado desde `backend/pyproject.toml` con:

```powershell
pip install -e ".[dev,benchmark-embeddings]"
```

El extra `benchmark-embeddings` contiene solo dependencias opcionales de investigación para candidatos locales (`sentence-transformers`, PyTorch u otras necesarias), con versiones fijadas por T-205 tras comprobar compatibilidad con Python 3.12. El procedimiento registra: versión de Python; versiones de `sentence-transformers`, PyTorch y dependencias relevantes; identificador y versión exacta del modelo; CPU, RAM y dispositivo usado; tamaño de lote; parámetros de codificación; normalización de vectores; semillas cuando apliquen; tiempo de carga del modelo separado de latencia por consulta; costo y configuración de cada candidato gestionado; comandos o notebook necesarios para reproducir. El resultado de T-205 es la única fuente para agregar dependencias definitivas de runtime.

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
3. **Normalización:** limpiar HTML de descripciones, truncar a 2.000 caracteres, extraer columnas (nombre, tipo, descripción), entidad, categoría y `rowsUpdatedAt` como `data_updated_at`. `metadata_synced_at` se asigna al momento de la ingesta. `latest_observed_cutoff_at` permanece `null` salvo que existan observaciones previas de evidencias.
3b. **Elegibilidad de datos personales:** marcar `pii_risk_level` por dataset/columna usando metadatos, nombres de columnas y fixture de patrones (`quality/pii_patterns.yaml`). Política normativa: `high` o `contains_personal_data=true` ⇒ no elegible; `unknown` ⇒ no elegible para consultar Socrata hasta clasificación; `medium` ⇒ solo elegible para consultas agregadas que cumplan agregación mínima y no devuelvan filas individuales; `low` ⇒ elegible si también pasa publicador y API activa. No se contempla revisión manual ad hoc en runtime; cualquier reclasificación manual debe quedar como metadato versionado (`pii_reviewed_by`, `pii_reviewed_at`, `pii_review_source`, `pii_review_notes`) en el catálogo.
3c. **Publicador oficial:** normalizar el publicador del catálogo contra `official_publishers` y `official_publisher_aliases` (fixture versionado cargado en T-106). Guardar `official_publisher_id` y `publisher_verification_status` (`verified` | `unknown` | `private_or_non_official`). Los alias no únicos se registran con `ambiguous=true`, pero el dataset queda `unknown` y no elegible. Los datasets no verificados pueden indexarse para diagnóstico, pero no son elegibles como evidencia hasta resolver el publicador.
3d. **Estado de elegibilidad:** calcular `eligibility_status` y `eligibility_reasons` por dataset y columna antes de permitir T5. `eligible` significa que puede consultarse como evidencia; `diagnostic_only` significa que puede aparecer en búsqueda con advertencia pero no ejecutarse; `blocked` significa que el agente debe descartarlo y buscar alternativa.
4. **Texto de embedding por dataset:** `título + descripción + entidad + categoría + nombres de columnas` (estrategia de compensación de metadatos pobres: si la descripción < 100 caracteres, se pesa más el título y las columnas).
5. **Embeddings por lotes** → upsert en `catalog_datasets` + `catalog_embeddings` (idempotencia por `dataset_id`, RF-304).
6. **Reporte:** filas nuevas/actualizadas/fallidas → tabla `ingest_runs` (RF-701).
7. **Programación:** GitHub Actions cron semanal + ejecución manual por CLI.
8. **Ventana de obsolescencia (RF-303):** un dataset cuyo `metadata_synced_at` sea más antiguo que `CATALOG_STALE_AFTER_DAYS` (default 8 días = ingesta semanal + 1 de margen) se marca `index_stale = true` en las respuestas de búsqueda (`/v2/catalog/search`) y se lista en `/v2/admin/metrics`.
9. **Corte estadístico:** cada `evidence_results` infiere su propio `data_cutoff_at` exclusivamente desde las filas de esa evidencia, con `data_cutoff_method`, `data_cutoff_column`, `data_cutoff_confidence`, `data_cutoff_basis` y `data_cutoff_inferred_at`. `catalog_datasets.latest_observed_cutoff_at` es solo una pista agregada actualizada desde evidencias, nunca la base normativa de calidad. La interfaz nunca usa `data_updated_at` como reemplazo silencioso de corte estadístico.

## 6. Rendimiento y presupuesto de latencia (RNF-001)

| Fase | Presupuesto p95 |
|---|---|
| Búsqueda semántica (pgvector/HNSW) | ≤ 1 s p95 medido sobre distribución de al menos 100 consultas representativas; además reporta cobertura real del índice sobre datasets tabulares activos |
| Llamada LLM por paso (Gemini Flash) | ≤ 6 s |
| Consulta Socrata | ≤ 5 s (timeout 10 s, 1 reintento) |
| Validación de calidad | ≤ 500 ms (determinista) |
| Consulta simple (1 dataset, 1 SoQL, sin perfilado extenso) | ≤ 20 s p95 |
| Investigación multi-paso completa (≤ 14 pasos por defecto, típica 4–6) | ≤ 75 s p95 |

Mitigaciones: consultas Socrata paralelas cuando el plan lo permita; `LIMIT` obligatorio; `SELECT *` prohibido; máximo 50 filas entran al contexto LLM; máximo 1.000 filas en `evidence_results.rows` solo cuando el usuario necesita descarga; presupuesto duro de evidencia serializada: `rows` ≤ 1 MB por evidencia, `tool_output_summary` ≤ 20 KB por paso y evento SSE `evidence` ≤ 256 KB salvo descarga explícita; streaming SSE para percepción de progreso (RNF-008). `perfilar_dataset` debe usar una o pocas consultas agregadas/concurrentes y no puede ejecutar una cascada secuencial que rompa RNF-001.

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
- Al iniciar, el proceso genera un `worker_instance_id` único y registra/renueva una lease en `worker_instances`. TTL normativo: `WORKER_LEASE_TTL_S = RUN_HEARTBEAT_TIMEOUT_S` y renovación cada `RUN_HEARTBEAT_TIMEOUT_S / 3` mientras el proceso acepte trabajo. Si la renovación falla, la instancia deja de aceptar nuevas corridas y las activas terminarán por heartbeat/lease.
- **Arranque idempotente:** antes de aceptar tráfico, el backend marca como `interrupted` solo las corridas `running` asociadas a un `worker_instance_id` cuya lease esté vencida, persiste un único evento terminal `error` con código `RUN_INTERRUPTED` o `WORKER_LOST` y conserva evidencias/claims parciales ya validados. Repetir el arranque no duplica eventos terminales. Si existe una instancia anterior con lease vigente, sus corridas no se interrumpen.
- **Estado de corrida** en `agent_runs.status` (+ `heartbeat_at` actualizado periódicamente por la corrida activa).
- **Checkpoints de LangGraph** persistidos en PostgreSQL (checkpointer oficial): se usan para inspección y diagnóstico del estado de una corrida. En el piloto NO existe reanudación automática del trabajo del agente.
- **Eventos numerados y reserva atómica:** cada evento SSE se persiste en `agent_run_events` con secuencia monotónica por corrida ANTES de emitirse. La secuencia se reserva dentro de la misma transacción lógica que inserta el evento mediante una actualización atómica de `agent_runs`, por ejemplo:

  ```sql
  UPDATE agent_runs
  SET last_event_seq = last_event_seq + 1
  WHERE id = :run_id
  RETURNING last_event_seq;
  ```

  La inserción en `agent_run_events(run_id, seq, event_type, payload)` usa el `seq` retornado y la unicidad `(run_id, seq)` como defensa adicional. Si la transacción hace rollback después de reservar, el incremento también revierte y el número puede reutilizarse sin hueco observable. Dos emisores concurrentes serializan por bloqueo de fila; un timeout que compite con un evento normal, un detector de worker perdido o una escritura duplicada del terminal deben ganar mediante transición terminal idempotente (`terminal_event_written_at`/estado terminal) y producir como máximo un evento terminal. Un reintento idempotente reutiliza la comprobación de evento terminal existente o inserta un evento nuevo solo si la transacción previa no confirmó.
- **Eventos terminales:** los eventos terminales (`answer`/`error`) se conservan siempre mientras exista la corrida y se escriben una sola vez aunque compitan timeout, worker perdido y cierre por reinicio.
- **Reconexión SSE:** el cliente reanuda enviando el encabezado estándar `Last-Event-ID` con el último `seq` recibido; el servidor reenvía los eventos persistidos con `seq` mayor y continúa en vivo. Sin pérdida ni duplicación (prueba de integración en pruebas.md §2.3). El token de acceso viaja SIEMPRE por encabezado `Authorization`, nunca en la URL.
- **Corridas huérfanas:** un barrido periódico detecta corridas `running` con `heartbeat_at` vencido (> `RUN_HEARTBEAT_TIMEOUT_S`, default 120 s) y las transiciona a `interrupted`; si la duración excede `RUN_MAX_DURATION_S` (default 600 s), transiciona a `failed` con código `RUN_TIMEOUT`.
- **Semántica normativa única (sin ambigüedad):**

| Caso | Estado final | Evento terminal | Código | Parciales | `GET /runs/{run_id}` | ¿Puede re-ejecutar? | ¿Reanudación automática? |
|---|---|---|---|---|---|---|---|
| Desconexión del navegador | No cambia; sigue `running` hasta terminar | Ninguno por la desconexión | — | Se siguen conservando | Si aún corre, devuelve estado actual + pasos/eventos persistidos | Sí, como nueva corrida si quiere | No aplica |
| Reconexión con `Last-Event-ID` | No cambia | Reenvía eventos `seq > Last-Event-ID` | — | Se conservan | Igual al estado actual | Sí | No |
| Reinicio del backend | `interrupted` | `error` | `RUN_INTERRUPTED` | Sí: evidencias y claims validados hasta el corte | `RespuestaFinal` persistida con `status=interrupted` + pasos | Sí | No |
| Proceso o worker desaparecido | `interrupted` | `error` | `WORKER_LOST` | Sí | Igual que `interrupted` | Sí | No |
| Heartbeat vencido | `interrupted` | `error` | `HEARTBEAT_EXPIRED` | Sí | Igual que `interrupted` | Sí | No |
| Duración máxima excedida | `failed` | `error` | `RUN_TIMEOUT` | Sí, para diagnóstico; no se presenta como respuesta completa | Error persistido + pasos/evidencias parciales | Sí | No |
| Error definitivo del proveedor LLM | `failed` | `error` | `LLM_PROVIDER_ERROR` | Sí | Error persistido + pasos parciales | Sí | No |
| Error definitivo de Socrata | `failed` | `error` | `SOCRATA_ERROR` o `SOCRATA_TIMEOUT` | Sí | Error persistido + pasos parciales | Sí | No |
| Agotamiento de presupuesto (pasos, consultas SoQL o autocorrecciones) | `no_evidence` si no hay evidencia suficiente; `completed` si los parciales bastan para responder con claims válidos | `answer` | `STEP_BUDGET_EXCEEDED` (agotamiento real de pasos) / `INSUFFICIENT_BUDGET_FOR_ACTION` (parada preventiva) / `SOQL_CALL_BUDGET_EXCEEDED` / `SOQL_CORRECTION_EXHAUSTED`, solo en `usage.termination_reason` (contracts/api-rest.md §4) | Sí | `RespuestaFinal` normal (`no_evidence` o `completed`) | Sí | No |
| Borrado solicitado por el usuario | La corrida deja de existir | Ninguno adicional; operación HTTP `204` | — | No: se borran corrida, eventos, evidencias, claims y checkpoints (`adelete_thread(run_id)`) | `404` tras el borrado | Sí, como nueva corrida | No |
| DELETE sobre corrida activa | La corrida se cancela por borrado y deja de existir | Ninguno visible adicional; se detiene la tarea antes del borrado | — | No: se borra completo | `404` tras el borrado | Sí, como nueva corrida | No |

- **Objeto persistido `RespuestaFinal` para `interrupted`:** `summary: string | null` (mensaje diagnóstico breve si pudo construirse), `narrative: null`, `evidence: Evidencia[]` (puede ser `[]`, solo evidencias ya validadas), `claims: Claim[]` (puede ser `[]`, solo claims ya validados), `no_evidence_report: null`, `usage: {steps_used: int, latency_ms: int | null, estimated_cost_usd: number | null, termination_reason: "RUN_INTERRUPTED" | "WORKER_LOST" | "HEARTBEAT_EXPIRED"}`.
- **Idempotencia:** todas las herramientas del agente son de solo lectura; repetir un paso tras recuperación es seguro por diseño (contracts/agent-tools.md, reglas comunes).
- **Checkpointer:** se usa `AsyncPostgresSaver` de `langgraph-checkpoint-postgres`; la inicialización del backend ejecuta `.setup()` de forma idempotente. Cada invocación del grafo usa `config={"configurable": {"thread_id": run_id}}`. RF-803 y la retención purgan checkpoints con `adelete_thread(run_id)`.

**Acceso a corridas (RF-801):**
- Al crear la corrida se genera un `run_access_token` aleatorio (≥ 256 bits), se entrega UNA vez en la respuesta `202` y se almacena solo su hash (SHA-256). **El token vive exactamente lo que viven los datos de su clase:** `user` ⇒ `created_at + RETENTION_USER_DAYS` (default 90 días); `eval` ⇒ `created_at + RETENTION_EVAL_MONTHS` (default 24 meses). Al vencer la retención, la corrida se elimina según data-model.md §7. Sin cuentas de usuario no existe mecanismo seguro de renovación, así que no se ofrece.
- `POST /v2/agent/query` crea siempre `retention_class=user`. Las corridas `eval` se crean solo desde el runner OE3 mediante servicio interno del backend con `EVAL_MODE=true`; el backend público mantiene `EVAL_MODE=false`.
- Toda lectura, streaming, reanudación o borrado exige `Authorization: Bearer <run_access_token>`; la comparación de hashes es en tiempo constante. El `run_id` solo identifica, no autoriza.
- Como `EventSource` nativo no admite encabezados, el frontend consume SSE mediante **fetch con stream de lectura** (patrón estándar), enviando el header. Los tokens NUNCA van en URLs ni en logs.
- **CORS:** FastAPI (`CORSMiddleware`) con orígenes tomados de la variable `CORS_ALLOWED_ORIGINS` (lista separada por comas). Valores base: producción (`https://cuestiondedatos.com`, `https://www.cuestiondedatos.com`) y desarrollo (`http://localhost:3000`). **Previews de Vercel:** se añade temporalmente el origen EXACTO del preview a la variable durante las pruebas; PROHIBIDO el comodín `*.vercel.app` o `*`. Métodos permitidos: `GET, POST, DELETE`; encabezados permitidos: `Authorization`, `Content-Type`, `Last-Event-ID`. La conexión navegador→backend es directa; no hay proxy en Next.js.

**Consentimiento y borrado (RF-802/803):** la UI informa antes de la primera investigación qué se almacena (pregunta, contexto acotado, trazas), con qué fin (funcionamiento y evaluación técnica), por cuánto tiempo (según `retention_class`, data-model.md §7) y cómo borrarlo (`DELETE /v2/agent/runs/{run_id}`).

**Retención (RF-804):** además del borrado por usuario, un servicio/CLI idempotente del backend ejecuta el barrido de retención; el endpoint administrativo `POST /v2/admin/retention/run` reutiliza la misma lógica para ejecución manual. La programación periódica se hace fuera de FastAPI cada 6 horas mediante el scheduler del proveedor de despliegue o un workflow programado autenticado con `ADMIN_TOKEN`; no se añade un servicio persistente ni scheduler interno. SLA: toda corrida vencida se borra físicamente en máximo 24 horas. Si cualquier acceso encuentra una corrida vencida, ejecuta borrado oportunista antes de responder. La operación es transaccional e idempotente: intentar `pg_try_advisory_xact_lock(20260707, 804)` al inicio del barrido → si el lock no se obtiene, registrar `already_running` y salir sin efectos → copiar métricas no identificables con `source_run_hash = sha256(run_id + RETENTION_HASH_SALT)` → asegurar snapshot eval si aplica → borrar checkpoints con `adelete_thread(run_id)` → borrar corrida y relaciones. `technical_metrics` se purga por `RETENTION_TECH_MONTHS`. En despliegue, el humano crea el cron externo, registra `ADMIN_TOKEN` y `RETENTION_HASH_SALT` como secretos, verifica la primera ejecución y revisa fallos.

## 12. Configuración del backend (T-102, RF/RNF relacionados)

Estas variables son la fuente para construir `backend/.env.example`. No se fijan secretos reales. `EMBEDDING_MODEL` quedó fijado por T-205 (`research.md` §1, 2026-07-09).

| Variable | Propósito | Tipo | Default documental | Obligatoria | Entornos | Validaciones | Requisitos |
|---|---|---|---|---|---|---|---|
| `DATABASE_URL` | Conexión PostgreSQL local, CI o desplegada | URL PostgreSQL | ninguno | Sí | dev/test/prod | Se acepta `postgresql://` o `postgres://`; la app normaliza internamente a driver async `postgresql+psycopg://` para SQLAlchemy. El checkpointer recibe una cadena compatible con psycopg v3 sin prefijo SQLAlchemy. Rechaza SQLite, URLs sin base, credenciales vacías en prod y parámetros inseguros; no se imprime en logs | DEP-01, RF-703, RF-804 |
| `GOOGLE_API_KEY` | Proveedor Gemini por defecto | string secreto | ninguno | Sí si `LLM_PROVIDER=google` o embeddings gestionados Google | dev/prod/eval | No vacía; solo servidor | RF-206, RNF-011 |
| `ANTHROPIC_API_KEY` | Proveedor comparativo OE3 | string secreto | ninguno | Sí si `LLM_PROVIDER=anthropic` o evaluación comparativa | eval/prod opcional | No vacía cuando se usa; solo servidor | RF-206, RF-601 |
| `SOCRATA_APP_TOKEN` | Aumentar límites de datos.gov.co | string secreto | ninguno | Sí | dev/prod/eval | No se envía al cliente ni logs | RF-207, RNF-011 |
| `LLM_PROVIDER` | Selección de proveedor LLM | enum `google`/`anthropic` | `google` | Sí | dev/prod/eval | Debe estar soportado por factory | RF-206 |
| `LLM_MODEL` | Modelo del proveedor LLM | string | `gemini-2.5-flash` | Sí | dev/prod/eval | Compatible con `LLM_PROVIDER`; override por request solo con `EVAL_MODE=true` | RF-206, RF-601 |
| `EMBEDDING_MODEL` | Modelo elegido para embeddings | string | `gemini-embedding-2` | Sí desde T-203 | dev/prod/eval | Debe coincidir con research.md §1 (768 dim) y dimensión migrada en T-104B | RF-301, T-205 |
| `AGENT_MAX_STEPS` | Presupuesto máximo del agente | int | `14` | Sí | dev/prod/eval | `1 <= valor <= 25` | RF-201, research.md §19 |
| `RUN_MAX_DURATION_S` | Duración máxima por corrida | int segundos | `600` | Sí | dev/prod/eval | Mayor que 0; al exceder termina `failed/RUN_TIMEOUT` | RF-209, RNF-001 |
| `RUN_HEARTBEAT_TIMEOUT_S` | Umbral para worker muerto | int segundos | `120` | Sí | dev/prod/eval | Mayor que heartbeat emitido; al vencer termina `interrupted` | RF-209 |
| `WORKER_LEASE_TTL_S` | TTL de lease de instancia | int segundos | igual a `RUN_HEARTBEAT_TIMEOUT_S` | Sí | dev/prod/eval | Mayor que intervalo de renovación; default derivado, no menor a 30 | RF-209 |
| `DELETE_ACTIVE_GRACE_S` | Espera cooperativa al borrar corrida activa | int segundos | `5` | Sí | dev/prod/eval | `0 <= valor <= 30`; después del plazo el borrado continúa | RF-803 |
| `RETENTION_USER_DAYS` | Retención y expiración token de corridas `user` | int días | `90` | Sí | dev/prod | Mayor que 0 | RF-801, RF-804 |
| `RETENTION_EVAL_MONTHS` | Retención y expiración token de corridas `eval` | int meses | `24` | Sí | eval/prod | Mayor que 0 | RF-801, RF-804, RF-603 |
| `RETENTION_TECH_MONTHS` | Retención de `technical_metrics` | int meses | `12` | Sí | prod/eval | Mayor que 0; sin contenido de usuario | RF-804 |
| `RETENTION_HASH_SALT` | Salt servidor para `technical_metrics.source_run_hash` | string secreto | ninguno | Sí en prod/eval; dev puede usar placeholder local no real | dev/prod/eval | Mínimo 32 bytes aleatorios en prod/eval; no se imprime en logs; rotación solo tras cerrar barridos pendientes | RF-804, RNF-011 |
| `CATALOG_STALE_AFTER_DAYS` | Marca `index_stale` | int días | `8` | Sí | dev/prod/eval | Mayor que 0 | RF-303 |
| `PLACEHOLDER_MIN_RATIO` | Umbral contextual de placeholders | decimal 0-1 | `0.30` | Sí | dev/prod/eval | `0 <= valor <= 1` | RF-401 |
| `MAX_CONCURRENT_RUNS` | Límite global de corridas activas por proceso | int | `3` | Sí | dev/prod | Mayor que 0; no persiste IP | RNF-009, RNF-011 |
| `CORS_ALLOWED_ORIGINS` | Orígenes frontend permitidos | lista CSV de URLs | `http://localhost:3000` | Sí | dev/prod | Sin `*`; previews Vercel solo origen exacto temporal | RF-204, RNF-011 |
| `ADMIN_TOKEN` | Token para endpoints administrativos | string secreto | ninguno | Sí en prod; opcional en dev local | dev/prod/eval | Longitud mínima 32 bytes aleatorios; header `X-Admin-Token` | RF-701, RF-702 |
| `EVAL_MODE` | Habilita overrides de modelo y corridas `eval` | boolean | `false` | Sí | dev/prod/eval | `true` solo en entorno controlado de evaluación | RF-601, RF-603 |

## 13. Enmienda: arquitectura dual y migración al núcleo determinista

**Implementa:** RF-201…209, RF-601…603 · **Verifica:** RNF-002…005 · **Decisión:** `research.md` §25.

Durante el rediseño existen dos rutas deliberadamente separadas:

| Ruta | Responsabilidad | Estado durante la migración |
|---|---|---|
| `legacy` | Grafo histórico de `app.agent.graph`, con router LLM iterativo, claim planner y guardas acumuladas. | Rollback obligatorio; no se retira ni se reinterpreta como determinista. |
| `deterministic` | Máquina de etapas que controla recuperación, candidatos, perfilado, `QueryPlan`, validación, exploración, renderizado SoQL, ejecución, calidad, claims y terminación. | Núcleo nuevo en validación; no sustituye al legado hasta superar las puertas. |

La selección se hace mediante `AGENT_RUNTIME=legacy|deterministic`. Mientras no se haya superado la puerta normativa, los entornos de usuario/producción deben fijar explícitamente `AGENT_RUNTIME=legacy`. Al superarla, `deterministic` se convierte inmediatamente en el default y `legacy` queda disponible solo como rollback de emergencia durante una versión. El default actual de `backend/app/config.py` (`deterministic`) sigue siendo una desviación mientras la puerta esté abierta y debe registrarse en T-610; esta enmienda no modifica código. El valor elegido al iniciar la corrida queda en el `config_snapshot` de evaluación. No existe fallback automático entre runtimes: si falla el determinista, la corrida termina con estado y código controlados; ejecutar el legado requiere una nueva corrida configurada explícitamente.

### 13.1 Pipeline del runtime determinista

```text
pregunta
  → intención estructurada
  → recuperación multiquery
  → candidatos ordenados
  → perfilado/esquema
  → QueryPlan estructurado
  → validación determinista del plan
  → exploración categórica acotada, si aplica
  → renderizado SoQL determinista
  → ejecución Socrata
  → calidad T6
  → claims T7
  → síntesis fundamentada o fallback seguro
  → persistencia y evento terminal único
```

Las transiciones, presupuestos y motivos de rechazo pertenecen al código. El LLM solo puede producir objetos dentro de los contratos estructurados que se le asignen y redactar desde evidencia/claims aceptados. No puede elegir una consulta SoQL libre, saltar la validación, reactivar un candidato rechazado ni convertir un fallo determinista en éxito narrativo.

### 13.2 Límites de compatibilidad

- Los contratos de `contracts/`, el modelo de datos vigente y `golden-v1.yaml` no cambian como parte de la validación inicial del runtime.
- Los componentes compartidos —PostgreSQL, Socrata, calidad, claims cuantitativos, API y durabilidad— deben demostrar compatibilidad con ambos runtimes.
- Los hechos textuales de primera clase son una evolución posterior. Antes de implementarlos deben enmendarse, en este orden, `spec.md` si cambia el QUÉ, `research.md`, `plan.md`, contratos y `data-model.md`.
- `golden-v2` solo puede crearse después de la auditoría de derivabilidad de los 50 casos y de una autorización expresa en el SDD. `GOLDEN_V2_PROPOSAL.md` no tiene rango normativo.

### 13.3 Secuencia y puertas

La ruta ejecutable es T-610 → T-611 → T-612 → T-613 → T-614 → T-615 → T-616 → T-617. El primer incremento modifica exclusivamente pruebas y clasificación de suites. Las mejoras de recuperación empiezan únicamente después de disponer de aceptación E2E, matriz diagnóstica y smoke reproducible.

Cuando el determinista cumpla simultáneamente aceptación E2E verde, integraciones compartidas verdes, negativos 100%, `golden-v2` ≥ 80%, cero fabricaciones, cero cifras huérfanas, persistencia/durabilidad verificadas y límites de latencia/costo satisfechos, pasa inmediatamente a ser el default. El runtime legado permanece congelado y accesible solo para rollback durante una versión. Después se eliminan el selector y el código legado mediante una fase independiente y reversible.
