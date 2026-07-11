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

*Para añadir una nueva decisión: sección numerada, estado, problema, alternativas, criterios, decisión y consecuencias. Las decisiones `PENDIENTE` bloquean las tareas que dependan de ellas (ver tasks.md).*
