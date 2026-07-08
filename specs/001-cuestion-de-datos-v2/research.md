# Registro de Investigación y Decisiones Técnicas — Cuestión de Datos v2.0

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Propósito:** documentar decisiones técnicas que requieren evaluación experimental o análisis de alternativas, con su estado (`PENDIENTE` / `DECIDIDA`). Ningún documento del paquete SDD debe presentar como definitiva una decisión que aquí figure como pendiente.

---

## 1. Decisión pendiente: modelo de embeddings — `PENDIENTE`

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

**Decisión:** _pendiente de T-205._

**Consecuencias de la decisión (cuando se tome):**
- Fija `<DIM>` en `data-model.md` §`catalog_embeddings` y en la migración de T-104B.
- Fija `EMBEDDING_MODEL` en `.env.example` y quickstart.md.
- NO se mezclan embeddings de modelos o dimensiones distintas en un mismo índice; cambiar de modelo después exige regenerar el índice completo o versionar índices separados (tabla por modelo).
- Si el elegido es gestionado, el cron de ingesta (T-206) necesita la API key correspondiente como secret.
- Restricción de compatibilidad pgvector: si T-104B mantiene `vector(<DIM>) + vector_cosine_ops`, la dimensión elegida DEBE ser `DIM <= 2000`. Si el benchmark justifica un modelo/dimensión mayor, T-205 debe documentar explícitamente el cambio a `halfvec` y T-104B debe crear el tipo/índice correspondiente; no se permite seleccionar silenciosamente un embedding de 3072 dimensiones con `vector`.

## 2. Decisión registrada: durabilidad de corridas y SSE — `DECIDIDA (piloto)`

**Problema.** El contrato promete `202` + stream + recuperación tras desconexión: eso exige que las corridas sobrevivan a cortes de red y reinicios del proceso, sin depender de la memoria de FastAPI.

**Alternativas consideradas:** (a) cola externa con workers (Celery/Redis, RQ) — descartada para el piloto por Art. III (máximo 2 servicios; complejidad no justificada a ~500 corridas/mes); (b) todo en memoria — descartada por violar RF-209; (c) **elegida:** un único worker + estado y eventos en PostgreSQL + secuencia de eventos por corrida + reconexión `Last-Event-ID` (detalle normativo en plan.md §11).

**Semántica única (revisión 3):** la desconexión del navegador NO interrumpe la ejecución; los eventos se reanudan con `Last-Event-ID`; un reinicio del proceso SÍ interrumpe la corrida activa, que queda en estado TERMINAL `interrupted` con eventos y resultados parciales disponibles; el usuario vuelve a ejecutar la consulta. Al arrancar, cada proceso genera un `worker_instance_id` y marca de forma idempotente como `interrupted` toda corrida `running` asociada a una instancia anterior. El heartbeat queda como mecanismo adicional para detectar workers muertos durante la operación. Se descartó la reanudación automática del trabajo del agente: prometer resurrección del grafo tras matar el único worker es frágil y deshonesto para un piloto; el checkpointer de LangGraph queda solo para inspección/diagnóstico.

**Decisión sobre timeout:** la duración máxima excedida termina como `failed` con código `RUN_TIMEOUT`, no como `interrupted`. Justificación: el timeout es un límite operacional definido por configuración (`RUN_MAX_DURATION_S`) y por tanto representa una falla controlada de ejecución, distinta de una interrupción externa causada por reinicio, heartbeat vencido o desaparición del worker. Esta separación permite medir problemas de latencia y costo sin mezclarlos con reinicios de infraestructura.

**Lease de instancia:** para evitar que un despliegue con dos procesos solapados interrumpa corridas sanas, `worker_instance_id` no basta por sí solo. Cada instancia mantiene una lease en `worker_instances`; al arrancar, el backend solo cierra corridas de otra instancia si la lease de esa instancia ya venció. Política normativa: `WORKER_LEASE_TTL_S = RUN_HEARTBEAT_TIMEOUT_S` por defecto y renovación cada tercio de ese TTL. El piloto limita la concurrencia con `MAX_CONCURRENT_RUNS`, pero no asume que solo pueda existir un proceso durante despliegues; la lease es la fuente de verdad para decidir si una instancia murió.

**Condición de revisión:** si el piloto supera ~2.000 corridas/mes o se necesita más de un worker, esta decisión se reabre aquí (la cola externa pasa a ser candidata) y requiere enmienda de plan.md §11 y Constitución Art. III.3.

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

---

*Para añadir una nueva decisión: sección numerada, estado, problema, alternativas, criterios, decisión y consecuencias. Las decisiones `PENDIENTE` bloquean las tareas que dependan de ellas (ver tasks.md).*
