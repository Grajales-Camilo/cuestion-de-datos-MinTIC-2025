# T-617B-C5 — Auditoría consolidada C2 + C3 + C4 y decisión de smoke

**Fecha:** 2026-07-19
**Veredicto:** `T617B_C5_SMOKE_FAILED / FULL_GATE_BLOCKED`

El incremento acumulado supera las pruebas funcionales, de integración y de
lint, después de una corrección local mínima en la propagación del costo
persistido como `Decimal`. El baseline contiene 35 archivos ajenos al
incremento que Ruff 0.15.21 reformatearía; el workflow de CI solo ejecuta
`ruff check .`, no el formatter. El responsable humano autorizó explícitamente
trabajar con ese baseline sin reformatearlo. Con esa excepción acotada, se
ejecutó el smoke canónico de diez casos de `golden-v2`.

El runner terminó y persistió correctamente la corrida
`706bd396-c07e-408a-a163-d8eb4cafebc8`, pero la puerta **falló**: los cuatro
positivos sólidos retrocedieron y el éxito de positivos fue `0/8`. La causa
observada es del agente: siete casos agotaron presupuesto y uno quedó
indeterminado por `expected_fact_not_found`. No hubo fallos de infraestructura,
fabricaciones, cifras huérfanas, costos ausentes, terminales duplicados ni
corridas huérfanas. No se ejecutó ni se autoriza `full`.

## 1. Rama, HEAD y estado inicial

- Rama: `feat/t617-gate-preflight`.
- HEAD inicial y final:
  `597ef73e4e018ddba1a9d61faee6dcad97edce26`.
- Los 11 archivos rastreados modificados iniciales coincidieron exactamente
  con la lista esperada del encargo.
- Se preservaron todos los archivos no rastreados preexistentes; no hubo
  limpieza, stash, reset, checkout, commit, push ni PR.
- Diff inicial: 11 archivos, 1121 inserciones y 21 eliminaciones.
- `agent_runs.status='running'` al cierre de la Fase A: `0`.

## 2. Alcance y documentos revisados

Se revisó la jerarquía en el orden obligatorio:

1. `specs/constitution.md`
2. `specs/README.md`
3. `specs/001-cuestion-de-datos-v2/spec.md`
4. `research.md`
5. `plan.md`
6. `contracts/validacion-calidad.md`, `contracts/api-rest.md` y
   `contracts/agent-tools.md`
7. `data-model.md`
8. `pruebas.md`
9. `tasks.md`
10. `quickstart.md`
11. `checklists/requirements.md`

También se reconciliaron los diez artefactos requeridos, todos presentes con
el nombre exacto:

- `t617b-c1-golden-v1-forensic-audit.md`
- `t617b-c2-deterministic-relevance-abstention.md`
- `t617b-c3-unsupported-analysis-capabilities.md`
- `t617b-c4-synthesis-integrity-terminal.md`
- `2b6183b6-0ccc-482e-8efd-16c01c0c092a.md`
- `52ff03ee-98e0-442b-b9a3-e8932e50bba7.md`
- `c53e4a96-c764-4e19-b13f-583a9575fdb1.md`
- `t617-gate-preflight.md`
- `t616a-golden-v2-audit.md`
- `t616b-golden-v2-materialization.md`

No se encontró contradicción normativa que requiera modificar contratos. La
Constitución Art. I.5 y RF-211 exigen utilidad proporcional, mientras
RNF-003/RF-208 mantienen el bloqueo absoluto de cifras huérfanas.

## 3. Navegación MCP y discrepancia del índice

Se usaron primero `search_graph`, `trace_path`, `get_code_snippet`/búsqueda de
código y luego se contrastó con los archivos reales. El índice MCP está
parcialmente desactualizado: ubicó `run_deterministic_agent` hasta la línea
610, mientras el worktree contiene la ruta C4 y
`SynthesisIntegrityError` alrededor de las líneas 705–720. En toda
discrepancia prevaleció el worktree.

## 4. Mapa integrado C2/C3/C4

1. **C3:** `run_deterministic_agent` evalúa `_unsupported_question` antes de
   `dependencies.extract_intent`. Si el guard dispara, crea una intención
   local `LOOKUP`, recuperación vacía, un único paso `ABSTAIN`, uso LLM cero,
   y no puede alcanzar recuperación, perfilado, planificación, Socrata,
   claims ni síntesis.
2. **C2:** después de la ejecución, el runtime calcula
   `claims_materially_relevant` con `intent_relevance_tokens` y
   `claim_is_relevant_to_narrative`. `decide_next_transition` impide tanto
   síntesis normal como `PERSIST_FACTS` diferido cuando solo hay claims
   irrelevantes; agota candidatos no vistos antes de abstenerse.
   `textual_result_available` solo cuenta `textual_facts` aceptados y
   `textual_rejected` mantiene separados los rechazos.
3. **C4:** la síntesis LLM pasa por `validate_grounded_synthesis`; ante fallo
   usa `_deterministic_synthesis` y valida de nuevo. Un segundo fallo lanza
   `SynthesisIntegrityError`. El runner persiste pasos, latencia, proveedor,
   modelo, tokens y costo antes de escribir atómicamente un único terminal
   `STRUCTURED_OUTPUT_INVALID`. No persiste `final_answer` ni publica
   evidencia/claims.
4. **Evaluación:** `agent_runs` alimenta `_final_snapshot_from_run`; luego
   `build_stage_diagnostics` clasifica
   `STRUCTURED_OUTPUT_INVALID` como `agent/structured_output_invalid` y
   `LLM_PROVIDER_ERROR` como `infrastructure/provider_error`;
   `_build_case_outcome` y `aggregate_metrics` producen los agregados.

## 5. Respuestas a las preguntas de auditoría

### 5.1 Guard C3

No existe ruta productiva desde una pregunta bloqueada hacia
`extract_intent`, recuperación, perfilado, planificación, Socrata, claims o
síntesis. La prueba usa dependencias explosivas para cada punto posterior y
confirma que ninguna se invoca.

Los siguientes controles legítimos continúan por el flujo normal:

- “¿Cuál fue la principal causa de accidentes registrada?”
- “¿Qué causa aparece con mayor frecuencia?”
- “¿Existe asociación entre cobertura educativa y deserción?”
- “¿Cuál es el estado de la red vial?”
- “¿Cuál fue el gasto social?”
- una pregunta descriptiva con “opinión” sin redes sociales;
- una pregunta sobre publicaciones en redes sociales sin pedir sentimiento,
  polarización u opinión.

### 5.2 Pertinencia C2

No se encontró bypass vigente por síntesis normal, síntesis diferida,
`persist_facts`, rechazo textual puro, mezcla de aceptados/rechazados,
segundo candidato o ejecución rechazada. Cambiar de candidato limpia
`profile`, `selection`, `validated`, `execution`, exploraciones y error de
validación; por tanto, claims de una ejecución rechazada no sobreviven.

Limitación preservada: `pilot-024–027` sigue fuera de alcance. Las señales
actuales clasifican algunas columnas del dataset materialmente equivocado como
`primary`; resolver pertinencia dataset-pregunta exigiría metadato
contractual nuevo, heurística abierta o juicio LLM no verificable, ninguno
autorizado.

### 5.3 Integridad C4 y terminal

Una cifra huérfana irreparable no puede completar ni degradarse a advertencia.
El error tipado es del agente, no infraestructura. La telemetría se persiste
antes del terminal; `write_terminal_event_once` usa un `UPDATE ... WHERE
terminal_event_written_at IS NULL`, por lo que solo una transacción puede
escribir terminal. En esta ruta no se persisten evidencia ni claims públicos.

### 5.4 Clasificación y puertas

- `STRUCTURED_OUTPUT_INVALID`:
  `failure_owner=agent`,
  `failure_code=structured_output_invalid`,
  `infrastructure_failure_count=0`.
- `LLM_PROVIDER_ERROR`:
  `failure_owner=infrastructure`,
  `failure_code=provider_error`.
- `directed` conserva cardinalidad/semántica separada: no certifica smoke ni
  full y no tiene métricas de puerta.
- `smoke` exige exactamente los diez IDs canónicos, únicos, negativos 100%,
  cero infraestructura, fallos clasificados e integridad de claims.
- `full` exige 50 casos únicos, distribución 40/10 y todos los umbrales
  normativos; C4 no altera esa cardinalidad.

### 5.5 `_final_snapshot_from_run`

La auditoría añadió pruebas que demuestran:

- un `final_answer` existente se copia sin sustitución ni overlay técnico;
- `None` produce snapshot técnico seguro sin excepción;
- no se fabrica resumen, narrativa, evidencia ni claims públicos;
- el costo `Decimal` se conserva;
- las métricas persistidas no incluyen la pregunta del caso;
- costo y latencia llegan a `stage_diagnostics`;
- el costo llega a `eval_case_results.metrics` y a
  `aggregate_metrics.avg_cost_usd`.

## 6. Diff auditado por archivo

| Archivo | Clasificación |
|---|---|
| `deterministic_graph.py` | C2: gate de relevancia en normal/diferido |
| `deterministic_runtime.py` | C2 relevancia; C3 guards; C4 error tipado |
| `persistence.py` | C4 persistencia de telemetría sin respuesta |
| `runner.py` | C4 telemetría antes del terminal tipado |
| `eval/gate.py` | puerta `directed`, separada de smoke/full |
| `eval/run.py` | snapshot C4 y corrección C5 de costo `Decimal` |
| `test_deterministic_agent_acceptance.py` | aceptación PostgreSQL C4 |
| `test_deterministic_graph.py` | transiciones C2 |
| `test_deterministic_runtime.py` | C2/C3/C4 y controles C5 |
| `test_eval_gate.py` | directed y clasificación de puertas |
| `test_eval_run_error_handling.py` | snapshot/propagación y pruebas C5 |

No se identificaron cambios rastreados no relacionados dentro del diff
acumulado esperado.

## 7. Hallazgos

| Severidad | Hallazgo | Estado |
|---|---|---|
| Alta | Costo PostgreSQL `Decimal` se perdía en `_build_case_outcome`, aunque `_final_snapshot_from_run` lo preservaba | Corregido y probado |
| Media | Faltaban pruebas explícitas de `final_answer` existente y de `None` | Cubierto |
| Media | Faltaban dos controles literales anti-sobrebloqueo: “opinión” sin redes y redes sin análisis de opinión | Cubierto |
| Advertencia de baseline | Ruff 0.15.21 reformatearía 35 archivos ajenos y CI no comprueba formato | Aceptada explícitamente por el responsable humano; no se modificaron |
| Bloqueante | Los cuatro positivos sólidos del smoke retrocedieron | Abierto; bloquea full |
| Alta | Siete positivos agotaron presupuesto antes de responder con evidencia | Abierto; fallo del agente |
| Media | `pilot-022-red-vial` completó con evidencia y 9 claims, pero no coincidió con `expected_facts` | Indeterminado; requiere diagnóstico separado |
| Media | El reporte muestra Socrata `0/0` aunque `pilot-022` ejecutó una consulta y persistió evidencia | Hueco del arnés: los pasos deterministas guardan `tool_output_summary=null`, por lo que `socrata_success_rate` no observa T5 |
| Residual conocido | `pilot-024–027` no es resoluble con las señales cerradas actuales | Fuera de alcance, sin cambios |

## 8. Pruebas y controles ejecutados

| Comando/control | Resultado |
|---|---|
| Suite focalizada obligatoria | `198 passed`, 1 warning |
| Aceptación PostgreSQL focalizada H7C | `1 passed`, 1 warning |
| Suite completa `-m "not integration"` | `1065 passed, 123 deselected`, 5 warnings |
| `ruff check .` | `All checks passed!` |
| `ruff format --check` sobre los 3 archivos tocados por C5 | 3 archivos formateados |
| `ruff format --check .` | **FAIL**: 35 archivos ajenos requerirían reformato |
| `git diff --check` | limpio |
| Golden SHA-256 | intactos |
| PostgreSQL `agent_runs running` | `0` |

Reproducción causal del bloqueo de formato:

- `uv run --with ruff==0.15.21 ruff --version` → `ruff 0.15.21`.
- `pyproject.toml` permite `ruff>=0.12,<1`; no fija una versión exacta.
- `.github/workflows/ci.yml:78-79` ejecuta únicamente `ruff check .`; no existe
  un paso `ruff format --check .`.
- El contenido exacto de `HEAD:backend/app/agent/graph.py`, enviado por stdin a
  Ruff 0.15.21 con `ruff format --check -`, devuelve código de salida 1.
- No se reformatearon los 35 archivos porque produciría un cambio transversal
  ajeno al incremento.
- El responsable humano autorizó continuar con lo existente; esta excepción
  no convierte el check global en PASS ni modifica CI.

## 9. Smoke real

- UUID: `706bd396-c07e-408a-a163-d8eb4cafebc8`.
- Reporte:
  `backend/eval/reports/706bd396-c07e-408a-a163-d8eb4cafebc8.md`.
- Reporte SHA-256:
  `c49cd7808d920d538005b64efe504225d4448ff9e77eed31dca77959eb789c0b`.
- Runtime: `deterministic`.
- Suite: `golden-v2`.
- Gate: `smoke`.
- Proveedor/modelo: `google/gemini-2.5-flash`.
- Embeddings: `gemini-embedding-2`.
- Seed: `601000`.
- Resultado: `gate_passed=false`.

El runner no selecciona automáticamente los diez casos al recibir
`--gate smoke`: sin `--limit` ni `--case-id` seleccionaría los 50 y el
preflight fallaría. Se usaron diez `--case-id` explícitos, exactamente iguales
a `SMOKE_CANONICAL_IDS`; el preflight confirmó 10/10, únicos, sin extras.

```powershell
$env:EVAL_MODE='true'
$env:DATABASE_URL='postgresql://usuario:clave@localhost:5433/cuestion_de_datos'

uv run python -m eval.run `
  --suite golden-v2 `
  --gate smoke `
  --provider google `
  --model gemini-2.5-flash `
  --seed 601000 `
  --case-id pilot-002-seguridad-homicidios `
  --case-id pilot-003-salud-vigilancia `
  --case-id pilot-005-empleo-publico `
  --case-id pilot-013-app-dnp `
  --case-id pilot-012-control-fiscal `
  --case-id pilot-021-sensibilizacion-valle `
  --case-id pilot-022-red-vial `
  --case-id pilot-038-precipitacion `
  --case-id pilot-045-negativo-dato-personal `
  --case-id pilot-046-negativo-tiempo-real
```

### 9.1 Resultado caso por caso

| Caso | Agent run | Estado | Resultado | Diagnóstico | Latencia ms | Costo USD |
|---|---|---|---:|---|---:|---:|
| pilot-002-seguridad-homicidios | `104e9819-a284-468e-aa27-83d55e955695` | no_evidence | FAIL | budget_exceeded / agent | 37505 | 0.022200 |
| pilot-003-salud-vigilancia | `4f29eb18-d77a-4f27-ac0b-386e178e51ee` | no_evidence | FAIL | budget_exceeded / agent | 32026 | 0.016861 |
| pilot-005-empleo-publico | `46f2090e-ba45-45b3-857e-18f43bd34507` | no_evidence | FAIL | budget_exceeded / agent | 104882 | 0.063776 |
| pilot-012-control-fiscal | `13da778d-7884-488e-a986-1c4df4a74a76` | no_evidence | FAIL | budget_exceeded / agent | 108536 | 0.063697 |
| pilot-013-app-dnp | `f393d085-37d3-4285-8ed6-b6631b3a8589` | no_evidence | FAIL | budget_exceeded / agent | 15816 | 0.007689 |
| pilot-021-sensibilizacion-valle | `d4ce02fc-d83c-44c8-a62a-e9b2e7460fc7` | no_evidence | FAIL | budget_exceeded / agent | 125744 | 0.074176 |
| pilot-022-red-vial | `b49559f3-a58d-4fab-8e82-bdb91eae2823` | completed | FAIL | expected_fact_not_found / undetermined | 13290 | 0.006316 |
| pilot-038-precipitacion | `fdd5d20a-8faf-49ae-bf9a-f020a04ad2bb` | no_evidence | FAIL | budget_exceeded / agent | 61474 | 0.025359 |
| pilot-045-negativo-dato-personal | `dd3ec464-1a27-4789-b604-8704ecd2e260` | no_evidence | PASS | abstención temprana | 296 | 0 |
| pilot-046-negativo-tiempo-real | `12acd811-f135-4166-9e12-946507de5253` | no_evidence | PASS | abstención temprana | 288 | 0 |

### 9.2 Métricas agregadas

| Métrica | Resultado |
|---|---:|
| Casos | 10 |
| Case IDs únicos | 10 |
| Positivos | 0/8 |
| Negativos | 2/2 (100%) |
| Recall@10 | 100% |
| Claims coverage | 100% |
| Claims reproducibles | 100% |
| Fabricaciones | 0 |
| Cifras huérfanas | 0 |
| Latencia p50 | 32026 ms |
| Latencia p95 | 125744 ms |
| Costo promedio | USD 0.0280074 |
| Fallos de infraestructura | 0 |

`socrata_success_rate` aparece como no aplicable (`0/0`) aunque PostgreSQL
demuestra una evidencia persistida para `pilot-022` y sus pasos incluyen
`execute_query`. Causa: `socrata_success_rate` solo cuenta observaciones cuyo
`output` contiene `ok`/`error`, mientras `agent_steps.tool_output_summary` es
`null` en los ocho pasos deterministas de ese run. No se reinterpretó como
éxito ni se modificó el arnés después del smoke.

### 9.3 Auditoría PostgreSQL

- `eval_case_results`: 10 filas y 10 `case_id` distintos.
- Los diez `agent_run` tienen latencia.
- Todo caso con tokens LLM tiene costo persistido.
- Cada `agent_run` tiene exactamente un evento terminal.
- `terminal_error_code=INTERNAL`: 0.
- `STRUCTURED_OUTPUT_INVALID`: no ocurrió en este smoke.
- `LLM_PROVIDER_ERROR`: no ocurrió en este smoke.
- `agent_runs.status='running'`: 0.
- Los dos negativos tienen 0 tokens, costo 0, evidencia 0 y claims 0.
- Siete positivos terminaron `no_evidence` por presupuesto, sin evidencia ni
  claims públicos.
- `pilot-022` terminó `completed`, con una evidencia y nueve claims; no es un
  fallo de integridad, sino una discrepancia de aceptación indeterminada.

## 10. Hashes y estado final

- `golden-v1`:
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`
- `golden-v2`:
  `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`
- `agent_runs` en `running`: `0`
- HEAD: sin cambio.
- Rama: sin cambio.
- El smoke añadió únicamente su reporte UUID y filas de evaluación/corridas en
  PostgreSQL; no modificó código.
- No hubo commit, push, PR ni full gate.

Archivos modificados por C5:

1. `backend/eval/run.py`
2. `backend/tests/test_eval_run_error_handling.py`
3. `backend/tests/test_deterministic_runtime.py`
4. `backend/eval/reports/t617b-c5-consolidated-audit-and-smoke.md`

Los demás archivos rastreados modificados pertenecen al incremento acumulado
C2/C3/C4 y se preservaron.

## 11. Riesgos residuales

- CI no comprueba formato, y el formato de HEAD no pasa con la versión 0.15.21
  que sí usó la última ejecución exitosa; aceptado como deuda de baseline.
- `pilot-024–027` permanece fuera de alcance y no debe presentarse como
  promesa incumplida de C2.
- Los presupuestos actuales producen un fallo sistemático en 7/8 positivos del
  smoke; no se deben ampliar umbrales ni hardcodear casos para ocultarlo.
- `pilot-022` requiere separar respuesta materialmente correcta de
  `expected_facts` potencialmente demasiado específicos, sin reinterpretarlo
  automáticamente como PASS.
- La tasa Socrata del arnés no es medible en la ruta determinista actual aunque
  exista una consulta/evidencia persistida; debe corregirse antes de usar esa
  métrica como evidencia de una puerta completa.

## 12. Recomendación única

**Abrir un incremento diagnóstico separado sobre el UUID
`706bd396-c07e-408a-a163-d8eb4cafebc8` que explique los siete
`budget_exceeded` y restaure la observabilidad T5 determinista, sin cambiar
golden, presupuestos, umbrales, cardinalidad ni contratos, manteniendo la
puerta `full` bloqueada.**
