# Contrato — API REST y Streaming (frontend ⇄ backend)

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Servidor:** FastAPI (`backend/app/main.py`) · **Consumidor:** el navegador, en conexión DIRECTA con CORS restringido a los orígenes del frontend (plan.md §11); el SSE se consume con `fetch()` + stream de lectura, no con `EventSource` nativo
**Regla:** el código se adapta a este contrato. Cambiarlo exige actualizar este archivo en el mismo PR (specs/README.md, regla 4).

Convenciones: JSON en `snake_case`; errores con el sobre estándar de §6; todas las fechas ISO-8601 UTC. Prefijo de versión: `/v2`. Excepción explícita: `/v2/health` devuelve siempre `HealthResponse`, incluso en `503`.

---

## 1. `GET /v2/health`
Verificación de vida (RF-702). Sin autenticación.

**200 OK**
```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "catalog_index": {"status": "ok", "datasets_indexed": 7842, "last_ingest_at": "2026-07-01T03:00:00Z"},
    "llm_provider": {"status": "ok", "provider": "google", "model": "gemini-2.5-flash"}
  },
  "version": "2.0.0"
}
```
**503 Service Unavailable**
Mismo esquema `HealthResponse`, con `"status": "degraded"` y cada check fallido marcado en `checks`. No usa el sobre estándar de error; esta excepción existe para que monitores puedan leer degradación parcial. No se usa `500` para dependencias esperadamente degradables.

## 2. `POST /v2/agent/query` — iniciar investigación
Inicia una corrida del agente (RF-201). Respuesta inmediata con `run_id`; el progreso se consume por SSE (§3).

**Request**
```json
{
  "question": "¿Cuál es la tasa de deserción escolar en Sonsón en los últimos 5 años?",
  "context_hint": "Sección: Definición del problema. Texto: La deserción escolar en el municipio...",
  "options": {
    "max_steps": 10,
    "llm_provider": null,
    "llm_model": null
  }
}
```
- `question`: obligatorio, 10–2.000 caracteres.
- `context_hint`: opcional, ≤ 1.000 caracteres (RF-104).
- `options.llm_*`: opcional; solo se respeta si `EVAL_MODE=true` en el servidor (uso del investigador ACT-03). Usuarios normales siempre reciben la configuración por defecto.
- Este endpoint público SIEMPRE crea `retention_class = "user"`. No acepta `retention_class` en JSON. Las corridas `eval` se crean únicamente por el runner OE3 mediante servicio interno del backend.

**202 Accepted**
```json
{
  "run_id": "1f0c...uuid",
  "run_access_token": "cdt_rt_9f8a...token-aleatorio-256-bits",
  "token_expires_at": "2026-10-04T14:22:31Z",
  "stream_url": "/v2/agent/stream/1f0c...uuid"
}
```
**Autorización (RF-801):** `run_access_token` se entrega **únicamente en esta respuesta** y no puede recuperarse después (el servidor solo guarda su hash). El cliente DEBE enviarlo en TODAS las operaciones posteriores sobre la corrida (§3, §7, §7b) mediante el encabezado `Authorization: Bearer <run_access_token>`. NO DEBE transmitirse en parámetros de URL. El `run_id` es público y no autoriza nada por sí mismo.
`token_expires_at` se calcula desde `retention_class`: corridas públicas `user` expiran en `created_at + RETENTION_USER_DAYS`; corridas internas `eval` expiran en `created_at + RETENTION_EVAL_MONTHS`.

**Consentimiento (RF-802):** el frontend DEBE haber mostrado el aviso de almacenamiento (qué se guarda, para qué, por cuánto tiempo, cómo borrarlo) antes de la primera llamada a este endpoint en la sesión.

**Errores:** `422` validación; `429` si hay más de `MAX_CONCURRENT_RUNS` corridas activas globales en el proceso. No se persiste IP en v2.0.

## 3. `GET /v2/agent/stream/{run_id}` — progreso en vivo (SSE)
`Content-Type: text/event-stream`. Requiere `Authorization: Bearer <run_access_token>` (401 sin token o inválido; si la corrida venció se ejecuta borrado oportunista y responde `404 RUN_NOT_FOUND`). Emite eventos hasta el evento terminal. Implementa RF-204 y RF-209.

> Nota de implementación: `EventSource` nativo no admite encabezados; el frontend consume este stream con `fetch` + lectura de stream (plan.md §11).

**Formato y reconexión:** cada evento incluye `id: <seq>` (secuencia monotónica por corrida, persistida en `agent_run_events`). Para reconectar, el cliente envía el encabezado estándar `Last-Event-ID: <último seq recibido>`; el servidor reenvía los eventos persistidos con `seq` mayor (sin pérdida ni duplicación) y continúa en vivo. Si la corrida ya terminó, el servidor reenvía los eventos faltantes hasta el terminal y cierra.

**Eventos (`id:` + `event:` + `data:` JSON):**

| event | data (campos principales) | Cuándo |
|---|---|---|
| `step` | `{step_number, node, display_message, detail}` | Cada transición del grafo. `display_message` en español claro ("Consultando indicadores de MinSalud…"); `detail` técnico opcional (SoQL, dataset). |
| `evidence` | objeto Evidencia (§5) | Cada evidencia validada lista. |
| `answer` | objeto RespuestaFinal (§4) | Terminal, status `completed` o `no_evidence`. |
| `error` | sobre de error (§6) con `status` terminal | Terminal, status `failed` o `interrupted`. |

Reglas: primer evento ≤ 2 s tras la conexión (RNF-008); heartbeat `: ping` cada 15 s; si el cliente se desconecta, la corrida continúa (estado y eventos persistidos, RF-209) y el resultado queda disponible por §7 o reconectando con `Last-Event-ID`. Si el servidor se reinicia, el cliente recibe al reconectar el evento terminal `error` con `status="interrupted"` y código `RUN_INTERRUPTED`; si la corrida excede `RUN_MAX_DURATION_S`, recibe `status="failed"` y código `RUN_TIMEOUT`.

## 4. Objeto `RespuestaFinal`
```json
{
  "run_id": "1f0c...",
  "status": "completed",
  "intention": "Consulta de deserción escolar municipal",
  "summary": "Según el Ministerio de Educación, la tasa de deserción en Sonsón...",
  "narrative": "De acuerdo con el conjunto de datos 'Estadísticas en Educación' (MEN, corte 2025), el municipio de Sonsón registró...",
  "evidence": [ /* array de objetos Evidencia, puede ser vacío */ ],
  "claims": [
    {
      "claim_id": "7c1d...uuid",
      "claim": "La tasa de deserción en transición fue 8,4 % en 2025",
      "claim_type": "derived",
      "evidence_id": "9a2b...",
      "dataset_id": "nudc-7mev",
      "source_row_indexes": [0, 1],
      "columns": ["matriculados", "desertores"],
      "formula": {"op": "mul", "args": [{"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]}, {"const": 100}]},
      "raw_value": 8.3721,
      "display_value": "8,4 %",
      "unit": "%",
      "rounding": 1,
      "source_hash": "sha256:ab12..."
    }
  ],
  "no_evidence_report": null,
  "usage": {"steps_used": 5, "latency_ms": 41200, "estimated_cost_usd": 0.011}
}
```
`status` permitido en `RespuestaFinal`: `completed`, `no_evidence`, `interrupted`, `failed`. Las corridas `running` usan `RunStatusResponse` (§7), no `RespuestaFinal`.
- `status = "no_evidence"` ⇒ `evidence: []` y `no_evidence_report` obligatorio (RF-205):
```json
{
  "reason": "No se encontraron datos de deserción desagregados para Sonsón.",
  "datasets_reviewed": [{"dataset_id": "abcd-1234", "name": "...", "why_rejected": "Solo tiene nivel departamental"}],
  "suggestions": ["Consultar la cifra a nivel de Antioquia", "Reformular por 'cobertura educativa'"]
}
```
- **Invariante (Art. I, RF-208):** toda cifra presente en `summary`, `narrative` o `evidence[].narrative` DEBE corresponder al `display_value` de un elemento de `claims`. El LLM NO calcula cifras: los claims `derived` los computa el módulo determinista (herramienta T7 de agent-tools.md). La coincidencia literal con `evidence[].rows` NO es suficiente por sí sola ni necesaria (los valores derivados no aparecen literalmente en las filas).
- `status = "interrupted"`: la corrida fue cortada por reinicio, heartbeat vencido o worker desaparecido (plan.md §11); `summary` es `string | null`, `narrative` es `null`, `evidence` y `claims` contienen solo lo validado hasta ese punto y pueden ser `[]`, `no_evidence_report` es `null`, y `usage` incluye `termination_reason` (`RUN_INTERRUPTED` | `WORKER_LOST` | `HEARTBEAT_EXPIRED`) con `latency_ms`/`estimated_cost_usd` nullable si no se alcanzaron a calcular.
- `status = "failed"`: `summary` es `string | null`, `narrative` es `null`, `evidence` y `claims` contienen solo parciales validados para diagnóstico y pueden ser `[]`, `no_evidence_report` es `null`, `usage.termination_reason` contiene el código terminal (`RUN_TIMEOUT`, `LLM_PROVIDER_ERROR`, `SOCRATA_ERROR`, `SOCRATA_TIMEOUT`, `INTERNAL`).

## 5. Objeto `Evidencia`
```json
{
  "evidence_id": "9a2b...",
  "dataset_id": "nudc-7mev",
  "dataset_name": "MEN_ESTADISTICAS_EN_EDUCACION_EN_PREESCOLAR...",
  "publisher": "Ministerio de Educación Nacional",
  "soql_query": "SELECT a_o, desercion_transicion WHERE codigo_municipio='05756' ORDER BY a_o DESC LIMIT 10",
  "executed_at": "2026-07-06T14:22:31Z",
  "source_url": "https://www.datos.gov.co/d/nudc-7mev",
  "data_updated_at": "2026-03-15T00:00:00Z",
  "data_cutoff_at": "2025-12-31T00:00:00Z",
  "data_cutoff_method": "max_temporal_column",
  "data_cutoff_column": "a_o",
  "data_cutoff_confidence": 0.9,
  "data_cutoff_basis": "data_cutoff_at",
  "data_cutoff_inferred_at": "2026-07-06T14:22:31Z",
  "columns": [{"field": "a_o", "type": "number"}, {"field": "desercion_transicion", "type": "number"}],
  "rows": [{"a_o": "2025", "desercion_transicion": "3.2"}],
  "row_count": 10,
  "narrative": "Párrafo citable…",
  "chart_suggestion": {"type": "line", "x": "a_o", "y": "desercion_transicion"},
  "quality": {
    "eligibility_status": "eligible",
    "eligibility_reasons": [],
    "score_total": 82,
    "classification": "alta",
    "warnings_user": [],
    "dimensions": { /* ver contracts/validacion-calidad.md §4 */ }
  },
  "citation": {
    "dataset_id": "nudc-7mev",
    "dataset_name": "…",
    "publisher": "Ministerio de Educación Nacional",
    "soql_query": "…",
    "executed_at": "2026-07-06T14:22:31Z",
    "source_url": "https://www.datos.gov.co/d/nudc-7mev",
    "data_updated_at": "2026-03-15T00:00:00Z",
    "data_cutoff_at": "2025-12-31T00:00:00Z"
  }
}
```
- `quality` es obligatorio: la API nunca serializa una Evidencia sin él (Art. I.4).
- `chart_suggestion` es `null` si no aplica (RF-503).
- `data_updated_at` proviene del portal; `data_cutoff_at` es nullable y se infiere únicamente desde las filas de ESTA evidencia. Si `data_cutoff_basis = "data_updated_at_fallback"`, la UI debe decir "fecha de actualización del portal; corte estadístico desconocido", no "corte".

## 6. Sobre de error estándar
Toda respuesta no-2xx:
```json
{
  "error": {
    "code": "SOCRATA_TIMEOUT",
    "status": "failed",
    "message_user": "La fuente de datos del Estado no respondió a tiempo. Intenta de nuevo en unos minutos.",
    "message_dev": "GET https://www.datos.gov.co/resource/... timed out after 10000ms (retry 1/1)",
    "retryable": true
  }
}
```
Códigos definidos: `VALIDATION_ERROR` (422), `UNAUTHORIZED` (401 — token ausente o inválido), `RATE_LIMITED` (429), `RUN_NOT_FOUND` (404), `RUN_INTERRUPTED`, `WORKER_LOST`, `HEARTBEAT_EXPIRED`, `RUN_TIMEOUT`, `SOCRATA_TIMEOUT`, `SOCRATA_ERROR`, `LLM_PROVIDER_ERROR`, `STEP_BUDGET_EXCEEDED`, `INTERNAL` (500). `message_user` siempre en español claro (Art. V.5). Si el token ya venció, la corrida también venció por retención y se ejecuta borrado oportunista; la respuesta observable es `404 RUN_NOT_FOUND`.

## 7. `GET /v2/agent/runs/{run_id}` — estado o resultado persistido
Requiere `Authorization: Bearer <run_access_token>` (RF-801). Si la corrida está vencida, el backend ejecuta borrado oportunista y responde `404 RUN_NOT_FOUND`; no hay estado público de "token expirado" porque los tokens viven exactamente lo que viven los datos. Uso: recuperación tras desconexión y panel de trazabilidad (ESC-04).

**200 — running (`RunStatusResponse`)**
```json
{
  "run_id": "1f0c...",
  "status": "running",
  "steps": [/* pasos persistidos */],
  "events": [/* eventos persistidos opcionales para reconstruir timeline */],
  "last_event_seq": 4,
  "partial_evidence": [/* evidencias validadas hasta ahora, puede ser [] */],
  "partial_claims": [/* claims validados hasta ahora, puede ser [] */],
  "usage": {"steps_used": 3, "latency_ms": null, "estimated_cost_usd": null}
}
```

**200 — completed/no_evidence/interrupted/failed (`RunResultResponse`)**
```json
{
  "run_id": "1f0c...",
  "status": "completed",
  "answer": { /* RespuestaFinal §4 */ },
  "steps": [/* traza RF-703 */],
  "events": [/* eventos persistidos */],
  "last_event_seq": 9
}
```
Estados terminales permitidos: `completed`, `no_evidence`, `interrupted`, `failed`. Errores: `401 UNAUTHORIZED`; `404 RUN_NOT_FOUND` si no existe, fue borrada o venció y fue borrada oportunistamente.

## 7b. `DELETE /v2/agent/runs/{run_id}` — borrado de la corrida (RF-803)
Requiere `Authorization: Bearer <run_access_token>`. Elimina de forma irreversible y COMPLETA la corrida y todas sus relaciones: pregunta, `context_hint`, pasos, eventos (`agent_run_events`), evidencias, claims, informes de calidad, checkpoints y el hash del token. Antes del borrado, las métricas agregadas no identificables (latencia, tokens, costo, estado) se copian a la tabla independiente `technical_metrics` (data-model.md §7).

Si la corrida está `running`, el backend primero marca internamente una solicitud de parada, deja de emitir nuevos eventos, espera la cancelación cooperativa de la tarea en curso durante un plazo corto (`DELETE_ACTIVE_GRACE_S`, default 5 s), y luego ejecuta el mismo borrado completo. No se conserva estado `cancelled`: la fila desaparece. Si la tarea no coopera antes del plazo, se bloquean nuevas escrituras de esa corrida por condición de existencia y el borrado continúa.

El borrado incluye `adelete_thread(run_id)` del checkpointer de LangGraph. Si la corrida participó en una evaluación OE3, `eval_case_results.agent_run_id` queda `NULL` por FK `ON DELETE SET NULL` y el resultado de evaluación conserva únicamente su instantánea no identificable de métricas. **204 No Content** al completarse. Errores: `401`, `404 RUN_NOT_FOUND`. La operación es idempotente: repetir el DELETE de una corrida ya borrada devuelve `404`.

## 8. `GET /v2/catalog/search?q=...&k=10` — búsqueda semántica directa
Expone RF-302 para el explorador de catálogo del frontend y para depuración.

**200 OK**
```json
{
  "query": "deserción escolar",
  "results": [
    {"dataset_id": "nudc-7mev", "name": "…", "publisher": "…", "official_publisher_id": "men",
     "publisher_verification_status": "verified", "pii_risk_level": "low",
     "eligibility_status": "eligible", "eligibility_reasons": [], "similarity": 0.87,
     "row_count": 250000, "data_updated_at": "2026-03-15T00:00:00Z",
     "latest_observed_cutoff_at": null, "metadata_synced_at": "2026-07-05T03:00:00Z", "index_stale": false,
     "columns_preview": ["a_o", "codigo_municipio", "desercion_transicion"]}
  ]
}
```
Límites: `q` 3–500 chars no vacíos tras trim; `k` 1–25 (default 10); `k > 25` devuelve `422 VALIDATION_ERROR`, no se recorta silenciosamente. Los datasets `api_active=false` se excluyen de resultados normales. `index_stale=true` no excluye el dataset, pero debe viajar como advertencia. `latest_observed_cutoff_at` es solo una pista histórica del dataset; no es corte de la evidencia. Latencia ≤ 1 s p95 (RNF-010).

## 9. Endpoints de administración (token `ADMIN_TOKEN` por header `X-Admin-Token`)
- `POST /v2/admin/ingest` → dispara ingesta (RF-701). Responde `202` con `ingest_run_id`.
- `GET /v2/admin/ingest/runs?limit=20` → historial de `ingest_runs`.
- `POST /v2/admin/publishers/reload` → recarga fixture versionado de publicadores oficiales y aliases (T-106/T-201A). Responde `202` con resumen de altas/cambios/aliases ambiguos.
- `POST /v2/admin/retention/run` → dispara manualmente el barrido idempotente de retención (T-306). Responde `202` con conteos planificados.
- `GET /v2/admin/metrics` → agregados de corridas y evaluación. Fuente normativa: RNF-001/RNF-009 desde `agent_runs` recientes y `technical_metrics`; RNF-002/RNF-003/RNF-004/RNF-005 desde `eval_runs` y `eval_case_results`, nunca estimado desde logs textuales.

## 10. Compatibilidad y versionado
- El prefijo `/v2` es estable; cambios incompatibles ⇒ `/v3`.
- Campos nuevos opcionales pueden añadirse sin romper el contrato (los clientes ignoran campos desconocidos).
- El endpoint v1 (`/api/consultar_v2` en Next.js) se mantiene operativo hasta el fin de la Fase 5 y se retira en la Fase 7 (tasks.md T-704).
