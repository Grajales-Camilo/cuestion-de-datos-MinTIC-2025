# T-617B-C2 — Abstención determinista ante evidencia temáticamente irrelevante

- Rama: `feat/t617-gate-preflight`
- HEAD de partida: `597ef73e4e018ddba1a9d61faee6dcad97edce26`
- Precede a: T-617B-C1 aprobada (`backend/eval/reports/t617b-c1-golden-v1-forensic-audit.md`), veredicto vigente `GOLDEN_V1_HISTORICAL_REGRESSION_FAIL / T617_RUNTIME_CORRECTIONS_REQUIRED`.
- No se ejecutó Gemini, Socrata ni ninguna evaluación real (golden-v1/v2/smoke). PostgreSQL sólo en modo lectura (relecturas puntuales de `quantitative_claims` sobre corridas ya persistidas, para diagnóstico). No se modificaron specs, contratos, `golden-v1.yaml`, `golden-v2.yaml`, `expected_facts`, `eval/metrics.py` ni umbrales/cardinalidades. No se creó commit, push ni PR.

## Revisión R2 — corrección del hueco en la ruta diferida (`CHANGES_REQUIRED — DEFERRED_SYNTHESIS_BYPASSES_RELEVANCE_GATE`)

Auditoría independiente encontró que la primera versión de este incremento dejaba una segunda rama de transición sin cubrir:

```python
if state.synthesis_deferred and state.claims_available:
    return Transition(node=SupervisorNode.PERSIST_FACTS, ...)
```

Esta rama, usada cuando `defer_synthesis_until_persisted=True` (ruta productiva de hechos textuales T-615F/RF-212, distinta del `defer=False` de la corrida golden-v1 auditada en T-617B-C1), se evalúa **antes** que la nueva rama `if not state.claims_materially_relevant: ...` y sólo comprobaba `claims_available` (existencia), no pertinencia. Reproducido de forma independiente con los mismos dobles: `defer_synthesis_until_persisted=True` + un único candidato con un claim irrelevante → `status=ready_for_synthesis`, `last_node=persist_facts`, `claims=1` — el claim irrelevante evitaba el gate por completo.

**Corrección aplicada** (sin mover la rama, ampliando su condición): la rama de `PERSIST_FACTS` diferido ahora exige `state.claims_materially_relevant or state.textual_result_available` — persiste si hay al menos un claim pertinente, **o** si hay un resultado textual (T-615F) pertinente que deba preservarse aunque el/los claims cuantitativos de esa misma evidencia sean irrelevantes. Si ninguna de las dos condiciones se cumple, la ejecución cae a través de las ramas siguientes (`textual_rejected`, segunda rama diferida específica de texto, `claims_available`) hasta llegar a la rama `claims_materially_relevant` ya existente, que decide `NEXT_CANDIDATE`/`ABSTAIN` igual que en modo inmediato.

Se añadieron 4 pruebas nuevas en `tests/test_deterministic_runtime.py` (sección 5, actualizada) que reproducen exactamente el hueco reportado contra el baseline intermedio y confirman la corrección. Suite completa no-integración tras esta corrección: **1032 passed, 122 deselected** (1018 base + 14: 3 de transición pura + 11 de runtime).

**Precisión terminológica exigida**: `claim_is_relevant_to_narrative` (RF-212, T-617C-A) **no mide pertinencia temática general entre el dataset y la intención de la pregunta**. Es un gate acotado de relevancia narrativa de claims: sólo excluye columnas cuya categoría léxica es `auxiliary` (identificadores, códigos) o exclusivamente `temporal` (fechas, años) cuando la intención no las solicita explícitamente; cualquier columna `primary` se considera pertinente sin más análisis. Este informe usa la expresión "pertinencia temática"/"materialmente pertinente" en sentido coloquial para describir el efecto observable (evita que evidencia ajena al tema se convierta en claims/narrativa), pero la señal subyacente es estrictamente léxica por categoría de columna, no una comprensión semántica del dataset. La limitación de `pilot-024–027` (sección 3) es la prueba directa de esta diferencia: columnas como `tasa_matriculacion_5_16`/`tamano_promedio_grupo`, provenientes de un dataset temáticamente equivocado, clasifican `primary` y el gate no las detecta, precisamente porque el gate nunca evaluó si el dataset en su conjunto responde la intención — sólo si sus columnas individuales pertenecen a una categoría léxica pedida.

## Revisión R3 — un rechazo textual puro no puede disfrazarse de "resultado pertinente" (`CHANGES_REQUIRED — TEXTUAL_REJECTION_MASQUERADES_AS_ACCEPTED_TEXTUAL_FACT`)

Auditoría independiente reprodujo un segundo hueco, esta vez en el cómputo de la señal usada por la propia corrección de R2: con `claims_materially_relevant=False`, `textual_rejected=True` y ningún hecho textual aceptado, la corrida en modo diferido igual llegaba a `PERSIST_FACTS`.

**Causa**: `deterministic_runtime.py` computaba

```python
textual_result_available = execution is not None and bool(
    getattr(execution, "textual_facts", ()) or getattr(execution, "textual_rejections", ())
)
```

es decir, la señal se activaba con la mera **presencia** de un rechazo textual, no con la existencia de un hecho **aceptado**. Como la rama de R2 (`if state.claims_materially_relevant or state.textual_result_available: PERSIST_FACTS`) se evalúa antes que el chequeo independiente `if state.textual_rejected: ABSTAIN`, un candidato con sólo rechazos (sin ningún hecho aceptado) hacía que `textual_result_available` fuera `True` únicamente por culpa de esos rechazos, colando el claim irrelevante a persistencia sin llegar nunca al chequeo de rechazo.

**Por qué no basta con `and not textual_rejected`** (como señaló correctamente la auditoría): un mismo candidato puede tener simultáneamente hechos aceptados y hechos rechazados (T-615F puede aceptar unos y rechazar otros dentro de la misma corrida); negar `textual_rejected` de forma global bloquearía indebidamente la persistencia de un hecho aceptado legítimo sólo porque coexiste con un rechazo no relacionado.

**Corrección aplicada** (separar las señales en su origen, no parchear el consumidor): `textual_result_available` ahora refleja **exclusivamente** la presencia de `textual_facts` aceptados:

```python
textual_result_available = execution is not None and bool(
    getattr(execution, "textual_facts", ())
)
```

`textual_rejected` ya era, y sigue siendo, una señal independiente y correctamente calculada sólo desde `textual_rejections`. No fue necesario ni se modificó nada en `deterministic_graph.py`: las tres ramas que consumen `textual_result_available` (la nueva de R2, la rama diferida preexistente de T-615F, y la de abstención cuando no hay claims) quedan correctas automáticamente al corregir la fuente. Se verificó que ninguna de las tres dependía de la semántica anterior (sección 5.3.2).

Se añadieron 3 pruebas nuevas exigidas por la auditoría (sección 5.1, puntos 15–17), reproducidas contra un baseline intermedio (falla como se esperaba) y verificadas con la corrección (pasan). Suite completa no-integración tras esta corrección: **1035 passed, 122 deselected** (1032 tras R2 + 3 nuevas).

---

## `git status --short` inicial (registrado antes de tocar código)

```
?? backend/eval/reports/019be4a6-da19-4153-b2d1-8b87763bb89d.md
?? backend/eval/reports/115de3e4-e06a-471b-af37-d4fa8d61cd36.md
?? backend/eval/reports/224159e0-7a8b-4646-819d-e1271bba38d2.md
?? backend/eval/reports/7bd186d1-b317-48d5-9e1e-262561b73a1a.md
?? backend/eval/reports/8ab794ac-50e6-453d-a7b7-3d8a1b95f973.md
?? backend/eval/reports/8f5cacf0-1205-4fb3-adc7-63fb452822bf.md
?? backend/eval/reports/b0d38f87-d2d3-4bc8-80ae-b197e278d328.md
?? backend/eval/reports/fd2da0f1-94b6-47e4-8ddc-30926266f944.md
?? backend/eval/reports/t617b-c1-golden-v1-forensic-audit.md
?? backend/eval/reports/t617b-d1-pilot005-timeout-diagnosis.md
?? backend/eval/reports/t617b-smoke2-passed.md
?? backend/eval/reports/t617b0-pilot005-directed-retry.md
?? backend/eval/reports/t617b0-pilot005-retry-blocked.md
?? backend/eval/reports/t617c-r1-pilot005-real-validation.md
?? backend/eval/reports/t617c-semantic-claim-labels.md
?? backend/eval/reports/t617c-smoke-passed.md
?? backend/uv.lock
?? docs/... (documentos internos preexistentes, sin relación con este incremento)
```

Todos los archivos no rastreados listados arriba se conservaron intactos; ninguno fue tocado por este incremento.

## Requisitos satisfechos

- **RF-205** (el sintetizador concluye honestamente que no hay evidencia, sin que el presupuesto sea la causa; `contracts/api-rest.md:128`).
- **RF-211** (una respuesta parcial pero materialmente pertinente sigue siendo entregable; no se exige perfección literal).
- **RF-212** (T-617C, `contracts/api-rest.md §4c`): este incremento **reutiliza sin modificar** la señal de relevancia léxica de columnas ya aprobada — no crea una nueva.
- **RNF-005** (honestidad frente a fabricación): cierra el mecanismo por el que `pilot-044`/`pilot-048` producían claims cuantitativos desde evidencia ajena al tema de la pregunta.

## 1. Diagnóstico causal

### 1.1 Flujo trazado

`run_deterministic_agent` (`backend/app/agent/deterministic_runtime.py:303-651`) construye en cada iteración un `SupervisorSnapshot` (`backend/app/agent/deterministic_graph.py:84-104`) con únicamente hechos verificables del estado, y `decide_next_transition` (puro, sin I/O) decide el siguiente nodo. La secuencia relevante:

```
SELECT_CANDIDATE → PROFILE_DATASET → BUILD_PLAN → EXECUTE_QUERY
  → (evidence_eligible?) → (claims_available?) → SYNTHESIZE → COMPLETE
```

`EXECUTE_QUERY` deriva los claims de forma síncrona (`execution.claims`); `DERIVE_CLAIMS` es, de hecho, un nodo muerto en este runtime (`deterministic_runtime.py:609-610`: `raise AssertionError("execute ya deriva claims de forma determinista")`). Antes de este incremento, en cuanto `evidence_eligible=True` (chequeo de **calidad de datos**: `execution.quality.eligibility_status == "eligible"`, computado en `backend/app/quality/eligibility.py`) y `claims_available=True` (mera existencia de al menos un claim), la transición pasaba directo a `SYNTHESIZE` — sin ningún chequeo de si esos claims respondían materialmente la intención de la pregunta.

### 1.2 Punto mínimo donde evidencia de buena calidad técnica se convertía en claims sin responder la intención

`evidence_eligible` mide **calidad del dato** (esquema, completitud, vigencia, trazabilidad — `app/quality/eligibility.py`, `app/quality/validator.py`), nunca **pertinencia temática** con la pregunta. Un dataset de códigos postales o de deserción escolar puede ser `eligible/alta` (score 91–100) de forma perfectamente legítima y, aun así, no tener nada que ver con "causalidad de política pública en reducción de pobreza" o "polarización en redes sociales". Verificado directamente contra la corrida real `b0d38f87-d2d3-4bc8-80ae-b197e278d328` (T-617B-C1):

- `pilot-044-negativo-causalidad-politica`: evidencia aceptada del dataset de códigos postales (`ixig-z8b5`), `eligibility_status=eligible`, `score_total=91`; único claim con columna fuente `fecha_registro_intervencion` (categoría léxica `temporal`).
- `pilot-048-negativo-ranking-corrupcion`: evidencia aceptada del dataset de deserción escolar (`ji8i-4anb`), `eligibility_status=eligible`, `score_total=100`; ~40 claims, todos con columnas fuente `codigo_departamento`/`codigo_municipio`/`codigo_postal` (categoría léxica `auxiliary`).

En ambos casos el resumen final en prosa razonaba correctamente ("No se encontró información sobre..."), pero el pipeline estructurado ya había generado claims cuantitativos desde esa evidencia ajena, y `status_final` quedaba en `completed`, no `no_evidence` (`fabrication_count=2` en el gate).

### 1.3 Por qué `accepted_dataset_id` puede quedar `null` con evidencia final `eligible/alta`

Confirmado con lectura directa de `eval_case_results`/`stage_diagnostics` para `pilot-024–027`: en los cuatro casos el dataset esperado por el caso golden fue efectivamente intentado (rank 1–2 en la recuperación), pero el plan contra ese dataset no llegó a producir un plan válido/candidato aceptado (`accepted_dataset_id=null` en los diagnósticos persistidos), y el runtime se replegó a un candidato posterior (`ji8i-4anb`, reusado en los cuatro) que sí resultó `eligible/alta` por calidad de datos aunque temáticamente distinto ("paridad de matrícula", "ETC" vs. deserción escolar). El campo `accepted_dataset_id` de los diagnósticos de evaluación (`backend/eval/diagnostics.py`) sólo se llena cuando el caso pasa la aceptación golden completa; el runtime interno, en cambio, sí registra y persiste evidencia de la ÚLTIMA fila aceptada por candidato aunque esa aceptación golden termine fallando — de ahí la aparente contradicción, que no es tal: son dos nociones de "aceptado" distintas (aceptación interna del runtime vs. aceptación del caso de evaluación).

### 1.4 Señales estructuradas ya existentes usadas (sin heurísticas nuevas)

`backend/app/quality/claim_labels.py` (RF-212, T-617C-A, módulo puro sin I/O ni LLM) ya expone:

- `classify_column_relevance(field_name) -> "primary" | "temporal" | "auxiliary"`: clasificación léxica determinista por nombre de columna real (conjuntos fijos `_AUXILIARY_TOKENS`/`_TEMPORAL_TOKENS` ya aprobados y en producción desde T-617C).
- `intent_relevance_tokens(topic, administrative_terms) -> frozenset[str]`: tokens de la intención de la corrida en curso (nunca `case_id`/`dataset_id`/texto literal de un caso concreto).
- `claim_is_relevant_to_narrative(source_columns, *, requested_tokens) -> bool`: decide si un claim pertenece a la narrativa principal según la categoría léxica de sus columnas fuente frente a los tokens de la intención.

Estas tres funciones **ya estaban importadas y en uso** en `deterministic_runtime.py` (función `_deterministic_synthesis`, el *fallback* sin LLM) y en `deterministic_dependencies.py` (la llamada real al sintetizador LLM) — en ambos lugares, para decidir **qué claims mostrar** al redactar la respuesta. El defecto es que, en los dos lugares, cuando el filtro de relevancia deja el conjunto vacío (`relevant = []`), el código cae de vuelta a mostrar **todos** los claims sin filtrar (`pool = relevant if relevant else indexed`) — exactamente el caso de `pilot-044`/`pilot-048`, donde el 100% de los claims son `auxiliary`/`temporal` no solicitados. La señal para detectar "esta evidencia no es materialmente pertinente" ya existía; sólo no se usaba para decidir la **transición** del supervisor (síntesis sí/no), sino únicamente qué mostrarle al LLM una vez que la síntesis ya estaba decidida.

Verificado con datos reales (lectura de solo lectura de `quantitative_claims` para las corridas de `pilot-044`/`pilot-048`/`pilot-024–027`): en `pilot-044` y `pilot-048` el 100% de los claims son `auxiliary`/`temporal`; en `pilot-024–027`, en cambio, columnas como `c_digo_departamento` (con tilde saneada por Socrata a guion bajo) y `tasa_matriculacion_5_16`/`tamano_promedio_grupo` clasifican como `primary` — la clasificación léxica por categoría de columna **no** detecta ese repliegue a dataset equivocado. Ver sección 3 (condición de parada) para esta segunda familia de casos.

### 1.5 Por qué no se usa el texto libre del sintetizador

El resumen final en prosa (`synthesis.answer`) llega **después** de que el pipeline estructurado ya ejecutó la consulta, generó `execution.claims` y (antes de este incremento) siempre alcanzaba `SYNTHESIZE`. Condicionar la abstención al texto generado por el LLM violaría "no juicio de LLM no validable" (punto 3 del encargo) y llegaría demasiado tarde: los claims ya estarían persistidos y expuestos. La corrección debe ocurrir en la capa de transición determinista, antes de invocar síntesis.

## 2. Diseño del gate

### 2.1 Punto exacto del flujo

Nuevo campo `claims_materially_relevant: bool = True` en `SupervisorSnapshot` (`deterministic_graph.py`). Se computa en `run_deterministic_agent` (`deterministic_runtime.py`), en el mismo punto donde ya se computaba `claims_available`, reutilizando exactamente las mismas funciones y el mismo objeto `intent` ya usados por `_deterministic_synthesis`:

```python
claims_materially_relevant = True
if execution is not None and execution.claims.claims:
    requested_tokens = intent_relevance_tokens(intent.topic, intent.administrative_terms)
    claims_materially_relevant = any(
        claim_is_relevant_to_narrative(
            getattr(claim, "public_columns", ()), requested_tokens=requested_tokens
        )
        for claim in execution.claims.claims
    )
```

En `decide_next_transition`, justo después de la rama existente `if not state.claims_available: ...` (que ya cubre "cero claims") y antes de `if not state.synthesis_valid: return SYNTHESIZE`, se inserta:

```python
if not state.claims_materially_relevant:
    if _has_unseen_candidate(state):
        return Transition(
            node=SupervisorNode.NEXT_CANDIDATE,
            reason="ningún claim deriva de una columna pertinente a la intención",
        )
    return Transition(
        node=SupervisorNode.ABSTAIN,
        reason="ninguna evidencia recuperada es pertinente a la intención",
        stop_reason=StopReason.CLAIMS_NOT_AVAILABLE,
    )
```

y la condición de `COMPLETE` en la parte superior de la función se amplía con `and state.claims_materially_relevant`, por completitud defensiva (en el flujo normal es inalcanzable violar esto, porque el nuevo gate intercepta antes de llegar a `SYNTHESIZE`).

`StopReason.CLAIMS_NOT_AVAILABLE` es un valor **ya existente** (usado, por ejemplo, para el rechazo textual T-615F), reutilizado en vez de crear un código nuevo — `contracts/api-rest.md:128` documenta explícitamente que `usage.termination_reason` para `status="no_evidence"` **"no es un enum cerrado"**, así que ni siquiera habría sido un cambio de contrato crear uno nuevo, pero reutilizar el existente evita cualquier ambigüedad.

El nodo `NEXT_CANDIDATE` reutiliza la máquina de estados ya existente y probada (`deterministic_runtime.py:643-650`): rechaza el candidato actual, resetea `execution`/`profile`/`selection` y continúa con el siguiente candidato no visto, exactamente el mismo patrón ya usado para `evidence_eligible=False`. Cuando no quedan candidatos, `ABSTAIN` termina la corrida con `status="abstained"`.

### 2.1.1 Ruta diferida (`defer_synthesis_until_persisted=True`, T-615F) — corregida en R2

La revisión R2 encontró que la rama `if state.synthesis_deferred and state.claims_available: return PERSIST_FACTS` (usada por la ruta productiva de hechos textuales, activa cuando `settings.deterministic_textual_facts_enabled=True`) se evaluaba **antes** de la rama `claims_materially_relevant` y sólo comprobaba existencia de claims, no pertinencia — dejando pasar claims irrelevantes a `PERSIST_FACTS` sin pasar por el gate. Reproducido de forma independiente: `defer_synthesis_until_persisted=True` + un candidato con un único claim irrelevante → `status=ready_for_synthesis`, último nodo `persist_facts`, `claims=1`.

**Corrección**: se amplió la condición de esa misma rama (sin moverla, para no alterar su prioridad frente a `textual_rejected` y la segunda rama diferida específica de texto) para exigir que el claim sea pertinente **o** que haya un resultado textual pertinente que deba preservarse:

```python
if state.synthesis_deferred and state.claims_available:
    if state.claims_materially_relevant or state.textual_result_available:
        return Transition(node=SupervisorNode.PERSIST_FACTS, ...)
```

Si ninguna de las dos condiciones se cumple, la ejecución no retorna aquí y cae a través de las ramas siguientes (`textual_rejected`, la segunda rama diferida específica de texto, `claims_available`) hasta alcanzar la rama `claims_materially_relevant` de la sección 2.1, que decide `NEXT_CANDIDATE`/`ABSTAIN` — el mismo desenlace que en modo inmediato, sin duplicar lógica. Esto preserva exactamente el requisito de no bloquear un hecho textual pertinente: si `textual_result_available=True` (independientemente de si el claim cuantitativo de esa misma evidencia es irrelevante), la persistencia procede con normalidad.

### 2.2 Por qué el resultado final ya cumple `evidence=[]`/`claims=[]`/`no_evidence_report` sin tocar la capa de persistencia

`backend/app/agent/runner.py:528,562,588-628` ya calcula `quantitative_completed = result.status == "completed"` y `public_completed = quantitative_completed or (...)`; `evidence`/`claims` sólo se llenan **dentro** del bloque `if public_completed:`. Al cambiar `result.status` de `"completed"` a `"abstained"` para el caso irrelevante, `public_completed` pasa a `False` automáticamente, y el `final_answer` persistido ya produce, sin ningún cambio adicional:

- `"status": "no_evidence"`
- `"evidence": []`
- `"claims": []`
- `"summary": "No encontré evidencia elegible suficiente para responder."`
- `"no_evidence_report": {"reason": "CLAIMS_NOT_AVAILABLE", ...}`

`orphan_figures_count` permanece en 0 porque, sin `evidence`/`claims` públicos, `_collect_orphan_figures` (`backend/eval/metrics.py`) no tiene nada que auditar (no cambia su implementación).

### 2.3 Trazabilidad de datasets revisados/rechazados

Cada rechazo por pertinencia pasa por `NEXT_CANDIDATE`, que ya deja constancia en `CandidateProgress`/`RuntimeTraceEntry` (persistidos como `agent_steps`/`stage_diagnostics.attempted_dataset_ids`/`retrieved_dataset_ids`, igual que cualquier otro rechazo de candidato — mecanismo ya existente, no se modifica). El campo `no_evidence_report.datasets_reviewed` de `runner.py` ya está hardcodeado a `[]` para **toda** abstención, con independencia de este incremento — es un vacío preexistente no introducido ni agravado aquí; la trazabilidad real está en `stage_diagnostics`, no en ese campo.

### 2.4 No confunde pertinencia con elegibilidad

`evidence_eligible` (calidad) y `claims_materially_relevant` (pertinencia temática) quedan como señales **independientes** en `SupervisorSnapshot`; ninguna sustituye a la otra. Una evidencia puede ser `eligible=False` y pertinente, o `eligible=True` e irrelevante — el gate nuevo sólo actúa cuando la evidencia ya pasó el chequeo de calidad, exactamente el hueco diagnosticado.

### 2.5 Respuesta parcial pertinente (RF-211)

Sin cambios: cuando `relevant` (dentro de `synthesize()`/`_deterministic_synthesis`) es no vacío —es decir, al menos un claim es pertinente— `claims_materially_relevant=True`, el flujo llega a `SYNTHESIZE` normalmente, y la selección de claims mostrados al sintetizador (`pool = relevant`) sigue funcionando exactamente igual que antes: los claims irrelevantes simplemente no se citan en la narrativa, pero la respuesta se entrega. Verificado con `test_runtime_completes_with_partially_relevant_evidence`.

## 3. Condición de parada aplicada — `pilot-024–027` (repliegue positivo)

Diagnosticado en la sección 1.4: para estos cuatro casos, la evidencia de repliegue tiene columnas como `c_digo_departamento`, `a_o`, `tasa_matriculacion_5_16`, `tamano_promedio_grupo` — nombres que, por categoría léxica (`auxiliary`/`temporal`/`primary`), no son distinguibles de columnas legítimamente pertinentes. `codigo_departamento` clasifica `auxiliary` (contiene el token `codigo`), pero **`c_digo_departamento`** (con la tilde saneada por Socrata a guion bajo, como ocurre realmente en este dataset) clasifica `primary`, porque `_tokens()` no reconoce `c_digo` como variante de `codigo`. Resolver esto exigiría **una de las cuatro condiciones de parada del encargo**:

- Un nuevo campo contractual o metadato (p. ej. tema/etiqueta temática del dataset comparable contra la intención) — no existe hoy en `catalog_datasets` ni en los contratos.
- Un nuevo juicio LLM de pertinencia semántica dataset-pregunta, no validable de forma cerrada.
- Heurísticas léxicas abiertas (comparar título/descripción del dataset contra el texto de la pregunta) — exactamente lo que el encargo prohíbe explícitamente ("no listas manuales de palabras", "no heurísticas léxicas abiertas").

**Por tanto, `pilot-024–027` queda fuera del alcance de este incremento.** No se implementó ninguna solución para este subconjunto. Queda documentado como diagnóstico con la mínima enmienda candidata: si en una ronda futura se aprueba un metadato estructurado de tema/categoría por dataset (ya presente parcialmente en `catalog_datasets` como categoría de publicación, sin confirmar), podría compararse contra `intent.topic` sin heurísticas léxicas abiertas ni LLM — pero eso requiere autorización normativa separada, no se resuelve aquí.

`pilot-007` (cifra huérfana / atribución de infraestructura, T-617B-C1 sección 6), `expected_facts` (T-617B-C1 §3), `budget_exceeded` (T-617B-C1 §4) y latencia (T-617B-C1 §7) — explícitamente fuera de alcance por instrucción del encargo — no se tocaron.

## 4. Archivos modificados

| Archivo | Cambio |
|---|---|
| `backend/app/agent/deterministic_graph.py` | Nuevo campo `claims_materially_relevant` en `SupervisorSnapshot`; nueva rama en `decide_next_transition` (NEXT_CANDIDATE/ABSTAIN); condición de `COMPLETE` ampliada; **R2**: condición de la rama diferida `PERSIST_FACTS` ampliada para exigir pertinencia o resultado textual. +33/-5 líneas (sin cambios adicionales en R3). |
| `backend/app/agent/deterministic_runtime.py` | Cómputo de `claims_materially_relevant` por iteración, reutilizando `intent_relevance_tokens`/`claim_is_relevant_to_narrative` ya importados (R1); **R3**: `textual_result_available` redefinido para excluir rechazos, reflejando sólo hechos aceptados. +21/-3 líneas en total. |
| `backend/tests/test_deterministic_graph.py` | 3 pruebas unitarias puras sobre `decide_next_transition` (sin cambios en R2/R3). |
| `backend/tests/test_deterministic_runtime.py` | 7 pruebas de extremo a extremo (R1) + 4 pruebas sobre la ruta diferida (R2) + **3 pruebas nuevas en R3** sobre el rechazo textual puro. 17 en total. |

Diff completo de `deterministic_graph.py` (R1+R2, sin cambios adicionales en R3):

```diff
--- a/backend/app/agent/deterministic_graph.py
+++ b/backend/app/agent/deterministic_graph.py
@@ -95,6 +95,7 @@ class SupervisorSnapshot(BaseModel):
     evidence_eligible: bool = False
     safe_aggregate_possible: bool = False
     claims_available: bool = False
+    claims_materially_relevant: bool = True
     textual_result_available: bool = False
     textual_rejected: bool = False
     synthesis_deferred: bool = False
@@ -133,7 +134,12 @@ def _has_unseen_candidate(state: SupervisorSnapshot) -> bool:
 def decide_next_transition(state: SupervisorSnapshot) -> Transition:
     """Decide el siguiente nodo usando solo hechos verificables del estado."""

-    if state.synthesis_valid and state.claims_available and state.evidence_eligible:
+    if (
+        state.synthesis_valid
+        and state.claims_available
+        and state.claims_materially_relevant
+        and state.evidence_eligible
+    ):
         return Transition(node=SupervisorNode.COMPLETE, reason="síntesis verificada desde claims")

     budget_stop = _budget_stop(state)
@@ -194,10 +200,17 @@ def decide_next_transition(state: SupervisorSnapshot) -> Transition:
             stop_reason=StopReason.EVIDENCE_NOT_ELIGIBLE,
         )
     if state.synthesis_deferred and state.claims_available:
-        return Transition(
-            node=SupervisorNode.PERSIST_FACTS,
-            reason="claims derivados listos para persistencia y reverificación",
-        )
+        # T-617B-C2 (corrección posterior): un claim cuantitativo irrelevante
+        # no puede persistirse solo porque exista. Se exige o bien que algún
+        # claim sea pertinente, o bien que haya un resultado textual
+        # pertinente (T-615F/RF-212) que igual deba conservarse — nunca se
+        # bloquea la persistencia de un hecho textual válido por culpa de
+        # claims cuantitativos irrelevantes.
+        if state.claims_materially_relevant or state.textual_result_available:
+            return Transition(
+                node=SupervisorNode.PERSIST_FACTS,
+                reason="claims derivados listos para persistencia y reverificación",
+            )
     if state.textual_rejected:
         return Transition(
             node=SupervisorNode.ABSTAIN,
@@ -217,6 +230,21 @@ def decide_next_transition(state: SupervisorSnapshot) -> Transition:
                 stop_reason=StopReason.CLAIMS_NOT_AVAILABLE,
             )
         return Transition(node=SupervisorNode.DERIVE_CLAIMS, reason="evidencia elegible sin claims")
+    if not state.claims_materially_relevant:
+        # T-617B-C2: evidencia técnicamente elegible cuyos claims no derivan
+        # de ninguna columna pertinente a la intención (RF-205/RF-211) no
+        # debe sintetizarse. Se agota primero el resto de candidatos, como ya
+        # ocurre con `evidence_eligible`, antes de abstenerse.
+        if _has_unseen_candidate(state):
+            return Transition(
+                node=SupervisorNode.NEXT_CANDIDATE,
+                reason="ningún claim deriva de una columna pertinente a la intención",
+            )
+        return Transition(
+            node=SupervisorNode.ABSTAIN,
+            reason="ninguna evidencia recuperada es pertinente a la intención",
+            stop_reason=StopReason.CLAIMS_NOT_AVAILABLE,
+        )
     if not state.synthesis_valid:
         return Transition(node=SupervisorNode.SYNTHESIZE, reason="claims aceptados listos")
     raise AssertionError("estado exhaustivo no cubierto")

--- a/backend/app/agent/deterministic_runtime.py
+++ b/backend/app/agent/deterministic_runtime.py
@@ -358,6 +358,21 @@ async def run_deterministic_agent(
         if is_cancelled is not None and is_cancelled():
             raise DeterministicRunCancelled("corrida cancelada")
         elapsed_ms = round((time.monotonic() - started) * 1000)
+        # T-617B-C2 (RF-205/RF-211): evidencia elegible por calidad puede
+        # seguir siendo ajena a la intención de la pregunta. Reutiliza la
+        # misma señal estructurada ya aprobada en T-617C (RF-212) que
+        # clasifica cada columna fuente de un claim frente a los tokens de
+        # la intención — sin heurísticas nuevas, sin `case_id`/`dataset_id`,
+        # sin juicio de LLM.
+        claims_materially_relevant = True
+        if execution is not None and execution.claims.claims:
+            requested_tokens = intent_relevance_tokens(intent.topic, intent.administrative_terms)
+            claims_materially_relevant = any(
+                claim_is_relevant_to_narrative(
+                    getattr(claim, "public_columns", ()), requested_tokens=requested_tokens
+                )
+                for claim in execution.claims.claims
+            )
         snapshot = SupervisorSnapshot(
             candidates=tuple(candidates),
             current_candidate_index=current,
@@ -371,11 +386,15 @@ async def run_deterministic_agent(
                 execution is not None and execution.quality.eligibility_status == "eligible"
             ),
             claims_available=execution is not None and bool(execution.claims.claims),
+            claims_materially_relevant=claims_materially_relevant,
+            # T-617B-C2 (corrección R3): `textual_result_available` señala
+            # exclusivamente hechos textuales ACEPTADOS. Un rechazo no es un
+            # resultado disponible para persistir — mezclarlos permitía que
+            # un rechazo textual puro disfrazara de "hecho pertinente" la
+            # persistencia de un claim cuantitativo irrelevante. `textual_
+            # rejected` (abajo) es la señal independiente para rechazos.
             textual_result_available=execution is not None
-            and bool(
-                getattr(execution, "textual_facts", ())
-                or getattr(execution, "textual_rejections", ())
-            ),
+            and bool(getattr(execution, "textual_facts", ())),
             textual_rejected=execution is not None
             and bool(getattr(execution, "textual_rejections", ())),
             synthesis_deferred=defer_synthesis_until_persisted,
```

`intent_relevance_tokens`/`claim_is_relevant_to_narrative` ya estaban importados en `deterministic_runtime.py:66` (usados por `_deterministic_synthesis`); **cero imports nuevos**. La corrección R3 no añade ninguna llamada ni importación adicional — sólo elimina la cláusula `or getattr(execution, "textual_rejections", ())` de una expresión ya existente.

## 5. Pruebas: baseline → cambio

### 5.1 Fixtures nuevas (genéricas, sin nombrar pilotos ni datasets de la suite)

En `tests/test_deterministic_runtime.py`, dobles locales sin red (`_relevance_dependencies`, `_irrelevant_claim`, `_relevant_claim`):

1. `test_runtime_abstains_when_only_evidence_is_eligible_but_irrelevant` — evidencia eligible/alta pero ajena → `no_evidence`, cero claims.
2. `test_runtime_causal_question_without_causal_evidence_abstains_cleanly` — pregunta causal sin diseño causal disponible → abstención limpia.
3. `test_runtime_network_analysis_question_without_network_evidence_abstains_cleanly` — pregunta de análisis de redes sin evidencia de redes → abstención limpia.
4. `test_runtime_completes_and_preserves_claims_when_evidence_is_materially_relevant` — evidencia materialmente pertinente → `completed`, claims preservados.
5. `test_runtime_completes_with_partially_relevant_evidence` — evidencia parcialmente pertinente → respuesta parcial permitida (RF-211).
6. `test_runtime_tries_next_candidate_before_abstaining_on_irrelevant_claims` — rechazo por pertinencia queda trazado (razón "pertinente" en el trace) antes de completar con el segundo candidato.
7. `test_runtime_abstains_cleanly_when_all_candidates_are_irrelevant` — con dos candidatos ajenos, ambos rechazados por pertinencia antes de la abstención final.

En `tests/test_deterministic_graph.py` (nivel de transición pura, sin runtime):

8. `test_claims_not_materially_relevant_tries_next_candidate_before_abstaining`
9. `test_claims_not_materially_relevant_abstains_when_no_candidates_remain`
10. `test_claims_materially_relevant_defaults_true_and_preserves_synthesize_path` (regresión del camino feliz)

**R2 — 4 pruebas nuevas en `test_deterministic_runtime.py`, específicas de la ruta diferida** (`_relevance_dependencies` extendida con `textual_facts_by_candidate`):

11. `test_deferred_mode_with_only_irrelevant_claims_never_reaches_persist_facts` — reproducción exacta del hueco reportado: modo diferido + único candidato con claim irrelevante → `NEXT_CANDIDATE` seguido de `ABSTAIN`, nunca `PERSIST_FACTS`.
12. `test_deferred_mode_tries_next_candidate_and_persists_the_relevant_one` — modo diferido + siguiente candidato relevante → completa (`ready_for_synthesis`) con el segundo candidato; el claim del primero no sobrevive.
13. `test_deferred_mode_preserves_pertinent_textual_fact_despite_irrelevant_claim` — claim cuantitativo irrelevante coexistiendo con hecho textual pertinente en la misma evidencia → `PERSIST_FACTS` procede, el hecho textual se conserva.
14. `test_rejected_candidate_claims_never_reach_the_accepted_execution` — en ambos modos (inmediato y diferido), el claim del candidato rechazado por pertinencia no aparece en `execution` final.

**R3 — 3 pruebas nuevas en `test_deterministic_runtime.py`, específicas del rechazo textual puro** (`_relevance_dependencies` extendida con `textual_rejections_by_candidate`):

15. `test_deferred_mode_with_irrelevant_claim_and_only_textual_rejection_never_persists` — reproducción exacta del hueco R3: claim irrelevante + único candidato con SOLO rechazo textual (sin hecho aceptado) + modo diferido → nunca `PERSIST_FACTS`.
16. `test_deferred_mode_preserves_accepted_fact_despite_simultaneous_rejection` — claim irrelevante + hecho textual aceptado + rechazo textual simultáneo en la misma evidencia → el hecho aceptado se preserva (`PERSIST_FACTS` procede).
17. `test_relevant_claim_with_textual_rejection_still_persists_the_claim` — claim relevante + rechazo textual → se conserva el comportamiento existente de persistir el claim cuantitativo válido.

### 5.2 Resultado contra el baseline R1 (código revertido temporalmente vía `git stash`, pruebas 1–10 ya presentes)

```
$ uv run pytest tests/test_deterministic_runtime.py -q
5 failed, 26 passed, 1 warning in 5.58s

FAILED test_runtime_abstains_when_only_evidence_is_eligible_but_irrelevant
FAILED test_runtime_causal_question_without_causal_evidence_abstains_cleanly
FAILED test_runtime_network_analysis_question_without_network_evidence_abstains_cleanly
FAILED test_runtime_tries_next_candidate_before_abstaining_on_irrelevant_claims
FAILED test_runtime_abstains_cleanly_when_all_candidates_are_irrelevant
```

Los dos casos de control positivo (`..._materially_relevant`, `..._partially_relevant_evidence`) **ya pasaban** en el baseline — correcto: la ruta feliz nunca estuvo rota, sólo el gate de abstención faltaba.

### 5.3 Resultado con el cambio R1 aplicado (`git stash pop`)

```
$ uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q
50 passed, 1 warning in 7.93s
```

### 5.3.1 R2 — Reproducción del hueco de la ruta diferida contra el baseline intermedio

Se revirtió **únicamente** la condición ampliada de la rama diferida (dejando intacto todo lo demás de R1, vía edición dirigida seguida de restauración exacta, sin usar `git stash` para no perder el resto del incremento), y se ejecutaron las 4 pruebas nuevas de la sección 5.1 (11–14):

```
$ uv run pytest tests/test_deterministic_runtime.py -k "deferred_mode or rejected_candidate_claims_never" -q
3 failed, 1 passed, 31 deselected, 1 warning in 7.83s

FAILED test_deferred_mode_with_only_irrelevant_claims_never_reaches_persist_facts
  AssertionError: assert False  -- (result.trace contenía SupervisorNode.PERSIST_FACTS)
FAILED test_deferred_mode_tries_next_candidate_and_persists_the_relevant_one
  AssertionError: assert ['1'] == ['42']  -- el claim irrelevante "1" del primer candidato llegó a persistencia
FAILED test_rejected_candidate_claims_never_reach_the_accepted_execution
  AssertionError: assert '999' not in ['999']  -- el claim irrelevante "999" apareció en la ejecución final
```

`test_deferred_mode_preserves_pertinent_textual_fact_despite_irrelevant_claim` **ya pasaba** contra este baseline intermedio — correcto: esa ruta (segunda rama diferida, específica de `textual_result_available`) nunca estuvo rota; el hueco estaba únicamente en la primera rama diferida, que ignoraba pertinencia por completo.

Esto reproduce exactamente el patrón reportado (`status=ready_for_synthesis`, último nodo `persist_facts`, claim irrelevante expuesto). Con la corrección restaurada:

```
$ uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q
54 passed, 1 warning in 5.28s
```

### 5.3.2 R3 — Reproducción del hueco del rechazo textual puro

Se revirtió **únicamente** la corrección de `textual_result_available` (dejando intactas todas las demás correcciones de R1/R2) y se ejecutaron las 3 pruebas nuevas:

```
$ uv run pytest tests/test_deterministic_runtime.py -k "textual_rejection or simultaneous_rejection" -q
1 failed, 2 passed, 35 deselected, 1 warning in 6.42s

FAILED test_deferred_mode_with_irrelevant_claim_and_only_textual_rejection_never_persists
  AssertionError: assert 'ready_for_synthesis' == 'abstained'
```

`test_deferred_mode_preserves_accepted_fact_despite_simultaneous_rejection` y `test_relevant_claim_with_textual_rejection_still_persists_the_claim` **ya pasaban** contra este baseline — correcto: ambos escenarios tenían, respectivamente, un hecho textual realmente aceptado o un claim realmente relevante, así que no dependían de la definición defectuosa. El hueco estaba exclusivamente en el caso "sólo rechazo, sin nada aceptado ni relevante".

Se verificó además que las tres ramas de `decide_next_transition` que leen `textual_result_available` no dependían de la semántica anterior: la rama de R2 (línea ~209) es precisamente la que se corrige aquí; la segunda rama diferida preexistente de T-615F (línea ~220) sólo se alcanza después de superar el chequeo `if state.textual_rejected: ABSTAIN` (línea ~214), por lo que en ese punto `textual_rejected` ya es `False` y la inclusión de rechazos en `textual_result_available` era de hecho un no-op; la rama de abstención sin claims (línea ~226) está en la misma situación, alcanzable sólo después de superar el mismo chequeo. Confirmado por la suite completa sin regresiones (5.4).

Con la corrección restaurada:

```
$ uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q
57 passed, 1 warning in 4.68s
```

### 5.4 Suite completa no-integración, antes y después

- Antes de este incremento (mismo HEAD, sin tocar código): **1018 passed, 122 deselected**.
- Después de R1: 1028 passed.
- Después de R2: 1032 passed.
- Después de R3 (estado final, con las 17 pruebas nuevas incluidas): **1035 passed, 122 deselected**.

Cero regresiones: los 1018 tests preexistentes siguen en verde sin modificación (salvo el `getattr` defensivo que reparó un doble de prueba incompleto en `test_deterministic_textual_planning.py::test_textual_rejection_never_reaches_synthesis_or_legacy_fallback`, sin alterar su aserción — ver 5.5).

### 5.5 Nota sobre un test preexistente afectado indirectamente

`test_textual_rejection_never_reaches_synthesis_or_legacy_fallback` usa un doble de claim (`object()`) sin atributo `public_columns`, porque el escenario que prueba (rechazo textual) nunca debía llegar a evaluar claims. Mi cómputo nuevo se ejecuta incondicionalmente antes de `decide_next_transition`, así que un `claim.public_columns` directo habría lanzado `AttributeError` en ese doble incompleto. Se resolvió con `getattr(claim, "public_columns", ())` (equivalente semánticamente: sin columnas → `claim_is_relevant_to_narrative` retorna `True` por vacuidad, `source_columns` vacío). **No se modificó ninguna aserción del test**; su assert original (`raise AssertionError` si síntesis es alcanzada) sigue intacto y sigue pasando.

## 6. Validación ejecutada

```
uv run pytest tests/test_deterministic_graph.py tests/test_deterministic_runtime.py -q   → 57 passed
uv run pytest -m "not integration" -q                                                     → 1035 passed, 122 deselected
uv run ruff check app/agent/deterministic_graph.py app/agent/deterministic_runtime.py \
    tests/test_deterministic_graph.py tests/test_deterministic_runtime.py                 → All checks passed
uv run ruff format --check <mismos 4 archivos>                                            → 4 files already formatted (tras un reformateo automático)
```

No se ejecutó smoke, golden-v1, golden-v2 ni aceptación legacy real, conforme al encargo. No se ejecutó `deterministic_agent_acceptance` (aceptación determinista E2E) porque requiere PostgreSQL con escritura y, de disponer de él, seguiría sin llamadas reales a Gemini/Socrata — no se intentó dado que el alcance autorizado es "dobles locales y cero red" y la cobertura de `test_deterministic_runtime.py` ya ejercita el mismo `run_deterministic_agent` real con dependencias inyectadas.

## 7. Riesgos y limitaciones

1. **`pilot-024–027` no quedan resueltos** (sección 3): el repliegue a un dataset de calidad alta pero temáticamente ajeno, cuando sus columnas clasifican léxicamente como `primary`, no es detectable con las señales estructuradas actuales sin violar alguna de las cuatro condiciones de parada del encargo. Requiere decisión normativa separada.
2. **Normalización de acentos en `claim_labels._tokens`**: el hallazgo de que `c_digo_departamento` (tilde saneada a guion bajo por Socrata) no coincide con el token `codigo` es un límite conocido de la tokenización actual, ya presente antes de este incremento (afecta igual a la clasificación de columnas para presentación, RF-212). No se corrige aquí — está fuera del alcance acotado y tocar `_tokens()`/`_AUXILIARY_TOKENS` sería exactamente la "heurística léxica abierta" que el encargo prohíbe ampliar sin autorización.
3. **`no_evidence_report.datasets_reviewed` sigue vacío** para toda abstención (defecto preexistente, no introducido ni agravado por este cambio); la trazabilidad real de datasets revisados/rechazados vive en `stage_diagnostics.attempted_dataset_ids`/`retrieved_dataset_ids`, ya persistidos.
4. **Este gate puede, en teoría, rechazar una evidencia legítima pero con nombres de columna atípicos** que no fueron clasificados `primary` por `classify_column_relevance` (p. ej. si toda la evidencia útil está en columnas auxiliares no solicitadas explícitamente por la intención). Este riesgo es idéntico al que ya existía en `_deterministic_synthesis`/`synthesize()` para decidir qué mostrar al LLM — no es nuevo, sólo ahora también decide si sintetizar en absoluto. Mitigado por el mecanismo ya existente de `requested_tokens`: si la intención menciona explícitamente el término administrativo (p. ej. "código"), esa columna deja de excluirse.
5. **No se verificó el efecto de este cambio contra una corrida real de `golden-v1`/`golden-v2`** (prohibido por el encargo). El impacto exacto en `success_rate`/`fabrication_count` de una futura corrida real queda sin confirmar hasta que se autorice.
6. **(R2, cerrado) Ruta diferida (`defer_synthesis_until_persisted=True`)**: la primera versión de este incremento no cubría la rama `PERSIST_FACTS` de la ruta productiva de hechos textuales (T-615F), que se evalúa antes que el nuevo gate y sólo comprobaba existencia de claims. Corregido en esta versión (sección 2.1.1) ampliando la condición de esa rama sin moverla, preservando explícitamente la persistencia de un hecho textual pertinente aunque el claim cuantitativo de esa misma evidencia sea irrelevante. Ambos modos (`defer=False`, el usado por la corrida golden-v1 auditada en T-617B-C1, y `defer=True`) quedan ahora cubiertos y probados (sección 5).
7. **Alcance de `claim_is_relevant_to_narrative` (precisión terminológica exigida en R2)**: la señal reutilizada por este gate es un filtro léxico acotado por categoría de columna (`auxiliary`/`temporal`/`primary`), no una prueba general de que el dataset completo responde la intención de la pregunta. No debe leerse como "verificación de pertinencia temática del dataset" — sólo excluye columnas específicas que, por su nombre, son identificadores o marcas temporales no solicitadas. La sección 3 (`pilot-024–027`) documenta el caso en que esta distinción importa: columnas `primary` de un dataset temáticamente equivocado no son detectadas por este gate.
8. **(R3, cerrado) Rechazo textual disfrazado de resultado pertinente**: `textual_result_available` incluía la mera presencia de `textual_rejections`, permitiendo que un rechazo textual puro (sin ningún hecho aceptado) activara la rama de persistencia diferida de R2. Corregido separando la señal en su origen (sección "Revisión R3") para que refleje exclusivamente hechos aceptados; `textual_rejected` sigue siendo la señal independiente para rechazos, ya correctamente calculada desde antes de este incremento.

## 8. Hashes de golden intactos

```
golden-v1.yaml   ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72
golden-v2.yaml   1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483
```

Idénticos a los valores congelados de referencia; ninguno de los dos archivos fue leído para escritura ni modificado.

## 9. `git status --short` final

```
 M backend/app/agent/deterministic_graph.py
 M backend/app/agent/deterministic_runtime.py
 M backend/tests/test_deterministic_graph.py
 M backend/tests/test_deterministic_runtime.py
?? backend/eval/reports/019be4a6-da19-4153-b2d1-8b87763bb89d.md
?? backend/eval/reports/115de3e4-e06a-471b-af37-d4fa8d61cd36.md
?? backend/eval/reports/224159e0-7a8b-4646-819d-e1271bba38d2.md
?? backend/eval/reports/7bd186d1-b317-48d5-9e1e-262561b73a1a.md
?? backend/eval/reports/8ab794ac-50e6-453d-a7b7-3d8a1b95f973.md
?? backend/eval/reports/8f5cacf0-1205-4fb3-adc7-63fb452822bf.md
?? backend/eval/reports/b0d38f87-d2d3-4bc8-80ae-b197e278d328.md
?? backend/eval/reports/fd2da0f1-94b6-47e4-8ddc-30926266f944.md
?? backend/eval/reports/t617b-c1-golden-v1-forensic-audit.md
?? backend/eval/reports/t617b-c2-deterministic-relevance-abstention.md   (este informe)
?? backend/eval/reports/t617b-d1-pilot005-timeout-diagnosis.md
?? backend/eval/reports/t617b-smoke2-passed.md
?? backend/eval/reports/t617b0-pilot005-directed-retry.md
?? backend/eval/reports/t617b0-pilot005-retry-blocked.md
?? backend/eval/reports/t617c-r1-pilot005-real-validation.md
?? backend/eval/reports/t617c-semantic-claim-labels.md
?? backend/eval/reports/t617c-smoke-passed.md
?? backend/uv.lock
?? docs/... (documentos internos preexistentes, sin cambios)
```

**No hay commit, push ni PR.** Sólo 4 archivos rastreados modificados (2 de producción, 2 de pruebas), los mismos desde R1; todos los archivos previamente no rastreados se preservaron intactos.

## Declaración explícita

No hubo llamadas reales a Gemini, Socrata ni ningún proveedor externo durante este incremento. Toda verificación de comportamiento se realizó con dobles locales en memoria (`DeterministicRuntimeDependencies` con funciones async puras) y con la suite de pruebas de Pytest, sin red. Las únicas operaciones de I/O reales fueron dos consultas de solo lectura a PostgreSQL (con `SET default_transaction_read_only = on`) para releer `quantitative_claims` de corridas ya persistidas anteriormente (T-617B-C1), con el único fin de fundamentar el diagnóstico de la sección 1; no se escribió en la base de datos.

## Bloqueos normativos pendientes (no resueltos aquí)

1. **`pilot-024–027`** (repliegue a evidencia de calidad alta pero temáticamente ajena, con columnas de nombre lexicalmente ambiguo): requiere decisión normativa sobre si autorizar un nuevo metadato de tema/categoría por dataset, un nuevo juicio LLM validable, o aceptar el riesgo residual. No implementado.
2. **Corrida real de validación**: el efecto exacto de este incremento sobre `pilot-044`/`pilot-048` (y potencialmente algunos de `pilot-024–027`, si su clasificación léxica cambia por azar en futuras preguntas) sólo puede confirmarse con una corrida real de golden-v1/golden-v2, no autorizada en este alcance.

## Estado tras revisión R3

Tres rondas de auditoría independiente, tres huecos encontrados y corregidos en la misma ruta diferida (T-615F, `defer_synthesis_until_persisted=True`):

- **R2** (`DEFERRED_SYNTHESIS_BYPASSES_RELEVANCE_GATE`): la rama `PERSIST_FACTS` diferida no consultaba pertinencia en absoluto. Corregido ampliando su condición sin moverla.
- **R3** (`TEXTUAL_REJECTION_MASQUERADES_AS_ACCEPTED_TEXTUAL_FACT`): la señal `textual_result_available` usada por esa misma corrección de R2 confundía rechazos con aceptaciones. Corregido separando las señales en su origen (`deterministic_runtime.py`), sin tocar `deterministic_graph.py`.

Ambos quedaron reproducidos de forma independiente contra baselines intermedios (fallan sin la corrección correspondiente, pasan con ella) y cubiertos por 7 pruebas nuevas específicas de la ruta diferida (11–17), sin duplicar lógica ni mover ramas existentes, preservando en todo momento la persistencia de hechos textuales genuinamente aceptados (T-615F/RF-212) y el comportamiento ya establecido para claims cuantitativos relevantes. Se corrigió además la imprecisión terminológica sobre el alcance de `claim_is_relevant_to_narrative` (riesgo 7). Suite completa final: **1035 passed, 122 deselected**, cero regresiones. Hashes de golden intactos, sin commit.

Me detengo aquí, conforme al encargo: incremento acotado a la abstención determinista por pertinencia (T-617B-C2), completado y probado en ambos modos (inmediato y diferido), incluyendo la coexistencia de hechos aceptados y rechazados dentro de la misma evidencia; sin iniciar `pilot-007`, `expected_facts`, `budget_exceeded`, latencia, ni `golden-v2`. No autorizo yo mismo la siguiente corrida real ni el siguiente incremento — queda a la espera de aprobación.
