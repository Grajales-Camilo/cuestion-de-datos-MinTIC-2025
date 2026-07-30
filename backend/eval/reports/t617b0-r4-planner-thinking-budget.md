# T-617B0-R4 — Presupuesto acotado de razonamiento del planificador Gemini

**Actividad:** T-617B0-R4 (implementación mínima, autorizada). **No** ejecuta
Gemini, Socrata ni PostgreSQL real. **No** modifica golden-v1/v2, contratos
normativos, cardinalidades ni umbrales. **No** marca T-617 como terminada.
**Gobierna:** `research.md` §25, `plan.md` §13, `pruebas.md` §4.4,
`tasks.md` T-610…T-617. Documento **no normativo**.
**Fecha:** 2026-07-19, America/Bogota (UTC-5).
**Baseline:** rama `feat/t617-gate-preflight`, HEAD
`e493e447a5101b8ca4f0627f45c514a091a66724`.

---

## 1. Causa y evidencia que motiva el cambio

Diagnóstico previo: `backend/eval/reports/t617b-d1-pilot005-timeout-diagnosis.md`
(T-617B-D1, `T617B_TIMEOUT_HYPOTHESIS_BOUNDED`). El mecanismo del fallo
reproducible de `pilot-005-empleo-publico` en `build_plan` quedó confirmado
por aritmética exacta: `timeout=30` × 2 intentos + 2 s de espera fija
(`langchain-google-genai`, `stop_after_attempt(2)` +
`wait_exponential(multiplier=2.0, min=1.0)`) reproduce sin residuo el patrón
de ~65 s observado en dos smokes reales independientes
(`agent_run 235466d2-…`, `agent_run 50b38f20-…`).

Evidencia adicional aportada para este incremento (fuera de este repositorio,
comunicada por el responsable del proyecto; **no** se ejecutó ninguna llamada
real durante T-617B0-R4 para producirla ni para verificarla):

| Configuración | Llamada | Latencia observada | Resultado |
|---|---|---|---|
| Sin `thinking_budget` | Prueba mínima de disponibilidad del modelo (sin el payload real de `build_plan`) | 1.418 s | — |
| Sin `thinking_budget` | `build_plan` real de `pilot-005`, 3 intentos | ~65 s cada uno | 504 `LLM_PROVIDER_ERROR` |
| `thinking_budget=1024` | `build_plan` real | 5.17 s | Salida estructurada **inválida** |
| `thinking_budget=4096` | `build_plan` real | 2.899 s | Salida estructurada **válida** |

**Corrección T-617B0-R4A:** los 1.418 s corresponden a una prueba mínima de
disponibilidad del modelo (sin el payload real de `build_plan`), **no** a una
llamada `build_plan`; una versión anterior de este informe los presentaba sin
esa distinción.

**Advertencia registrada explícitamente:** el rechazo `max` frente a `lookup`
observado en el arnés aislado usado para producir esa evidencia **no es
concluyente**, porque ese arnés omitió `normalize_system_owned_operation`
(`app/agent/llm_contracts.py:276`), que el runtime productivo aplica
**siempre**, inmediatamente después de `dependencies.plan(...)`
(`app/agent/deterministic_runtime.py:463`, nodo `BUILD_PLAN`) y antes de
cualquier otra normalización/materialización/validación. Este incremento
**no** cambia esa llamada ni su ubicación; ver §4.

---

## 2. Alcance exacto

### 2.1 Implementado

- `backend/app/agent/deterministic_dependencies.py`:
  - Nueva constante de módulo `PLANNER_THINKING_BUDGET_TOKENS = 4096`.
  - `_model()` gana un parámetro `thinking_budget: int | None = None`
    (keyword-only). Solo se agrega a los kwargs del modelo cuando
    `thinking_budget is not None` **y** `settings.llm_provider == "google"`
    — separación explícita por proveedor, verificable por lectura directa
    del código (una única condición, sin ramas ocultas). **Corregido en
    T-617B0-R4A (§10):** además de por proveedor, la condición se acota por
    modelo exacto (`settings.llm_model == "gemini-2.5-flash"`), porque la
    evidencia de la tabla de §1 se produjo específicamente contra ese
    modelo.
  - `timeout=30` y `max_retries=2` permanecen **hardcodeados sin cambios**,
    para las 4 llamadas y ambos proveedores.
  - Solo la construcción de `planner_model` pasa
    `thinking_budget=PLANNER_THINKING_BUDGET_TOKENS`. `intent_model`,
    `synthesis_model` y `synthesis_plan_model` se construyen exactamente
    igual que antes (sin el kwarg, por lo que su valor por defecto es
    `None` y no se agrega nada a la llamada real).

### 2.2 Explícitamente NO tocado

- `backend/app/agent/llm_contracts.py` (schemas, `normalize_system_owned_operation`).
- `backend/app/agent/deterministic_runtime.py` (orden de normalización tras
  `dependencies.plan`).
- `backend/app/llm/factory.py` (`get_chat_model`/`get_structured_chat_model`
  siguen siendo agnósticos de proveedor y de `thinking_budget`; el kwarg
  fluye igual que cualquier otro `**kwargs`, sin lógica nueva ahí).
- Prompts, cardinalidades, umbrales normativos, `golden-v1.yaml`,
  `golden-v2.yaml`, contratos (`contracts/`), `specs/**`.
- Ninguna condición por `case_id`, `dataset_id` ni texto de la pregunta:
  `PLANNER_THINKING_BUDGET_TOKENS` es una constante de módulo aplicada
  siempre que se construye el planificador, para **todos** los casos.

---

## 3. Comportamiento por proveedor y por rol del modelo

| Rol | Schema (según `deterministic_textual_facts_enabled`) | Proveedor `google` | Proveedor `anthropic` | `timeout` | `max_retries` |
|---|---|---|---|---:|---:|
| `intent_model` | `IntentExtraction` | sin `thinking_budget` | sin `thinking_budget` | 30 | 2 |
| `planner_model` | `QuantitativePlanSelection` (flag off) / `EnumeratedPlanSelection` (flag on) | **`thinking_budget=4096`** | sin `thinking_budget` | 30 | 2 |
| `synthesis_model` | `GroundedSynthesis` | sin `thinking_budget` | sin `thinking_budget` | 30 | 2 |
| `synthesis_plan_model` | `GroundedSynthesisPlan` (solo si flag on) | sin `thinking_budget` | sin `thinking_budget` | 30 | 2 |

`thinking_budget` es un campo propio de `ChatGoogleGenerativeAI`
(`langchain_google_genai._common`, `Optional[int]`, tokens); `ChatAnthropic`
no lo expone (`hasattr(chat_anthropic_instance, "thinking_budget") is False`)
— la condición `settings.llm_provider == "google"` en `_model()` es necesaria
y suficiente para que nunca se envíe a Anthropic. **Corregido en T-617B0-R4A
(§10):** la tabla de arriba refleja el estado tras R4; desde R4A, la columna
"Proveedor `google`" del rol `planner_model` solo aplica
`thinking_budget=4096` cuando el modelo efectivo es exactamente
`gemini-2.5-flash` — otro modelo Google queda sin `thinking_budget`, igual
que Anthropic.

---

## 4. `normalize_system_owned_operation` — confirmación sin duplicar cobertura

`app/agent/deterministic_runtime.py:454-463` (nodo `BUILD_PLAN`, sin cambios
en este incremento):

```python
if transition.node is SupervisorNode.BUILD_PLAN:
    assert profile is not None
    selection = await dependencies.plan(
        intent, profile.context, explored, validation_error,
    )
    llm_calls += 1
    selection = normalize_system_owned_operation(selection, intent)
    selection = normalize_budget_snapshot(...)
    ...
```

`dependencies.plan` es exactamente la función que invoca `planner_model`
(construido con `thinking_budget=4096` desde este incremento). La llamada a
`normalize_system_owned_operation` es **incondicional**, inmediatamente
posterior, y **antes** de cualquier otra normalización/materialización. No se
duplica cobertura: la normalización en sí ya tiene prueba unitaria directa en
`tests/test_llm_contracts.py::test_count_operation_is_owned_by_system_and_always_becomes_count_star`
y `::test_lookup_preserves_metric_columns_as_enumerated_output_dimensions`; el
punto de integración (que se invoque tras cada `dependencies.plan` real) lo
ejercita implícitamente cualquier prueba de `tests/test_deterministic_runtime.py`
que alcance `BUILD_PLAN` — no está detrás de ninguna rama que este incremento
module. Referenciado, no duplicado, en
`tests/test_deterministic_dependencies.py` (comentario junto a las pruebas
nuevas).

---

## 5. Pruebas ejecutadas y resultados exactos

Todas deterministas, con dobles y/o claves falsas (`"fake-google-key"`,
`"fake-anthropic-key"`), `Settings(_env_file=None, ...)` (aísla del `.env`
real) — **cero llamadas de red**, cero uso de `GOOGLE_API_KEY`/
`ANTHROPIC_API_KEY` reales.

Nuevas en `tests/test_deterministic_dependencies.py`:

1. `test_only_planner_receives_thinking_budget_with_correct_schema`
   (parametrizada `textual_facts_enabled=False/True`) — requisitos 1, 2, 5, 6.
2. `test_model_signature_has_no_case_or_dataset_specific_parameter` —
   requisito 6 (estructural: `inspect.signature(_model)` solo tiene
   `settings`, `schema`, `thinking_budget`).
3. `test_planner_thinking_budget_reaches_google_model_without_changing_timeout`
   — requisitos 1 y 4, con `ChatGoogleGenerativeAI` real (clave falsa, sin
   red) inspeccionado vía `structured.first.steps__["raw"].bound`.
4. `test_thinking_budget_never_reaches_anthropic_model` — requisito 3, con
   `ChatAnthropic` real (clave falsa, sin red).
5. `test_intent_and_synthesis_models_have_no_thinking_budget_by_default` —
   requisito 2, complementaria a la 1 a nivel de `_model()` directo.

Actualizada (no rota, ajuste de firma):
`test_feature_flag_changes_the_llm_schema_itself` — su `fake_model` ahora
acepta `thinking_budget=None` para seguir siendo compatible con el nuevo
call-site del planificador.

### 5.1 Resultados

```
pytest tests/test_deterministic_dependencies.py tests/test_deterministic_runtime.py \
  tests/test_llm_factory.py tests/test_llm_contracts.py tests/test_settings.py -q
```
→ **91 passed**, 0 fallos.

```
pytest -m "not integration" -q
```
→ **947 passed, 122 deselected**, 0 fallos.

```
pytest -m deterministic_agent_acceptance -q
```
(PostgreSQL local, sin LLM real) → **18 passed, 1 xfailed** (el
`xfail(strict=True)` preexistente del octavo candidato, documentado en
T-615/T-617A, no relacionado con este cambio).

```
ruff check .
```
→ **All checks passed!**

```
ruff format --check app/agent/deterministic_dependencies.py tests/test_deterministic_dependencies.py
```
→ limpio tras un reformateo automático de ambos archivos (líneas largas,
sin cambio semántico).

```
git diff --check
```
→ limpio (exit 0).

### 5.2 Prueba fallo→pasa contra el baseline

Worktree temporal en `e493e447a5101b8ca4f0627f45c514a091a66724`
(`git worktree add`/`git worktree remove --force`, sin afectar este
worktree), copiando únicamente `tests/test_deterministic_dependencies.py`:

```
ImportError while importing test module 'tests/test_deterministic_dependencies.py'.
ImportError: cannot import name 'PLANNER_THINKING_BUDGET_TOKENS' from
'app.agent.deterministic_dependencies'
1 error during collection
```

Las 6 pruebas (5 nuevas + la actualizada) fallan contra el baseline (fallo de
colección, ya que `PLANNER_THINKING_BUDGET_TOKENS`/el parámetro
`thinking_budget` de `_model` no existían) y pasan con la implementación de
este incremento.

---

## 6. Confirmación de cero llamadas reales

- Ninguna prueba invoca red: `ChatGoogleGenerativeAI`/`ChatAnthropic` se
  construyen con claves falsas (`"fake-google-key"`/`"fake-anthropic-key"`),
  y ninguna prueba invoca `.invoke`/`.ainvoke`/`with_structured_output(...).invoke`
  — solo se inspeccionan los atributos del objeto ya construido
  (`thinking_budget`, `timeout`, `max_retries`).
- `pytest -m deterministic_agent_acceptance` usa PostgreSQL local
  (`localhost:5433`) con dobles/fixtures de LLM ya establecidos por la suite
  existente (sin cambios en esta área); no se tocó ni se ejecutó Socrata
  real.
- No se ejecutó `eval.run`, ningún smoke, golden-v1, golden-v2 ni aceptación
  legacy en este incremento.

---

## 7. Hashes golden (antes y después, idénticos)

```
golden-v1: ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72
golden-v2: 1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483
```

Verificados antes de iniciar el incremento y de nuevo antes de cerrar este
informe: sin cambios.

---

## 8. Limitación pendiente

**Solo una corrida real posterior podrá confirmar calidad y latencia
extremo a extremo.** Este incremento demuestra, con evidencia de código y
pruebas deterministas, que la configuración se aplica correctamente (al
planificador Google únicamente, sin afectar timeout/max_retries ni a
Anthropic, sin excepciones por caso). **No** demuestra por sí mismo que
`thinking_budget=4096` evite el 504 observado en producción real contra
Gemini, ni que la salida estructurada del planificador siga siendo válida
extremo a extremo (incluyendo `normalize_system_owned_operation` y el resto
del pipeline de validación) con tráfico real. Esa confirmación requiere una
corrida real autorizada por separado (T-617B0-R4 no la ejecuta ni la
autoriza).

---

## 9. Verificación final del worktree

`git status --short` (antes y después de este incremento, fuera de los
archivos propios listados en el commit): solo los mismos archivos no
rastreados preexistentes, más este informe y los reportes reales generados
por tareas previas ya archivados. Sin cambios en `backend/app/agent/**` más
allá de `deterministic_dependencies.py`; sin cambios en `specs/**` salvo la
nota operativa añadida a `tasks.md` bajo T-617 (no marca la tarea cerrada);
sin push ni PR.

---

## 10. Corrección T-617B0-R4A — acotado a `gemini-2.5-flash` y comentario corregido

**Baseline de este sub-incremento:**
`c5cda0d184e1b74eac162ca4d7e19d396e720d39` (T-617B0-R4).

### 10.1 Motivo

La evidencia de §1 (`thinking_budget=1024`→salida inválida,
`thinking_budget=4096`→salida válida) se produjo **específicamente** contra
`gemini-2.5-flash`. R4 aplicaba `thinking_budget` a cualquier modelo Google
configurado (`settings.llm_provider == "google"`, sin mirar
`settings.llm_model`), lo que habría enviado un presupuesto de razonamiento
sin evidencia si `LLM_MODEL` cambiara a otro modelo Google (p. ej.
`gemini-2.5-pro`). R4A cierra ese hueco.

### 10.2 Corrección aplicada

`backend/app/agent/deterministic_dependencies.py`:

- Nueva constante `_PLANNER_THINKING_BUDGET_LLM_MODEL = "gemini-2.5-flash"`.
- La condición de `_model()` pasa de
  `thinking_budget is not None and settings.llm_provider == "google"` a
  `thinking_budget is not None and settings.llm_provider == "google" and
  settings.llm_model == _PLANNER_THINKING_BUDGET_LLM_MODEL`.
- `timeout=30`, `max_retries=2`, prompts, schemas, `normalize_system_owned_operation`,
  golden-v1/v2 y contratos: **sin cambios** (idénticos a R4).
- Comentarios corregidos: los 1.418 s de la tabla de §1 se re-etiquetan
  explícitamente como "prueba mínima de disponibilidad del modelo (sin el
  payload real de `build_plan`)", distinta de los renglones de
  `build_plan` real (~65 s sin budget, 5.17 s con 1024, 2.899 s con 4096).

### 10.3 Regresión parametrizada nueva

`tests/test_deterministic_dependencies.py::test_thinking_budget_is_scoped_to_google_gemini_2_5_flash`,
3 casos:

| `llm_provider` | `llm_model` | `thinking_budget` esperado |
|---|---|---|
| `google` | `gemini-2.5-flash` | `4096` |
| `google` | `gemini-2.5-pro` | ninguno |
| `anthropic` | `claude-sonnet-5` | ninguno |

En los tres casos se verifica además `timeout=30`/`max_retries=2` cuando el
proveedor expone esos atributos (Anthropic no expone `.timeout`
directamente; se omite esa aserción puntual con un `hasattr` guard, sin
dejar de verificar `max_retries`).

### 10.4 Verificación (2026-07-19)

```
pytest tests/test_deterministic_dependencies.py -q
```
→ **15 passed** (las 5 de R4 + la actualizada + la nueva parametrizada de 3
casos).

```
pytest tests/test_deterministic_dependencies.py tests/test_deterministic_runtime.py \
  tests/test_llm_factory.py tests/test_llm_contracts.py tests/test_settings.py -q
```
→ **92 passed**.

```
pytest -m "not integration" -q
```
→ **948 passed, 122 deselected**, 0 fallos.

```
pytest -m deterministic_agent_acceptance -q
```
(PostgreSQL local, sin LLM real) → **18 passed, 1 xfailed** (mismo `xfail`
preexistente de R4, no relacionado).

```
ruff check .
```
→ **All checks passed!**

```
ruff format --check app/agent/deterministic_dependencies.py tests/test_deterministic_dependencies.py
```
→ **2 files already formatted**.

```
git diff --check
```
→ limpio (exit 0).

### 10.5 Prueba fallo→pasa contra el baseline de R4

Worktree temporal en `c5cda0d184e1b74eac162ca4d7e19d396e720d39`
(`git worktree add`/`git worktree remove --force`), copiando únicamente
`tests/test_deterministic_dependencies.py`:

```
FAILED tests/test_deterministic_dependencies.py::test_thinking_budget_is_scoped_to_google_gemini_2_5_flash[google-gemini-2.5-pro-api_key_kwargs1-None]
AssertionError: assert (not True or 4096 is None)
1 failed, 14 passed
```

El caso `google/gemini-2.5-pro` falla exactamente como se esperaba contra el
baseline de R4 (que aplicaba `thinking_budget` a cualquier modelo Google) y
pasa con la corrección de este sub-incremento; los otros 2 casos de la misma
parametrización (`google/gemini-2.5-flash`, `anthropic`) ya pasaban en R4 y
siguen pasando.

### 10.6 Hashes golden (antes y después, idénticos)

```
golden-v1: ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72
golden-v2: 1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483
```

### 10.7 Alcance respetado

Sin cambios en Anthropic, `timeout`, `max_retries`, prompts, schemas,
`golden-v1.yaml`, `golden-v2.yaml` ni contratos. No se ejecutó Gemini,
Socrata, `pilot-005` ni el smoke en este sub-incremento. T-617 sigue
**abierta**.
