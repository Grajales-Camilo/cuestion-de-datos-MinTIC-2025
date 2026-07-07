# Modelo de Datos — Cuestión de Datos v2.0

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Base:** PostgreSQL 15+ con extensión `pgvector` · Migraciones con Alembic
**Implementa:** RF-301…304, RF-703, RF-601…603 de [`spec.md`](./spec.md)

> Convenciones: nombres de tabla en `snake_case` plural; PK `id` (UUID v4 salvo indicación); timestamps `created_at`/`updated_at` en UTC (`timestamptz`); borrado lógico solo donde se indica.

---

## 1. Diagrama entidad-relación (lógico)

```
catalog_datasets 1──N catalog_columns
catalog_datasets 1──1 catalog_embeddings
catalog_datasets 1──N evidence_results        ingest_runs (independiente, log)
agent_runs       1──N agent_steps
agent_runs       1──N agent_run_events        (eventos SSE numerados, durabilidad)
agent_runs       1──N evidence_results
evidence_results 1──1 quality_reports
evidence_results 1──N quantitative_claims     (afirmaciones cuantitativas, RF-208)
eval_suites      1──N eval_cases
eval_runs        N──1 eval_suites
eval_runs        1──N eval_case_results N──1 eval_cases
divipola_entries (tabla de referencia estática)
technical_metrics (independiente: métricas no identificables de corridas ya borradas)
(+ tablas de checkpoints gestionadas por el checkpointer PostgreSQL de LangGraph)
```

## 2. Entidades del catálogo (índice semántico)

### `catalog_datasets`
Espejo de metadatos de un dataset de datos.gov.co. Fuente: Discovery API.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | text PK | El identificador Socrata de 9 caracteres (`xxxx-xxxx`). No UUID: se usa el ID natural. |
| `name` | text NOT NULL | Título del dataset. |
| `description` | text | Limpia de HTML, truncada a 2.000 chars en ingesta. |
| `publisher` | text | Entidad publicadora (ej. "Ministerio de Salud"). |
| `category` | text | Categoría del portal. |
| `row_count` | bigint | Filas aproximadas reportadas. |
| `data_updated_at` | timestamptz | Última actualización de los DATOS en el portal. Insumo de la dimensión *temporalidad*. |
| `metadata_synced_at` | timestamptz NOT NULL | Última sincronización de la ingesta (RF-303). |
| `api_active` | boolean NOT NULL default true | false si el recurso dejó de responder; los inactivos se excluyen de la búsqueda. |
| `embedding_text` | text | Texto compuesto usado para el embedding (auditable). |

**Reglas de negocio:**
- Upsert por `id` (idempotencia, RF-304). Nunca se borra físicamente: si desaparece del portal, `api_active = false`.
- Un dataset sin `name` no se indexa.

### `catalog_columns`
| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK | |
| `dataset_id` | text FK → catalog_datasets ON DELETE CASCADE | |
| `field_name` | text NOT NULL | Nombre de campo API (el que se usa en SoQL). |
| `display_name` | text | |
| `data_type` | text NOT NULL | `text`, `number`, `calendar_date`, etc. (tipos Socrata). |
| `description` | text | |
| `sample_values` | jsonb | Hasta 5 valores de ejemplo capturados en ingesta/perfilado (insumo del agente). |
| `null_ratio` | numeric(5,4) | Proporción de nulos si fue perfilada (insumo de *completitud*). |

- Única por (`dataset_id`, `field_name`).

### `catalog_embeddings`
| Campo | Tipo | Reglas |
|---|---|---|
| `dataset_id` | text PK/FK → catalog_datasets | 1:1. |
| `embedding` | vector(`<DIM>`) NOT NULL | **La dimensión NO está fijada todavía.** Se define con la selección del modelo de embeddings (benchmark T-205, decisión documentada en [`research.md`](./research.md) §1). La migración definitiva de esta tabla (T-104B) se crea DESPUÉS de esa decisión y DEBE usar la dimensión seleccionada. |
| `model` | text NOT NULL | Nombre+versión del modelo de embeddings. NO DEBEN mezclarse embeddings de modelos o dimensiones distintas en el mismo índice; cambiar de modelo exige regenerar completamente el índice o versionar índices separados. |

- Índice: `HNSW (embedding vector_cosine_ops)`, creado en la migración de T-104B.

### `ingest_runs`
Log de ejecuciones de ingesta (RF-701).

| Campo | Tipo |
|---|---|
| `id` uuid PK · `started_at` / `finished_at` timestamptz · `trigger` text (`manual`\|`cron`) · `datasets_new` int · `datasets_updated` int · `datasets_failed` int · `error_summary` jsonb |

## 3. Entidades de ejecución del agente

### `agent_runs`
Una investigación completa (RF-703). **No almacena el documento del usuario** (Art. VI.4): solo la pregunta y los resultados.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK | Devuelto al cliente como `run_id`. |
| `question` | text NOT NULL | Pregunta efectiva enviada al agente. |
| `context_hint` | text | Fragmento de sección del lienzo (≤ 1.000 chars) si vino de RF-104. |
| `status` | text NOT NULL | `running` → `completed` \| `no_evidence` \| `failed` \| `interrupted` \| `cancelled`. Transiciones solo hacia adelante. `interrupted`: corrida huérfana o cortada por reinicio/timeout (plan.md §11). `cancelled`: reservado — no existe endpoint de cancelación en v2.0; añadirlo requiere actualizar `contracts/api-rest.md`. |
| `heartbeat_at` | timestamptz | Actualizado periódicamente por la corrida activa; base de la detección de huérfanas. |
| `last_event_seq` | int NOT NULL default 0 | Última secuencia emitida en `agent_run_events`. |
| `run_access_token_hash` | text NOT NULL | Hash SHA-256 del token de acceso. El token en claro NUNCA se almacena (RF-801). |
| `run_access_token_expires_at` | timestamptz NOT NULL | Expiración del token. REGLA: `= created_at + RETENTION_USER_DAYS` — el token expira exactamente cuando vence la retención de los datos, nunca antes (evita datos inaccesibles pero retenidos). |
| `retention_class` | text NOT NULL default `user` | `user` \| `eval` (ver §7, regla 1). Las métricas técnicas NO son una clase de corrida: viven en la tabla independiente `technical_metrics`. |
| `delete_requested_at` | timestamptz | Marca de solicitud de borrado (RF-803). |
| `deleted_at` | timestamptz | Marca del borrado completo efectivo (§7, regla 1). |
| `llm_provider` / `llm_model` | text | Configuración usada (RF-206, comparativas OE3). |
| `steps_used` | int | ≤ presupuesto (RF-201). |
| `latency_ms` | int | Total. |
| `input_tokens` / `output_tokens` | int | Suma de todos los pasos. |
| `estimated_cost_usd` | numeric(10,6) | Para RNF-009. |
| `final_answer` | jsonb | Respuesta sintetizada (estructura del contrato REST). |
| `created_at` | timestamptz | Retención según `retention_class` (§7, regla 1). |

### `agent_steps`
| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK · `run_id` uuid FK → agent_runs CASCADE · `step_number` int NOT NULL | Único por (`run_id`,`step_number`). |
| `node` | text NOT NULL | `planner` \| `router` \| `tool:<nombre>` \| `quality_validator` \| `claim_builder` \| `synthesizer`. |
| `tool_input` | jsonb | Entrada de la herramienta (contrato agent-tools.md). |
| `tool_output_summary` | jsonb | Salida truncada (máx. 20 KB; nunca datasets completos). |
| `display_message` | text | Mensaje en lenguaje claro mostrado al usuario (RF-204). |
| `latency_ms` | int · `error` | text | |

### `agent_run_events`
Registro durable de TODOS los eventos SSE de una corrida (RF-209, plan.md §11). Se inserta ANTES de emitir cada evento; habilita la reconexión con `Last-Event-ID`.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK | |
| `run_id` | uuid FK → agent_runs CASCADE | |
| `seq` | int NOT NULL | Secuencia monotónica por corrida. Único por (`run_id`, `seq`). |
| `event_type` | text NOT NULL | `step` \| `evidence` \| `answer` \| `error` (mismos tipos del contrato SSE). |
| `payload` | jsonb NOT NULL | Cuerpo exacto emitido al cliente. |
| `created_at` | timestamptz NOT NULL | |

**Reglas:** los eventos terminales (`answer`/`error`) se conservan mientras exista la corrida; en el borrado RF-803 se eliminan con ella. La emisión SSE lee de esta tabla para reenviar `seq > Last-Event-ID` sin pérdida ni duplicación.

### `technical_metrics`
Métricas agregadas **no identificables**, copiadas de una corrida justo antes de su borrado (por retención vencida o por RF-803). Sin FK a `agent_runs` (la corrida ya no existe) y sin ningún contenido de usuario.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK | |
| `run_month` | text NOT NULL | Mes de la corrida (`2026-07`) — granularidad gruesa a propósito. |
| `retention_class_origin` | text NOT NULL | `user` \| `eval`. |
| `status_final` | text NOT NULL | Estado terminal de la corrida. |
| `llm_provider` / `llm_model` | text | |
| `steps_used` / `latency_ms` / `input_tokens` / `output_tokens` | int | |
| `estimated_cost_usd` | numeric(10,6) | |
| `created_at` | timestamptz NOT NULL | Retención: 12 meses (`RETENTION_TECH_MONTHS`). |

**Prohibido** añadir a esta tabla campos con contenido de usuario (pregunta, contexto, filas, narrativas, citas): hacerlo requiere enmienda de este documento y revisión contra RF-802/804.

### Checkpoints de LangGraph
El checkpointer PostgreSQL oficial de LangGraph crea y gestiona sus propias tablas (esquema controlado por la librería, no por Alembic). Su uso en el piloto es exclusivamente de **inspección y diagnóstico**: `interrupted` es un estado terminal y NO hay reanudación automática (plan.md §11). Se purgan junto con la corrida a la que pertenecen.

## 4. Entidades de evidencia y calidad

### `evidence_results`
Resultado de datos que el agente presenta al usuario. Es la unidad citable (Art. I.2).

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK |
| `run_id` | uuid FK → agent_runs CASCADE |
| `dataset_id` | text FK → catalog_datasets | NOT NULL: no hay evidencia sin fuente. |
| `soql_query` | text NOT NULL | Consulta exacta ejecutada. |
| `executed_at` | timestamptz NOT NULL | |
| `source_url` | text NOT NULL | URL pública del dataset en datos.gov.co. |
| `rows` | jsonb NOT NULL | Filas devueltas (máx. 1.000; el LIMIT lo garantiza el tool). |
| `row_count` | int | |
| `narrative` | text | Párrafo citable generado por el sintetizador. |
| `citation` | jsonb NOT NULL | Objeto de cita completo: `{dataset_id, dataset_name, publisher, soql_query, executed_at, source_url, data_updated_at}`. Es lo que viaja al documento del usuario (RF-103). |

**Regla dura:** un `evidence_results` sin `quality_reports` asociado NO puede entregarse al cliente (Art. I.4). La API lo garantiza componiendo ambos en la misma transacción.

### `quality_reports`
Resultado de la capa de validación (RF-401/402). Estructura detallada del cálculo en `contracts/validacion-calidad.md`.

| Campo | Tipo | Reglas |
|---|---|---|
| `evidence_id` | uuid PK/FK → evidence_results | 1:1. |
| `score_total` | int NOT NULL CHECK 0–100 | |
| `classification` | text NOT NULL | `alta` \| `media` \| `baja` \| `no_recomendada` (umbrales del contrato). |
| `dim_schema` / `dim_completeness` / `dim_timeliness` / `dim_traceability` | jsonb NOT NULL | Cada una: `{score, checks: [{check, passed, detail}]}`. |
| `warnings_user` | jsonb | Lista de advertencias en lenguaje claro (RF-403). |
| `validator_version` | text NOT NULL | Versión del módulo de validación (reproducibilidad). |

### `quantitative_claims`
Afirmaciones cuantitativas trazables (RF-208). Toda cifra presentada al usuario DEBE tener exactamente un claim; la narrativa se genera SOLO a partir de `display_value` de claims. Las cifras derivadas las calcula el módulo determinista (herramienta T7 de `contracts/agent-tools.md`), nunca el LLM.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid PK | Es el `claim_id` del contrato REST. |
| `run_id` | uuid FK → agent_runs CASCADE | |
| `evidence_id` | uuid FK → evidence_results CASCADE | NOT NULL: no hay claim sin evidencia fuente. |
| `claim_text` | text NOT NULL | Enunciado en lenguaje natural ("La tasa fue 8,4 %"). |
| `claim_type` | text NOT NULL | `direct` (valor tomado tal cual de una celda) \| `derived` (calculado con fórmula). |
| `source_row_indexes` | int[] NOT NULL | Índices de las filas de `evidence_results.rows` usadas (o `[-1]` si opera sobre el agregado completo). |
| `columns_used` | text[] NOT NULL | Columnas utilizadas. |
| `formula` | text | Fórmula reproducible (`desertores / matriculados * 100`). NULL solo si `claim_type = direct`. |
| `raw_value` | numeric NOT NULL | Valor bruto sin redondear (`8.3721`). |
| `display_value` | text NOT NULL | Valor exactamente como se presenta ("8,4 %"). |
| `unit` | text | `%`, `COP`, `personas`, `casos/100k`… |
| `rounding` | int | Decimales de la regla de redondeo aplicada. |
| `source_hash` | text NOT NULL | Hash SHA-256 del subconjunto de filas fuente + fórmula: referencia reproducible del cálculo. |

**Reglas:** `raw_value` DEBE ser reproducible re-aplicando `formula` sobre las filas referenciadas (verificado en pruebas.md §4.2); `display_value` DEBE derivarse de `raw_value` + `rounding` + `unit`; el verificador de groundedness comprueba que ninguna cifra del texto final carece de claim.

## 5. Entidades de evaluación (OE3)

### `eval_suites`
`id` uuid PK · `name` text UNIQUE (ej. `golden-v1`) · `description` text · `version` text · `created_at`.

### `eval_cases`
| Campo | Tipo | Reglas |
|---|---|---|
| `id` uuid PK · `suite_id` FK → eval_suites | |
| `question` | text NOT NULL | |
| `case_type` | text NOT NULL | `positive` (existe evidencia) \| `negative` (no existe: mide honestidad RNF-005). |
| `expected_dataset_ids` | text[] | Datasets que deberían recuperarse (recall@k). Vacío en negativos. |
| `expected_facts` | jsonb | Hechos verificables opcionales (valores/orden de magnitud) para groundedness asistido. |
| `notes` | text | Por qué existe el caso; fuente de verdad usada. |

- El golden set también se versiona como archivo en `backend/eval/golden/` (Art. II.3); la tabla es su materialización para corridas.

### `eval_runs`
`id` uuid PK · `suite_id` FK · `git_commit` text NOT NULL · `llm_provider`/`llm_model` text NOT NULL · `embedding_model` text · `started_at`/`finished_at` · métricas agregadas: `success_rate`, `claims_coverage` (debe ser 1.0), `claims_reproducible` (debe ser 1.0), `orphan_figures_count` (debe ser 0), `recall_at_10`, `fabrication_count`, `latency_p50_ms`, `latency_p95_ms`, `avg_cost_usd` (RF-602/603, RNF-003).

### `eval_case_results`
`id` uuid PK · `eval_run_id` FK CASCADE · `case_id` FK · `agent_run_id` FK → agent_runs · `passed` boolean · `metrics` jsonb (detalle por métrica) · `failure_reason` text.

## 6. Tabla de referencia geográfica

### `divipola_entries`
Reemplaza el arreglo hardcodeado `utils/maestro_divipola.js` de v1.0 con el maestro DANE completo (1.103+ municipios).

| Campo | Tipo | Reglas |
|---|---|---|
| `code` | text PK | Código DIVIPOLA de 5 dígitos (municipio) o 2 (departamento). |
| `name` | text NOT NULL | Nombre oficial DANE. |
| `department_code` / `department_name` | text | |
| `level` | text NOT NULL | `department` \| `municipality`. |
| `name_normalized` | text NOT NULL | Sin tildes, mayúsculas — para matching (`BOGOTA`, `MEDELLIN`). Índice trigram (`pg_trgm`) para búsqueda difusa. |
| `alt_names` | text[] | Alias comunes ("Bogotá D.C.", "Santafé de Bogotá"). |

- Datos cargados una vez desde el dataset oficial DIVIPOLA de datos.gov.co (script en Fase 2); actualización manual anual.

## 7. Reglas transversales de datos

1. **Retención diferenciada (RF-804).** Períodos por `retention_class`, todos **configurables** por variables de entorno (valores propuestos para el piloto, revisables en research.md §4):

   | Clase | Contenido | Retención propuesta | Al vencer |
   |---|---|---|---|
   | `user` | Corridas normales: pregunta, `context_hint`, evidencias, claims, eventos, checkpoints | 90 días (`RETENTION_USER_DAYS`) | **Borrado completo** de la corrida y TODAS sus relaciones (steps, events, evidence, claims, quality_reports, checkpoints, hash del token), tras copiar las métricas agregadas no identificables a `technical_metrics`. NO se anonimiza fila a fila: el borrado total evita conflictos con campos `NOT NULL` y copias residuales. |
   | `eval` | Corridas de la batería OE3 | 24 meses (`RETENTION_EVAL_MONTHS`) | Igual procedimiento; el plazo largo garantiza la reproducibilidad del working paper. |

   Las métricas técnicas viven en la tabla independiente `technical_metrics` (12 meses, `RETENTION_TECH_MONTHS`). El borrado por solicitud (RF-803) tiene prioridad sobre estos plazos y sigue el mismo procedimiento. Las trazas nunca contienen documentos completos del usuario, solo `context_hint` acotado.
2. **El documento del usuario NO se persiste en servidor en v2.0**: vive en `localStorage` del navegador (RF-102). Si en v2.x se añade persistencia, requiere enmienda a este documento + mecanismo de borrado (Art. VI.4).
3. **Integridad de espacios vectoriales:** `catalog_embeddings.model` homogéneo en toda la tabla; NO DEBEN convivir embeddings de modelos o dimensiones distintas en el mismo índice. Cambiar de modelo exige truncar y regenerar el índice completo, o versionar índices separados (tabla nueva por modelo). La dimensión definitiva se decide en research.md §1 (T-205) antes de la migración de T-104B.
4. **Zonas horarias:** todo en UTC en base de datos; conversión a `America/Bogota` solo en presentación.
5. **Volumetría estimada:** catálogo ~8.000 filas + 8.000 vectores (trivial); trazas ~50 KB por investigación → ~25 MB / 500 investigaciones/mes. El tier gratuito (500 MB–1 GB) alcanza para el piloto; alerta al 70% de capacidad.
