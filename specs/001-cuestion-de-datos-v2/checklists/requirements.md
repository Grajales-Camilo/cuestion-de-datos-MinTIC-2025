# Checklist de Verificación — Resolución de Bloqueos Documentales

**Última revisión:** 2026-07-07 (ronda 4) · **Revisor:** editor SDD (sesión de revisión técnica)
**Uso:** verificar que los bloqueos identificados quedaron resueltos de forma consistente en todo `specs/`. Re-ejecutar tras cualquier enmienda mayor.

Comando de búsqueda sugerido (PowerShell, desde `specs/`):
```powershell
Get-ChildItem . -Recurse -Filter *.md |
    Select-String -Pattern 'sentence-transformers|benchmark-embeddings|T-202|T-205|quick_counts|pytest|integration|HealthResponse|catalog_index|last_event_seq|agent_run_events|alias_normalized|ambiguous|source_hash|evidence_id|retention|T-306|RNF-012|ESC-06|ESC-07'
```

---

# Ronda 1 — Bloqueos documentales originales

## Bloqueo 1 — Modelo de embeddings obsoleto
- [x] Cero referencias vigentes a `text-embedding-004` en `specs/`.
- [x] Candidatos planteados sin ganador: `intfloat/multilingual-e5-large`, `gemini-embedding-2`, otro justificable (plan.md §2, tasks.md T-205).
- [x] `research.md` §1 con problema, alternativas, 10 criterios, procedimiento de benchmark y estado `PENDIENTE`.
- [x] quickstart.md no fija un modelo por defecto.

## Bloqueo 2 — Orden migraciones ↔ selección de modelo
- [x] `T-104A` crea las tablas SIN `catalog_embeddings` (tasks.md, Fase 1).
- [x] Orden documental: T-201 → T-201A → T-202 → T-205 (benchmark) → T-104B (migración definitiva) → T-203 → T-204.
- [x] `data-model.md` usa `vector(<DIM>)` con nota de decisión pendiente.
- [x] Reglas: no mezclar modelos/dimensiones; cambio de modelo ⇒ regenerar índice o versionar índices separados.

## Bloqueo 3 — Reproducibilidad local
- [x] Constitución Art. II.2: componentes propios ejecutables localmente; `compose.yaml` como vía oficial.
- [x] plan.md §2 distingue modalidad local (Docker) y despliegue (gestionado).
- [x] quickstart.md: Docker como prerrequisito; Supabase/Neon NO requeridos para desarrollo.
- [x] Tarea T-105 define `compose.yaml` (el archivo aún no se crea: es implementación).
- [x] pruebas.md §2.3: integración contra Postgres local real; CI sin credenciales gestionadas.

## Bloqueo 4 — `run_id` como credencial implícita
- [x] RF-801…804 en spec.md (Grupo 800): token, consentimiento, borrado, retención diferenciada.
- [x] Token entregado UNA vez; `Authorization: Bearer`; nunca en URL (api-rest.md §2, §3, §7, §7b).
- [x] data-model.md: `run_access_token_hash`, `run_access_token_expires_at`, `retention_class`, `worker_instance_id`, `terminal_error_code`, `terminal_event_written_at`; no quedan campos de ciclo indefinido (`delete_requested_at`, `deleted_at`) en `agent_runs`.
- [x] Contrato `DELETE /v2/agent/runs/{run_id}` (api-rest.md §7b).
- [x] Retención diferenciada con valores configurables.
- [x] Consentimiento previo a persistir (RF-802; T-502).
- [x] Pruebas de token, expiración, hash y borrado (pruebas.md §2.2 y §6).

## Bloqueo 5 — Durabilidad de ejecuciones
- [x] plan.md §11: un worker, estado en PostgreSQL, eventos numerados, huérfanas, timeouts, terminales conservados.
- [x] RF-209 en spec.md; tabla `agent_run_events`; `heartbeat_at`; estado `interrupted`.
- [x] SSE con `id:` y reconexión `Last-Event-ID` (api-rest.md §3).
- [x] PoC temprana T-300 antes del grafo completo.
- [x] Prueba de integración de 6 pasos (`test_durability.py`, pruebas.md §2.3).

## Bloqueo 6 — Groundedness insuficiente
- [x] RF-208; entidad `quantitative_claims`; nodo determinista T7; `claims[]` en el contrato REST.
- [x] Narrativa generada SOLO desde `display_value` de claims validados.
- [x] Métrica = verificación de la cadena completa del claim; regex solo detector auxiliar.
- [x] validacion-calidad.md §6 articula calidad de evidencia ↔ claims.

## Bloqueo 7 — Accesibilidad
- [x] Objetivo = WCAG 2.2 nivel AA en constitución, spec, tasks y pruebas; cero referencias a 2.1.
- [x] Lighthouse/axe como puerta parcial, no certificación.
- [x] Revisión manual obligatoria documentada (pruebas.md §5) con acta por release.

## Validación transversal (ronda 1)
- [x] Jerarquía documental respetada; nada eliminado sin justificación; IDs preservados (T-104 → T-104A/B por estrategia indicada).
- [x] research.md y este checklist en el índice de specs/README.md.

---

# Ronda 2 — Revisión externa (2026-07-06)

## Bloqueos nuevos

- [x] **R2-1 Integridad de cifras 100%.** RNF-003 ya no admite 5% de cifras sin respaldo: cobertura de claims = 100%, reproducibles = 100%, huérfanas = 0, con bloqueo en runtime (re-síntesis o `failed`). El 80% de RNF-002 se conserva solo para la tasa general de éxito. Métricas de `eval_runs`: `claims_coverage`, `claims_reproducible`, `orphan_figures_count`.
- [x] **R2-2 Orden de tareas ejecutable.** Fase 3: T-300 → T-301 → T-302 (T1–T5) → T-401 (nodo T6) → T-403 (nodo T7) → T-303 (integración) → T-304 → T-305; Fase 4 = verificación integrada (T-402). T6/T7 reclasificados como nodos deterministas del pipeline, NO herramientas invocables por el LLM (agent-tools.md).
- [x] **R2-3 Token vive lo que viven los datos.** La expiración deriva de `retention_class`: `user = created_at + RETENTION_USER_DAYS`; `eval = created_at + RETENTION_EVAL_MONTHS`; al vencer la retención se elimina la corrida; sin renovación (imposible sin cuentas). quickstart, plan §11, data-model y research §3 alineados.
- [x] **R2-4 Borrado ejecutable, no anonimización imposible.** Al vencer retención o ante RF-803: borrado COMPLETO de la corrida y relaciones (compatible con `NOT NULL`), tras copiar métricas no identificables a la nueva tabla `technical_metrics`. `retention_class` reducido a `user`|`eval`.
- [x] **R2-5 Semántica única de durabilidad.** Desconexión NO interrumpe; reinicio SÍ; `interrupted` es TERMINAL; sin reanudación automática (checkpointer solo diagnóstico); el usuario re-ejecuta. RF-209, plan §11, data-model, T-300 y api-rest coherentes.

## Correcciones adicionales

- [x] **R2-6 Reproducibilidad local bien formulada.** Art. II.2: "componentes propios" localmente; datos.gov.co y proveedores LLM son dependencias remotas declaradas. DEP-01 = "PostgreSQL 15+ con pgvector, local o gestionado".
- [x] **R2-7 Fuente no oficial = regla dura.** `publisher_official` ya no puntúa: evidencia RECHAZADA (no elegible), coherente con Art. I. Puntos de D4 redistribuidos (60/40). Caso de prueba §5.8.
- [x] **R2-8 Temporalidad corregida.** Base preferida `data_cutoff_at` (corte inferido de los datos) con fallback explícito a `data_updated_at` declarando `basis`; advertencia cuando D3 ≤ 70; ejemplo del contrato con fechas coherentes (corte 2025-03-15 ≈ 16 meses). Ver R3-1 para la reubicación normativa al nivel de evidencia.
- [x] **R2-9 Placeholders contextuales.** Patrón configurado por dataset/columna + codebook/descripción + proporción mínima (`PLACEHOLDER_MIN_RATIO`); casos de falsos positivos ("Total" legítimo, `9` real) en la suite.
- [x] **R2-10 Guardia SoQL estructural.** Parseo a gramática + listas blancas de cláusulas/funciones + columnas contra `catalog_columns` + complejidad máxima; lista negra solo defensa en profundidad. Nuevo error `SOQL_UNKNOWN_COLUMN`.
- [x] **R2-11 CORS completo.** Headers `Authorization`, `Content-Type`, `Last-Event-ID`; orígenes por `CORS_ALLOWED_ORIGINS`; previews de Vercel con origen exacto temporal, sin comodines.
- [x] **R2-12 RF-303 con ventana real.** `CATALOG_STALE_AFTER_DAYS=8` (plan §5.8); `metadata_synced_at` + `index_stale` en `/v2/catalog/search`.
- [x] **R2-13 Orden de lectura del README** alineado con la jerarquía normativa; research.md antes del plan.
- [x] **R2-14 Menores.** Constitución 1.2.0 con nota de enmienda; plan §3 referencia T-101 (no T-103); quickstart describe el sistema completo y activa el venv con `Activate.ps1`; `sentence-transformers` no es dependencia obligatoria pre-T-205; `agent_steps.node` incluye `claim_builder`; imagen pgvector con versión fijada; Art. V.4 habla de acciones observables, no "pasos de razonamiento".

---

# Ronda 3 — Bloqueos de implementación backend (2026-07-07)

- [x] **R3-1 Temporalidad al nivel correcto.** `catalog_datasets.latest_observed_cutoff_at` queda solo como pista; el corte normativo vive en `evidence_results.data_cutoff_at` y se calcula exclusivamente sobre las filas de esa evidencia. El fallback a `data_updated_at` debe decir "fecha de actualización del portal; corte estadístico desconocido".
- [x] **R3-2 Dependencias backend completas.** T-102 fija SQLAlchemy asíncrono, `psycopg[binary,pool]`, `langgraph-checkpoint-postgres`, `AsyncPostgresSaver.setup()`, `thread_id=run_id`, purga con `adelete_thread(run_id)` y `pip-audit`.
- [x] **R3-3 Retención implementable.** T-306 define job periódico, SLA máximo 24 h, borrado oportunista, copia atómica de métricas, snapshot eval, purga de checkpoints y purga de `technical_metrics`; pruebas de concurrencia e idempotencia.
- [x] **R3-4 RF-803 sin anonimización.** RF-803 elimina la alternativa "anonimizar" y exige borrado completo e irreversible de la corrida operativa y relaciones.
- [x] **R3-5 Publicadores oficiales normalizados.** Contratos y modelo usan `official_publishers.id`; alias viven en `official_publisher_aliases`; alias ambiguos producen `unknown`; entidades históricas tienen vigencia y sucesor; T-106/T-201 exigen cobertura verificable.
- [x] **R3-6 Corridas `eval` internas.** El endpoint público crea solo `user`; `retention_class` no entra por JSON público; el runner OE3 crea `eval` mediante servicio interno con `EVAL_MODE=true`.
- [x] **R3-7 `/health` sin contrato doble.** `/v2/health` usa `HealthResponse` tanto en 200 como en 503; es la única excepción al sobre estándar de errores.
- [x] **R3-8 Estados de corridas cerrados.** `GET /v2/agent/runs/{id}` define respuestas para `running`, `completed`, `no_evidence`, `interrupted` y `failed`; timeout = `failed/RUN_TIMEOUT`; reinicio/worker/heartbeat = `interrupted`.
- [x] **R3-9 Worker lease.** El arranque solo interrumpe corridas de instancias cuya lease venció; una instancia nueva no cancela corridas sanas durante despliegues solapados.
- [x] **R3-10 Límite de concurrencia viable.** `MAX_CONCURRENT_RUNS` es global por proceso; no se persiste IP ni hash de IP en v2.0.
- [x] **R3-11 PII y minimización.** La validación rechaza evidencia con datos personales identificables; T-201 clasifica riesgo PII; T5 prohíbe `SELECT *`; pruebas cubren rechazo y volumetría.
- [x] **R3-12 Parser SoQL definido.** T-302 implementa gramática restringida propia, canonicalización, listas blancas, alias/literales, `OFFSET <= 5000` y funciones permitidas.
- [x] **R3-13 Dimensión de embeddings acotada.** T-205 debe aceptar `vector(<DIM>)` solo con `DIM <= 2000`; dimensiones mayores requieren cambiar explícitamente a `halfvec`.
- [x] **R3-14 Quickstart PowerShell.** El POST del agente ya no usa continuaciones Bash; búsqueda de catálogo habla de `latest_observed_cutoff_at`; el modelo de embeddings queda como valor decidido por T-205 en el sistema completo.

---

# Ronda 4 — Auditoría de ejecución T-101 a T-300 (2026-07-07)

- [x] **R4-1 Estructura inicial desbloqueada.** T-105 queda antes de T-102; T-102 usa la base local ya creada; T-103 define servicio PostgreSQL+pgvector en CI cuando las pruebas tocan DB.
- [x] **R4-2 `DATABASE_URL` ejecutable.** plan.md §12 define formatos aceptados, transformación a SQLAlchemy async y cadena compatible con psycopg para checkpointer.
- [x] **R4-3 Modelo cerrado antes de T-104A.** `technical_metrics.source_run_hash` es clave idempotente; `eval_runs`/`eval_cases` tienen semilla/configuración; se agrega `socrata_success_rate`; T-104A incluye elegibilidad, PII y constraints.
- [x] **R4-4 Publicadores sin circularidad.** T-106 carga fixture inicial; T-201 ingesta con ese fixture; T-201A mide cobertura y propone mantenimiento. Alias no único produce `unknown`, nunca asignación automática.
- [x] **R4-5 Privacidad antes de Socrata.** PII `unknown` y `high` bloquean antes de T5; `medium` exige agregación mínima y ausencia de filas individuales; `sample_values` queda restringido a columnas `low`.
- [x] **R4-6 T6/T7 deterministas.** T6 separa elegibilidad de calidad y amplía salida; T7 usa DSL JSON, definición normativa de cifra y `source_hash` canónico.
- [x] **R4-7 Corridas sin ambigüedad operacional.** Token vencido converge a borrado oportunista + `404`; DELETE sobre corrida activa tiene gracia cooperativa; errores SSE terminales incluyen `status`.
- [x] **R4-8 Durabilidad y embeddings cerrados.** Lease tiene TTL/renovación; T-104B es condicional `vector`/`halfvec`; T-205 debe propagar modelo/dimensión a modelo, dependencias, `.env.example`, plan y quickstart.
- [x] **R4-9 Pruebas y trazabilidad.** Endpoints admin tienen dueño; pruebas cubren RF-403, CSV, gráficas, RNF-001 simple/multi-paso, RNF-010 p95/cobertura real y presupuestos de bytes.

# Ronda 5 — Corrección documental focalizada T-202/T-205/T-306/RNF-012 (2026-07-07)

- [x] **R5-1 Entorno T-205 reproducible.** T-102 distingue extra opcional `benchmark-embeddings` de dependencias definitivas de runtime; T-205 exige `pip install -e ".[dev,benchmark-embeddings]"`, versiones compatibles con Python 3.12 y registro de entorno/modelo/parámetros/costos.
- [x] **R5-2 Ruta con T-202.** Rutas y checklist incluyen `T-201 → T-201A → T-202 → T-205`; `resolver_geografia` depende de `divipola_entries` cargado.
- [x] **R5-3 Quickstart sin función fantasma.** `quick_counts()` se reemplaza por consultas `docker compose exec db psql` sobre `official_publishers`, `catalog_datasets`, `catalog_embeddings` y `divipola_entries`.
- [x] **R5-4 Suites pytest separadas.** `pytest -m "not integration"` y `pytest -m integration`; marcador `integration` registrado en `pyproject.toml`; sin `addopts` global excluyente.
- [x] **R5-5 Healthcheck por fase.** Antes de T-203/T-204, `catalog_index` degradado/no inicializado produce `503 degraded`; después del índice, conteos sanos permiten `200 ok`.
- [x] **R5-6 Secuencia SSE atómica.** T-300, plan, modelo y pruebas exigen `UPDATE agent_runs ... RETURNING last_event_seq` y transacción coherente con `agent_run_events`.
- [x] **R5-7 Aliases con índice parcial.** Alias no ambiguos únicos por índice parcial; aliases ambiguos duplicados permitidos si no asignan automáticamente.
- [x] **R5-8 `source_hash` reproducible.** Hash de contenido excluye `evidence_id`, `claim_id` y `run_id`; pruebas cubren estabilidad y cambios materiales.
- [x] **R5-9 Retención programada.** T-306 documenta servicio/CLI idempotente, endpoint admin, cron externo cada seis horas, secreto admin, ejecución única lógica, logs/métricas y acciones humanas en T-701.
- [x] **R5-10 RNF-012 verificable.** Pruebas y T-505 exigen acta manual de idioma/claridad en español con responsable, evidencia, criterio y ubicación.
- [x] **R5-11 ESC-06/ESC-07 trazables.** ESC-06 referenciado en T-601/T-602/T-603 y pruebas de evaluación; ESC-07 en T-201/T-203/T-206 y pruebas de ingesta/índice.

# Ronda 6 — Correcciones de auditoría integral preimplementación (2026-07-07)

- [x] **R6-1 Bootstrap de pruebas T-103.** T-102 exige pruebas mínimas deterministas sin red para que `pytest -m "not integration"` no falle por ausencia de tests; T-103 consume esa suite en el primer PR.
- [x] **R6-2 Retención sin decisión implícita.** `RETENTION_HASH_SALT` queda documentado en plan, modelo, pruebas, quickstart y despliegue; `source_run_hash` usa ese secreto servidor para idempotencia.
- [x] **R6-3 Lock concreto del barrido.** Research, plan, modelo, contrato admin, pruebas y T-306 usan advisory lock PostgreSQL `pg_try_advisory_xact_lock(20260707, 804)` y respuesta `already_running` sin efectos.
- [x] **R6-4 Quickstart PowerShell literal.** Las variables usadas como `$env:...` se exportan explícitamente en la sesión antes de los comandos manuales.
- [x] **R6-5 Trazabilidad auxiliar.** README/AGENTS aclaran que `AGENTS.md` es operativo y no altera la jerarquía; T-705 referencia el sitio divulgativo/producto público sin ampliar el alcance funcional del software.

## Pendientes (sin cambios)

- [x] Decisión de embeddings y dimensión (research.md §1) — resuelta por
  T-205 con `gemini-embedding-2`, 768 dimensiones; T-104B/T-203 ya no están
  bloqueadas por esta decisión.

# Ronda 7 — Enmienda propuesta T-615 (2026-07-16)

> **PROPUESTA PARA REVISIÓN — NO IMPLEMENTADA.** Marcar esta ronda como
> aprobada requiere decisión humana explícita; el commit documental no la
> aprueba automáticamente.

- [ ] **R7-1 Concepto y separación.** Aprobar
  `GroundedFact = QuantitativeClaim | TextualFact` y tabla separada
  `textual_facts`; RF-208/RNF-003 permanecen intactos.
- [ ] **R7-2 Operaciones cerradas.** Aprobar
  `direct_text`, `value_presence`, `category_selection`, `argmax_label`,
  `argmin_label` y `ordered_text_set`; prohibir texto mediante `count=1`.
- [ ] **R7-3 Normalización.** Aprobar `text-es-v1`: NFC, espacios/saltos
  canónicos, `casefold` solo para comparación y preservación de
  tildes/`ñ`/puntuación/grafía mostrada.
- [ ] **R7-4 Ambigüedad.** Aprobar `tie_policy=reject` para extremos y
  prohibición de seleccionar por orden incidental.
- [ ] **R7-5 Procedencia y hash.** Aprobar material canónico, exclusión de
  UUIDs/timestamps y dataset resuelto obligatoriamente desde la evidencia.
- [ ] **R7-6 API.** Aprobar lista `claims` única con discriminador
  `claim_kind`, campos cuantitativos conservados y adaptador histórico
  estrictamente cuantitativo.
- [ ] **R7-7 Síntesis.** Aprobar selección de IDs + conectores cerrados +
  renderizado factual determinista; no admitir prosa factual libre.
- [ ] **R7-8 Métricas.** Aprobar métricas textuales separadas y puerta total
  por conjunción, sin cambiar umbrales ni RNF-003.
- [ ] **R7-9 Golden.** Confirmar que T-615 no toca `golden-v1` ni crea
  `golden-v2`; `acceptable_facts` discriminados solo se trabajan en T-616.
- [ ] **R7-10 Entregas.** Aprobar secuencia T-615A…T-615J y autorización
  separada por incremento, migración y cierre.
