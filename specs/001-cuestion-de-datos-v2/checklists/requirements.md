# Checklist de Verificación — Resolución de Bloqueos Documentales

**Última revisión:** 2026-07-06 (ronda 2) · **Revisor:** editor SDD (sesión de revisión técnica)
**Uso:** verificar que los bloqueos identificados quedaron resueltos de forma consistente en todo `specs/`. Re-ejecutar tras cualquier enmienda mayor.

Comando de búsqueda sugerido (PowerShell, desde `specs/`):
```powershell
Get-ChildItem . -Recurse -Filter *.md |
    Select-String -Pattern 'text-embedding-004|WCAG 2\.1|vector\(1024\)|Supabase|Neon|Last-Event-ID|run_access_token|claim|interrupted'
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
- [x] Orden documental: T-201 → T-205 (benchmark) → T-104B (migración definitiva) → T-203 → T-204.
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
- [x] data-model.md: `run_access_token_hash`, `run_access_token_expires_at`, `retention_class`, `delete_requested_at`, `deleted_at`.
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
- [x] **R2-3 Token vive lo que viven los datos.** `RUN_TOKEN_TTL = RETENTION_USER_DAYS` (90 días); al vencer la retención se elimina la corrida; sin renovación (imposible sin cuentas). quickstart, plan §11, data-model y research §3 alineados.
- [x] **R2-4 Borrado ejecutable, no anonimización imposible.** Al vencer retención o ante RF-803: borrado COMPLETO de la corrida y relaciones (compatible con `NOT NULL`), tras copiar métricas no identificables a la nueva tabla `technical_metrics`. `retention_class` reducido a `user`|`eval`.
- [x] **R2-5 Semántica única de durabilidad.** Desconexión NO interrumpe; reinicio SÍ; `interrupted` es TERMINAL; sin reanudación automática (checkpointer solo diagnóstico); el usuario re-ejecuta. RF-209, plan §11, data-model, T-300 y api-rest coherentes.

## Correcciones adicionales

- [x] **R2-6 Reproducibilidad local bien formulada.** Art. II.2: "componentes propios" localmente; datos.gov.co y proveedores LLM son dependencias remotas declaradas. DEP-01 = "PostgreSQL 15+ con pgvector, local o gestionado".
- [x] **R2-7 Fuente no oficial = regla dura.** `publisher_official` ya no puntúa: evidencia RECHAZADA (no elegible), coherente con Art. I. Puntos de D4 redistribuidos (60/40). Caso de prueba §5.8.
- [x] **R2-8 Temporalidad corregida.** Base preferida `data_cutoff_at` (corte inferido de los datos) con fallback explícito a `data_updated_at` declarando `basis`; advertencia cuando D3 ≤ 70; ejemplo del contrato con fechas coherentes (corte 2025-03-15 ≈ 16 meses).
- [x] **R2-9 Placeholders contextuales.** Patrón configurado por dataset/columna + codebook/descripción + proporción mínima (`PLACEHOLDER_MIN_RATIO`); casos de falsos positivos ("Total" legítimo, `9` real) en la suite.
- [x] **R2-10 Guardia SoQL estructural.** Parseo a gramática + listas blancas de cláusulas/funciones + columnas contra `catalog_columns` + complejidad máxima; lista negra solo defensa en profundidad. Nuevo error `SOQL_UNKNOWN_COLUMN`.
- [x] **R2-11 CORS completo.** Headers `Authorization`, `Content-Type`, `Last-Event-ID`; orígenes por `CORS_ALLOWED_ORIGINS`; previews de Vercel con origen exacto temporal, sin comodines.
- [x] **R2-12 RF-303 con ventana real.** `CATALOG_STALE_AFTER_DAYS=8` (plan §5.8); `metadata_synced_at` + `index_stale` en `/v2/catalog/search`.
- [x] **R2-13 Orden de lectura del README** alineado con la jerarquía normativa; research.md antes del plan.
- [x] **R2-14 Menores.** Constitución 1.1.0 con nota de enmienda; plan §3 referencia T-101 (no T-103); quickstart describe el sistema completo y activa el venv con `Activate.ps1`; `sentence-transformers` no es dependencia obligatoria pre-T-205; `agent_steps.node` incluye `claim_builder`; imagen pgvector con versión fijada; Art. V.4 habla de acciones observables, no "pasos de razonamiento".

## Pendientes (sin cambios)

- [ ] Decisión de embeddings y dimensión (research.md §1) — se resuelve en T-205; bloquea T-104B/T-203.
