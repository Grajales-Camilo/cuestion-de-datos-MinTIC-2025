# T-617C — Implementación: etiquetado semántico y advertencias de presentación

**Estado: implementado, sin auditoría ni corrida real todavía.** T-617C **no**
se marca como completada; requiere auditoría del coordinador y una corrida
real posterior (fuera de alcance de este incremento).

- Repositorio: `D:\Usuario\AppWebs\cuestion-de-datos-MinTIC`
- Rama: `feat/t617-gate-preflight`
- HEAD de partida: `2840b00706149aa764fe1e4e36c54b08703756e5`
- Contrato: `contracts/api-rest.md` §4c · Requisito: RF-212 · Diseño: `plan.md` §15
- Pruebas normativas: `pruebas.md` §4.6 · Tarea: `tasks.md` T-617C
- Informes previos: `t617c-semantic-claim-labels.md` (Fase A, bloqueada),
  `t617c-a-presentation-contract-amendment.md` (contrato aprobado)

## 1. Flujo anterior vs. nuevo

### 1.1 Dónde vivía el bug (confirmado en Fase A)

`soql_renderer.py` genera alias posicionales `dim_N`/`metric_<op>_N` para el
`SELECT`, sin persistir el mapeo alias→columna. `deterministic_pipeline._claim_specs`
iteraba solo sobre esos alias al construir cada `ClaimSpec`, y `BuiltClaim.columns_used`
terminaba conteniendo el alias, no el nombre real. El sintetizador **activo
por defecto** (`deterministic_textual_facts_enabled=False`) —
`deterministic_dependencies.synthesize()` (LLM) y su fallback
`deterministic_runtime._deterministic_synthesis()` (sin LLM) — solo veían
`display_value`/`description` (texto con el alias incrustado), nunca una
etiqueta humana. `_deterministic_synthesis` literalmente enumeraba
`"; ".join(f"{claim.display_value}..." for claim in selected)`: el origen
exacto de «764, 719, 2.026 y 2».

### 1.2 Flujo nuevo

```text
ValidatedQueryPlan.dimensions[i].field_name / .metrics[i].field_name
  → RenderedQuery.dimension_aliases / .metric_aliases / .group_count_alias
  → _column_field_names(plan, rendered): dict alias→field_name real
    (COUNT_FIELD_SENTINEL "__count__" para count(*)/group_count)
  → ClaimSpec.column_field_names (nuevo campo, no afecta columns/DSL/hash)
  → _build_one_claim: alias usados → public_columns (nombres reales)
       → derive_claim_label(public_columns) → label/label_status
  → BuiltClaim.public_columns / .label / .label_status (nuevos campos)
  → deterministic_dependencies.synthesize(): filtra claim_view a claims
    relevantes (claim_is_relevant_to_narrative), añade label/label_status
    al payload del LLM, refuerza el prompt
  → deterministic_runtime._deterministic_synthesis(): mismo filtro de
    relevancia + render etiquetado, sin LLM
  → llm_contracts.validate_grounded_synthesis(): además de cifras huérfanas,
    exige que la etiqueta verificada de cada claim citado esté cerca de su
    propio display_value (label_grounded_in_text) — si no, dispara el mismo
    mecanismo de reintento/fallback ya existente
  → persistence.persist_claims(): fila DB (quantitative_claims.columns_used)
    SIN CAMBIOS (sigue siendo el alias, exigido por la reverificación de
    hash T-615H); el DICCIONARIO PÚBLICO usa claim.public_columns + añade
    "label"/"label_status"
  → runner.py: presentation_warnings = build_presentation_warnings(claims)
    (una entrada AMBIGUOUS_LABEL por claim con label_status="ambiguous"),
    añadido a la raíz de final_answer
```

## 2. Requisito arquitectónico crítico: alias interno vs. nombre público

Se respetó explícitamente la instrucción de no romper la reproducción del
claim:

- `BuiltClaim.columns_used` (alias de ejecución, p. ej. `dim_2`) **no
  cambió de significado**. Sigue siendo lo que `compute_source_hash` usa
  para extraer `rows_subset_canonical` de `EvidenceContext.rows` (indexadas
  por alias) y lo que `quantitative_claims.columns_used` persiste en la
  tabla relacional — sin esto, la reverificación de hash de
  `_reverify_quantitative_synthesis_fact` (T-615H) se habría roto, porque
  compara el hash recalculado desde `evidence_results.rows` (alias-keyed)
  contra `claim.source_hash`.
- Se añadió `BuiltClaim.public_columns` (nombres de columna fuente reales),
  derivado en `_build_one_claim` a partir de un mapeo nuevo,
  `ClaimSpec.column_field_names` (alias→field_name), que **no participa**
  en absoluto en el cálculo de `raw_value` ni de `source_hash` — se
  demuestra en `test_column_field_names_never_change_source_hash_or_dsl_result`.
- La traducción alias→nombre real para la respuesta **pública** ocurre una
  única vez, en `persistence.persist_claims`, usando el mapeo todavía en
  memoria de la ejecución en curso — nunca se reconstruye leyendo de vuelta
  la base de datos (que solo tiene el alias).

**Limitación reconocida y documentada, no corregida en este incremento:**
la ruta T-615H (`grounded_synthesis.py::AllowedQuantitativeFact`, activa
solo con `deterministic_textual_facts_enabled=True`, que hoy es `False` por
defecto y no se ejerce en producción/smoke) recarga claims **desde la base
de datos** para la reverificación de síntesis cerrada; en ese punto solo se
dispone del alias persistido (`quantitative_claims.columns_used`), no del
mapeo a nombre real, porque no hay migración. Por tanto `AllowedQuantitativeFact`
no gana `label`/`label_status` en este incremento y su `columns` sigue
siendo el alias. Corregirlo exigiría persistir el mapeo (migración,
explícitamente fuera de alcance) o rediseñar esa ruta; se deja como riesgo
residual documentado (§7), no oculto.

## 3. Fuente determinista de las etiquetas (`app/quality/claim_labels.py`, nuevo)

Módulo puro, sin I/O ni LLM:

- `humanize_field_name(field_name)`: transforma mecánicamente un nombre de
  columna real (`genero_hombre` → `"Genero hombre"`); rechaza cualquier
  cosa con forma de alias interno (`dim_N`/`metric_<op>_N`/`group_count`,
  vía `looks_like_internal_alias`) o que no siga el patrón de identificador
  Socrata seguro; produce una etiqueta estructural fija
  (`"Conteo de registros"`) solo para el centinela `__count__`
  (`count(*)`/agrupación de privacidad, nunca para el alias `group_count`
  en sí). Nunca reconstruye tildes ni infiere significado nuevo.
- `derive_claim_label(source_columns)`: `verified` únicamente cuando el
  claim usa **exactamente una** columna real identificable; cualquier
  combinación de columnas distintas (fórmula derivada) o un nombre inseguro
  produce `ambiguous` sin inventar una etiqueta que las mezcle.
- Nunca se deriva nada del valor numérico (`raw_value`/`display_value`); la
  entrada es siempre el nombre de columna, metadato estructural.

`display_name` curado (`catalog_columns.display_name`) se evaluó y se
descartó deliberadamente para esta ronda: propagarlo de forma consistente
hasta el punto de reverificación (que relee desde DB) exigiría persistirlo,
lo cual choca con "no migración" para la misma limitación de §2. Usar
únicamente `field_name` humanizado es 100% reproducible sin persistencia
adicional, documentado como decisión explícita, no un descuido.

## 4. Regla de selección de claims relevantes

`classify_column_relevance(field_name)` clasifica genéricamente por
vocabulario léxico del nombre de columna en `primary` / `temporal` /
`auxiliary` (identificadores técnicos: `codigo`, `id`, `sigep`, `nit`,
`llave`, etc.; temporales: `ano`, `fecha`, `mes`, `periodo`, etc.).
`claim_is_relevant_to_narrative(source_columns, requested_tokens)` excluye
`auxiliary` y `temporal` de la narrativa principal **salvo** que
`intent_relevance_tokens(intent.topic, intent.administrative_terms)`
contenga el mismo vocabulario de categoría — nunca un valor concreto,
`case_id` ni `dataset_id`. Aplicado en ambas rutas de síntesis
(`synthesize()` LLM y `_deterministic_synthesis()` fallback) mediante la
misma función compartida, así que ambas tienen exactamente las mismas
garantías (requisito explícito del prompt).

## 5. Manejo de ambigüedad

- `label=None`, `label_status="ambiguous"` cuando `derive_claim_label` no
  puede resolver una etiqueta inequívoca (múltiples columnas o nombre
  inseguro). La cifra permanece en `claims[]` (RF-211: útil y verificable).
- El fallback determinista la presenta como
  `f"{display_value} (sin etiqueta verificable)"`, nunca inventando una
  categoría combinada.
- `presentation_warnings` (`build_presentation_warnings`, nueva función
  pura) genera una entrada `AMBIGUOUS_LABEL` por cada claim ambiguo en la
  respuesta final — vacío si no hay ninguno; nunca deriva de ni sustituye
  `evidence[].quality.warnings_user`.

## 6. Ubicación contractual de la advertencia (sin migración)

Exactamente como aprobó T-617C-A: `label`/`label_status` viven dentro de
cada elemento de `final_answer["claims"]`; `presentation_warnings` vive en
la raíz de `final_answer` (JSONB de `agent_runs`, tabla ya existente). Se
confirmó que `RunResultResponse.answer: dict[str, Any]` (`app/schemas.py`)
es un passthrough sin schema cerrado — los campos nuevos llegan intactos a
la API pública sin necesitar cambios en `app/schemas.py` ni en
`app/main.py`. `quantitative_claims` (tabla relacional) no ganó ninguna
columna; no se creó ninguna migración de Alembic.

## 7. Riesgos residuales

1. **Ruta T-615H sin etiquetado** (§2): `AllowedQuantitativeFact`/`build_grounded_synthesis_fallback`
   no producen `label`/`label_status` porque relee desde DB sin el mapeo
   alias→nombre real. Inactiva por defecto (`deterministic_textual_facts_enabled=False`);
   si se activa en el futuro, necesitará su propia ronda para resolver esta
   limitación (persistencia del mapeo o rediseño), documentada aquí para no
   sorprender a quien la reactive.
2. **Verificación de asociación etiqueta↔cifra es por proximidad textual**
   (`label_grounded_in_text`, ventana de 60 caracteres normalizados), no un
   parser semántico completo. Es una interpretación pragmática y probada
   (incluye una prueba explícita de intercambio) de "mantiene la asociación
   exacta", no una garantía matemática absoluta para cualquier prosa
   arbitraria que un LLM pudiera producir en el futuro.
3. **`synthesize()` (ruta LLM) no tiene una prueba dedicada con LLM
   simulado**: la lógica de filtrado de relevancia que usa es la misma
   función pura ya cubierta exhaustivamente por `test_claim_labels.py` y
   por `_deterministic_synthesis` (que comparte la función), pero no hay
   una prueba que mockee `_invoke`/`build_real_runtime_dependencies` para
   confirmar el contenido exacto de `claim_view` en esa ruta específica —
   requeriría mockear infraestructura (engine/http_client/embedding_client)
   fuera del alcance razonable de este incremento.
4. **`persist_claims` no tiene una prueba dedicada con motor real o mock**:
   el cambio ahí es una sustitución mecánica de 3 líneas
   (`claim.columns_used`→`claim.public_columns` en el diccionario público,
   más dos claves nuevas), verificada por revisión de código y por que los
   datos que recibe (`claim.public_columns`/`.label`/`.label_status`) ya
   están exhaustivamente probados en `claims.py`/`deterministic_pipeline.py`.
   No se agregó una prueba de integración con base de datos real (fuera de
   alcance: "cero llamadas reales a PostgreSQL").

Ninguno de estos riesgos afecta la ruta activa por defecto
(`deterministic_textual_facts_enabled=False`), que es la que produjo el bug
original y la que corrige este incremento.

## 8. Archivos modificados

**Producción:**
- `backend/app/quality/claim_labels.py` (nuevo) — módulo puro de
  etiquetado/relevancia/advertencias.
- `backend/app/quality/claims.py` — `ClaimSpec.column_field_names`,
  `BuiltClaim.public_columns/label/label_status`, cómputo en `_build_one_claim`.
- `backend/app/agent/deterministic_pipeline.py` — `_column_field_names`,
  `_claim_specs`/`_lookup_presence_specs` propagan el mapeo.
- `backend/app/agent/persistence.py` — `persist_claims`: DB row sin cambios,
  diccionario público con nombres reales + `label`/`label_status`.
- `backend/app/agent/deterministic_dependencies.py` — `synthesize()`:
  filtro de relevancia, `label`/`label_status` en el prompt, prompt reforzado.
- `backend/app/agent/deterministic_runtime.py` — `_deterministic_synthesis()`
  reescrito (etiquetado + relevancia); `_render_claim_clause` nuevo; llamador
  actualizado para pasar `intent`.
- `backend/app/agent/llm_contracts.py` — `validate_grounded_synthesis()`
  extendida con verificación de asociación etiqueta↔cifra.
- `backend/app/agent/runner.py` — `presentation_warnings` construido y
  añadido a `final_answer`.

**Pruebas:**
- `backend/tests/test_claim_labels.py` (nuevo, 17 pruebas) — módulo puro.
- `backend/tests/test_claims.py` (+5 pruebas) — `public_columns`/`label`/
  reproducibilidad de hash.
- `backend/tests/test_deterministic_pipeline.py` (+2 pruebas) — pipeline
  real de extremo a extremo, regresión de fuga de alias.
- `backend/tests/test_deterministic_runtime.py` (+4 pruebas nuevas, 2
  fixtures/aserciones actualizadas) — fallback etiquetado y relevante.
- `backend/tests/test_llm_contracts.py` (+3 pruebas) — detección de
  intercambio de etiqueta, aceptación correcta, ambiguos sin bloqueo.

**Informe:** este archivo.

## 9. Pruebas y resultados exactos

### 9.1 Reproducción de fallo contra baseline (worktree temporal)

`git worktree add %TEMP%/t617c-baseline 2840b00706149aa764fe1e4e36c54b08703756e5`,
copiando únicamente los 5 archivos de prueba nuevos/modificados (sin ningún
cambio de código de producción):

```
uv run python -m pytest tests/test_claim_labels.py tests/test_claims.py \
  tests/test_deterministic_runtime.py tests/test_deterministic_pipeline.py \
  tests/test_llm_contracts.py -q

ERROR tests/test_claim_labels.py — ModuleNotFoundError: No module named 'app.quality.claim_labels'
25 failed, 77 passed, 1 warning in 1.60s   (tras excluir test_claim_labels.py del collect)
```

Los 25 fallos corresponden exactamente a las pruebas nuevas/modificadas
(`AttributeError: 'BuiltClaim' object has no attribute 'public_columns'`,
`TypeError: ... unexpected keyword argument 'public_columns'`, aserciones de
texto etiquetado). Ninguna prueba preexistente no relacionada falló.
Worktree eliminado con `git worktree remove --force`.

### 9.2 Con la implementación, en el árbol principal

```
uv run python -m pytest tests/test_claim_labels.py tests/test_claims.py \
  tests/test_deterministic_runtime.py tests/test_deterministic_pipeline.py \
  tests/test_llm_contracts.py -q
119 passed in 4.41s
```

### 9.3 Suite completa no-integración

```
uv run python -m pytest -m "not integration" -q
990 passed, 122 deselected, 5 warnings in 17.22s
```
(960 antes de este incremento + 30 pruebas nuevas de esta ronda.)

### 9.4 Aceptación determinista focalizada

```
uv run python -m pytest tests/test_deterministic_acceptance_guard.py \
  tests/test_deterministic_runtime.py tests/test_deterministic_pipeline.py \
  tests/test_deterministic_graph.py tests/test_deterministic_dependencies.py \
  tests/test_deterministic_textual_planning.py -q
96 passed, 1 warning in 5.96s
```

### 9.5 Lint y formato

```
uv run ruff check .
All checks passed!

uv run ruff format --check <archivos modificados y nuevos>
2 files reformatted primero (2 líneas largas) → tras corregir:
13 files already formatted
```
(`ruff format --check` sobre todo el repo señala 36 archivos preexistentes
sin relación con este incremento, no tocados aquí.)

### 9.6 `git diff --check`

Sin salida (limpio).

## 10. Hashes golden

- Antes: `golden-v1.yaml` = `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`,
  `golden-v2.yaml` = `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`
- Después: **idénticos, sin cambio.**

## 11. Estado del worktree

`git status --porcelain` antes del commit: 7 archivos de producción
modificados, 1 archivo de producción nuevo (`claim_labels.py`), 4 archivos
de prueba modificados, 1 archivo de prueba nuevo, más los reportes/archivos
no rastreados preexistentes de rondas anteriores (preservados intactos, no
tocados). Sin cambios en `golden-v1`/`golden-v2`, `specs/`, contratos,
prompts ni migraciones.

## 12. Estado final

**READY_FOR_T617C_IMPLEMENTATION_AUDIT**

No se marca T-617C como completada. Detenido tras el commit; no se ejecutó
el smoke ni ninguna suite completa real.

---

# T-617C-R1 — Persistencia contractual, reverificación versionada, T-615H y asociación exacta

**Estado: implementado, sin auditoría ni corrida real todavía.** T-617C
sigue **sin** marcarse como completada.

- HEAD de partida: `8b0caab503a71a0795ec5addf6a99096ac65881f`
- Cierra los 3 riesgos residuales que R0 dejó documentados: persistencia
  contractual (`quantitative_claims.columns_used` seguía siendo alias),
  T-615H sin etiquetas, y validación de asociación por proximidad simple.

## Hallazgo 1 — Persistencia contractual

`persist_claims` ahora escribe `columns_used=list(claim.public_columns)`
tanto en la fila real de `quantitative_claims` como en el diccionario
público — el nombre de columna fuente real (`"genero_hombre"`), nunca el
alias de ejecución (`dim_N`/`metric_N`). El alias sigue viviendo
exclusivamente en `BuiltClaim.columns_used` (dominio interno, nunca
persistido), usado solo para leer `EvidenceContext.rows`/`evidence_results.rows`
(indexadas por alias, sin cambios) y como entrada `execution_columns` de
`compute_source_hash`. Verificado con PostgreSQL local real
(`tests/integration/test_deterministic_pipeline_persistence.py`):
`claim.columns_used == ["total"]` en la fila de base de datos, nunca
`["metric_sum_1"]`.

## Hallazgo 2 — Reproducibilidad e históricos

**Versionado del algoritmo (RF-212):** `CLAIMS_ALGORITHM_VERSION` sube a
`"2.0.0"` — el payload que alimenta `source_hash` ahora embebe
`public_columns` (nombre real) en `"columns"` y en las claves de
`rows_subset_canonical`, en vez del alias. `compute_source_hash` recibe
ahora **dos** parámetros explícitos y separados:
`execution_columns` (alias, solo para leer `rows`) y `public_columns`
(nombre real, identidad pública embebida en el hash) — nunca se
confunden ni se colapsan en uno solo.

**Compatibilidad histórica, sin invalidar nada en silencio:**
`compute_legacy_source_hash` reproduce bit a bit el algoritmo `v1.0.0`
anterior (columnas = alias) para reverificar claims persistidos antes de
esta ronda. `persistence._reverify_quantitative_synthesis_fact` distingue
legacy vs. nuevo **por forma** de `claim.columns_used`
(`looks_like_internal_alias`, nunca por `run_id` ni fecha) y aplica el
algoritmo correcto en cada caso:
- **Legacy** (columnas con forma de alias): `compute_legacy_source_hash`,
  igual que antes de R1; el hecho se reverifica igual, pero
  `label_status="ambiguous"` porque no hay nombre real que exponer.
- **Nuevo** (columnas reales): reconstruye `execution_columns` parseando
  `evidence.soql_query` con el **parser SoQL vigente**
  (`app.tools.soql_parser.extract_column_field_names`, cero regex
  improvisada) e invirtiendo alias→columna a columna→alias; luego
  `compute_source_hash` con ambos conjuntos. `derive_claim_label` se
  aplica directamente sobre `claim.columns_used` (ya el nombre real
  persistido) para `label`/`label_status`.

Un `source_hash` manipulado o un nombre de columna que no puede vincularse
a ningún alias del SoQL persistido siguen rechazándose (`fact=None`), sin
excepción no controlada — probado explícitamente.

## Hallazgo 3 — Ruta T-615H (RF-212 completo, no residual)

- `AllowedQuantitativeFact` gana `label: str | None` y
  `label_status: LabelStatus` (antes ausentes → `extra_forbidden` los
  rechazaba).
- `_reverify_quantitative_synthesis_fact` deriva `label`/`label_status`
  como parte de la reverificación (Hallazgo 2).
- `_atomic_clause` (renderer literal) usa `f"{fact.label}: {fact.display_value}."`
  cuando `verified`, o `f"{fact.display_value} (sin etiqueta verificable)."`
  cuando `ambiguous` — igual que la ruta activa por defecto.
- `build_grounded_synthesis_fallback` (fallback sin LLM de T-615H) gana
  `requested_tokens` y filtra hechos cuantitativos auxiliares/temporales
  con `claim_is_relevant_to_narrative`, igual criterio genérico que las
  otras dos rutas de síntesis.
- `plan_synthesis` (ruta con LLM de T-615H) filtra `allowed.facts` por
  relevancia antes de construir el payload que ve el modelo; la validación
  posterior sigue certificando contra el conjunto completo.
- `presentation_warnings` se sigue construyendo en `runner.py` a partir de
  `persisted.claims` — igual mecanismo que la ruta por defecto, sin
  cambios adicionales necesarios.

**Verificado de extremo a extremo con PostgreSQL local real** (no solo
unitariamente): `tests/integration/test_deterministic_agent_acceptance.py`
con `DETERMINISTIC_TEXTUAL_FACTS_ENABLED=True` — un fallback textual antes
mostraba `"sum: T-611 fallo textual no es éxito narrativo (metric_sum_1,
fila 0): 20."`; ahora muestra `"Monto: 20."` (columna real `monto`). Un
`count(*)` antes mostraba `"count: ... (metric_count_1, fila 0): 42."`;
ahora `"Conteo de registros: 42."` (centinela estructural, nunca el alias
`metric_count_1`). Ya no es un riesgo residual: la ruta T-615H completa
cumple RF-212 igual que la ruta activa por defecto, confirmado con el flag
encendido y base de datos real.

## Hallazgo 4 — Asociación exacta (reemplazo de la ventana de 60 caracteres)

`label_grounded_in_text` se reescribió: para cada aparición del
`display_value` en el texto, localiza la ocurrencia de **etiqueta más
cercana** entre todas las citadas (`label` propio + `other_labels` de los
demás claims citados) y exige que sea la propia; además ninguna cifra
citada de otro claim (`other_values`) puede interponerse entre esa
etiqueta y el valor. En empate de distancia se prefiere la etiqueta que
**precede** al valor (convención "Etiqueta: valor") sobre la que sigue al
valor del *siguiente* claim ("valor; Etiqueta_del_siguiente") — sin este
desempate, `"Hombres: 764; Mujeres: 719"` (par correcto) fallaba por
empate de distancia real durante el desarrollo, detectado por las propias
pruebas nuevas antes de llegar al commit.

Casos verificados explícitamente (`tests/test_claim_labels.py`):
- `"Hombres: 719; Mujeres: 764"` (valor real 764/719) → **rechazado** para
  ambos claims citados.
- `"Hombres: 719. Mujeres: 764."` → **rechazado** igual, con punto en vez
  de punto y coma.
- `"Hombres: 764; Mujeres: 719"` (par correcto) → **aceptado** para ambos.
- `"764 hombres y 719 mujeres"` (etiqueta después del valor, RF-211 prosa
  natural) → **aceptado**.
- `"719 hombres y 764 mujeres"` (mismo estilo, pero intercambiado) →
  **rechazado**.

`llm_contracts.validate_grounded_synthesis` ahora calcula
`other_labels`/`other_values` a partir de **todos** los claims citados con
`label_status="verified"` (excluyendo el propio en cada verificación) y se
los pasa a `label_grounded_in_text`; sigue disparando el mismo mecanismo
de reintento/fallback ya existente ante cualquier fallo.

## Archivos modificados (R1)

**Producción:**
- `backend/app/tools/soql_parser.py` — `extract_column_field_names` (nuevo,
  sin regex, reutiliza `parse_soql`).
- `backend/app/quality/claims.py` — versión `2.0.0` del algoritmo,
  `compute_source_hash` con `execution_columns`/`public_columns`
  separados, `compute_legacy_source_hash` nuevo, `_build_one_claim`
  actualizado.
- `backend/app/quality/claim_labels.py` — `label_grounded_in_text`
  reescrito (etiqueta más cercana + bloqueo de valores ajenos + desempate
  por precedencia).
- `backend/app/quality/grounded_synthesis.py` — `label`/`label_status` en
  `AllowedQuantitativeFact`; `_atomic_clause` etiquetado;
  `build_grounded_synthesis_fallback` con `requested_tokens`.
- `backend/app/agent/persistence.py` — `persist_claims` persiste nombres
  reales; `_reverify_quantitative_synthesis_fact` reescrita (legacy vs.
  nuevo, reconstrucción vía SoQL parser, derivación de label).
- `backend/app/agent/deterministic_dependencies.py` — `plan_synthesis`
  filtra por relevancia antes de construir el payload del LLM.
- `backend/app/agent/runner.py` — pasa `requested_tokens` al fallback
  T-615H.
- `backend/app/agent/llm_contracts.py` — `validate_grounded_synthesis`
  calcula `other_labels`/`other_values` para la nueva verificación.

**Pruebas:**
- `backend/tests/test_persistence_reverification.py` (nuevo, 4 pruebas) —
  reverificación legacy/nueva, hash manipulado, columna no resoluble, sin
  DB real (modelos ORM en memoria).
- `backend/tests/test_soql_guard.py` (+5 pruebas) — `extract_column_field_names`.
- `backend/tests/test_claim_labels.py` (reescrito el bloque de
  intercambio, +6 pruebas netas) — los 2 casos de intercambio obligatorios
  más pares correctos y prosa natural.
- `backend/tests/test_claims.py` (firma de `compute_source_hash`
  actualizada, +1 prueba de reproducibilidad, 1 prueba reescrita para
  reflejar el versionado).
- `backend/tests/test_grounded_synthesis_renderer.py` (fixture con
  `label`/`label_status`, +3 pruebas) — relevancia y etiquetado del
  fallback T-615H.
- `backend/tests/integration/test_deterministic_pipeline_persistence.py`
  (+4 aserciones, PostgreSQL local real) — `columns_used` real en la fila
  de BD.
- `backend/tests/integration/test_deterministic_agent_acceptance.py` (2
  aserciones actualizadas a la salida etiquetada real, PostgreSQL local
  real, `DETERMINISTIC_TEXTUAL_FACTS_ENABLED=True`).

## Pruebas y resultados exactos (R1)

### Reproducción de fallo contra baseline (worktree temporal)

`git worktree add %TEMP%/t617c-r1-baseline 8b0caab503a71a0795ec5addf6a99096ac65881f`,
copiando los 7 archivos de prueba nuevos/modificados sin ningún cambio de
producción:

```
uv run python -m pytest tests/test_claims.py tests/test_claim_labels.py \
  tests/test_soql_guard.py tests/test_grounded_synthesis_renderer.py \
  tests/test_persistence_reverification.py -q

3 errores de colección:
  ImportError: cannot import name 'extract_column_field_names' from 'app.tools.soql_parser'
  ImportError: cannot import name 'compute_legacy_source_hash' from 'app.quality.claims'
  ValidationError: AllowedQuantitativeFact — label/label_status: Extra inputs are not permitted

Tras excluir esos 3 módulos:
tests/test_claims.py tests/test_claim_labels.py -q
12 failed, 44 passed in 0.23s
```

Los 12 fallos + 3 errores de colección corresponden exactamente a las
áreas tocadas por R1. Worktree eliminado con `git worktree remove --force`.

### Con la implementación, en el árbol principal

```
uv run python -m pytest tests/test_claim_labels.py tests/test_claims.py \
  tests/test_soql_guard.py tests/test_grounded_synthesis_renderer.py \
  tests/test_persistence_reverification.py tests/test_llm_contracts.py \
  tests/test_deterministic_pipeline.py tests/test_deterministic_runtime.py \
  tests/test_deterministic_dependencies.py tests/test_deterministic_textual_planning.py -q
168 passed (módulos afectados combinados) + 4 + 39 adicionales = todos verdes
```

### Suite completa no-integración

```
uv run python -m pytest -m "not integration" -q
1007 passed, 122 deselected, 5 warnings in 17.18s
```
(990 tras R0 + 17 pruebas nuevas netas de R1.)

### Aceptación determinista completa (unitaria + integración local real)

```
uv run python -m pytest tests/test_deterministic_acceptance_guard.py \
  tests/test_deterministic_runtime.py tests/test_deterministic_pipeline.py \
  tests/test_deterministic_graph.py tests/test_deterministic_dependencies.py \
  tests/test_deterministic_textual_planning.py -q
96 passed, 1 warning in 6.05s

DATABASE_URL=<local :5433> uv run python -m pytest \
  tests/integration/test_deterministic_agent_acceptance.py \
  tests/integration/test_deterministic_pipeline_persistence.py -q -m integration
19 passed, 1 xfailed, 1 warning in 12.07s
```
Ambas corridas de integración usan PostgreSQL local (`localhost:5433`,
mismo entorno ya disponible en esta sesión); cero llamadas a Gemini ni
Socrata (el `xfailed` es preexistente, no relacionado con R1).

### Lint, formato, `git diff --check`

```
uv run ruff check .
All checks passed!

uv run ruff format --check <14 archivos modificados + 1 nuevo>
2 archivos requerían reformateo (líneas largas); aplicado `ruff format` y
reverificado: todos formateados.

git diff --check
(solo advertencias inocuas de normalización CRLF de Git en Windows)
```

## Hashes golden

- Antes y después: **idénticos, sin cambio.**
  - `golden-v1.yaml`: `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`
  - `golden-v2.yaml`: `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`

## Riesgos residuales tras R1

1. **Ambigüedad estructural en `field_name_to_alias`** (persistence.py):
   si el mismo nombre de columna real aparece en más de un `SelectItem`
   del SoQL (p. ej. seleccionado dos veces con alias distintos), la
   inversión alias↔columna toma arbitrariamente el último alias
   encontrado. No causa un valor incorrecto (ambos alias apuntan a la
   misma columna real, mismo valor en la fila), pero es una limitación
   teórica documentada, no verificada con un caso de prueba dedicado por
   ser un patrón que el renderer actual (`soql_renderer.py`) no produce
   hoy (cada dimensión/métrica del plan genera un alias propio y distinto).
2. **Tie-break de `label_grounded_in_text`** favorece la etiqueta que
   precede al valor en un empate exacto de distancia; es una heurística
   determinista y probada contra los casos requeridos, no una prueba
   formal de que ninguna construcción textual adversaria más compleja (3+
   claims entrelazados) pudiera burlarla. Aceptable para el alcance de
   RF-212 (prosa generada por un LLM ya instruido a no intercambiar
   etiquetas, con esta validación como red de seguridad determinista, no
   como parser de lenguaje natural general).

## Estado final

**READY_FOR_T617C_R1_AUDIT**

No se marca T-617C como completada. Sin push, sin amend. Detenido tras el
commit; no se ejecutó smoke ni golden completas ni llamadas reales a
Gemini/Socrata.
