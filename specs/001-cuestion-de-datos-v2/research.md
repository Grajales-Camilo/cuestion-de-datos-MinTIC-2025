# Registro de Investigación y Decisiones Técnicas — Cuestión de Datos v2.0

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Propósito:** documentar decisiones técnicas que requieren evaluación experimental o análisis de alternativas, con su estado (`PENDIENTE` / `DECIDIDA`). Ningún documento del paquete SDD debe presentar como definitiva una decisión que aquí figure como pendiente.

---

## 1. Decisión registrada: modelo de embeddings — `DECIDIDA`

**Problema.** El índice semántico del catálogo (RF-301…304) necesita un modelo de embeddings multilingüe con buen desempeño en español administrativo colombiano (títulos y descripciones de datasets estatales, topónimos DIVIPOLA). La elección fija la dimensión vectorial de `catalog_embeddings`, por lo que la migración definitiva de esa tabla (T-104B) NO puede crearse antes de esta decisión.

**Alternativas.**

| Candidato | Tipo | Dimensión | Notas |
|---|---|---|---|
| `intfloat/multilingual-e5-large` | Local (sentence-transformers) | 1024 | Citado en la propuesta de maestría; sin costo por consulta; exige CPU/RAM del servidor. |
| `gemini-embedding-2` | Gestionado (API Google) | según configuración del proveedor | Sin carga en el servidor; costo por token; dependencia de proveedor. |
| Otro modelo multilingüe actual | Local o gestionado | — | PUEDE incorporarse al benchmark si se justifica aquí por desempeño en español o eficiencia (documentar antes de evaluar). |

**Criterios de selección (todos se miden en el benchmark):**
1. Recuperación en español (recall@10 sobre consultas de prueba).
2. Calidad sobre consultas territoriales colombianas (municipios, departamentos, jerga administrativa).
3. Dimensión de los vectores (impacto en almacenamiento e índice HNSW).
4. Latencia (embedding de consulta en caliente, p95).
5. Costo (por 1.000 consultas y por reindexación completa del catálogo).
6. Capacidad de ejecución local (¿corre en el servidor del piloto?).
7. Dependencia de proveedor (lock-in, riesgo de deprecación).
8. Reproducibilidad (¿un tercero puede regenerar el índice idéntico?).
9. Tamaño del índice resultante (~8.000 vectores × dimensión).
10. Compatibilidad con PostgreSQL + pgvector (límites de dimensión del índice HNSW).

**Procedimiento de benchmark (T-205, reproducible):** notebook `notebooks/01_benchmark_embeddings.ipynb` versionado, con: (a) entorno instalado desde `backend/pyproject.toml` mediante el extra opcional de investigación `benchmark-embeddings`; (b) muestra fija de metadatos ya ingeridos (T-201) y maestro DIVIPOLA cargado (T-202), congelados como fixture; (c) ≥ 30 consultas de prueba en español con dataset esperado anotado a mano (incluidas ≥ 10 territoriales); (d) las mismas consultas contra cada candidato; (e) tabla comparativa contra los 10 criterios; (f) decisión razonada firmada por el responsable del proyecto.

**Dependencias de investigación para T-205.** T-102 PUEDE preparar un grupo opcional en `backend/pyproject.toml` exclusivamente para ejecutar el benchmark, por ejemplo:

```toml
[project.optional-dependencies]
benchmark-embeddings = [
    "sentence-transformers==<VERSION_COMPATIBLE_PY312>",
    "torch==<VERSION_COMPATIBLE_PY312>"
]
```

T-205 debe comprobar y fijar versiones compatibles con Python 3.12 antes de ejecutar el benchmark local, registrar esas versiones y usar un comando reproducible equivalente a `pip install -e ".[dev,benchmark-embeddings]"`. Estas dependencias opcionales NO convierten al modelo local en decisión de runtime. La dependencia definitiva de runtime se incorpora solo después de que T-205 registre el modelo ganador, dimensión, tipo `vector`/`halfvec` y justificación.

**Decisión (T-205, 2026-07-09):** `gemini-embedding-2` (Google, gestionado), dimensión **768**, columna `vector(768)` con `vector_cosine_ops` (no requiere `halfvec`).

**Evidencia del benchmark** (`notebooks/01_benchmark_embeddings.ipynb`, muestra congelada `notebooks/fixtures/`: 200 datasets reales de T-201 + 1.155 filas reales de T-202; 34 consultas anotadas a mano, 11 territoriales):

| Criterio | `intfloat/multilingual-e5-large` (local) | `gemini-embedding-2` (gestionado) |
|---|---|---|
| 1. recall@10 (todas) | 94,12% | 94,12% |
| 2. recall@10 (territoriales) | 90,91% | 90,91% |
| 3. dimensión | 1024 | 768 |
| 4. latencia p95 embed consulta | 120,2 ms | 41,8 ms |
| 5. costo (corpus 200 + 34 consultas, tokens reales) | $0,00 (API) | $0,0092 |
| 5. costo reindexación completa (~8.416 datasets activos) | $0,00 (API) | $0,39 (evento raro, no recurrente) |
| 6. ¿corre en el servidor del piloto? | RAM pico medida: **2.430,7 MB** — excede el tier gratuito de Railway (0,5 GB); como RF-302 exige embeber la consulta "en caliente" en el mismo proceso del backend, esa RAM queda reservada de forma permanente dentro del tier Hobby (~USD 5/mes, plan.md §2) sin importar el volumen de uso | Sin huella de RAM relevante en el backend (solo llamada HTTP) |
| 7. dependencia de proveedor | Ninguna (pesos abiertos) | Alta (API de Google) |
| 8. reproducibilidad | Sí (determinístico, CPU) | No (modelo cerrado, solo vía API) |
| 9. tamaño de índice (catálogo completo) | 32,88 MB | 24,66 MB |
| 10. compatibilidad pgvector | `vector(1024)` ✓ | `vector(768)` ✓ |

**Justificación.** Recall@10 empata exactamente en ambos candidatos (criterios 1-2) — no discrimina. `gemini-embedding-2` gana en latencia real (~3x más rápido) y, sobre todo, evita el costo de infraestructura que impone el local: su pico de RAM medido (2,43 GB) es incompatible con el tier gratuito de Railway y consume de forma permanente una porción fija del tier Hobby presupuestado en `plan.md`, independientemente del volumen real de consultas. El costo de la API gestionada es marginal al volumen del piloto (`spec.md` SUP-02, ~500 investigaciones/mes) y la reindexación completa es un evento raro y acotado (~$0,39 al tamaño actual del catálogo). Se acepta conscientemente perder los criterios 7 y 8 (dependencia de proveedor y reproducibilidad, donde el local es superior): el proyecto ya tiene precedente arquitectónico de capa multi-proveedor para el LLM (RF-206), y cambiar de modelo de embeddings en el futuro exige regenerar el índice completo — costo conocido y acotado, no catastrófico. Firmado por Juan Camilo Grajales B., 2026-07-09.

**Consecuencias de la decisión:**
- `<DIM>` en `data-model.md` §`catalog_embeddings` queda fijado en `768`; T-104B puede crear la migración definitiva (`vector(768)` + `vector_cosine_ops`).
- `EMBEDDING_MODEL=gemini-embedding-2` en `.env.example` y `quickstart.md`.
- NO se mezclan embeddings de modelos o dimensiones distintas en un mismo índice; cambiar de modelo después exige regenerar el índice completo o versionar índices separados (tabla por modelo).
- El cron de ingesta (T-206) necesita `GOOGLE_API_KEY` como secret — ya es una dependencia existente del proyecto (LLM por defecto), no una nueva.
- Restricción de compatibilidad pgvector satisfecha: `DIM=768 <= 2000`, se mantiene `vector` + `vector_cosine_ops`, sin necesidad de `halfvec`.

## 2. Decisión registrada: durabilidad de corridas y SSE — `DECIDIDA (piloto)`

**Problema.** El contrato promete `202` + stream + recuperación tras desconexión: eso exige que las corridas sobrevivan a cortes de red y reinicios del proceso, sin depender de la memoria de FastAPI.

**Alternativas consideradas:** (a) cola externa con workers (Celery/Redis, RQ) — descartada para el piloto por Art. III (máximo 2 servicios; complejidad no justificada a ~500 corridas/mes); (b) todo en memoria — descartada por violar RF-209; (c) **elegida:** un único worker + estado y eventos en PostgreSQL + secuencia de eventos por corrida + reconexión `Last-Event-ID` (detalle normativo en plan.md §11).

**Semántica única (revisión 3):** la desconexión del navegador NO interrumpe la ejecución; los eventos se reanudan con `Last-Event-ID`; un reinicio del proceso SÍ interrumpe la corrida activa, que queda en estado TERMINAL `interrupted` con eventos y resultados parciales disponibles; el usuario vuelve a ejecutar la consulta. Al arrancar, cada proceso genera un `worker_instance_id` y marca de forma idempotente como `interrupted` toda corrida `running` asociada a una instancia anterior. El heartbeat queda como mecanismo adicional para detectar workers muertos durante la operación. Se descartó la reanudación automática del trabajo del agente: prometer resurrección del grafo tras matar el único worker es frágil y deshonesto para un piloto; el checkpointer de LangGraph queda solo para inspección/diagnóstico.

**Decisión sobre timeout:** la duración máxima excedida termina como `failed` con código `RUN_TIMEOUT`, no como `interrupted`. Justificación: el timeout es un límite operacional definido por configuración (`RUN_MAX_DURATION_S`) y por tanto representa una falla controlada de ejecución, distinta de una interrupción externa causada por reinicio, heartbeat vencido o desaparición del worker. Esta separación permite medir problemas de latencia y costo sin mezclarlos con reinicios de infraestructura.

**Lease de instancia:** para evitar que un despliegue con dos procesos solapados interrumpa corridas sanas, `worker_instance_id` no basta por sí solo. Cada instancia mantiene una lease en `worker_instances`; al arrancar, el backend solo cierra corridas de otra instancia si la lease de esa instancia ya venció. Política normativa: `WORKER_LEASE_TTL_S = RUN_HEARTBEAT_TIMEOUT_S` por defecto y renovación cada tercio de ese TTL. El piloto limita la concurrencia con `MAX_CONCURRENT_RUNS`, pero no asume que solo pueda existir un proceso durante despliegues; la lease es la fuente de verdad para decidir si una instancia murió.

**Condición de revisión:** si el piloto supera ~2.000 corridas/mes o se necesita más de un worker, esta decisión se reabre aquí (la cola externa pasa a ser candidata) y requiere enmienda de plan.md §11 y Constitución Art. III.3.

**Aclaración `RUN_INTERRUPTED` vs `WORKER_LOST` (T-300, 2026-07-09).** plan.md §11 permite persistir el evento terminal con código `RUN_INTERRUPTED` **o** `WORKER_LOST` al cerrar corridas huérfanas, sin regla explícita de cuándo usar cada uno; el PoC de T-300 necesitó una regla determinista para implementar y probar ambos casos de la tabla de semántica única sin ambigüedad. Convención adoptada: `RUN_INTERRUPTED` lo escribe el **arranque idempotente** (una instancia nueva descubre, al iniciar, corridas `running` de una instancia anterior con lease vencida — plan.md §11 "Arranque idempotente"); `WORKER_LOST` lo escribe el **barrido periódico** (plan.md §11 "Corridas huérfanas") cuando detecta, durante la operación normal (sin que la propia instancia se haya reiniciado), que la lease del `worker_instance` dueño de una corrida venció. `HEARTBEAT_EXPIRED` sigue siendo un chequeo independiente de ambos (heartbeat propio de la corrida, no de la instancia). Motivo práctico verificado en T-300: con el piso `WORKER_LEASE_TTL_S >= 30` (config.py), reiniciar el proceso inmediatamente después de matarlo NO produce `RUN_INTERRUPTED` de inmediato si la lease todavía no venció — el arranque idempotente respeta correctamente la lease vigente (research.md §2 "Lease de instancia"); la interrupción solo se observa una vez vencida la lease, ya sea porque el proceso reiniciado la encuentra vencida al arrancar (`RUN_INTERRUPTED`) o porque el barrido periódico la detecta en operación (`WORKER_LOST`). La demo/prueba de T-300 que mata el proceso de verdad espera explícitamente ese piso de 30s antes de reiniciar, documentado en `backend/tests/integration/test_t300_durability.py`.

## 3. Decisión registrada: acceso a corridas persistidas — `DECIDIDA (piloto)`

**Problema.** Un `run_id` adivinable o filtrado no debe dar acceso a preguntas, contexto y trazas de otra persona. El piloto no tiene cuentas de usuario (fuera de alcance v2.0).

**Alternativas consideradas:** (a) UUID como capacidad implícita — descartada: un identificador no es autorización; (b) autenticación completa de usuarios — descartada en v2.0 por alcance; (c) **elegida:** token secreto por corrida (`run_access_token`, ≥ 256 bits) entregado una sola vez, hash SHA-256 en servidor, transmisión exclusiva por `Authorization: Bearer` (nunca URL). Normativo en RF-801 y contracts/api-rest.md.

**Alineación TTL–retención (revisión 3):** el token expira exactamente cuando vence la retención de los datos de su clase. Regla normativa: `user` ⇒ `created_at + RETENTION_USER_DAYS`; `eval` ⇒ `created_at + RETENTION_EVAL_MONTHS`. Se descartó un TTL único basado solo en `RETENTION_USER_DAYS` porque dejaría corridas `eval` retenidas durante 24 meses pero inaccesibles e imborrables por token. Se descartó un TTL más corto que la retención (dejaría datos retenidos pero inaccesibles e imborrables por su dueño) y también la renovación de tokens (sin cuentas de usuario no hay forma segura de demostrar quién puede renovar).

**Creación de corridas `eval`:** el contrato público no acepta `retention_class`. `POST /v2/agent/query` siempre crea corridas `user`. El runner OE3 crea corridas `eval` mediante una función/repositorio interno del backend, habilitado solo con `EVAL_MODE=true` en entorno controlado. `EVAL_MODE` no se activa en el backend público.

**Condición de revisión:** si v2.x introduce cuentas de usuario, el token por corrida se subordina a la identidad (las corridas pasan a pertenecer a un usuario) — enmienda de spec.md Grupo 800.

## 4. Decisión registrada: política de retención — `DECIDIDA (valores provisionales)`

**Problema.** Retener todo 12 meses trataba igual datos de usuarios reales y corridas de evaluación, sin base de minimización.

**Decisión (revisada en revisión 3):** dos clases de corrida (`user` 90 días, `eval` 24 meses), valores **configurables** por entorno. Al vencer la retención (o ante borrado por solicitud, que tiene prioridad): **borrado completo** de la corrida operativa y todas sus relaciones con contenido de usuario, tras copiar métricas agregadas no identificables a la tabla independiente `technical_metrics` (12 meses). Para OE3, `eval_case_results.agent_run_id` es nullable con FK `ON DELETE SET NULL` y conserva una instantánea no identificable de métricas por caso (`status_final`, hit de dataset esperado, métricas de claims, latencia, costo, códigos de error, hashes/fingerprints técnicos y resumen de calidad), sin pregunta de usuario, contexto, filas, narrativas ni eventos. Se descartó la anonimización fila a fila: era incompatible con los campos `NOT NULL` del modelo (p. ej. `question`) y dejaba copias residuales en `final_answer`, `tool_input/output`, eventos, narrativas y citas; el borrado total + métricas separadas es ejecutable literalmente. Los valores son provisionales del piloto: la validación aplicada (OE4) con las alcaldías puede exigir ajustarlos; cualquier cambio se registra aquí.

**SLA de borrado:** una corrida vencida no debe permanecer accesible. Si una solicitud `GET`, `stream` o `DELETE` encuentra una corrida vencida, ejecuta borrado oportunista antes de responder (`404` posterior). El job periódico de retención debe borrar físicamente corridas vencidas en un máximo de 24 horas desde el vencimiento lógico; fallos se registran y reintentan sin duplicar métricas ni eventos.

**Programación del job de retención (piloto).** La lógica vive en el backend como servicio/CLI idempotente reutilizado por el endpoint administrativo `POST /v2/admin/retention/run`. La ejecución periódica se programa fuera de FastAPI cada 6 horas mediante el scheduler del proveedor de despliegue o un workflow programado, autenticado con `ADMIN_TOKEN`. No se añade un scheduler persistente dentro del proceso ni servicios nuevos (Art. III). Para asegurar una única ejecución lógica ante despliegues solapados o reintentos, cada barrido debe intentar adquirir al inicio un advisory lock transaccional de PostgreSQL con clave fija del proyecto (`pg_try_advisory_xact_lock(20260707, 804)`). Si no adquiere el lock, no copia métricas ni borra datos y responde como ejecución omitida por `already_running`. Si lo adquiere, registra métricas/logs de cada barrido y conserva el SLA de borrado físico dentro de las 24 horas posteriores al vencimiento lógico. `technical_metrics.source_run_hash` se calcula con `RETENTION_HASH_SALT`, secreto servidor obligatorio en prod/eval; rotarlo durante reintentos pendientes puede romper la deduplicación y solo debe hacerse después de cerrar barridos en curso. En despliegue, el humano debe crear el cron externo, registrar `ADMIN_TOKEN` y `RETENTION_HASH_SALT` como secretos, verificar la primera ejecución y revisar fallos.

## 5. Decisión registrada: modelo de afirmaciones cuantitativas — `DECIDIDA`

**Problema.** Verificar groundedness por coincidencia literal de cifras (regex sobre `rows`) falla con porcentajes calculados, sumas, promedios, tasas, redondeos, conversiones de unidades, formatos de miles y fechas: ni valida lo derivado ni impide que el LLM "calcule" mal en la narrativa.

**Decisión:** toda cifra presentada nace de un **claim** estructurado (`quantitative_claims`, RF-208): filas fuente + columnas + fórmula + valor bruto + valor presentado + unidad + redondeo + hash reproducible. Los claims `derived` los computa un evaluador determinista (herramienta T7), no el LLM; el sintetizador solo cita `display_value`. El verificador de groundedness re-ejecuta la cadena completa (pruebas.md §4.2); la regex sobrevive únicamente como detector auxiliar de cifras huérfanas.

**Semántica única de `source_hash`.** `source_hash` es un hash de contenido reproducible entre corridas, no un identificador de instancia. Se calcula sobre una representación canónica que incluye, como mínimo: versión del algoritmo, `dataset_id`, consulta SoQL canonicalizada, filas fuente seleccionadas y ordenadas por una regla determinista documentada, columnas usadas, DSL de fórmula canonicalizada, `raw_value`, unidad y regla de redondeo. No se incluyen identificadores aleatorios o de instancia (`evidence_id`, `claim_id`, `run_id`) ni marcas de tiempo de ejecución. Cambiar fórmula, fila fuente, contenido de fila, `raw_value`, unidad o redondeo debe cambiar el hash; cambiar solo UUIDs de corrida/evidencia/claim no debe cambiarlo.

**Alternativa descartada:** regex + normalización numérica como mecanismo principal — insuficiente por las razones del problema; se documenta para no reintroducirla.

## 6. Decisión registrada: conexión frontend→backend para SSE — `DECIDIDA`

**Problema.** El diseño inicial hacía pasar todo el tráfico (incluido el stream SSE de hasta 75 s) por un proxy serverless en Next.js/Vercel. Un proxy serverless introduce límites de duración, posible buffering y un comportamiento dependiente del runtime y del plan contratado, por lo que no es una ruta confiable para una conexión SSE durable como la que exigen RNF-008 (feedback en vivo) y RF-209 (reanudación); además, "ocultar la URL interna" no aporta: `api.cuestiondedatos.com` es pública.

**Alternativas consideradas:** (a) mantener el proxy y configurar streaming en Vercel — descartada: frágil, dependiente de límites del plan; (b) **elegida:** conexión directa del navegador a FastAPI con `CORSMiddleware` restringido a los orígenes del frontend, consumiendo el SSE con `fetch()` + stream de lectura — nunca `EventSource` nativo, que no admite el encabezado `Authorization` requerido por RF-801. Normativo en plan.md §11 y contracts/api-rest.md.

**Consecuencias:** variable `NEXT_PUBLIC_BACKEND_URL` en el frontend; CORS con orígenes de producción, preview y `localhost:3000`; se elimina el catch-all `pages/api/v2/[...path].js` del diseño (T-502/T-702 actualizadas).

## 7. Decisión registrada: publicadores oficiales — `DECIDIDA`

**Problema.** La regla de rechazar fuentes no oficiales no es implementable si `publisher` es solo texto libre: nombres con tildes, siglas, abreviaturas o cambios institucionales podrían aceptar o rechazar datasets de forma no reproducible.

**Decisión:** se crea un registro versionado de publicadores oficiales (`official_publishers`) y una tabla normalizada de alias (`official_publisher_aliases`) cargados desde un fixture canónico del repositorio y mantenidos con procedencia explícita. Cada publicador conserva: `id` estable, nombre canónico, tipo de entidad, estado, fuente de verificación y fecha de actualización. Cada alias conserva su forma normalizada, fuente y estado de ambigüedad. La ingesta normaliza el nombre del publicador del catálogo y lo enlaza a `official_publishers.id`; si no hay coincidencia única y activa/histórica válida, el dataset queda `publisher_verification_status = "unknown"` y la evidencia no es elegible hasta revisar el fixture.

**Reglas de normalización:** trim, colapso de espacios, mayúsculas, eliminación de tildes y signos de puntuación no significativos, equivalencias comunes (`MINISTERIO DE`/`MIN`, `ALCALDIA`/`MUNICIPIO`, siglas registradas como alias), y comparación contra alias normalizados versionados. No se permite una heurística opaca ni una lista embebida en código sin procedencia. Si un alias coincide con más de una entidad, se marca `official_publisher_aliases.ambiguous=true` y el dataset queda `publisher_verification_status="unknown"` con razón `publisher_alias_ambiguous`.

**Entidades con nombres variables:** universidades públicas, empresas industriales y comerciales del Estado, establecimientos públicos, alcaldías, gobernaciones y demás entidades estatales se aceptan solo si existen en el registro canónico como entidad activa o histórica válida al momento de publicación, o alias verificado. Las entidades inactivas pueden ser elegibles para datasets históricos si `valid_until` y, cuando exista, `successor_id` lo documentan. Una entidad privada o desconocida se rechaza para evidencia.

**Fuente y mantenimiento:** T-106 crea un fixture inicial no circular desde fuentes institucionales verificables: directorios oficiales de entidades públicas, páginas institucionales `.gov.co`/`.edu.co` cuando aplique, documentos de creación o transformación institucional y una referencia al publicador reportado por datos.gov.co solo como insumo, no como prueba única. T-201 usa ese fixture para ingestar; T-201A mide cobertura real y propone aliases nuevos. El fixture se actualiza por PR documental/datos, con `verification_source` por registro, fecha y justificación. Cobertura mínima: después de T-201A, al menos 90% de datasets tabulares activos deben quedar `verified`; los aliases ambiguos no cuentan como verificados.

## 8. Decisión registrada: fecha de actualización vs fecha de corte — `DECIDIDA`

**Problema.** La búsqueda de catálogo puede conocer `data_updated_at` desde metadatos del portal, pero no siempre puede conocer `data_cutoff_at`, que es la fecha estadística real de los datos.

**Decisión:** `metadata_synced_at` registra cuándo el índice sincronizó metadatos; `data_updated_at` registra cuándo el portal informa actualización del dataset; `catalog_datasets.latest_observed_cutoff_at` es solo una pista agregada para búsqueda; `evidence_results.data_cutoff_at` es el corte normativo y se calcula exclusivamente sobre las filas de esa evidencia. La inferencia de evidencia persiste método, columna usada, confianza, base utilizada e instante de inferencia. La UI y la API nunca presentan `data_updated_at` como corte estadístico.

**Consecuencia:** RF-302 puede devolver `latest_observed_cutoff_at` como pista, pero cada Evidencia puede tener un corte distinto. Si no se puede inferir `data_cutoff_at`, la calidad usa `data_updated_at` solo como fallback de antigüedad y el mensaje debe decir "fecha de actualización del portal; corte estadístico desconocido".

## 9. Decisión registrada: persistencia PostgreSQL y LangGraph — `DECIDIDA`

**Decisión:** el backend usa SQLAlchemy **asíncrono** con `psycopg` v3 como controlador PostgreSQL (`psycopg[binary,pool]`) y `AsyncEngine`/pool asíncrono para la aplicación. El checkpointer usa `langgraph-checkpoint-postgres` y `AsyncPostgresSaver`. En la inicialización del backend se ejecuta `.setup()` del checkpointer de forma idempotente. El `thread_id` de LangGraph es siempre `run_id`.

**Borrado:** RF-803 y el job de retención deben llamar a `adelete_thread(run_id)` antes de borrar la fila de `agent_runs`, dentro de la misma unidad operacional documentada; si el borrado de checkpoints falla, la transacción de borrado operativo no se considera completa y se reintenta.

## 10. Decisión registrada: health, rate limiting y SoQL — `DECIDIDA`

**Health:** `/v2/health` es una excepción explícita al sobre estándar de errores: responde `HealthResponse` tanto en `200` como en `503 degraded`, para que monitores puedan leer checks parciales.

**Concurrencia:** en el piloto se usa límite global por proceso (`MAX_CONCURRENT_RUNS`), no por IP persistida. No se almacena IP ni hash de IP en v2.0. Si se requiere límite por IP, debe diseñarse con minimización de datos.

**Parser SoQL:** T-302 implementa una gramática restringida propia con parser estructural mantenido en `app/tools/soql_parser.py` para el subconjunto permitido. Se prohíbe `SELECT *`; `OFFSET` máximo 5.000; alias solo en `SELECT` para agregados y deben resolverse al validar `ORDER BY`; literales permitidos: strings escapados, números, booleanos y fechas ISO; funciones permitidas son solo las listadas en `contracts/agent-tools.md`. La consulta se canonicaliza antes de persistirla.

## 11. Decisión registrada: privacidad y elegibilidad previa a Socrata — `DECIDIDA`

**Decisión:** la privacidad se decide antes de ejecutar T5. `pii_risk_level="unknown"` bloquea la consulta hasta clasificación; `high` o `contains_personal_data=true` bloquean siempre; `medium` solo permite consultas agregadas con columnas explícitas, sin filas individuales y con agregación mínima verificable (`count >= 5` por fila o equivalente). `low` puede continuar si el publicador y la API son elegibles.

**Revisión manual:** no existe aprobación manual ad hoc durante una corrida. Si un humano reclasifica un dataset o columna, la decisión queda versionada en el catálogo con `pii_reviewed_by`, `pii_reviewed_at`, `pii_review_source` y `pii_review_notes`; sin esos metadatos, la clasificación automática conserva su efecto.

**Razón:** la Constitución Art. VI prohíbe incorporar datos personales identificables. Una fuente oficial y pública no prueba por sí sola que sea segura para trazas, SSE o reproducción de evidencias.

## 12. Decisión registrada: configuración del backend — `DECIDIDA`

**Problema.** T-102 no puede crear un `.env.example` suficiente si la lista de variables, tipos y obligatoriedad está dispersa o incompleta.

**Decisión:** `plan.md` §12 es la fuente documental de configuración del backend. `EMBEDDING_MODEL` permanece sin valor por defecto hasta T-205; el resto de variables tiene propósito, tipo, obligatoriedad, entornos, validaciones y relación con requisitos.

## 13. Hallazgo registrado: calibración del clasificador PII y bugs de ejecución real bloqueando T-303 — `RESUELTO`

**Problema.** El criterio de aceptación literal de T-303 (ESC-02 produce `completed` con `claims[]` reales en ≤10 pasos) no pasó en la primera implementación. La causa raíz NO era el grafo del agente sino una cadena de problemas descubiertos únicamente al ejecutar contra Postgres/Socrata/Gemini reales (nunca visibles en pruebas con mocks, que es exactamente lo que este tipo de verificación de punta a punta está diseñada a exponer):

1. **Clasificador PII casi nunca resolvía `low`.** `app/quality/pii_classifier.py::classify_column` evaluaba el allowlist de `low` (patrones anclados `^...$`) contra el mismo haystack concatenado (`field_name+display_name+description`) que high/medium; con `description` no vacía (el caso normal en producción) el ancla de fin de cadena nunca se alcanzaba. Verificado contra el catálogo real ya ingerido (8.418 datasets): **0 de 2.611** datasets `api_active`+`publisher verified` resultaban `pii_risk_level=low`; **0 datasets eran `eligible`** en todo el catálogo. Ninguna pregunta, sin importar el tema, podía producir evidencia real mientras esto no se corrigiera.
2. **`httpx.AsyncClient()` sin `base_url` en `app/agent/runner.py`.** `SodaClient` construye rutas relativas (`/resource/{id}.json`); sin `base_url`, cada llamada real a Socrata (`perfilar_dataset`/`explorar_valores`/`ejecutar_soql`) lanzaba `httpx.UnsupportedProtocol` (subclase de `TransportError`) de forma instantánea, indistinguible en los logs de un timeout real porque el manejador de errores de `SodaClient.query` captura `(TimeoutException, TransportError)` con el mismo código `SOCRATA_TIMEOUT` tras 1 reintento. Esto hacía **estructuralmente imposible** que T2/T4/T5 tuvieran éxito alguna vez en una corrida real, para cualquier pregunta.
3. **`_count_alias` en `app/quality/validator.py` exigía alias explícito.** Una consulta `count(*)` sin `AS alias` (válida per RF-401: "incluir `count(*)` o agregado equivalente", sin exigir alias) hace que Socrata nombre la columna de salida literalmente `count`; `_count_alias` devolvía `None` si `item.alias` no era verdadero, y `_aggregation_min_count` trataba una fila con conteo real ≥5 como si no tuviera conteo, bloqueando evidencia PII `medium` genuinamente agregada.
4. **`ClaimSpecPayload.claim_type` como `str` libre en `app/agent/graph.py`.** El LLM podía (y lo hizo, en ejecución real) alucinar valores como `"direct_value"`, que `build_claims` rechaza correctamente (`claim_type` solo admite `direct`/`derived`, T-403) pero gastando un paso completo del presupuesto en el intento fallido.

**Decisión.** Se corrigen los cuatro puntos como bugs (no como cambios de contrato): (1) el allowlist de `low` se evalúa contra `display_name` (preferido, preserva tildes que Socrata reemplaza por `_` en `field_name`) o `field_name` normalizados, nunca concatenados con `description`; se amplía `pii_patterns.yaml` con los patrones reales observados (indicadores educativos MEN, código ETC, métricas institucionales). (2) `runner.py` pasa `base_url=SOCRATA_RESOURCE_BASE_URL` al construir el cliente HTTP compartido. (3) `_count_alias` retorna `"count"` como nombre por defecto cuando no hay alias explícito. (4) `claim_type` se restringe a `Literal["direct", "derived"]`, para que el proveedor de structured output nunca pueda producir un valor inválido.

**Verificación real (no simulada).** Tras las cuatro correcciones y un recálculo idempotente de PII/elegibilidad sobre el catálogo ya ingerido (`scripts/recompute_pii_eligibility.py`, sin re-consultar Socrata; 9 de 8.418 datasets pasaron a `eligible`, incluidos varios del Ministerio de Educación), la pregunta real *"¿Cuál fue el promedio de deserción escolar en el departamento de Antioquia entre 2018 y 2022?"* contra `ji8i-4anb` produjo `status=completed`, 2 `claims[]` aceptados, `quality.classification=alta`, en 7 pasos, con `synthesis_attempts=2` (el reintento por cifras huérfanas se activó y corrigió un intento real antes de aceptar la respuesta final).

**Hallazgo relacionado, NO resuelto aquí (seguimiento separado).** La pregunta original de ESC-02 ("...Oriente antioqueño...") sigue sin poder responderse: (a) el dataset candidato original `2d3i-f9wd` (cooperación internacional) carece de cualquier columna de municipio/departamento/subregión en su esquema; (b) `divipola_entries` solo modela dos niveles (`department`/`municipality`) — las subregiones administrativas de Antioquia (Oriente, Suroeste, Urabá, etc.) no existen en ningún lado del sistema de geografía, y `resolver_geografia` no tiene forma de expandir una subregión a sus municipios constituyentes. Resolver esto requiere un fixture nuevo (subregiones → códigos DIVIPOLA de municipio) y, si se quiere usar `2d3i-f9wd` específicamente, una revisión PII manual documentada (`pii_reviewed_by`/`pii_review_source`) de ese dataset. Ninguna de las dos cosas es responsabilidad de T-303; quedan como seguimiento para cuando se priorice ampliar la cobertura geográfica del catálogo o para T-601 (el propio hallazgo es un caso límite útil para el golden set).

**Consecuencias:** `backend/scripts/recompute_pii_eligibility.py` queda como utilidad reutilizable (idempotente) para cualquier futura recalibración del fixture PII sin re-ingestar desde Socrata. `quickstart.md` §5.3 actualiza la pregunta de demostración por consola a una verificada contra datos reales. Firmado por Juan Camilo Grajales B., 2026-07-10.

## 14. Hallazgo registrado: T4 `explorar_valores` incompatible con la gramática SoQL real — `RESUELTO`

**Problema.** Una verificación independiente de T-303 (posterior al cierre documentado en §13) encontró que el criterio literal seguía sin cumplirse: la demostración oficial terminó en `no_evidence`/`STEP_BUDGET_EXCEEDED` porque `explorar_valores` (T4, T-302) consumía dos ciclos de autocorrección fallidos antes de que el grafo forzara la síntesis sin llegar a `ejecutar_soql`. Causa raíz: `app/tools/explorar_valores.py` construía `upper(columna) LIKE upper('%termino%') ESCAPE '\'` — la cláusula `ESCAPE` es sintaxis SQL estándar que **la gramática SoQL de Socrata no soporta**; Socrata la rechaza con `400 query.compiler.malformed`. Las pruebas de T-302 (`test_tools_explorar_valores.py`) usan mocks (`respx`) que nunca validan la gramática real de Socrata, por lo que este bug existía desde T-302 y sobrevivió sin detectarse hasta esta segunda verificación real. El cierre documentado en §13 no lo detectó porque la corrida exitosa citada allí resolvió la ambigüedad geográfica sin pasar por T4 (fue directo a `perfilar_dataset` + `ejecutar_soql`); cerrar T-303 sin haber ejercitado esa ruta fue un descuido de cobertura, no solo un bug de código.

**Verificación empírica del mecanismo correcto (contra `ji8i-4anb` real).** Se confirmó que Socrata SÍ trata `\` como carácter de escape **por defecto**, sin necesidad (ni soporte) de declarar `ESCAPE`:
- `LIKE upper('_ntioquia')` (comodín `_` sin escapar) → matchea `"Antioquia"` (comodín activo, como se espera).
- `LIKE upper('\_ntioquia')` (escapado con `\`, SIN cláusula `ESCAPE`) → no matchea nada (tratado como literal, correcto).
- Mismo comportamiento verificado con `%`.

**Decisión.** Se elimina la cláusula ` ESCAPE '\'` de `explorar_valores.py`; `sanitize_like_term` (que ya escapaba `\`, `%`, `_` con backslash) no cambia — solo sobraba la cláusula final. Se añade `tests/integration/test_explorar_valores_live.py` (marcado `pytest.mark.integration`) que ejercita T4 contra Socrata real, cerrando el hueco de cobertura que pruebas.md §2.3 exige ("explorar_valores reales") y que T-302 nunca implementó.

**Verificación real posterior al fix:** una corrida real del grafo con una pregunta que fuerza al router a pasar por `explorar_valores` antes de `ejecutar_soql` muestra `tool:explorar_valores` con `{"ok": true, ...}` contra Socrata real (antes: `SOQL_SYNTAX`/`SOCRATA_TIMEOUT` según qué otro bug estuviera activo). Esa corrida específica terminó en `no_evidence` de todas formas, pero por la aritmética de presupuesto de pasos ya documentada (3 acciones de exploración antes de `ejecutar_soql` deja solo 4 de los 5 pasos que exige la cola obligatoria T5→T6→router→T7→sintetizador) — un comportamiento ya entendido y correcto (protege que la cola obligatoria siempra quepa), no un bug nuevo. Una corrida separada con una formulación más eficiente (columnas exactas provistas) reconfirmó el camino feliz completo: `status=completed`, 2 `claims[]`, calidad `alta`, 7 pasos.

**Consecuencias:** T4 queda funcional contra Socrata real por primera vez. La variabilidad de cuántos pasos de verificación decide tomar el LLM antes de consultar (0, 1 o 2 pasos de exploración) sigue siendo inherente a un agente basado en LLM real; el criterio de aceptación exige que el grafo PUEDA producir una respuesta completa en ≤10 pasos con una pregunta real, no que toda formulación posible lo logre — eso ya está demostrado. Firmado por Juan Camilo Grajales B., 2026-07-10.

## 15. Recalibración PII de la Hoja de Ruta Nacional de Datos Abiertos Estratégicos 2025-2026

**Universo y procedencia (2026-07-11).** Se consultó la fuente oficial
`fn2v-r4gu` por SODA3. Sus enlaces contienen 66 IDs Socrata únicos realmente
identificables: 53 datasets tabulares accesibles, 4 recursos externos o
federados sin columnas SODA, 3 recursos privados (`403`) y 6 retirados
(`404`). Los 53 tabulares ya estaban presentes en el catálogo local; no fue
necesario inventar ni completar metadatos para los otros 13.

**Decisión.** Se conserva `unknown` como default y la regla MAX. La cobertura
se amplía con revisiones versionadas por `dataset_id` y lista exacta de
`field_name`; una columna nueva o renombrada vuelve a `unknown`. Las señales
globales `high`/`medium` se evalúan antes de estas listas y nunca pueden ser
rebajadas por ellas. Se revisaron 30 esquemas institucionales, territoriales,
ambientales o agregados. Fuentes con personas, contactos, declaraciones,
resultados individuales o identidad ambigua permanecen bloqueadas.

**Resultados medidos.** El recálculo limitado a los 66 IDs encontró 54 ya
almacenados (los 53 tabulares vigentes más un recurso actualmente inaccesible),
procesó 998 columnas y convirtió 27 datasets a `eligible`. En el catálogo
completo la simulación determinista pasa de 9 a 36 elegibles (verificado
directamente contra Postgres: `eligible=36`, `pii_risk_level`: `low=32`,
`medium=15`, `high=1055`, `unknown=7316` — coincide exactamente con lo medido).
`2d3i-f9wd` (el dataset de cooperación internacional referenciado en §13)
queda `low`/`eligible` en su totalidad; sigue sin tener columna geográfica,
por lo que el seguimiento de subregiones de §13 no cambia. También se
corrigió el falso positivo de `NOMINA` dentro de `DENOMINABA` y se reforzaron
señales inequívocas de nombres, apellidos, identificación y contacto directo.

## 16. Decisión registrada: creación pública de corridas y token — `DECIDIDA`

**Problema.** `runner.create_run` nació para el PoC T-300: genera un token
requerido por la tabla, pero lo descarta. Ampliarlo para devolver el token y
aceptar clase de retención desde el endpoint público arriesgaba mezclar el
alcance PoC con RF-801 o, peor, permitir que un cliente cree corridas `eval`.

**Decisión (T-304, 2026-07-10).** Se conserva `create_run` sin cambios de
semántica para el PoC y se añade `create_public_run` como interfaz separada.
Esta fija por construcción `retention_class="user"`, genera un token
criptográficamente aleatorio (≥256 bits), persiste exclusivamente su
SHA-256 y devuelve `(run_id, token_en_claro, expires_at)` solo al handler
que construye la respuesta `202`. El handler no registra ni reutiliza el
token, y las lecturas/borrados calculan SHA-256 del Bearer recibido y lo
comparan con `hmac.compare_digest`.

**Consecuencias.** El JSON público mantiene `extra="forbid"`, por lo que
`retention_class` se rechaza con `422`; las corridas `eval` siguen siendo una
interfaz interna del runner OE3 con `EVAL_MODE=true`. La excepción para
vencimiento conserva la semántica contractual: se borra oportunistamente y
se observa solo `404 RUN_NOT_FOUND`, nunca un estado de token vencido.

## 17. Decisión registrada: operación compartida de borrado RF-803/RF-804 — `DECIDIDA`

**Problema.** T-304 implementó el orden requerido para borrar una corrida
(`adelete_thread(run_id)` y después copia atómica de métricas + borrado de la
fila) dentro de `main.py`. T-306 necesita exactamente esa operación; importarla
desde la capa HTTP invertiría la dependencia y duplicarla arriesgaría que
RF-803 y RF-804 divergieran.

**Alternativas.** (a) importar la función privada de `main.py` desde el job;
(b) copiar la secuencia en un módulo nuevo; (c) mover la operación de negocio a
`app.agent.durability` y dejar en `main.py` solo el adaptador de event loop de
Windows.

**Decisión.** Se adopta (c): `durability.delete_run_with_checkpoints` es la
única operación compartida. Recibe el engine y la URL psycopg de forma
explícita, ejecuta checkpoints primero y delega la copia/borrado transaccional
en `delete_run_with_metrics`. T-304 conserva sus adaptadores
`_delete_run_with_platform_loop` para `SelectorEventLoop`; T-306 y su CLI
llaman a la misma función de servicio sin importar `main.py`.

**Consecuencias.** Un fallo de checkpoints deja intacta la corrida; un fallo
posterior se puede reintentar y `ON CONFLICT (source_run_hash) DO NOTHING`
evita duplicar `technical_metrics`. La FK `ON DELETE SET NULL` conserva el
snapshot no identificable de `eval_case_results` sin un mecanismo paralelo.

---

## 18. Decisión registrada: comparabilidad territorial y aportes manuales del usuario — `DECIDIDA (fuente) / PENDIENTE (ingesta de población como cifra citable)`

**Problema.** El agente resuelve territorios por nombre (T3) pero no advierte cuando dos territorios resueltos en la misma corrida no son comparables entre sí (municipio vs. departamento que lo contiene, o municipios de capacidad/escala muy distinta) — riesgo señalado por el cap. 9 de `docs/capitulos-css-politicas-publicas.md`. Además, cuando el catálogo Socrata no tiene el dato, el agente hoy solo dice "sin evidencia" sin orientar al usuario sobre dónde más buscarlo, y el usuario no tiene forma de incorporar un dato externo al canvas de forma distinguible de la evidencia verificada.

**Alternativas evaluadas para la fuente de comparabilidad:**
(a) Dataset suelto de Ley 617 de la Contraloría en Socrata (`vztn-viv4`) — descartado: congelado en `vigencia=2020` (última actualización 2021-04-19), llave de unión es código CHIP (no DIVIPOLA, requiere fuzzy-match por nombre) y, sobre todo, agrupa al 86,3% de los municipios en una sola categoría (Sexta), sin poder discriminatorio para la mayoría del país (verificado contra el archivo real).
(b) Tipologías del DNP, Resolución 3910 de 2025 (`Tipologías de las entidades territoriales para el reconocimiento de capacidades`, vigencia 2026) — **elegida**. Verificado contra el archivo real `01_ResultadosTipologias2026.xlsx`: 1.103 filas municipales con `CodDANE_txt` = código DIVIPOLA exacto de 5 dígitos (join directo, sin fuzzy-match), incluye además `Cat 617_2025` en la misma fila (más reciente que (a)), y discrimina dentro del 86,3% que (a) agrupa en una sola categoría (tabla 6-1 del informe DNP, cruzada contra 1.103 municipios).

**Decisión sobre citar población/ingresos como cifra:** `PENDIENTE` deliberadamente, no resuelta implícitamente en código. `territorio_tipologia.poblacion`/`ingresos_totales_cop` (cargados del mismo archivo DNP) se usan solo como señal interna para T8; el Art. I exige que toda cifra citada en el documento venga de una consulta SoQL ejecutada con `dataset_id` trazable, y el archivo DNP no es un recurso Socrata. Citar población exacta como cifra requeriría ingestar una fuente de población por el pipeline T1/T2 normal — evaluado y descartado por ahora por costo/alcance frente al golden set actual; queda como trabajo futuro si el golden set demuestra que hace falta.

**Decisión sobre recomendación de fuentes externas:** catálogo curado y fijo (`external_sources.yaml`) con match determinista por palabras clave, NO generación libre de URLs por el LLM — mismo principio del Art. I extendido a enlaces: nunca presentar como verificado algo que el modelo pudo haber alucinado.

**Consecuencias.** Tabla nueva `territorio_tipologia` (data-model.md §6) cargada una vez al año por `scripts/load_tipologias_dnp.py` (T-207) desde un archivo local (el DNP no publica URL estable por vigencia). Nodo determinista T8 (`contracts/agent-tools.md`) advierte comparabilidad sin fabricar cifras. Campo `external_sources` en `no_evidence_report` (`contracts/api-rest.md` §4). Módulo de aporte manual en el frontend (T-506) persiste como nodo del documento, NUNCA en `evidence`/`claims`, y debe ser visualmente distinguible de una tarjeta de evidencia verificada (Art. I + V) — evita que el documento final mezcle cifras verificadas con cifras que el usuario escribió a mano sin que el lector pueda distinguirlas.

## 19. Hallazgo registrado: pérdida referencial `claim_planner`→`claim_builder` y presupuesto de pasos sin margen de recuperación — `RESUELTO EN CÓDIGO, verificado en pruebas; NO demostrado causalmente en smoke real`

**Problema.** Un smoke real contra Gemini (suite `golden-v1`, 8 casos, reporte `backend/eval/reports/994e0730-4586-4716-b500-657347838aef.md`, 0/8 `completed`) expuso dos problemas distintos en la misma traza (`pilot-003-salud-vigilancia`):

1. **Enlace referencial roto entre `claim_planner` y `claim_builder`.** `EvidenceClaimPlan.evidence_id` (esquema estructurado del `claim_planner`) solo exigía `str`; nada validaba que el valor devuelto por el LLM correspondiera a un `evidence_id` real de `state["evidences"]`. La traza mostró `claim_planner: planned=10` seguido de `claim_builder: accepted=0, rejected=0` — el LLM devolvió un `evidence_id` que no coincidía con ninguna evidencia real; `_claim_builder_node` hacía `specs_by_id.get(evidence_id, [])`, que en un `evidence_id` desconocido devuelve `[]` en silencio (ni acepta ni rechaza nada), perdiendo por completo la investigación ya validada. Además, el step `claim_planner` solo persistía `planned=<conteo>`, sin los `evidence_id` propuestos, dificultando el diagnóstico.
2. **El camino feliz de 10 pasos por defecto (RF-201, `AGENT_MAX_STEPS`) no deja margen para NINGÚN mecanismo de recuperación ya implementado en el grafo.** El camino sin errores (`planner→router→T1→router→T5→T6→router→claim_planner→claim_builder→synthesizer`) consume exactamente 10 pasos. El propio `_claim_builder_node` ya implementa un retry determinista (`claim_builder_retry_pending`) para cuando T7 rechaza claims o queda evidencia elegible sin cubrir, pero exige `remaining_after_this_step >= 3` (claim_planner + claim_builder + synthesizer) — con el presupuesto por defecto, ese retry entra exactamente en el paso 9, con 1 paso restante, así que nunca puede dispararse en la práctica. El mismo problema aplica a correcciones de SoQL o pasos de exploración adicionales del router: cualquier desviación del camino perfecto agota el presupuesto antes de poder cerrar con `claim_planner`/`synthesizer`.

**Decisión.**
1. La validación de `evidence_id` **no puede expresarse en el esquema de Pydantic** (depende del estado real en tiempo de ejecución, no de la forma del JSON), así que `_claim_planner_node` ahora valida cada `evidence_id` propuesto contra `state["evidences"]` elegibles y, si encuentra alguno desconocido, repara **dentro del mismo paso** (mensaje de corrección al mismo modelo, acotado por `MAX_CLAIM_EVIDENCE_ID_REPAIR_ATTEMPTS`) — igual que el repair loop existente de `ainvoke_structured_chat_model` para errores de esquema, sin gastar presupuesto de pasos del grafo. Si tras agotar los intentos el `evidence_id` sigue sin coincidir, se descarta explícitamente con una entrada en `rejected_claims` (nunca en silencio) y el step persiste `evidence_ids`/`invalid_evidence_ids` para diagnóstico.
2. RF-201 ya declara el presupuesto como "configurable (por defecto 10)", no como tope fijo. Se sube el valor por defecto de `AGENT_MAX_STEPS` de 10 a **14** (`backend/app/config.py`, `plan.md` §Variables de entorno, `spec.md` RF-201) — suficiente para que el camino feliz (10) más una ronda completa de reparación de claims (+3) quepan con 1 paso de margen adicional, sin tocar el límite configurable de `1..25` ni el criterio de aceptación de research.md §13 ("el grafo PUEDE producir una respuesta completa en ≤10 pasos con una pregunta real, no que toda formulación posible lo logre" — sigue siendo cierto, ahora además puede recuperarse cuando no la produce a la primera).

**Consecuencias.** No cambia ningún contrato de `contracts/agent-tools.md` ni la lógica de `_router_force_finish`/`_minimum_after_router` (siguen protegiendo que la cola obligatoria quepa dentro de `max_steps`, cualquiera sea su valor). Pendiente de re-ejecutar el smoke completo contra Gemini real para confirmar el efecto sobre `success_rate`/`recall_at_10` (research.md §19 no cierra por sí solo los hallazgos #3-#7 del mismo diagnóstico, que quedan como seguimiento separado: abandono prematuro del router, límite de reformulación de `explorar_valores`, `k` de búsqueda semántica, auditoría de `pilot-001` contra la política PII, y puerta de CI basada en `success_rate`).

**Corrección tras revisión externa (2026-07-12, mismo día).** Dos precisiones importantes que el cierre inicial no hacía:
1. **El aumento de presupuesto SÍ está confirmado causalmente**: la corrida que motivó este hallazgo (`994e0730-...`, `AGENT_MAX_STEPS=10` real, tanto en `config.py` como en el `.env` local sin editar todavía) terminó `no_evidence`; las corridas posteriores (`.env` corregido a `14`) muestran `pilot-003` completando en 12 pasos — un camino que exige exactamente la cola completa (`T1→T5→T6→router→claim_planner→claim_builder→synthesizer`, 10 pasos) más recuperación real, imposible con presupuesto 10.
2. **La reparación de `evidence_id` NO está confirmada causalmente contra Gemini real.** Se inspeccionaron los 32 `agent_runs` reales de las cuatro corridas comparables de 8 casos (research.md §21) buscando `claim_planner.detail.invalid_evidence_ids` no vacío en `agent_run_events` — **ninguna corrida real mostró el repair loop disparándose**: en los dos `pilot-003` inspeccionados a nivel de detalle, `evidence_ids` coincidió con el real desde el primer intento (`invalid_evidence_ids: []`). El mecanismo está implementado correctamente y cubierto por pruebas unitarias que sí fuerzan un `evidence_id` alucinado (`test_hallucinated_evidence_id_is_repaired_within_the_same_graph_step`, `test_unrepaired_hallucinated_evidence_id_is_rejected_explicitly_not_silently`), pero su efecto sobre `pilot-003` en producción real sigue sin observarse — Gemini simplemente no volvió a alucinar un `evidence_id` en ninguna de las corridas posteriores inspeccionadas. El estado correcto de este punto es "corregido en código y verificado por pruebas", no "causa confirmada de una mejora observada en smoke".

## 20. Auditoría registrada: `pilot-001-educacion-magdalena` NO está bloqueado por política PII — `RESUELTO (diagnóstico corregido, sin cambio de código)`

**Problema.** Un diagnóstico previo atribuyó la falla de `pilot-001` a que la evidencia llegaba a T5/T6 y quedaba `classification=no_recomendada`/`eligibility_status=blocked` por la política de PII/agrupación mínima, planteando la disyuntiva de si el SoQL, el dataset esperado o el propio caso positivo del golden estaban mal. Antes de tocar la política de privacidad, el golden o el dataset esperado (`c4qb-ek68`), se auditaron los 5 `agent_runs` reales existentes en la base local para la pregunta exacta de `pilot-001` (`SELECT ... FROM agent_runs WHERE question = '¿Qué municipio de Magdalena registró...'`) y el catálogo real de `c4qb-ek68`.

**Verificación real (no simulada).**
1. `c4qb-ek68` (INDICADORES EDUCATIVOS DEL DEPARTAMENTO DEL MAGDALENA POR MUNICIPIOS 2018-2024, Gobernación del Magdalena) tiene `pii_risk_level=low` a nivel de dataset **y en las 11 columnas sin excepción** (`municipios`, `a_o`, `tasa_de_deserci_n`, etc., todas `low`), `eligibility_status=eligible`. Ninguna regla de PII/agrupación mínima (que solo aplica a columnas `medium`) puede bloquear una consulta de fila simple sobre este dataset.
2. Los 3 `agent_runs` reales completos e inspeccionables (`fd0dc901-...`, `048ba2c3-...`, `907a0341-...`) muestran la MISMA causa raíz, y ninguno de los tres llega siquiera a tocar `c4qb-ek68`: `buscar_catalogo({"query": "deserción escolar"})` (sin "Magdalena" en la consulta, `k` por defecto) solo devuelve el dataset nacional `sras-4t5p` (MEN, indicadores por ETC) — el dataset departamental correcto nunca aparece entre los resultados. A partir de ahí, dos de los tres runs perfilan `sras-4t5p`, ven que sus valores de `nombre_etc` son entidades certificadas ("Amazonas (ETC)", "Antioquia (ETC)", ...) y el router hace `finish` sin intentar `ejecutar_soql` (bug de abandono prematuro, ya corregido en el prompt); el run más reciente sí ejecuta SoQL sobre `sras-4t5p` con `nombre_etc LIKE '%MAGDALENA%'`, que devuelve 0 filas (el departamento "Magdalena" no es una ETC certificada por sí solo). Ninguno de los tres reporta `blocked` ni `no_recomendada` en ningún paso — el resultado real es `schema.non_empty_result` fallido (0 filas) o `finish` sin evidencia alguna.

**Decisión.** No se modifica la política de privacidad, el golden set ni `c4qb-ek68`: el caso positivo es correcto y el dataset esperado es legítimamente elegible. Mantiene el estado `RESUELTO (diagnóstico corregido)` — la causa NO es PII/elegibilidad — pero el comportamiento del caso **permanece abierto y sin aprobar** (ver research.md §21): `pilot-001` no volvió a fallar por falta de recall en las cuatro corridas posteriores de 8 casos. En las tres que se inspeccionaron con detalle (`9d495a7d-...`, `b65a9eb9-...`, `b96c1a04-...`), el agente **sí llegó** a `c4qb-ek68` (`expected_dataset_hit=True`) y terminó `completed`, pero `expected_facts` no coincidió: el agente seleccionó el municipio con la tasa de deserción más alta del dataset (`Cerro de San Antonio`, 6,28%), mientras el golden espera específicamente `Zona Bananera` (2,44%) — un valor real y presente en la misma consulta, pero no el que el `ORDER BY ... DESC LIMIT` del agente selecciona. La cuarta corrida (`ebabf87c-...`) terminó `failed` (`terminal_error`). Es decir: el problema evolucionó de "el dataset correcto nunca se encuentra" (recall) a "el dataset correcto se encuentra pero la fila/formulación de la consulta no produce el hecho exacto que el golden espera" — ya no es el mismo problema que `pilot-004/005/007` (que siguen fallando por no llegar al dataset esperado en absoluto). Ver research.md §21 para el detalle de las cuatro corridas.

**Consecuencias.** Corrige el diagnóstico original: el punto 5 ("golden positivo contradice la política de elegibilidad") no aplica a `pilot-001` tal como está el código y el catálogo hoy. La nota original del caso en `golden-v1.yaml` ("Verificar antes de congelar que la Gobernación de Magdalena esté resuelta como publicador oficial y que el dataset siga siendo elegible") ya está satisfecha. Queda **sin resolver, fuera de alcance de esta auditoría**: si `pilot-001` es ambiguo por diseño (la pregunta "¿qué municipio... registró una tasa alta...?" admite más de una respuesta defendible y el golden fijó una que no es la más alta del propio dataset) o si el agente debería preferir explícitamente el máximo cuando la pregunta usa un adjetivo relativo ("alta") sin más contexto — es una decisión de producto/redacción del caso, no un bug de código.

## 21. Hallazgo registrado: verificación real contra Gemini — tres bugs adicionales confirmados y corregidos; mejora real pero acotada — `RESUELTO (parcial)`

**Problema.** Tras los hallazgos de research.md §19/§20 se ejecutaron cinco corridas reales contra Gemini, **no comparables entre sí** (composición y presupuesto distintos — corregido aquí tras una revisión externa que señaló que una redacción anterior de esta sección las presentaba como una secuencia única):

| Corrida | Casos | `AGENT_MAX_STEPS` real | Resultado |
|---|---|---|---|
| `659eea4d-3000-42a7-8abf-5784fabe1053` | 50 (golden-v1 completo) | 10 (`.env` aún sin corregir) | 10/50 = 20% |
| `9d495a7d-8eaf-4959-ac07-b26960eb7ae5` | 8 (`pilot-001..008`) | 14 | 0/8 = 0% |
| `b65a9eb9-9c7d-4bfd-ac2a-b570795d77e6` | 8 | 14 | 1/8 = 12,5% |
| `b96c1a04-efc8-4d3d-b55c-bb873c3af114` | 8 | 14 | 1/8 = 12,5% |
| `ebabf87c-fd2c-4b4a-acf0-b8f6297412fb` | 8 | 14 | 2/8 = 25% |

**Primera corrida (50 casos, `659eea4d`) — el 20% no indica progreso positivo.** Los 10 aprobados fueron **los 10 casos negativos completos** (abstención limpia); de los 40 casos positivos, **0 aprobaron**. Esta corrida es la que expuso los hallazgos de §19/§20 (usó `AGENT_MAX_STEPS=10` porque en ese momento solo se había corregido el default de `config.py`, no el `.env` local — el override de entorno seguía en 10). No debe leerse como "20% de éxito" sin esa aclaración ni compararse directamente con las corridas de 8 casos.

**Cuatro smokes comparables (8 casos positivos, presupuesto 14) — mejora real y acotada: 0/8 → 1/8 → 1/8 → 2/8.** Solo `pilot-002` y `pilot-003` llegaron a aprobar, y no en la misma corrida hasta la última. Se encontraron y corrigieron tres bugs reales adicionales, ninguno anticipado en el diagnóstico original:

1. **`_has_untried_eligible_dataset` no contaba evidencia `blocked` como "sin evidencia usable".** `pilot-002` mostró al router ejecutar SoQL, recibir evidencia `eligibility_status=blocked`, y su propio `reasoning_summary` (460 caracteres, oración completa, no truncada) explicaba textualmente que iba a reintentar con mejor agregación — pero el campo `action` real era `finish`. La guarda de reparación no se disparaba porque `state["evidences"]` ya no estaba vacío (contenía la evidencia bloqueada). Corregido: la guarda ahora distingue evidencia *usable* (`eligible` y no `no_recomendada`) de cualquier evidencia; con `t5_calls>0` y solo evidencia no usable, sigue intentando. Se subió también `MAX_ROUTER_FINISH_REPAIR_ATTEMPTS` de 1 a 2 tras observar que un único mensaje de corrección no siempre revertía la inconsistencia razonamiento/acción del proveedor.
2. **`app/quality/validator.py::_count_alias` solo reconoce `count(...)`.** Una consulta agregada con `sum()`/`avg()`/`min()`/`max()` sin un `count(*)` explícito no puede verificar cuántas filas reales aporta cada grupo (`sum(cantidad)=66723` es indistinguible de una sola fila que ya trae ese valor) y por diseño correcto (Art. VI) queda `blocked` por PII aunque el agregado real sume miles de casos — exactamente lo que le pasó a `pilot-002-seguridad-homicidios` (`SELECT departamento, sum(cantidad)... GROUP BY departamento`, bloqueado). El bug real no era el validador (su conservadurismo es intencional) sino que `router_v1.md` nunca le exigía al LLM incluir `count(*)` al agregar. Se agrega la regla explícita al prompt; `pilot-002` pasó limpio en la corrida siguiente (`ebabf87c`).
3. **`eval/metrics.py::_row_matches` comparaba por nombre exacto de columna** — hallazgo real, pero la primera corrección fue insuficiente (ver subsección siguiente).

**Corrección del harness de evaluación (`eval/metrics.py`) — historial de dos intentos.** El SoQL lo genera el LLM en cada corrida sin obligación de usar el mismo alias que el autor del golden usó al verificar el hecho a mano: `pilot-003-salud-vigilancia` devolvió la fila semánticamente idéntica al `expected_value` (mismo evento, mismo conteo exacto `1470739`) con la columna nombrada `total_casos` en vez de `total_reportes`, y el caso se marcaba erróneamente como fallido.

- **Primer intento (revertido tras revisión externa):** comparar por valor, ignorando el nombre de columna — cualquier valor esperado calzaba con cualquier valor de la fila. Una revisión posterior identificó correctamente que esto abre falsos positivos reales: dos claves esperadas podrían satisfacerse con la misma celda, un valor esperado podría calzar por coincidencia con una columna sin relación semántica, o dos dimensiones podrían intercambiarse entre sí sin que nada lo detecte. Es una señal legítima de "harness ajustado para hacer pasar un caso concreto", exactamente como se señaló.
- **Segundo intento (también superado, ver siguiente):** un alias solo se aceptaba si estaba **declarado explícitamente**, por caso y por clave, en un diccionario `_DECLARED_VALUE_ALIASES` en `eval/metrics.py`. Se evaluó declarar el alias directamente en `golden-v1.yaml`, pero `eval/persistence.py::sync_golden_suite` **rechaza cualquier mutación a `expected_facts` de un caso ya persistido** ("cree golden-v2 en lugar de editar golden-v1") — los 50 casos, incluido `pilot-003`, ya están persistidos desde la primera corrida, así que editar el YAML habría roto `sync_golden_suite` en la siguiente ejecución. Una segunda revisión externa detectó el problema real de este diseño: solo cubría el alias YA OBSERVADO en `pilot-003` (`total_reportes`→`total_casos`) y dejaba fuera el MISMO problema en `pilot-002` (`total`→`total_homicidios`, confirmado con el run real `e0250b8a-...`) — re-verificar (solo lectura) la corrida `ebabf87c` con este diseño dio **1/8**, no 2/8: agregar cada alias observado a mano es "ajustar el harness a la corrida", exactamente lo que se quería evitar.
- **Tercer diseño (vigente):** en vez de una lista de alias por caso, se distingue **DIMENSIÓN** (valor esperado de texto: departamento, municipio, nombre_evento — exige coincidencia EXACTA de nombre de columna, nunca se adivina) de **MÉTRICA CALCULADA** (valor esperado numérico: el LLM agrega con `sum`/`avg`/`count`/etc. y elige libremente el alias). Para una métrica sin coincidencia exacta de nombre, se acepta como máximo UNA correspondencia sin ambigüedad entre las métricas no resueltas y las columnas numéricas restantes (bipartita 1 a 1, cada columna se consume una sola vez; si hay 0 o más de 1 candidato para alguna métrica, se rechaza). Esto es general — no requiere declarar ningún alias específico — y se verificó (solo lectura) que cubre AMBOS casos reales (`pilot-002` con `total`→`total_homicidios`, `pilot-003` con `total_reportes`→`total_casos`) sin ningún hardcodeo: re-anotar `ebabf87c` con este diseño da **2/8**, igual que se predijo. Riesgo residual documentado (no eliminado): si una fila tiene EXACTAMENTE una columna numérica sobrante que coincide por pura casualidad con el valor esperado, este diseño la acepta — distinguir eso del caso legítimo exigiría recalcular la métrica desde las filas crudas de origen contra una fórmula declarada (re-consultar Socrata en tiempo de evaluación), fuera de alcance de esta sesión. `tests/test_eval_metrics.py` cubre: ambos casos reales por tipo (no por alias), que una dimensión nunca use el mecanismo de métrica, que dos métricas no puedan reclamar la misma columna, y que una métrica sin ninguna columna candidata falle.
- **Sobre "reanotar el resultado ya persistido":** la verificación se hizo llamando `assess_case(case, final_answer)` en un script Python de solo lectura, leyendo `agent_runs.final_answer` con `SELECT` y computando el resultado localmente **sin ninguna escritura a Postgres** (ni a `eval_case_results` ni a ninguna otra tabla) — el registro histórico de las corridas no cambió de veredicto en la base de datos; solo se confirmó localmente, contra los tres diseños sucesivos, qué `final_answer` ya persistido calza y cuál no.

**Decisión.** Los tres bugs se corrigen como bugs de código/prompt/harness, no como relajación de política ni cambios al golden. Las siguientes son **hipótesis parcialmente verificadas, no cierres**, tal como señaló la revisión — los reportes `.md` solo muestran el resultado final de cada corrida, no bastan para aislar la causa exacta sin más instrumentación o corridas dedicadas:
- `pilot-004-justicia-presupuesto`: el dataset esperado (`f4a5-ab9q`, confirmado `eligible`/`low` PII y con embedding real en `catalog_embeddings`) nunca aparece en el top-10 de `buscar_catalogo` para ninguna consulta que el router formuló; el agente llega a una respuesta completa y honesta con `5phs-yqfw` (otro dataset presupuestal real), pero no es el que el golden espera. Hipótesis: problema de ranking semántico (texto de embedding o ponderación de la consulta) — no confirmado contra el pipeline de ingesta real, fuera de alcance de una auditoría del grafo. Ver además research.md §22: en corridas anteriores del mismo caso, `SOQL_FORBIDDEN` también contribuyó, y esa causa sí quedó confirmada y corregida.
- `pilot-005`/`pilot-007`: mismo patrón de inconsistencia razonamiento/acción de Gemini que `pilot-002`, mitigado pero no eliminado por el segundo intento de reparación. Se descartó específicamente que sea un agotamiento de presupuesto disfrazado (`force_finish`): ninguna de las corridas inspeccionadas llegó siquiera a la mitad de los 14 pasos disponibles en el momento del `finish` inconsistente (research.md §22). Sigue sin aislarse entre prompt insuficiente, guarda de recuperación incompleta para este patrón específico, o no-determinismo genuino del proveedor.
- `pilot-006`/`pilot-008`: la entidad/municipio buscado no aparece bajo los términos probados (2 reformulaciones, tope correcto) y el agente se abstiene. Hipótesis sin descartar: el dataset esperado nunca se recuperó en primer lugar, se exploró la columna incorrecta, la normalización del término fue deficiente, o el dato cambió en Socrata desde que se congeló el golden — no se confirmó cuál aplica.

**Consecuencias.** Existe una mejora real y reproducible en el subconjunto comparable de 8 casos positivos (0/8 → 1/8 → 1/8 → 2/8), impulsada por dos bugs de código concretos y corregidos (`pilot-002`, `pilot-003`). Esto **no permite extrapolar** una mejora del golden set completo de 50 casos ni acercamiento al 80% de RNF-002 — no existe todavía una corrida completa posterior a estos fixes. El agente sigue lejos del umbral de release. No se relajó ninguna política de privacidad ni se tocó el contenido del golden set. Pendiente, fuera de alcance de esta sesión: (a) correr la suite completa de 50 casos con presupuesto 14 y los fixes de esta sección y de research.md §22; (b) investigar el pipeline de ingesta/embeddings para `pilot-004`; (c) instrumentación adicional para separar las hipótesis de `pilot-005/006/007/008` en vez de inferirlas de reportes agregados.

## 22. Hallazgo registrado: dos bugs adicionales confirmados sin gastar cuota de Gemini (`SOQL_FORBIDDEN` real y cifra huérfana del propio filtro) — `RESUELTO EN CÓDIGO, sin nueva corrida real`

**Problema.** Tras research.md §21, se investigaron con más profundidad `pilot-004-justicia-presupuesto` (SOQL_FORBIDDEN) y `pilot-001-educacion-magdalena` (cifra huérfana), usando solo datos ya persistidos en Postgres y una consulta directa (gratuita, sin LLM) contra Socrata — sin ejecutar un nuevo smoke contra Gemini, siguiendo la instrucción explícita de no gastar más cuota hasta corregir estas causas.

**1. `SOQL_FORBIDDEN` real en `pilot-004` (dos corridas de rondas anteriores, `dc242801-...` y `55e053b0-...`).** El router intentó `SUM(REPLACE(REPLACE(apropiaci_n_vigente, ',', ''), '- 0', '0')::NUMBER)`, luego `TO_NUMBER(...)`, luego `CAST(... AS NUMBER)`, luego `CAST(... AS FLOAT)` — cuatro variantes, todas rechazadas por `soql_parser.ALLOWED_FUNCTIONS` (`{sum, avg, count, min, max, upper, lower, date_extract_y, date_trunc_*}`, ninguna función de conversión numérica). Verificado contra Socrata real (consulta HTTP directa, sin costo de LLM): el propio `expected_fact` del golden para este caso **no requiere agregación en absoluto** — es un filtro de una sola fila (`entidad='sector justicia' AND descripci_n='Funcionamiento' AND a_o='2023'`) que Socrata devuelve tal cual, con `apropiaci_n_vigente` como texto con coma de miles ("3,893,283,514,468.00"), exactamente el valor esperado. El router intentaba agregar/convertir un problema que en realidad era un filtro directo.

Pero incluso con el filtro correcto, `app/quality/claims.py::_to_decimal` (`Decimal(str(value).strip())`) **no admite comas** — `Decimal("3,893,283,514,468.00")` lanza `InvalidOperation`, así que el claim se habría rechazado igual como "no numérico". Este es un segundo bug, independiente del primero: columnas monetarias de datasets del Estado llegan frecuentemente como texto con separador de miles porque el propio dataset las publica como `Text`, no `Number` (confirmado en `f4a5-ab9q`). Corregido: `_to_decimal` retira comas antes de convertir a `Decimal` (`tests/test_claims.py::test_direct_claim_parses_thousands_separator_from_text_column`, con el valor real del caso). Se refuerza además `router_v1.md`: prohibición explícita de CAST/TO_NUMBER/REPLACE/`::` (siempre `SOQL_FORBIDDEN`, sin excepción) y la instrucción de preferir un filtro directo a una fila resumen en vez de intentar agregar una columna de texto.

**2. Cifra huérfana `'2024'` en `pilot-001` (dos corridas `failed`, `eb702c23-...` y `919c44f6-...`).** Confirmado exactamente: `synthesizer` registró el error `"Cifras huérfanas tras 3 intentos: ['2024']"` — la corrida no solo eligió el municipio/valor equivocado (research.md §20), en dos de once corridas persistidas **falló por completo** sin llegar a entregar ninguna respuesta. Causa: `_orphan_figures` (`app/agent/graph.py`) solo acepta como "respaldada" una cifra que aparece en `claim.display_value` — nunca en la propia consulta SoQL ya ejecutada. El `canonical_soql` real filtra `WHERE a_o = 2024` (el año que la pregunta pide explícitamente), pero como el claim solo lleva la tasa (`"6,28 %"`), cualquier mención de "2024" en el resumen/narrativa del sintetizador —natural, dado que el propio `soql_query` se le pasa como contexto— se rechazaba como no verificada. Corregido: `_orphan_figures` ahora también acepta cifras presentes en `evidence["soql_query"]` de cada evidencia (`tests/test_agent_graph.py::test_orphan_figures_accepts_a_year_present_in_the_evidence_soql_query`, que confirma explícitamente que SIN el contexto de evidencia "2024" sigue sin respaldo — el fix depende de esa información nueva, no de relajar `find_orphan_figures` en general).

**Verificación explícita: NO se descartó `pilot-005`/`pilot-007` como agotamiento de presupuesto.** Se confirmó con los `agent_steps` reales que ninguna de las cuatro corridas inspeccionadas de estos dos casos superó los 11 pasos (de 14 disponibles) en el momento del `finish` con razonamiento inconsistente — descarta que `force_finish` sea la causa oculta. Esta causa **sigue sin resolverse**; no se intentó un fix nuevo en esta sección.

**Decisión.** Ambos son bugs de código reales, corregidos con pruebas que usan los valores exactos observados en producción, sin tocar contratos ni relajar validación de calidad/privacidad. No se ejecutó ningún smoke nuevo contra Gemini en esta sección (instrucción explícita) — el efecto de estos dos fixes sobre `pilot-001`/`pilot-004` sigue sin confirmarse con LLM real.

**Consecuencias.** De las dos causas que bloqueaban una nueva corrida completa según la instrucción recibida, `SOQL_FORBIDDEN` queda corregida en su raíz (parseo de comas + guía de prompt); `pilot-005`/`pilot-007` (abandono sin evidencia con razonamiento inconsistente) permanece abierta. Antes de la siguiente corrida real, decidir si: (a) se ejecuta ya con esta cobertura parcial, o (b) se invierte más tiempo en aislar la causa de `pilot-005`/`pilot-007` primero.

## 23. Investigación registrada: inconsistencia razonamiento/acción en `pilot-005`/`pilot-007` — patrón confirmado a escala, hipótesis de causa PROBADA Y DESCARTADA, mitigación de prompt aplicada — `ABIERTO`

**Problema.** A pedido explícito, se continuó investigando por qué el router declara `action="finish"` mientras su propio `reasoning_summary` describe una intención de seguir investigando (research.md §21), sin ejecutar ningún smoke nuevo contra Gemini.

**Escala real del patrón.** Se inspeccionaron las 19 corridas reales ya persistidas de `pilot-005` (10) y `pilot-007` (9) — todas las que existen en la base local, no solo las de las 4 corridas comparables — contando cada decisión `action="finish"` cuyo `reasoning_summary` contiene lenguaje de continuidad ("voy a ejecutar", "procedo a", "I will now query", etc.). Resultado: **7 de 17 decisiones `finish` inspeccionadas (41%)** muestran esta inconsistencia — no es un caso aislado, es el patrón dominante de falla en estos dos casos. Un hallazgo lateral en el mismo barrido: `pilot-007` también fue bloqueado al menos una vez por el mismo problema de agregación PII de research.md §21 punto 2 (`"la consulta anterior fue bloqueada por el validador de calidad...no cumplía con los requisitos de agregación"`), ya cubierto por la regla de `count(*)`.

**Hipótesis probada: orden de campos del esquema.** `ClaimPlannerOutput` declara `reasoning_summary` antes que el campo de decisión; `RouterOutput` declaraba `action` primero. La hipótesis: si Gemini genera JSON en el orden declarado del esquema, el modelo se compromete con la decisión antes de poder "razonar en voz alta". Se implementó el reordenamiento y, antes de darlo por bueno, se verificó **directamente contra el conversor real** (`_convert_pydantic_to_genai_function`, no `convert_to_openai_tool` — la lección de research.md, sección "Regresión del incidente" en `test_agent_router_contracts.py`, ya advertía sobre esto):
- `RouterOutput.model_json_schema()['properties']` sí refleja el orden declarado.
- `dereference_refs` (usado por el conversor) tampoco lo altera.
- Pero el orden final en `FunctionDeclaration.parameters.properties` (comparado con los 4 esquemas del grafo, antes y después de reordenar) **no coincide con el orden declarado, ni con orden alfabético, ni con ningún patrón estable entre esquemas distintos**. `Schema.properties` de `google.ai.generativelanguage` es un mapa protobuf — sin garantía de orden en su representación.
- **Conclusión: la hipótesis es incorrecta.** Reordenar campos de un modelo Pydantic no tiene efecto verificable sobre qué orden recibe Gemini. Se revirtió el reordenamiento (queda documentado en el docstring de `RouterOutput` para que nadie repita el mismo camino sin verificar primero).

**Verificación explícita: no es presupuesto disfrazado.** Se confirmó con `agent_steps` reales que ninguna de las corridas inspeccionadas superó los 11 pasos de los 14 disponibles en el momento del `finish` inconsistente — descarta `force_finish` como causa oculta (ya mencionado en research.md §22, reafirmado aquí a escala de las 19 corridas).

**Mitigación aplicada (prompt, no esquema).** Se agrega a `router_v1.md` una regla explícita de autoconsistencia: antes de fijar `action="finish"`, el router debe releer su propio `reasoning_summary`; si describe intención de continuar, `action` no puede ser `finish` (debe cambiar a la herramienta que el razonamiento describe, o el razonamiento debe reescribirse honestamente). Es una instrucción textual, no un mecanismo determinista — no hay garantía de que Gemini la respete de forma consistente, a diferencia de las guardas deterministas de research.md §19/§21 (`_has_untried_eligible_dataset`, presupuesto de `explorar_valores`). `tests/test_agent_graph.py::test_router_prompt_requires_reasoning_action_self_consistency` fija que la regla no desaparezca en un futuro edit, pero **no puede verificar que el LLM real la siga** — eso solo se confirma con una corrida real.

**Decisión.** No se encontró una palanca de código/esquema determinista para esta causa específica — a diferencia de los otros ~6 bugs de esta sesión, este parece ser genuinamente un límite de confiabilidad del proveedor en la generación de campos estructurados relacionados, mitigable solo por prompt (sin garantía) o por más intentos de reparación (costo creciente, retornos decrecientes ya sugeridos por research.md §21). Se deja así documentado en vez de forzar una "solución" no verificada.

**Consecuencias.** `pilot-005`/`pilot-007` permanecen sin corrección determinista. La mitigación de prompt aplicada es razonable pero de eficacia desconocida hasta la próxima corrida real. De las dos causas que bloqueaban un nuevo smoke (research.md §21), `SOQL_FORBIDDEN` está resuelta en su raíz; esta permanece como el límite conocido y documentado, no resuelto, de esta ronda de auditoría.

## 24. Sexta corrida real (post research.md §22/§23) y hallazgo adicional confirmado: truncamiento silencioso de `reasoning_summary` — `RESUELTO EN CÓDIGO (parcial); mejoras de §22 confirmadas`

**Problema.** A pedido explícito se ejecutó una sexta corrida real de los 8 casos originales (`672df769-dbd4-4d26-9910-c07f5db98f91`), con todas las correcciones de research.md §19-§23 aplicadas, para medir el efecto acumulado.

**Resultado: 2/8 (25%), estable respecto a la corrida anterior — `pilot-002` y `pilot-003` vuelven a pasar limpio.** No hay regresión. Más relevante que el número agregado es lo que cambió en los 6 casos que siguen sin aprobar:

- **`pilot-004`: la corrección de `SOQL_FORBIDDEN` (research.md §22) queda confirmada con LLM real.** Esta vez el router llegó al dataset correcto (`f4a5-ab9q`, el que espera el golden), perfiló, ejecutó SoQL sin ningún rechazo `SOQL_FORBIDDEN`, pasó `quality_validator` y llegó a `claim_planner`/`claim_builder`. La corrida terminó `failed`, pero por un **error transitorio de infraestructura** (`504 The request timed out`) durante un reintento de `claim_planner`, no por un bug de diseño. Es la primera vez que este caso llega tan lejos.
- **`pilot-001` y `pilot-002`/`pilot-003`: siguen (o vuelven a) alcanzar sus datasets esperados de forma consistente**, reafirmando que las correcciones de recall/navegación de research.md §19-§21 son estables entre corridas, no un artefacto de una sola ejecución.
- **`pilot-005`: la regla de autoconsistencia (research.md §23) sí tuvo un efecto observable, aunque no alcanzó a producir un `pass`.** La razón de `finish` ahora es completamente coherente: *"El dataset `fvq4-wwtz` es el único elegible encontrado, pero no contiene una columna de sexo, que es fundamental para responder..."* — ya no describe una intención de continuar mientras declara `finish`. El caso sigue sin aprobar por una razón real y distinta (no se encontró el dataset correcto, `h8rs-jxum`, en esta formulación de búsqueda), no por la inconsistencia razonamiento/acción documentada en §23.
- **`pilot-007`: la misma inconsistencia SIGUE apareciendo** en su decisión final (*"...Procedo a realizar una nueva consulta..."* con `action=finish`), confirmando que la regla de prompt no es suficiente por sí sola para este caso — consistente con lo ya documentado en §23 (mitigación sin garantía).
- **`pilot-006`: abstención honesta reafirmada** (evidencia `no_recomendada` por 0 filas para la entidad buscada, `claim_builder` con `accepted=0, rejected=0` correctamente explicado por el router antes de llegar ahí).
- **`pilot-008`: mismo patrón que rondas anteriores** (2 reformulaciones de `explorar_valores`, tope correcto, sin intentar T5) pero con un matiz nuevo (ver hallazgo siguiente).

**Hallazgo adicional confirmado: truncamiento silencioso de `reasoning_summary` en el límite de 500 caracteres.** Al clasificar las 9 instancias de inconsistencia razonamiento/acción confirmadas hasta ahora (incluyendo esta corrida) por longitud y puntuación final:
- **7 de 9** son oraciones completas (terminan en punto), muy por debajo de 500 caracteres (266-491): inconsistencia genuina, sin causa aislada (research.md §23, sin cambios).
- **2 de 9** (`714d3aa7-...` de §22 y `e5779726-...`, `pilot-008` de esta corrida) terminan **exactamente en 500 caracteres y a mitad de frase** — el ejemplo de `pilot-008`: `"...para Villamaría, agrupado por año (a_o_del_cargue), e incluyendo el"` (sin sustantivo tras "el"). El texto real era más largo; `_truncate_overflowing_strings` (`app/llm/factory.py`) lo recortó en silencio al límite de Pydantic, perdiendo la parte final — que en un campo de razonamiento suele ser la conclusión/justificación de la decisión, no contenido intercambiable con el resto del texto.

**Decisión.** Se sube `RouterOutput.reasoning_summary.max_length` de 500 a 900 (`app/agent/graph.py`, `tests/test_agent_router_contracts.py::test_reasoning_summary_allows_900_characters`). No corrige el 78% de casos que son inconsistencia genuina (sigue abierto, research.md §23), pero cierra un artefacto real, confirmado sin ambigüedad y de causa mecánica clara (a diferencia de la hipótesis de orden de campos, descartada en §23 con evidencia directa contra el conversor real).

**Consecuencias.** El efecto de subir `max_length` sobre `pilot-008` específicamente no se verificó con una séptima corrida (para no seguir gastando cuota sin que el usuario lo pida); queda para la próxima corrida real. El estado general no cambia: 2/8 en el subconjunto comparable, mejoras reales y verificadas en la profundidad de investigación alcanzada por `pilot-001/002/003/004`, `pilot-005/007` con causa raíz aún sin resolver de forma determinista. El agente sigue lejos del 80% de RNF-002; no se ha corrido el golden set completo de 50 casos con el conjunto acumulado de correcciones de esta sesión.

---

## 25. Enmienda de arquitectura: coexistencia del runtime legado y el núcleo determinista — `DECIDIDA; MIGRACIÓN EN CURSO`

**Problema.** La arquitectura implementada evolucionó más allá del grafo descrito originalmente en `plan.md` §1. El runtime legado (`app.agent.graph`) conserva un enrutador LLM iterativo y continúa siendo necesario como rollback, mientras que el nuevo núcleo desplaza al código determinista las decisiones estructurales de recuperación, selección de candidato, perfilado, construcción y validación de `QueryPlan`, renderizado SoQL, exploración acotada, presupuestos y transición entre etapas. El LLM queda restringido a contratos estructurados y síntesis, sin autoridad para saltar validaciones ni ejecutar consultas libres. Sin esta enmienda, el código y las pruebas pueden parecer alineados aunque una suite etiquetada como “rediseño” siga ejecutando realmente el agente legado.

**Evidencia vigente al aprobar esta enmienda (2026-07-16).**

- La rama de trabajo es `feat/deterministic-agent-core`.
- Existen módulos separados para el núcleo: `deterministic_graph.py`, `deterministic_runtime.py`, `deterministic_dependencies.py`, `deterministic_pipeline.py`, `query_plan.py`, `plan_validator.py`, `soql_renderer.py`, `llm_contracts.py` y `multiquery_retrieval.py`.
- Existe integración de persistencia del pipeline determinista, pero no una aceptación E2E que ejecute su entrada productiva completa.
- `backend/tests/integration/test_agent_redesign_acceptance.py` importa `app.agent.graph.build_graph`; por tanto, sus siete historias pertenecen al runtime legado aunque su nombre sugiera lo contrario.
- `backend/app/config.py` declara actualmente `AGENT_RUNTIME=deterministic` como default. Esto contradice la política de migración conservadora aprobada aquí; no se corrige en esta enmienda documental porque el siguiente incremento está limitado a pruebas. Hasta resolver la desviación en una tarea explícita, los entornos de usuario/producción deben fijar `AGENT_RUNTIME=legacy` de forma explícita.
- La última línea base completa registrada es 25/50. Ese resultado demuestra que el runner funciona, no que el núcleo nuevo haya superado RNF-002.
- `backend/eval/golden/GOLDEN_V2_PROPOSAL.md` es una propuesta de trabajo. No es una suite normativa y no autoriza crear o modificar `golden-v2.yaml`.

**Decisión de arquitectura.**

1. Durante la migración coexistirán dos runtimes explícitos: `legacy`, el grafo histórico basado en router LLM; y `deterministic`, la máquina de etapas con transiciones, validaciones y presupuestos gobernados por código.
2. La selección se realiza mediante `AGENT_RUNTIME`; durante la validación el valor operativo es `legacy`. Al superar la puerta normativa, `deterministic` se convierte inmediatamente en el default. No se permite fallback automático de `deterministic` a `legacy` dentro de una corrida. Un fallo del runtime seleccionado debe quedar tipado y observable.
3. Los contratos existentes de herramientas, API, calidad y claims cuantitativos permanecen vigentes. Esta enmienda no los cambia para acomodar el runtime.
4. `golden-v1.yaml` permanece congelado. El runtime no puede incorporar IDs, cifras, filtros, estaciones, horas ni respuestas específicas de sus casos.
5. El agente legado se conserva congelado como rollback. Al superar el determinista todas las puertas de `pruebas.md` §4.4 deja de ser el default y permanece disponible solo como rollback de emergencia durante una versión adicional; después se eliminan el selector `AGENT_RUNTIME` y el código legado en una tarea independiente.
6. La aceptación de cada runtime debe estar separada y nombrada inequívocamente: `legacy_agent_acceptance` y `deterministic_agent_acceptance`.
7. La evaluación debe registrar etapa y motivo de fallo tipados; el porcentaje agregado no basta para dirigir el desarrollo.

**Secuencia aprobada de desarrollo.**

1. Congelar y documentar la línea base sin cambiar comportamiento.
2. Crear aceptación E2E determinista desde `execute_deterministic_agent_run_async`.
3. Reclasificar la aceptación existente como legacy y registrar marcadores pytest independientes.
4. Añadir matriz de etapas y motivos de fallo al evaluador.
5. Ejecutar un smoke determinista representativo de 8–10 casos.
6. Atacar primero los diez fallos de recuperación con reglas generales y evidencia comparativa.
7. Diseñar hechos textuales de primera clase; cualquier cambio de contrato o modelo exige enmienda separada antes de código.
8. Auditar los 50 casos y construir `golden-v2` sin modificar `golden-v1`.
9. Ejecutar ambas suites y mantener el rollback hasta superar la puerta normativa.

**Límites contra sobreajuste.**

- No relajar `backend/eval/metrics.py` para hacer pasar resultados observados.
- No crear mapas pregunta→dataset ni boosts por IDs del golden.
- No introducir en prompts o runtime restricciones ocultas tomadas de `expected_facts` o `source_url`.
- No aumentar presupuestos sin diagnóstico por etapa que demuestre que el presupuesto es la causa.
- No atribuir al runtime determinista una prueba que importe o ejecute `app.agent.graph`.

**Consecuencias.** `plan.md` documenta desde esta enmienda la arquitectura dual; `pruebas.md` define suites, diagnósticos y puertas; `tasks.md` contiene la secuencia ejecutable T-610…T-617. La siguiente implementación autorizada es T-611, precedida únicamente por el cierre reproducible de la línea base T-610. No se autorizan todavía cambios de comportamiento para mejorar recuperación, claims o síntesis.

## 26. Decisión registrada: materialización lexical para RNF-010 — `DECIDIDA`

**Problema.** T-614R1 conserva cobertura completa y cero errores, pero obtiene
p95 1293,6 ms. `EXPLAIN ANALYZE` atribuye ~545 ms a recalcular por solicitud un
`to_tsvector` mediante `Parallel Seq Scan`; HNSW tarda menos de 1 ms.

**Alternativas.** Se descartó una generated column porque no puede agregar
filas hijas de `catalog_columns`. El mantenimiento exclusivo en la aplicación
no cubre escrituras SQL externas. Se compararon GIN y GiST sobre una tabla
experimental reversible con los 8.398 datasets reales.

**Decisión.** `catalog_datasets.lexical_search_vector` será `tsvector NOT NULL`
con configuración `spanish` y contendrá exactamente `name`, `description`,
`publisher`, `category`, `embedding_text` y, ordenados por `field_name`,
`catalog_columns.field_name`, `display_name` y `description`. Un trigger de
dataset y triggers de sentencia con transition tables para cambios de columnas
lo mantendrán transaccionalmente. El índice será GIN.

**Evidencia.** GIN midió 0,38 ms frente a 6,17 ms de GiST para búsqueda
selectiva; GiST exigió 8.321 rechecks falsos. GIN ocupó ~3,0–3,3 MiB y se
construyó en 146–175 ms; GiST ocupó ~3,1 MiB y se construyó en 114–118 ms.
Actualizar 100 vectores costó ~2,7 ms con ambos. Para términos amplios el
planificador puede recorrer el vector almacenado en 12–22 ms; esto sigue
eliminando el recálculo dominante de ~545 ms.

**Consecuencias.** La migración hace backfill idempotente (~3,2 s medidos),
crea triggers e índice y es reversible. No cambia contrato HTTP, embedding,
dimensión, percentiles, muestras, golden ni fórmula híbrida. La evidencia
completa vive en `proposals/rnf010-lexical-materialization.md` y
`backend/eval/reports/rnf010-lexical-optimization.md`.

**Extensión medida de la misma decisión.** Se materializa un segundo
`lexical_rank_vector`, sin índice, con la expresión histórica exacta de ranking
(`name`, `publisher`, `category`, `description`, columnas ordenadas). Así se
preserva el rank byte a byte y se evita agregar texto de columnas para todos
los candidatos. `columns_preview`/`columns_all` se enriquecen solo para el
top-10. SQL+Python p95 diagnóstico bajó a 144,4 ms y las agregaciones laterales
de 384 a 20.

## 27. Propuesta T-615: hechos textuales de primera clase — `PROPUESTA PARA REVISIÓN`

**Estado y límite.** Esta decisión no está aprobada ni implementada. No
autoriza código, migraciones, `golden-v2`, cambios de métricas, retiro del
legado ni edición de `golden-v1`. La propuesta completa está en
`proposals/textual-claims.md`.

**Problema comprobado.** El modelo vigente solo prueba cifras mediante
`QuantitativeClaim`. El constructor rechaza celdas no numéricas y la ruta de
consulta textual del runtime determinista las representa hoy como
`derived count=1`; la descripción contiene la etiqueta, pero la magnitud no la
prueba. El verificador de síntesis y el evaluador solo detectan cifras
huérfanas. En `golden-v1`, 36 de 40 positivos contienen valores textuales y
nueve dependen exclusivamente de ellos. Por tanto, los pases actuales no
demuestran integridad textual.

**Alternativas evaluadas.**

1. Reutilizar `quantitative_claims` con nulos o JSON polimórfico: rechazada
   porque debilita restricciones numéricas y mezcla semánticas.
2. Representar texto mediante presencia o conteo igual a uno: rechazada
   porque prueba una cantidad distinta del dato afirmado.
3. Crear `textual_facts` y exponer ambas variantes como unión discriminada:
   propuesta por aislamiento, restricciones fuertes, compatibilidad y
   rollback.

**Decisión propuesta.**

- Concepto común `GroundedFact`, discriminado por
  `claim_kind=quantitative|textual`; `QuantitativeClaim` conserva
  `claim_type=direct|derived`, DSL, formato y todas las guardas RNF-003.
- Tabla separada `textual_facts`, vinculada a corrida y evidencia, con
  operación cerrada, filas, columnas, valores brutos/normalizados, valor
  presentado, perfil de normalización, parámetros, versión y hash.
- Operaciones iniciales: `direct_text`, `value_presence`,
  `category_selection`, `argmax_label`, `argmin_label` y
  `ordered_text_set`.
- Perfil `text-es-v1`: Unicode NFC, saltos y espacios canonicalizados,
  `casefold` solo para comparación, tildes/`ñ`/puntuación preservadas; la
  presentación conserva caja y grafía de la fuente.
- `argmax_label` y `argmin_label` usan `tie_policy=reject`: un empate no se
  resuelve por orden incidental.
- `source_hash` incluye versión, operación, normalización, dataset, SoQL
  canónica, filas y subconjunto fuente, columnas, valores y parámetros; no
  incluye UUIDs de instancia ni timestamps.
- `RespuestaFinal.claims` permanece como lista única con modelos tipados
  discriminados. Los históricos sin `claim_kind` solo pueden inferirse como
  cuantitativos si cumplen su forma completa; nunca se infiere texto.
- La síntesis factual se vuelve estructural: el LLM selecciona identificadores
  y conectores cerrados; un renderizador determinista inserta valores y
  plantillas. No se promete detectar hechos arbitrarios dentro de prosa libre.
- RF-602 añade métricas textuales separadas. RNF-003 no se modifica; se
  propone RF-210/RNF-013 para cobertura y reproducibilidad textual.

**Atribución de fallos.** T-615 no absorbe problemas de otras capas:
`pilot-012` falla después de recuperación por presupuesto/selección;
`pilot-021` ejecutó `count(*)` en vez de `cantidad`; `pilot-022` pasó el smoke
final; `pilot-038` es ambiguo porque la hora esperada no está en la pregunta.
Los desacuerdos restantes se mantienen `undetermined` hasta T-616.

**Dependencias y gate.** T-615A…T-615J se detallan en `tasks.md`. La primera
implementación depende de aprobación explícita de esta enmienda. T-616 y
T-617 continúan bloqueadas. Aprobar el documento no autoriza automáticamente
una migración o cambio de runtime.

---

*Para añadir una nueva decisión: sección numerada, estado, problema, alternativas, criterios, decisión y consecuencias. Las decisiones `PENDIENTE` bloquean las tareas que dependan de ellas (ver tasks.md).*
