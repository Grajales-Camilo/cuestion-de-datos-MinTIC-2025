# T-617C-R2 — Compatibilidad RF-212 del verificador de claims y cierre del falso PASS del smoke

**T-617C permanece abierta.** Este incremento corrige exclusivamente el
arnés de evaluación (`eval/gate.py`); no toca el runtime productivo, no
implementa nada nuevo de RF-212, no cierra T-617.

- Repositorio: `D:\Usuario\AppWebs\cuestion-de-datos-MinTIC`
- Rama: `feat/t617-gate-preflight`
- HEAD de partida: `8bfd7501ad9afb7341a1447f925df0c0735b0470`
- Evidencia disparadora: smoke `fd2da0f1-94b6-47e4-8ddc-30926266f944`
  (`claims_coverage=1.0`, `claims_reproducible=0.0`, `fabrication_count=0`,
  `orphan_figures_count=0`, `gate_passed=true`)

## 1. Causa raíz confirmada

T-617C-R1 hizo correctamente público y persistente el nombre real de
columna: `final_answer.claims[].columns = ["genero_hombre"]`. La evidencia
sigue con filas indexadas por el alias de ejecución SoQL:
`evidence.rows = [{"dim_2": "764", ...}]` — eso nunca cambió (correcto:
las filas que devuelve Socrata están indexadas por el `SELECT ... AS dim_N`
real).

`eval/gate.py::_reproduce_one_claim` seguía construyendo `ClaimSpec.columns`
directamente con el nombre público (`["genero_hombre"]`) y pasándolo a
`build_claims` contra las filas alias-keyed. Como `"genero_hombre"` nunca es
clave de `{"dim_2": "764"}`, el claim se rechazaba con `"la columna
'genero_hombre' no existe en la evidencia"` → `not_reproducible` para el
100% de los claims cuantitativos. `evaluate_smoke_gate` nunca miraba
`claims_integrity`/`claims_reproducible`, así que el smoke aprobaba
igualmente.

La ruta productiva (`persistence.py::_reverify_quantitative_synthesis_fact`,
T-617C-R1) ya resolvía exactamente este problema reconstruyendo el alias
desde `evidence.soql_query` con `extract_column_field_names`. R2 aplica el
mismo mecanismo al verificador del arnés.

## 2. Objetivo A — Corrección de `_reproduce_one_claim`

Nueva función pura `_resolve_execution_columns(columns, rows, soql_query)`
en `eval/gate.py`:

1. **Camino directo (compatibilidad)**: si `set(columns) <= row_keys` (los
   nombres públicos ya son claves de las filas — claims persistidos antes
   de T-617C-R1, o dobles/fixtures que ya usan el nombre real como alias),
   se usan tal cual, sin tocar el SoQL. `column_field_names={}` (el
   fallback de `ClaimSpec.column_field_names.get(alias, alias)` en
   `claims.py` ya resuelve esto correctamente).
2. **Camino nuevo**: si no, parsea `soql_query` con
   `app.tools.soql_parser.extract_column_field_names` (parser SoQL
   vigente, cero regex improvisada) e invierte alias→columna a
   columna→alias(es). Para cada nombre público:
   - Sin ningún alias correspondiente → `"column_unresolvable"`.
   - Con **más de un** alias distinto apuntándole → `"column_mapping_ambiguous"`
     (nunca se toma el último en silencio).
   - Con exactamente uno → se usa ese alias como columna de ejecución.
3. Un `SoqlGuardError`/`TypeError`/`ValueError` al parsear produce
   `"soql_unparseable"`, nunca una excepción sin controlar que interrumpa
   la evaluación completa.
4. `_reproduce_one_claim` construye `ClaimSpec(columns=<alias de
   ejecución>, column_field_names=<alias→nombre público>)` con el
   resultado y reejecuta `build_claims` exactamente como antes — **no se
   reimplementó el DSL ni el algoritmo de hash**, ambos siguen siendo
   `app.quality.claims.build_claims`/`compute_source_hash` sin tocar.
5. Las comprobaciones de evidencia, filas, columnas, fórmula, `raw_value`,
   `display_value` y `source_hash` permanecen exactamente iguales después
   de la resolución.

`count(*)` se resuelve mediante el centinela estructural ya existente
(`COUNT_FIELD_SENTINEL = "__count__"`, definido en
`app.quality.claim_labels`, importado por `extract_column_field_names`),
nunca mediante texto inventado — sin cambios en esa pieza, ya introducida
en T-617C-R1.

## 3. Objetivo B — Métrica bloqueante `integridad_claims`

Nueva métrica en `evaluate_smoke_gate`, añadida al final de la lista antes
de calcular `passed = all(m.passed for m in metrics)` (no se tocó ninguna
métrica existente):

```python
broken_integrity = [
    o.case_id
    for o in outcomes
    if o.claims_integrity.applicable and not o.claims_integrity.integrity_ok
]
```

Condición: todo `CaseOutcome` con `claims_integrity.applicable=True` debe
tener `integrity_ok=True` (que ya encapsula cobertura=100%,
reproducibles=100% y huérfanas=0 — RF-208/RNF-003). Una falla produce
`gate_passed=false` con una razón que lista los `case_id` afectados. No
evalúa perfección de respuesta ni `expected_facts`: solo trazabilidad y
reproducibilidad, calculadas exactamente igual que antes por
`evaluate_claims_integrity` (sin cambios en esa función). No se modificaron
las demás condiciones del smoke (`cobertura_canónica`, `negativos`,
`positivos_sólidos`, `infraestructura`, `fallos_clasificados`) ni ningún
umbral de la puerta `full`.

## 4. Objetivo C — Regresiones (11 pruebas nuevas en `tests/test_eval_gate.py`)

| # | Prueba | Cubre |
|---|---|---|
| 1 | `test_r2_reproduces_public_real_column_name_against_alias_keyed_rows` | `columns=["genero_hombre"]`, filas `{"dim_2": "764"}`, SoQL con `AS dim_2` → reproduce al 100% con hash v2.0.0 |
| 2 | `test_r2_derived_claim_with_alias_formula_and_public_columns_reproduces` | fórmula con alias interno (tal como la persiste el pipeline real) + `columns` público real → reproduce exacto |
| 3 | `test_r2_count_star_sentinel_reproduces` | `count(*)` con el centinela `__count__` reproduce correctamente |
| 4 | `test_r2_direct_path_still_works_when_public_column_is_already_a_row_key` | camino directo de compatibilidad sigue funcionando (`_valid_final()` preexistente) |
| 5 | `test_r2_nonexistent_public_column_fails_deterministically` | columna pública inexistente falla (`column_unresolvable`) |
| 6 | `test_r2_invalid_soql_fails_safely_without_uncontrolled_exception` | SoQL inválido falla con código seguro, sin excepción sin controlar |
| 7 | `test_r2_ambiguous_alias_mapping_fails_instead_of_picking_last_silently` | dos alias para el mismo nombre real fallan por ambigüedad, nunca selección arbitraria |
| 8 | `test_r2_tampered_raw_value_display_value_or_hash_still_fail` | `raw_value`/`display_value`/`source_hash` manipulados siguen fallando en formato R1 |
| 9 | `test_r2_smoke_with_broken_claims_integrity_cannot_pass` | 10 canónicos perfectos salvo integridad rota en uno → smoke NO aprueba |
| 10 | `test_r2_smoke_with_full_claims_integrity_can_pass` | mismo smoke con integridad completa → sí aprueba |
| 11 | `test_r2_other_smoke_metrics_remain_intact` | cardinalidad/negativos/sólidos/infraestructura/clasificados intactos, solo se añadió `integridad_claims` |

Además se actualizó `test_corruption_unknown_column_fails` (preexistente):
antes esperaba el código genérico `"not_reproducible"`; ahora,
correctamente, el código específico `"column_unresolvable"` — no es una
regresión, es una mejora de precisión del diagnóstico.

## 5. Objetivo D — Recálculo de la corrida real sin gastar cuota

Script temporal fuera del repositorio (`%TEMP%\t617cr2_recompute_integrity.py`,
eliminado tras su uso junto con su salida), **solo lectura** sobre
PostgreSQL: para cada uno de los 10 `agent_run_id` del smoke
`fd2da0f1-94b6-47e4-8ddc-30926266f944`, carga `agent_runs.final_answer`
(sin modificarlo) y recalcula `evaluate_claims_integrity`/`evaluate_smoke_gate`
con el código corregido. No se ejecutó Gemini, Socrata, ni ninguna corrida
nueva; no se modificó `eval_runs` ni `eval_case_results`.

| Caso | aplicable | claims | reproducibles antes | reproducibles después | `integrity_ok` después |
|---|---|---|---|---|---|
| pilot-002-seguridad-homicidios | sí | 1 | 0 | **1** | ✓ |
| pilot-003-salud-vigilancia | sí | 1 | 0 | **1** | ✓ |
| pilot-005-empleo-publico | sí | 4 | 0 | **4** | ✓ |
| pilot-012-control-fiscal | no (sin evidencia) | 0 | — | — | ✓ (trivial) |
| pilot-013-app-dnp | sí | 1 | 0 | **1** | ✓ |
| pilot-021-sensibilizacion-valle | sí | 1 | 0 | **1** | ✓ |
| pilot-022-red-vial | sí | 3 | 0 | **3** | ✓ |
| pilot-038-precipitacion | sí | 200 | 0 | **200** | ✓ |
| pilot-045-negativo-dato-personal | no (sin evidencia) | 0 | — | — | ✓ (trivial) |
| pilot-046-negativo-tiempo-real | no (sin evidencia) | 0 | — | — | ✓ (trivial) |

**Totales**: 7 casos aplicables, **211 claims cuantitativos**, 0
reproducibles antes de R2, **211 reproducibles después** (`claims_reproducible=1.0`
en los 7 casos, `claims_coverage=1.0` sin cambio, `failure_codes=[]` en
todos). `integrity_ok=True` en los 10 casos.

**Veredicto recalculado de `evaluate_smoke_gate`** sobre esos mismos
resultados: `gate_passed=true`, con las 6 métricas (incluida
`integridad_claims`, nueva) en PASS:

```
cobertura_canónica: PASS (10/10 canónicos, 10 resultados)
negativos: PASS (2/2)
positivos_sólidos: PASS (0 retrocesos)
infraestructura: PASS (0 corridas no evaluables)
fallos_clasificados: PASS (0 sin clasificar)
integridad_claims: PASS (0 casos con integridad rota)
```

El `gate_passed=true` del smoke original **sigue siendo el veredicto
correcto** — pero ahora lo es por reproducibilidad real (211/211 claims
reproducidos), no por un hueco del verificador que nunca llegó a
ejecutarlo. Esto es justamente lo que motivó a esta ronda: antes de R2 el
`PASS` era mecánicamente cierto pero engañoso (`claims_reproducible=0%`
sin bloquear nada); después de R2, el mismo `PASS` es evidencia genuina de
integridad.

## 6. Alcance respetado

**Modificado únicamente:**
- `backend/eval/gate.py` — `_resolve_execution_columns` (nueva),
  `_reproduce_one_claim` (corregida), métrica `integridad_claims` en
  `evaluate_smoke_gate`.
- `backend/tests/test_eval_gate.py` — 11 pruebas nuevas + 1 aserción
  actualizada (código de fallo más específico).
- `specs/001-cuestion-de-datos-v2/tasks.md` — nota `T-617C-R2` añadida
  dentro del bloque de T-617C existente; **T-617C sigue con `- [ ]`, sin
  marcar**.
- Este informe.

**No tocado**: `backend/app/agent/**` (no fue necesario ningún cambio en el
runtime productivo — la ruta productiva ya estaba correcta desde R1;
solo el arnés de evaluación estaba desactualizado), ninguna migración,
`golden-v1`/`golden-v2`, `expected_facts`, cardinalidades/umbrales,
contratos públicos, ninguna regla específica de `pilot-005`, `constitution.md`,
`checklists/requirements.md`. Sin llamadas reales a Gemini/Socrata. No se
ejecutó el smoke de nuevo. Sin push, sin PR, sin amend.

## 7. Pendiente separado (no corregido en esta ronda)

`evidence[].quality.warnings_user` de `pilot-005-empleo-publico`
(confirmado en el smoke `fd2da0f1-…` y ya señalado en la ronda anterior)
sigue exponiendo el alias interno `dim_5` y describiendo el "38% de
registros" cuando en realidad son celdas vacías de esa columna:

```json
["El 38% de los registros de la columna 'dim_5' están vacíos; los promedios o totales calculados pueden variar."]
```

Es una deuda de presentación de `app/quality/validator.py`/`messages_es.py`
(capa de calidad de evidencia, ajena a `quantitative_claims`/`final_answer.claims`
que sí tocó T-617C), no corregida aquí conforme a la instrucción explícita
de esta ronda. Queda documentada para una ronda futura separada.

## 8. Verificación — pruebas y resultados exactos

### 8.1 Reproducción de fallo contra baseline (worktree temporal)

`git worktree add %TEMP%/t617c-r2-baseline 8bfd7501ad9afb7341a1447f925df0c0735b0470`,
copiando únicamente `tests/test_eval_gate.py` (sin ningún cambio de
producción):

```
uv run python -m pytest tests/test_eval_gate.py -q
10 failed, 56 passed, 1 warning in 16.81s
```

Los 10 fallos corresponden exactamente a las 10 pruebas nuevas de R2 (la
undécima, `test_corruption_unknown_column_fails` actualizada, no cuenta
como "nueva" pero también difiere del baseline por el código de fallo
esperado). Crítico: `test_r2_smoke_with_broken_claims_integrity_cannot_pass`
falla contra el baseline con `AssertionError: assert True is False` —
**demuestra en código que el smoke aprobaba con integridad de claims
rota antes de R2**, exactamente el defecto real. Worktree eliminado con
`git worktree remove --force`.

### 8.2 Con la corrección, en el árbol principal

```
uv run python -m pytest tests/test_eval_gate.py -q
66 passed in 5.45s
```

### 8.3 Suite completa no-integración

```
uv run python -m pytest -m "not integration" -q
1018 passed, 122 deselected, 5 warnings in 19.95s
```
(1007 antes de esta ronda + 11 pruebas nuevas de `test_eval_gate.py`.)

### 8.4 Integración local con PostgreSQL

`eval/gate.py` es un módulo puro (sin I/O, sin base de datos, según su
propio docstring); ningún archivo de `tests/integration/` lo importa.
No existe integración local pertinente que ejecutar para este cambio — se
verificó explícitamente (`grep` sin resultados) antes de omitirla.

### 8.5 Lint, formato, `git diff --check`

```
uv run ruff check .
All checks passed!

uv run ruff format --check eval/gate.py tests/test_eval_gate.py
2 files already formatted

git diff --check
(solo advertencias inocuas de normalización CRLF de Git en Windows)
```

## 9. Hashes golden

- Antes y después: **idénticos, sin cambio.**
  - `golden-v1.yaml`: `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`
  - `golden-v2.yaml`: `1c78264cccb0da6a10920b6b212438cc40c2b70d2bbd40265f5794fdc754e483`

## 10. Estado final

**READY_FOR_T617C_R2_AUDIT**

T-617C permanece abierta. No se ejecutó el smoke de nuevo ni ninguna otra
corrida real. Sin push, sin PR, sin amend. Detenido tras el commit y este
informe.
