# T-402 — Cierre formal: verificación integrada de calidad (T6) y claims (T7)

**Tarea:** T-402 — Verificación integrada de calidad y claims (Fase 4).
**Requisitos:** RF-208, RF-401, RF-402, RF-403, RF-404; Constitución Art. I.1,
I.2, I.3, I.4, IV.2.
**Fecha:** 2026-07-18.

Este acta reproduce la evidencia de T-402 sobre el HEAD actual, cierra los tres
huecos de prueba pendientes, ejecuta una corrida viva real y consolida la
comprobación de los invariantes A–G. No es un documento normativo.

## 1. Rama y HEAD base

- Rama base de trabajo: `v2`.
- Rama del incremento: `feat/t402-formal-closure` (creada desde `v2`).
- HEAD base: `d8b9c5172d66a9e329ec1317547cded6908497cb`
  (`feat(eval): materialize approved golden v2 suite`).
- `git rev-list --left-right --count origin/v2...v2` = `0  82` (la ref local
  `origin/v2` está 82 commits detrás; base local correcta, sin pull/rebase).
- Worktree al iniciar: 0 cambios rastreados, exactamente 18 archivos no
  rastreados preexistentes (conservados intactos: `backend/uv.lock`, el informe
  UUID bajo `backend/eval/reports/`, y documentos/figuras/prompts bajo `docs/`).

## 2. Commits históricos inspeccionados

- `ebee12f feat(agent): T-402 verificacion integrada de calidad y claims + robustez del router`.
- `c8f5ffa feat(agent): congela mejoras del agente autonomo`.
- La evidencia histórica de T-402 (tasks.md) documenta: el fix de
  `_claim_builder_node` (filtro `classification == "no_recomendada"`), la matriz
  de integración `test_t402_quality_claims_integration.py`, el refuerzo del
  prompt del sintetizador y las corridas en vivo de 2026-07-11. El pendiente
  literal registrado era «evidencia consolidada y PR hacia `v2`». Esta acta lo
  reproduce todo contra el HEAD actual; no se declara cierre por el texto
  histórico.

## 3. Resultado del MCP y discrepancias

- Proyecto `D-Usuario-AppWebs-cuestion-de-datos-MinTIC`: índice `ready`,
  4396 nodos / 19001 aristas, `head_sha = d8b9c51` (coincide con el HEAD real).
- `detect_changes` reportó 355 archivos cambiados; corresponden al diff contra
  `base_sha = 2304335` (merge-base 82 commits atrás), **no** a staleness del
  índice. El índice está sincronizado con HEAD; no requirió reindexado.
- Se reconstruyeron con `search_graph`/`grep` y se contrastaron contra el
  worktree (que prevalece): `_after_t5`, `_quality_node` (T6),
  `_claim_planner_node`, `_claim_builder_node`, `_after_claim_builder`,
  `_synthesizer_node`, `_orphan_figures`, `_tool_node` (T5),
  `execute_legacy_agent_run_async`. **Discrepancia menor:** el grafo omite las
  aristas dinámicas de LangGraph (condicionales `add_conditional_edges`); se
  verificaron directamente en `backend/app/agent/graph.py` (`build_graph`,
  líneas ~1950-1980). Sin contradicción con el código real.

## 4. Matriz requisito → código → prueba → evidencia

| Requisito | Código | Prueba | Evidencia |
|---|---|---|---|
| RF-401 T5⇒T6 obligatorio | `_after_t5` (arista condicional fija a `quality_validator` si `pending_t5`), `graph.py` | `test_dos_t5_en_una_corrida_producen_dos_t6_y_persistencia_1a1` + matriz alta/baja/no_rec/diag | 5 pruebas verdes + corrida viva (T5=1→T6=1) |
| RF-402 clasificación no excluye baja | `_claim_builder_node` (filtra solo `!= eligible` y `no_recomendada`) | `test_evidencia_baja_...` | claim construido sobre baja |
| RF-403 advertencias en lenguaje claro heredadas | `quality.warnings_user` en Evidencia pública; `_synthesizer_node` payload | `test_evidencia_baja_...` (cadena en `final_answer`) | warnings viajan a síntesis y a `final_answer.evidence[].quality` |
| RF-404 no_recomendada no sustenta | `_claim_builder_node` (`classification == "no_recomendada"` → skip) | `test_evidencia_no_recomendada_...` | claims=[], `no_evidence` |
| RF-208 solo cifras respaldadas | `_orphan_figures` (whitelist = `claims[].display_value` + literales del SoQL) | matriz alta + corrida viva | cero cifras huérfanas |
| Art. I.4 ninguna evidencia sin calidad | `persist_evidence_and_quality` (1:1) | `_evidence_quality_counts`, `_evidence_ids_without_exactly_one_quality` | evidence_results == quality_reports |

## 5. Prueba T5→T6 con una y múltiples consultas

- **Estructural:** `_after_t5` es una `add_conditional_edges` fija: tras
  `tool__ejecutar_soql`, si existe `pending_t5`, la única transición es
  `quality_validator`. El LLM/router no participa en esa decisión; es imposible
  omitir T6. Cada T5 exitoso pone `pending_t5`; `_quality_node` lo limpia
  (`"pending_t5": {}`), habilitando el siguiente ciclo.
- **Una consulta:** las 4 pruebas de la matriz verifican
  `_quality_validator_step_count(...) == 1`.
- **Múltiples consultas (hueco cerrado):**
  `test_dos_t5_en_una_corrida_producen_dos_t6_y_persistencia_1a1` ejerce una
  sola corrida con dos `ejecutar_soql` exitosos (datasets `t402-multi-a` y
  `t402-multi-b`) y verifica **exactamente dos** pasos `quality_validator`, dos
  evidencias y dos claims (uno por evidencia, con `claim.evidence_id`
  correcto). Nota de diseño: el router reserva presupuesto mínimo
  (`_minimum_after_router("ejecutar_soql") = 6`), por lo que la corrida usa
  `max_steps=14` para permitir dos T5 antes del cierre; con menos presupuesto el
  router fuerza `finish` preventivo (`INSUFFICIENT_BUDGET_FOR_ACTION`), lo que
  se observó y corrigió durante la construcción de la prueba.

## 6. Evidencia 1:1 evidence_results / quality_reports

- Helper nuevo `_evidence_quality_counts` (conteo por `run_id`) y
  `_evidence_ids_without_exactly_one_quality` (FK inversa: evidencias con
  `count(quality_reports) != 1`).
- En la corrida de dos T5: `(evidence_results, quality_reports) == (2, 2)` y
  cero evidencias sin exactamente un reporte.
- En la corrida baja: `(1, 1)`.
- En la corrida viva real: `evidence_results=1, quality_reports=1,
  quantitative_claims=1`.

## 7. Resultado de evidencia `alta`

`test_evidencia_alta_produce_claims_sin_cifras_huerfanas`: clasificación `alta`,
`eligible`, un claim reproducible (`display_value == "100 COP"`),
`final_answer.status == "completed"`, `synthesis_attempts == 1` (sin reintentos
por cifras huérfanas), `quality_validator` corrió una vez, `quality_reports`
persistido con `classification == "alta"`. Confirmado también en vivo (§12).

## 8. Resultado de evidencia `baja`

`test_evidencia_baja_conserva_advertencia_y_llega_al_sintetizador` (extendido):
- corte >48 meses + columna mayormente vacía ⇒ `classification == "baja"`,
  `eligible`, `warnings_user` no vacío.
- **RF-402:** `baja` NO es regla dura ⇒ sigue sustentando un claim;
  `final_answer.status == "completed"`.
- **RF-403 (hueco cerrado):** la advertencia llega intacta al payload del
  sintetizador (`received_warnings == quality.warnings_user`) **y** se demuestra
  la cadena en la respuesta FINAL entregable:
  `final_answer.claims[0].evidence_id == evidences[0].evidence_id` y la
  evidencia correspondiente en `final_answer.evidence[]` porta
  `quality.classification == "baja"` con `quality.warnings_user` idéntico. Es la
  herencia de advertencia del contrato §6.2(3) por vínculo `claim.evidence_id`,
  sin inventar un campo nuevo en el claim.
- Límite documentado (no forzado por la prueba): el sintetizador parafrasea la
  limitación en términos cualitativos; `_orphan_figures` bloquearía una cifra de
  `warnings_user` citada literalmente por no estar en la whitelist de
  `display_value`. Es una tensión RF-402/403 ↔ RF-208 resuelta por prompt, cuya
  obediencia solo la confirma el conjunto dorado con LLM real (Art. IV.2).

## 9. Resultado de evidencia `no_recomendada`

`test_evidencia_no_recomendada_no_sustenta_claims_pese_a_ser_elegible`: fuente
incompleta (`source_url` ausente) fuerza `no_recomendada` aunque publicador/PII
mantengan `eligible`. Aunque el router pide un claim, `_claim_builder_node` lo
rechaza por su cuenta (`classification == "no_recomendada"`): `claims == []`,
`final_answer.status == "no_evidence"`, `final_answer.claims == []`,
`final_answer.evidence == []`. La evidencia y su `quality_report` sí quedan
persistidos. Es la regresión del fix histórico, verificada contra Postgres real.

## 10. Resultado de `diagnostic_only` / `blocked`

- `test_evidencia_diagnostic_only_no_sustenta_claims`: publicador no verificado
  ⇒ `diagnostic_only`; T5 se ejecuta (fines diagnósticos), `quality_report`
  persistido, pero `claims == []` y `final_answer.status == "no_evidence"`.
- `blocked`: el contrato §3.1 lo descarta **antes de T5** (regla dura de
  privacidad), por lo que no genera evidencia entregable. Su exclusión de claims
  comparte exactamente la ruta `eligibility_status != "eligible"` de
  `_claim_builder_node` ejercida por `diagnostic_only`. La generación de
  `blocked` está cubierta de forma determinista en
  `tests/test_quality_validator.py` (casos 12: PII `medium` con agregación
  insuficiente y `sum` sin `count` ⇒ `blocked`; PII `unknown`/`high` ⇒
  bloqueo). No se añadió una prueba de integración redundante para `blocked`
  porque está fuera del incremento mínimo y no relaja privacidad ni
  elegibilidad.

## 11. Cómo heredan advertencias los claims

El contrato (validacion-calidad.md §6.2 punto 3) resuelve la herencia por el
**vínculo** `claim.evidence_id → evidence.evidence_id → evidence.quality.warnings_user`,
no por un campo nuevo en el claim. `final_answer` conserva ese vínculo:
`final_answer.claims[]` lleva `evidence_id`; `final_answer.evidence[]` lleva
`evidence_id` + `quality` (con `warnings_user`). La prueba baja extendida
demuestra el vínculo explícitamente sobre la respuesta final. No hay
contradicción entre contrato y representación real; no se cambió esquema.

## 12. Corrida viva (runner legacy real)

Ejecutada con `execute_legacy_agent_run_async` (Postgres real en `localhost:5433`
vía `docker compose up -d db`, imagen `pgvector/pgvector:0.8.0-pg16` con catálogo
sembrado de 8398 datasets; Gemini `gemini-2.5-flash` y Socrata reales; run
`retention_class=eval`). Un solo intento controlado, exitoso:

- **run_id:** `3ff03835-0512-4f2a-a6b6-fd8b0f927ed0`.
- **pregunta:** «¿Cuál es el volumen total de gas natural comprimido vehicular
  suministrado registrado en Colombia?»
- **dataset:** `v8jr-kywh` — «Consulta Ventas de Gas Natural Comprimido
  Vehicular», Ministerio de Minas y Energía, `verified` / `pii_risk_level=low`
  / `eligible` / `api_active=true`.
- **SoQL canónica:** `SELECT sum(cantidad_volumen_suministrado), count(*) GROUP BY tipo_de_combustible LIMIT 1000 OFFSET 0`.
- **clasificación / elegibilidad:** `alta`, `eligible`, `score_total=100`,
  `data_cutoff_basis=data_updated_at_fallback`.
- **advertencias:** `[]` (clasificación `alta`; el sub-requisito «advertencias
  preservadas si la clasificación no es alta» no aplica a esta corrida y queda
  cubierto de forma determinista por la prueba baja de §8).
- **claims:** 1 aceptado — `direct`, `display_value='1.715.000.807'`,
  `evidence_id=a0e691b2-44f4-4288-9ff4-ad96535ae785`; 0 rechazados.
- **secuencia de pasos (persistida en `agent_steps`):** `planner → router →
  tool:buscar_catalogo → router → tool:ejecutar_soql → quality_validator →
  router → claim_planner → claim_builder → synthesizer` (10 pasos, sin errores).
  **T5=1, T6=1.**
- **persistencia:** `evidence_results=1`, `quality_reports=1`,
  `quantitative_claims=1`.
- **estado final:** `agent_runs.status = completed`, `final_answer.status =
  completed`; `summary`/`narrative` citan exactamente la cifra del claim
  (`1.715.000.807`), **cero cifras huérfanas** (`synthesis_attempts=1`, sin
  bloqueo del sintetizador).
- **terminal único:** exactamente 1 evento terminal (`answer`).

Las 9 condiciones de la corrida viva quedan demostradas: (1) T5 real contra
Socrata; (2) `quality_validator`; (3) evidencia + `quality_report` persistidos;
(4) claim reproducible vinculado a la evidencia; (5) síntesis; (6) `completed`;
(7) cero cifras huérfanas; (8) un único terminal; (9) advertencias — N/A por
clasificación `alta`, cubierto deterministamente.

Nota de entorno: la corrida creó un `worker_instances` `t402-live-<uuid>` y un
`agent_runs` `retention_class=eval` (expira por el barrido de retención). No se
alteró ni reingirió el catálogo compartido; no se borraron filas por prefijos.

## 13. Resultado exacto de cada comando

Desde `backend/` (PowerShell/Bash; `.env` cargado al entorno para las de
integración):

- `uv run pytest tests/test_agent_graph.py tests/test_quality_validator.py tests/test_claims.py -q`
  → **88 passed**.
- `uv run pytest tests/integration/test_t402_quality_claims_integration.py -q`
  → **5 passed** (4 preexistentes + `test_dos_t5_...` nueva).
- `uv run pytest -m "not integration" -q` → **869 passed, 121 deselected**
  (sin fallos preexistentes).
- `uv run ruff check .` → **All checks passed!**
- `uv run ruff format --check tests/integration/test_t402_quality_claims_integration.py`
  → **1 file already formatted** (tras `ruff format` del mismo archivo).
- `git diff --check` → sin errores de whitespace (solo aviso informativo
  LF/CRLF, resuelto normalizando el archivo a CRLF como sus hermanos).
- Deuda preexistente reproducida y NO tocada: `ruff format --check .` global
  reporta ~39 archivos históricos fuera de este incremento; no se reformatearon.

## 14. Archivos modificados

- `backend/tests/integration/test_t402_quality_claims_integration.py`
  (+271 / −1): dos datasets nuevos (`t402-multi-a/b`), helpers
  `_evidence_quality_counts` y `_evidence_ids_without_exactly_one_quality`,
  extensión de la prueba baja con la cadena claim→evidencia→warnings en
  `final_answer`, y prueba nueva `test_dos_t5_en_una_corrida_producen_dos_t6_y_persistencia_1a1`.
- `backend/eval/reports/t402-integrated-quality-claims-closure.md` (este acta,
  nuevo).
- `specs/001-cuestion-de-datos-v2/tasks.md`: T-402 marcada `[x]` con nota de
  cierre.

**No se modificó código productivo.** Todas las puertas pasaron sin necesidad de
tocar `backend/app/`.

## 15. Confirmación de no-cambios

- `backend/eval/golden/golden-v1.yaml`: intacto.
- `backend/eval/golden/golden-v2.yaml`: intacto.
- `backend/eval/metrics.py`: intacto.
- Contratos, OpenAPI, migraciones, modelos relacionales: intactos.
- Selector/default del runtime, runtime determinista, prompts del agente,
  datasets golden, umbrales/tolerancias: intactos.
- Los 18 archivos no rastreados preexistentes: intactos (no agregados al commit).

## 16. Confirmación de que T-617 no empezó

No se inició T-617 ni ninguna de sus sub-puertas (smoke 10, golden-v1 50,
golden-v2 50, aceptación legacy). No se cambió el default a `deterministic`. No
se retiró el runtime legacy. No se ejecutó el golden completo.

## 17. Riesgos o límites residuales

1. La corrida viva fue `alta`, no `baja`; el sub-requisito «advertencias
   preservadas si no es alta» se cubre deterministamente (§8), no en vivo. Un
   futuro smoke con LLM real sobre un dataset antiguo lo confirmaría de punta a
   punta, pero excede el alcance de T-402 y el presupuesto de intentos.
2. La obediencia del LLM real al prompt del sintetizador (parafraseo cualitativo
   de advertencias) no es una garantía dura de T-402; solo la confirma el
   conjunto dorado con LLM real (Art. IV.2), fuera de este alcance.
3. `blocked` no tiene prueba de integración dedicada (comparte ruta con
   `diagnostic_only` en `_claim_builder_node` y está cubierto en el nivel de
   calidad); fuera del incremento mínimo.
4. La corrida viva dejó un `worker_instances`/`agent_runs (eval)` durables como
   evidencia; expiran por retención. Docker Desktop fue arrancado para levantar
   el Postgres del catálogo.
