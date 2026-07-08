# Plan de Trabajo Ejecutable — Cuestión de Datos v2.0

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Fuente:** [`plan.md`](./plan.md) §8 · Los IDs de requisitos (`RF-###`, `RNF-###`) vienen de [`spec.md`](./spec.md)

> **Cómo leer este archivo (para Camilo):** las tareas están en orden de ejecución. Cada una dice *qué* se hace, *por qué*, *qué necesitas hacer tú manualmente* (cuentas, claves, decisiones) y *cómo verificar que quedó bien* antes de pasar a la siguiente. Las marcadas 🧑 requieren acción humana tuya; las demás las puede ejecutar un agente de desarrollo. Marca `[x]` al completar. No saltes fases: cada una asume la anterior verificada.

---

## FASE 0 — Preparación de cuentas y herramientas externas

*Objetivo: tener todas las credenciales e infraestructura gratuita lista ANTES de escribir código, para que ninguna tarea posterior se bloquee esperando un registro.*

- [ ] **T-001 🧑 Preparar las bases de datos (local y despliegue).**
  *El desarrollo diario usa PostgreSQL LOCAL en Docker (Constitución Art. II.2); el servicio gestionado es solo para DESPLIEGUE y puede crearse más tarde (se necesita a partir de T-206/T-701).*
  1. **Local (requisito para desarrollar):** instala [Docker Desktop](https://www.docker.com/products/docker-desktop/). La base local se levantará con el `compose.yaml` que se crea en T-105 — aquí solo asegura que `docker compose version` funciona.
  2. **Despliegue (puede diferirse):** regístrate en [supabase.com](https://supabase.com) (o [neon.tech](https://neon.tech), equivalente) con tu cuenta de GitHub; crea el proyecto `cuestion-de-datos`; en el editor SQL ejecuta `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;`; guarda la cadena de conexión (`postgresql://usuario:clave@host-remoto:5432/base`) en tu gestor de contraseñas.
  - ✅ *Verificación:* `docker compose version` responde; y, cuando crees la gestionada, `SELECT extname FROM pg_extension;` lista `vector` y `pg_trgm`.

- [ ] **T-002 🧑 Verificar/crear las API keys de los modelos.**
  1. **Gemini (defecto):** ya tienes `GOOGLE_API_KEY` en `.env.local` de v1.0. Confirma en [aistudio.google.com](https://aistudio.google.com) que sigue activa y revisa los límites del tier actual (necesitamos ~10 llamadas por investigación).
  2. **Anthropic (comparativa OE3):** crea una key en [console.anthropic.com](https://console.anthropic.com) → `ANTHROPIC_API_KEY`. Carga el crédito mínimo (USD 5 basta para las corridas de evaluación). *Solo se usa en la Fase 6.*
  3. **Socrata:** confirma tu `SOCRATA_APP_TOKEN` actual en [datos.gov.co](https://www.datos.gov.co/profile/edit/developer_settings) (aumenta los límites de tarifa de la API).
  - ✅ *Verificación:* cada key responde a una llamada mínima de prueba (`curl` de ejemplo en quickstart.md §7).

- [ ] **T-003 🧑 Crear el servicio de hosting del backend.**
  1. Regístrate en [railway.app](https://railway.app) (o render.com) con GitHub.
  2. Todavía NO despliegues nada; solo confirma que la cuenta puede crear servicios web con Python. El despliegue real es T-701.
  - ✅ *Verificación:* panel accesible, plan y límites anotados.

- [ ] **T-004 Preparar el repositorio.**
  1. Crear rama `v2` en el repo actual (`cuestion-de-datos-MinTIC-2025`). Todo el trabajo v2.0 ocurre en ramas hijas de `v2` con PRs.
  2. Añadir `LICENSE` (MIT — compromiso de software libre de la propuesta) y `CHANGELOG.md` con la entrada `2.0.0-dev`.
  3. Actualizar `.gitignore`: añadir `backend/.env`, `__pycache__/`, `.venv/`, `*.pyc`.
  - ✅ *Verificación:* rama `v2` existe; `git log` limpio; ningún secreto en el historial.

## FASE 1 — Reorganización del repositorio (sin cambios funcionales)

*Objetivo: estructura de plan.md §3 con la v1.0 funcionando igual que antes. Hacerlo primero evita mezclar refactor con features nuevos.*

- [x] **T-101 Mover el frontend a `frontend/`.** Mover `components/`, `pages/`, `styles/`, `public/`, `data/`, `utils/`, configs de Next/Tailwind/PostCSS y `package.json` a `frontend/`. Actualizar rutas relativas si alguna se rompe.
  - ✅ `cd frontend && npm install && npm run dev` sirve la app idéntica a v1.0 en `localhost:3000`.
- [x] **T-105 Crear `compose.yaml` en la raíz del repositorio.** Define, como mínimo: servicio PostgreSQL con extensión pgvector con **versión fijada por tag completo o digest** (nunca `latest` ni alias flotante como único pin), volumen persistente, healthcheck y variables configurables vía `.env` (usuario, clave, base, puerto). Documentar en el README del repo el comando `docker compose up -d db`. Este archivo es la vía oficial de desarrollo local (Constitución Art. II.2); Supabase/Neon quedan solo para despliegue.
  - ✅ `docker compose up -d db` deja Postgres sano (healthcheck OK); las extensiones `vector` y `pg_trgm` quedan creadas por el script `init` del contenedor local; `psql` o `docker compose exec db psql ... -c "SELECT extname FROM pg_extension;"` lista ambas; los datos sobreviven a `docker compose restart`.
- [x] **T-102 Crear el esqueleto de `backend/`.** Estructura de carpetas de plan.md §3, `pyproject.toml` (Python 3.12; dependencias de runtime/dev: fastapi, uvicorn, langgraph, langgraph-checkpoint-postgres, langchain-core, langchain-google-genai, langchain-anthropic, sqlalchemy async, alembic, psycopg[binary,pool], pgvector, httpx, pydantic-settings, pytest, pytest-asyncio, respx, ruff, pip-audit). Registrar el marcador pytest `integration` en `[tool.pytest.ini_options]` sin `addopts` global que excluya integración. Preparar, si se desea para T-205, el extra opcional `[project.optional-dependencies].benchmark-embeddings` con marcadores de versión para `sentence-transformers` y `torch` (`<VERSION_COMPATIBLE_PY312>`), pero NO instalarlas ni tratarlas como runtime hasta la decisión de T-205. Crear `app/main.py` con `GET /v2/health` (200 `ok` y 503 `degraded` como `HealthResponse`, excepción explícita al sobre estándar), settings async, transformación validada de `DATABASE_URL` según plan.md §12, inicialización idempotente del checkpointer (`AsyncPostgresSaver.setup()`) contra la base local creada en T-105, `.env.example` con todas las variables de plan.md §12/quickstart.md §2, sin valores reales ni secretos, y un mínimo de pruebas deterministas sin red (`backend/tests/test_settings.py` y/o `backend/tests/test_health.py`) para que pytest no falle por ausencia de tests.
  - ✅ Con la base de T-105 arriba, `uvicorn app.main:app` responde en `/v2/health`; antes de T-203/T-204 el check `catalog_index` puede estar `degraded/not_initialized` y la respuesta global ser `503`; el checkpointer inicializa sus tablas; la app usa SQLAlchemy async + psycopg v3; `pytest -m "not integration"` ejecuta al menos una prueba determinista real y termina en verde; `pytest -m integration` es comando válido aunque no tenga casos hasta las fases de integración.
- [x] **T-103 Configurar CI básico.** `.github/workflows/ci.yml`: jobs `backend` (ruff + `pytest -m "not integration"` + pip-audit) y `frontend` (build de Next). El job backend consume las pruebas mínimas creadas en T-102 y añade un servicio PostgreSQL+pgvector con healthcheck cuando ejecute pruebas de contrato o integración que toquen DB; las unitarias puras pueden correr sin DB. La suite `pytest -m integration` queda separada para corridas etiquetadas/diarias según pruebas.md. Debe correr en cada PR a `v2`.
  - ✅ El primer PR muestra los dos checks en verde; el job backend exporta un `DATABASE_URL` de CI compatible con psycopg v3 y confirma extensiones `vector`/`pg_trgm` antes de pruebas con DB. Verificado en [PR #1](https://github.com/Grajales-Camilo/cuestion-de-datos-MinTIC-2025/pull/1): `Backend` y `Frontend` en verde. `pip-audit` corre en modo informativo (`continue-on-error: true`) por incompatibilidad actual de `langgraph`/`langgraph-checkpoint`/`langgraph-sdk` 1.x con `langchain-core < 1` que aún requieren `langchain-google-genai`/`langchain-anthropic`; volver bloqueante antes de T-301 o T-701.
- [x] **T-104A Migraciones iniciales (SIN la tabla vectorial definitiva).** Alembic configurado; migración 001 crea todas las tablas de `data-model.md` EXCEPTO `catalog_embeddings`, cuya dimensión depende del benchmark de embeddings (T-205 → T-104B). Modelos SQLAlchemy en `app/db/models.py` espejando el documento exactamente (nombres, constraints y FKs), incluidos `official_publishers`, `official_publisher_aliases` con índice parcial único `alias_normalized WHERE ambiguous=false`, `worker_instances`, campos de token por `retention_class`, elegibilidad/PII, metadatos de revisión PII, cortes por evidencia, eventos (`agent_run_events`), `quantitative_claims` con `source_hash` de contenido reproducible, `technical_metrics.source_run_hash UNIQUE`, semillas/configuración eval, constraints de dominio y `eval_case_results.agent_run_id ON DELETE SET NULL`.
  - ✅ Con la base local ya levantada en T-105, `alembic upgrade head` crea las tablas; `psql`/`docker compose exec db psql ... -c "\\dt"` las lista; NO existe aún `catalog_embeddings`; duplicar un alias no ambiguo falla y dos ambiguos con el mismo texto son válidos; `eval_case_results.agent_run_id` permite `NULL`; los CHECK de status/retention/PII/elegibilidad/confianza rechazan valores inválidos; `technical_metrics.source_run_hash` impide duplicados.
- [ ] **T-106 Registro canónico inicial de publicadores oficiales.** Crear fixture versionado, script de carga y endpoint admin `POST /v2/admin/publishers/reload` para `official_publishers` y `official_publisher_aliases` según `data-model.md` y `contracts/validacion-calidad.md`: `id`, nombre canónico, alias normalizados, tipo de entidad, vigencia, sucesor, estado, fuente de verificación y fecha de actualización. Incluir el conjunto mínimo para arrancar la ingesta: DANE, ministerios, gobernaciones/alcaldías piloto, universidades públicas, empresas industriales y comerciales del Estado y establecimientos públicos ya identificados. No exige cobertura de catálogo completo porque esa medición depende de T-201.
  - ✅ Cargar el fixture en la base local resuelve nombre canónico, alias único, mayúsculas/tildes y entidad abreviada; alias no único queda marcado `ambiguous=true` y produce `publisher_verification_status="unknown"`; publicador privado queda `private_or_non_official`.

## FASE 2 — Índice semántico del catálogo (RF-301…304, RNF-010)

*Objetivo: pasar de 5 datasets hardcodeados a ~8.000 buscables semánticamente. Es el cimiento del agente: sin esto no hay v2.0.*

- [ ] **T-201 Cliente de la Discovery API (ESC-07).** `scripts/ingest_catalog.py`: pagina `https://api.us.socrata.com/api/catalog/v1?domains=www.datos.gov.co&only=dataset` (respetando límites de tarifa), filtra tabulares con API activa y normaliza según plan.md §5. Upsert en `catalog_datasets` + `catalog_columns`, enlazando publicador contra `official_publishers`/aliases, distinguiendo `metadata_synced_at` de `data_updated_at`, calculando `pii_risk_level`, `eligibility_status` y `eligibility_reasons`. Registra `ingest_runs`.
  - ✅ Correr el script llena ≥ 7.000 datasets; re-correrlo no duplica nada (RF-304).
- [ ] **T-201A Auditoría de cobertura de publicadores.** Después de la primera ingesta real, generar `backend/data/official_publishers_coverage.json` con conteos por `publisher_verification_status`, aliases no únicos detectados, candidatos a alias nuevos y cobertura de datasets tabulares activos. Actualizar el fixture solo con procedencia verificable.
  - ✅ Cobertura `verified` ≥ 90% o reporte explícito de brecha; ningún alias no único asigna publicador automáticamente.
- [ ] **T-202 Carga del maestro DIVIPOLA.** Script que descarga el dataset oficial DIVIPOLA de datos.gov.co (dataset del DANE, id `gdxc-w37w` o su vigente — confirmar en el portal) y llena `divipola_entries` con `name_normalized` y `alt_names`.
  - ✅ `SELECT count(*) FROM divipola_entries WHERE level='municipality';` ≥ 1.100; buscar `carmen viboral` con trigram devuelve `05148`.
- [ ] **T-205 🧑 Benchmark de embeddings y decisión (ANTES de crear la tabla vectorial).** Notebook `notebooks/01_benchmark_embeddings.ipynb`: instalar entorno con `pip install -e ".[dev,benchmark-embeddings]"`, fijando antes en `backend/pyproject.toml` versiones compatibles con Python 3.12 para `sentence-transformers`, PyTorch y dependencias relevantes del candidato local. Comparar `intfloat/multilingual-e5-large` (local), `gemini-embedding-2` (gestionado) y, si se justifica en `research.md`, otro modelo multilingüe actual, sobre una muestra de los metadatos ya ingeridos (T-201) y el maestro DIVIPOLA cargado (T-202), con 30+ consultas de prueba. Evaluar TODOS los criterios de `research.md` §1: recuperación en español, calidad en consultas territoriales colombianas, dimensión de vectores, latencia, costo, ejecución local, dependencia de proveedor, reproducibilidad, tamaño del índice y compatibilidad pgvector. Registrar versión de Python, versiones de librerías, identificador y versión exacta del modelo, CPU/RAM/dispositivo, tamaño de lote, parámetros de codificación, normalización de vectores, semillas, tiempo de carga separado de latencia por consulta, costo/configuración del candidato gestionado y comandos/notebook de reproducción. Si se mantiene `vector(<DIM>)`, aceptar solo `DIM <= 2000`; si se elige una dimensión mayor, documentar cambio a `halfvec` antes de T-104B. **Tú decides** el modelo y con él la dimensión; registrar la decisión y su justificación en `research.md` §1 y propagar el resultado a `data-model.md`, dependencias definitivas de `pyproject.toml`, `.env.example`, `plan.md` y `quickstart.md`.
  - ✅ Decisión, dimensión, tipo (`vector`/`halfvec`) y propagación documental documentadas con la evidencia del benchmark; las dependencias definitivas de runtime se agregan solo después de registrar esta decisión.
- [ ] **T-104B Migración definitiva de `catalog_embeddings`.** Con el modelo y la dimensión decididos en T-205: migración Alembic que crea `catalog_embeddings` con `vector(<dimensión elegida>)` + `vector_cosine_ops` si `DIM <= 2000`, o `halfvec(<dimensión elegida>)` + operador compatible si `DIM > 2000`. Actualizar `data-model.md` reemplazando `<DIM>` por el valor real en el mismo PR.
  - ✅ `alembic upgrade head` crea la tabla e índice correctos para `vector` o `halfvec`; `data-model.md` ya no contiene `<DIM>` sin resolver.
- [ ] **T-203 Generación de embeddings (ESC-07).** `scripts/build_embeddings.py`: construye `embedding_text` (plan.md §5.4), genera embeddings por lotes con el modelo seleccionado y hace upsert en `catalog_embeddings`.
  - ✅ 100% de datasets activos con embedding; `model` homogéneo en toda la tabla.
- [ ] **T-204 Endpoint de búsqueda.** `GET /v2/catalog/search` según `contracts/api-rest.md` §8: valida `q`, limita `k`, excluye datasets inactivos, marca `index_stale` y devuelve `latest_observed_cutoff_at` solo como pista, nunca como corte de evidencia.
  - ✅ "deserción escolar" retorna datasets del MEN en el top-5; latencia < 1 s; `k=999` devuelve 422; un dataset inactivo no aparece.
- [ ] **T-206 Cron de ingesta (ESC-07).** `.github/workflows/ingest-cron.yml` semanal (domingo 3:00 UTC) que ejecuta T-201+T-203 contra la base productiva usando secrets del repo. Implementa `POST /v2/admin/ingest` y `GET /v2/admin/ingest/runs` (RF-701).
  - ✅ Ejecución manual del workflow termina en verde y crea un `ingest_runs` nuevo.

## FASE 3 — Agente multi-paso (RF-201…209)

*Objetivo: el grafo LangGraph con sus herramientas reemplaza el bucle manual de v1.0, con durabilidad desde el primer día.*

- [ ] **T-300 Prueba de concepto de durabilidad (ANTES de construir el grafo completo).** Prototipo mínimo (un endpoint + un grafo de juguete de 3 nodos) que demuestre de punta a punta la semántica única de plan.md §11: `worker_instance_id` + lease con TTL y renovación, cierre idempotente solo de instancias con lease vencida, eventos SSE numerados persistidos en `agent_run_events` con reserva atómica de `last_event_seq` vía `UPDATE agent_runs ... RETURNING last_event_seq` dentro de la misma transacción que inserta el evento, evento terminal `error` con `status`, `thread_id=run_id`, reconexión con `Last-Event-ID` sin pérdida ni duplicación, reinicio real ⇒ `interrupted/RUN_INTERRUPTED`, heartbeat vencido ⇒ `interrupted/HEARTBEAT_EXPIRED`, duración máxima ⇒ `failed/RUN_TIMEOUT`, DELETE de corrida activa y limpieza de checkpoints con `adelete_thread`. Cubrir dos emisores concurrentes, timeout compitiendo con evento normal, detector de worker perdido, escritura duplicada del evento terminal, rollback tras reservar secuencia y reintento idempotente. Si algo del diseño no funciona en la práctica, se corrige plan.md/contratos AQUÍ, no en la Fase 5.
  - ✅ Demo reproducible documentada: iniciar corrida → recibir 2+ eventos → matar el proceso → reiniciar → reconectar con `Last-Event-ID` → recibir los eventos faltantes y un estado terminal coherente; repetir el arranque no duplica el evento terminal; una instancia nueva NO interrumpe corridas de una instancia anterior con lease vigente; prueba concurrente demuestra secuencias contiguas sin duplicados.
- [ ] **T-301 Capa multi-proveedor LLM.** `app/llm/factory.py`: devuelve el chat model según `LLM_PROVIDER`/`LLM_MODEL` (google | anthropic), con structured output y conteo de tokens unificado (RF-206).
  - ✅ Prueba unitaria instancia ambos proveedores (con mock) y el conteo de tokens/costo funciona.
- [ ] **T-302 Implementar las herramientas T1–T5** (las ÚNICAS invocables por el enrutador LLM, `contracts/agent-tools.md`) en `app/tools/`, cada una con esquema Pydantic, sanitización (T4), guardia SoQL estructural (T5) y pruebas unitarias con HTTP mockeado (respx). `resolver_geografia` (T3) depende de T-202 y de que `divipola_entries` esté cargada con el maestro DIVIPOLA; no debe volver al arreglo hardcodeado de v1.0. La guardia usa gramática restringida propia en `app/tools/soql_parser.py`, canonicaliza la consulta, prohíbe `SELECT *`, limita `OFFSET`, valida alias/literales, aplica la guardia PII/elegibilidad antes de Socrata y mantiene lista blanca de funciones. Los nodos deterministas T6 y T7 NO van aquí: se implementan en T-401 y T-403.
  - ✅ Suite de pruebas de herramientas en verde (casos de pruebas.md §2.1, no §4.1).
- [ ] **T-401 Implementar `app/quality/` (nodo determinista T6).** Exactamente según `contracts/validacion-calidad.md`: elegibilidad separada de calidad, 4 dimensiones, pesos, reglas duras, política PII `unknown`/`medium`/`high`, agregación mínima, inferencia de `data_cutoff_at` sobre las filas de la evidencia, fallback `data_updated_at_fallback` con mensaje correcto, salida ampliada (`eligibility_status`, razones, corte, política de filas), mensajes en `messages_es.py`, `validator_version`. Módulo puro, probado en aislamiento — no requiere el grafo.
  - ✅ Los casos de prueba obligatorios del contrato (§5) pasan.
- [ ] **T-403 Módulo de afirmaciones cuantitativas (nodo determinista T7, RF-208).** `app/quality/claims.py` según `contracts/agent-tools.md` T7: DSL JSON de fórmulas, evaluador seguro, formato es-CO de `display_value`, canonicalización de `source_hash` como hash de contenido reproducible entre corridas (sin `evidence_id`, `claim_id` ni `run_id`), definición normativa de “cifra”, persistencia en `quantitative_claims`, y verificador de cifras huérfanas para el texto del sintetizador. Módulo puro, probado en aislamiento.
  - ✅ Casos de pruebas.md §2.1 (claims) en verde, incluido detector de cifras huérfanas y pruebas de que cambiar solo UUIDs de corrida/evidencia/claim no cambia `source_hash`.
- [ ] **T-303 Integrar el grafo del agente.** `app/agent/graph.py` según plan.md §1: planificador → enrutador → herramientas T1–T5 (T-302) → nodo validador T6 (T-401) → nodo constructor de afirmaciones T7 (T-403) → sintetizador restringido (solo `display_value` de claims; cifras huérfanas bloquean y fuerzan re-síntesis, máx. 2 intentos, luego `failed`), con presupuestos del contrato de tools, checkpointer PostgreSQL, heartbeat, eventos numerados en `agent_run_events` y persistencia de `agent_runs`/`agent_steps` (RF-703, RF-209), sobre la base del PoC de T-300. Prompts en `app/agent/prompts/`, versionados.
  - ✅ En consola: la pregunta de ESC-02 produce respuesta con evidencias reales, `claims[]` completos y cero cifras huérfanas en ≤ 10 pasos; matar el proceso a mitad de corrida deja estado `interrupted` coherente al reiniciar.
- [ ] **T-304 Endpoints del agente.** `POST /v2/agent/query` (endpoint público siempre `retention_class=user`, emite `run_access_token` una sola vez y guarda solo el hash), `GET /v2/agent/stream/{run_id}` (SSE con `id:` de secuencia, `Last-Event-ID`, autorización Bearer y evento terminal con `status`), `GET /v2/agent/runs/{run_id}` (Bearer, esquemas para `running`, `completed`, `no_evidence`, `interrupted`, `failed`) y `DELETE /v2/agent/runs/{run_id}` (borrado RF-803 + `adelete_thread`, incluida corrida activa), según el contrato REST; rate limiting global por proceso; cierre de corridas huérfanas y timeout según plan.md §11. Si un acceso encuentra corrida vencida, ejecuta borrado oportunista y responde `404 RUN_NOT_FOUND`.
  - ✅ `curl -N` con Bearer muestra eventos en vivo y termina con `answer`; sin token → 401; token `user` expira según retención; reconexión con `Last-Event-ID` no pierde ni duplica; `GET` valida los cinco estados; `DELETE` borra checkpoints y el `GET` posterior da 404.
- [ ] **T-306 Job de retención y purga.** Implementar barrido RF-804 como servicio/CLI idempotente del backend y endpoint admin `POST /v2/admin/retention/run`: corridas `user`, corridas `eval`, `technical_metrics` vencidas, borrado oportunista compartido con T-304, copia atómica de métricas con `source_run_hash = sha256(run_id + RETENTION_HASH_SALT)`, snapshot eval, `adelete_thread(run_id)`, borrado físico y reintento idempotente ante fallos. Preparar ejecución lógica única ante concurrencia con advisory lock transaccional PostgreSQL `pg_try_advisory_xact_lock(20260707, 804)`; si otro barrido ya tiene el lock, responder/registrar `already_running` sin efectos. Documentar la programación externa cada 6 horas mediante scheduler del proveedor o workflow programado autenticado con `ADMIN_TOKEN`; SLA de borrado físico máximo 24 horas desde vencimiento lógico.
  - ✅ Pruebas con reloj simulado cubren `user`, `eval`, `technical_metrics`, concurrencia DELETE/job, dos barridos simultáneos, reintento tras fallo de checkpoints e idempotencia sin duplicar métricas; quickstart permite ejecución manual local.
- [ ] **T-305 Casos de honestidad.** Probar manualmente ESC-03 (pregunta sin respuesta en el catálogo): el agente debe producir `no_evidence_report` sin cifras inventadas.
  - ✅ 3 preguntas negativas manuales pasan; se registran como semillas del golden set (T-601).

## FASE 4 — Verificación integrada de las capas deterministas (RF-401…404, RF-208)

*Nota de reordenamiento: T-401 y T-403 se ejecutan dentro de la Fase 3 (antes de T-303) porque el grafo los integra; se conservan sus IDs. Esta fase verifica la integración de punta a punta con datos reales.*

- [ ] **T-402 Verificación integrada de calidad y claims.** Con el grafo completo (T-303): el nodo `quality_validator` corre SIEMPRE tras cada `ejecutar_soql` (imposible saltarlo); el objeto `quality` viaja en cada Evidencia; el sintetizador ajusta la narrativa según la clasificación (`baja` ⇒ mencionar limitación; `no_recomendada` ⇒ evidencia no elegible como sustento); los claims heredan las advertencias de su evidencia fuente.
  - ✅ ESC-05 reproducido con un dataset viejo real: advertencia visible en la respuesta; una respuesta real de ESC-01 muestra `claims[]` y cero cifras huérfanas; un dataset de publicador no oficial es rechazado con explicación clara.

## FASE 5 — Frontend v2 (RF-101…104, RF-501…503, RNF-007/008, Art. V)

- [ ] **T-501 Sistema de diseño azul.** Aplicar los tokens de plan.md §7 en `tailwind.config.js`; refactorizar componentes a la paleta; eliminar colores fuera de paleta salvo semánticos. Objetivo de accesibilidad: WCAG 2.2 nivel AA.
  - ✅ Revisión visual página por página + captura de pantalla en el PR; Lighthouse/axe accesibilidad ≥ 95 como puerta parcial (RNF-007) — la conformidad se completa con la revisión manual de T-505.
- [ ] **T-502 Conectar el copiloto al backend v2.** Reemplazar el fetch a `/api/consultar_v2` por el flujo `query` → SSE consumido con fetch-stream (el token Bearer viaja por encabezado; `EventSource` nativo no sirve — plan.md §11): pasos del agente renderizados en vivo como línea de tiempo en lenguaje claro, con detalle técnico expandible (ESC-04); reconexión automática con `Last-Event-ID`; el `run_access_token` se guarda junto al historial local de la sesión. Aviso de consentimiento ANTES de la primera investigación (RF-802: qué se guarda, para qué, por cuánto tiempo, cómo borrarlo) y acción "borrar esta investigación" que llama al `DELETE` (RF-803). Historial de sesión con re-ejecución/refinado de consultas anteriores (RF-502); todos los textos en español (RNF-012). Conexión DIRECTA del navegador al backend vía `NEXT_PUBLIC_BACKEND_URL` (sin proxy en Next.js); configurar `CORSMiddleware` en FastAPI restringido a los orígenes del frontend (plan.md §11).
  - ✅ RNF-008 medido: primer feedback < 500 ms, primer paso < 2 s; cortar la red a mitad de corrida y recuperarla continúa el stream sin duplicar pasos; el aviso de consentimiento aparece antes de la primera investigación.
- [ ] **T-503 Tarjetas de evidencia v2.** Mostrar tabla + badge de calidad + advertencias + narrativa citable + botón "insertar en sección" y descarga CSV (RF-501). Gráfica simple cuando `chart_suggestion` no es null (RF-503). Flujo de confirmación para `no_recomendada` (RF-404).
  - ✅ ESC-01 completo de punta a punta en local.
- [ ] **T-504 Citas y persistencia del documento.** Extensión Tiptap "cita de evidencia" que fija el objeto `citation` al fragmento insertado (RF-103); autoguardado en localStorage ≤ 5 s (RF-102); exportación a `.docx` con citas al pie (RF-102/103).
  - ✅ ESC-08: cerrar y reabrir el navegador conserva documento y citas; el .docx exportado muestra las citas.
- [ ] **T-505 Pruebas E2E, accesibilidad y RNF-012.** Playwright: ESC-01 feliz, ESC-03 sin evidencia, navegación por teclado del flujo principal. Además, revisión MANUAL de accesibilidad WCAG 2.2 AA según la lista de pruebas.md §5 (teclado, orden y visibilidad de foco, lector de pantalla, zoom y reflujo a 320 px, anuncios de contenido SSE con `aria-live` sin saturar, reducción de movimiento, no depender solo del color). Revisar RNF-012 con checklist manual: etiquetas del frontend, mensajes de error, `message_user`, advertencias de calidad, estados/mensajes SSE, consentimiento, retención/borrado, "sin evidencia" y ausencia de jerga técnica sin explicación. Las herramientas automáticas son auxiliares (RNF-007).
  - ✅ Suite E2E en CI (con backend mockeado por fixtures) + acta de revisión manual WCAG y acta RNF-012 archivadas en `docs/`.

## FASE 6 — Evaluación técnica OE3 (RF-601…603)

*Objetivo: la batería que produce las métricas del working paper (Producto 3 de la propuesta).*

- [ ] **T-601 🧑 Construir el golden set v1 (ESC-06).** 50 casos en `backend/eval/golden/golden-v1.yaml`: ~40 positivos (pregunta + `expected_dataset_ids` + hechos verificados a mano contra el portal) y ~10 negativos (RNF-005). **Requiere tu criterio de politólogo:** las preguntas deben representar necesidades reales de funcionarios (usa los hallazgos del OE1 cuando existan). Documentar cada caso en `notes`.
  - ✅ Revisión cruzada: cada `expected_dataset_id` verificado manualmente en datos.gov.co.
- [ ] **T-602 Runner de evaluación (ESC-06).** CLI `python -m eval.run --suite golden-v1 --provider google --model gemini-2.5-flash --seed <int>`: ejecuta cada caso contra el grafo real con semilla y `config_snapshot` persistidos, calcula recall@10, éxito, `socrata_success_rate`, **groundedness por verificación de claims** (cada cifra del texto tiene claim; operandos existen en las filas fuente; la fórmula DSL re-ejecutada reproduce `raw_value`; el redondeo produce `display_value`; el texto coincide con `display_value` — la coincidencia literal por regex queda solo como detector auxiliar de cifras huérfanas, pruebas.md §4.2), fabricaciones en negativos, latencias simples/multi-paso y costo; persiste `eval_runs`/`eval_case_results` y emite reporte Markdown en `backend/eval/reports/`.
  - ✅ Corrida completa contra Gemini termina y el reporte muestra las métricas de RNF-001…005.
- [ ] **T-603 🧑 Corridas comparativas (ESC-06).** Ejecutar la batería con ≥ 2 configuraciones (p. ej. Gemini 2.5 Flash vs Claude vs Gemini Pro). **Tú decides** las configuraciones finales según presupuesto. Analizar en `notebooks/02_analisis_eval.ipynb`.
  - ✅ Tabla comparativa lista para el working paper; configuración ganadora fijada como default.
- [ ] **T-604 Puertas RNF-002.** Configurar tres niveles: cada PR corre pruebas deterministas con LLM guionado y smoke reducido sin LLM real; semanalmente corre golden set con LLM real y abre issue/alerta si hay regresión o `success_rate < 80%`; antes de release corre golden completo y bloquea el release si `success_rate < 80%`.
  - ✅ Workflows visibles en Actions: PR determinista bloqueante, semanal con issue/alerta, y pre-release bloqueante.

## FASE 7 — Endurecimiento y despliegue

- [ ] **T-701 🧑 Desplegar el backend.** Railway/Render: servicio desde `backend/` con las variables de `.env.example` como secrets (usa los valores reales de la Fase 0). Conectar dominio `api.cuestiondedatos.com` (añadir CNAME en tu DNS). Crear el cron externo de retención cada 6 horas, registrar `ADMIN_TOKEN` y `RETENTION_HASH_SALT` como secretos, verificar la primera ejecución de `POST /v2/admin/retention/run` y revisar fallos.
  - ✅ `https://api.cuestiondedatos.com/v2/health` responde `ok` desde internet; primera ejecución de retención registrada en logs/métricas.
- [ ] **T-702 🧑 Desplegar el frontend.** En Vercel, apuntar el proyecto existente a `frontend/` de la rama `v2` con `NEXT_PUBLIC_BACKEND_URL=https://api.cuestiondedatos.com` como variable de entorno; verificar que el CORS del backend incluye el dominio del preview de Vercel durante las pruebas. Probar en preview antes de promover a producción (cuestiondedatos.com).
  - ✅ ESC-01 funciona en el dominio de preview y luego en producción.
- [ ] **T-703 🧑 Monitoreo.** UptimeRobot sobre `/v2/health` cada 5 min con alerta a tu correo (RNF-006); revisar `GET /v2/admin/metrics` tras la primera semana para verificar RNF-001/009 con tráfico real.
  - ✅ Monitor activo; primer reporte semanal de métricas archivado en `docs/`.
- [ ] **T-704 Retirar el endpoint v1.** Eliminar `pages/api/consultar_v2.js`, `utils/systemPrompt.js` y `utils/maestro_divipola.js` (ya reemplazados). Actualizar README.md raíz con la arquitectura v2.0 y CHANGELOG a `2.0.0`.
  - ✅ Sin referencias muertas (`grep` de los archivos borrados no encuentra imports).
- [ ] **T-705 🧑 Cierre documental.** Verificar los criterios de cierre de plan.md §10; capturar evidencia (reportes, métricas, screenshots) en `docs/`; preparar la actualización del registro en herramientas.datos.gov.co y del sitio divulgativo/producto público con la documentación de los nuevos componentes, sin convertir OE1/OE4 en funcionalidad de software.
  - ✅ Checklist de plan.md §10 completo y archivado.

---

## Dependencias entre fases

```
F0 ──▶ F1 ──▶ F2 ──▶ F3 ──▶ F4 ──▶ F5 ──▶ F7
                      └────────────▶ F6 ──▶ F7   (F6 puede iniciar al terminar F3/F4)
```

**Ruta backend ejecutable hasta T-403:** T-105 → T-102 → T-103 → T-104A → T-106 → T-201 → T-201A → T-202 → T-205 → T-104B → T-203 → T-204 → T-300 → T-301 → T-302 → T-401 → T-403. Para cerrar los endpoints y la retención después de T-403: T-303 → T-304 → T-306 → T-305. T-102 y T-104A dependen de la base local de T-105; T-205 depende de T-202 para consultas territoriales; T-104B depende de la decisión humana de T-205.

## Resumen de acciones humanas (🧑) para planear tu agenda

| Tarea | Qué haces tú | Tiempo estimado |
|---|---|---|
| T-001/002/003 | Instalar Docker Desktop y crear cuentas/claves (Anthropic; Supabase y Railway solo para despliegue) | 1–2 h |
| T-205 | Decidir modelo de embeddings y dimensión con el benchmark (research.md §1) | 2–3 h |
| T-601 | Construir y verificar el golden set (criterio experto) | 2–3 días |
| T-603 | Decidir configuraciones comparativas y analizar | 1 día |
| T-701/702/703 | Despliegues, DNS y monitoreo | 2–4 h |
| T-705 | Cierre documental y registro MinTIC | 1 día |
