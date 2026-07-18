# T-616A-R — Auditoría corregida de los 50 casos de `golden-v1` para una propuesta `golden-v2`

> **NON_NORMATIVE_AUDIT_PROPOSAL.**
> Corrige y completa la auditoría T-616A tras la revisión coordinadora.
> No modifica `golden-v1.yaml`, ni `eval/metrics.py`, ni contratos, ni el
> runtime. No crea `golden-v2.yaml`. No cierra T-616 ni inicia T-616B/T-617.
> Toda recomendación queda pendiente de aprobación humana explícita.

La matriz estructurada y canónica vive en `t616a-case-audit.json`
(esquema `t616a-case-audit-v2`). La evidencia reproducible (consultas, URLs,
HTTP, conteos, hashes) vive en `t616a-evidence-manifest.json`
(`t616a-evidence-manifest-v2`). Este informe los resume; ante divergencia,
prevalecen el JSON, el manifiesto y el `golden-v1.yaml` real.

---

## 0. Qué cambió respecto de T-616A (y por qué)

La revisión coordinadora encontró en T-616A: solo 12/40 verificados contra
Socrata; 28 con conclusiones estructurales sin evidencia; `audit_confidence=high`
mal calibrada; `missing_evidence=[]` pese a evidencia faltante; confusión entre
caso incompatible / dataset incompatible / URL mal construida; hechos que mezclan
`fact_kind=quantitative` con operaciones textuales (`argmax_label`);
`canonical_text_set` propuesto para conjuntos de cientos/miles; y errores
concretos en `pilot-001`, `pilot-016`, `pilot-022`, `pilot-038/039`.

T-616A-R rehace la auditoría **desde cero, caso por caso**, con verificación real:

- **40/40 positivos verificados contra el catálogo PostgreSQL local** (todos
  existen, `api_active`, `eligible`, `pii_risk` registrado y publicador
  `verified`), en modo solo lectura.
- **40/40 positivos verificados contra Socrata real** (HTTP 200) ejecutando
  **solo restricciones derivables de la pregunta** (nunca los filtros-respuesta
  de `golden-v1`), con esquema, conteo físico, cardinalidad de la proyección,
  nulos, duplicados, valores distintos acotados, selección/empates y hashes de
  las respuestas oficiales completas.
- Reproducibilidad demostrada: `t616a_audit.py --verify-live` re-ejecuta las 40
  consultas y compara estrictamente contra el manifiesto; cualquier diferencia
  material devuelve código distinto de cero.

## 1. Veredicto ejecutivo

`golden-v1` sigue siendo una línea histórica valiosa pero **no apta como suite de
exactitud determinista** en su forma actual: **35 de 40 positivos** fijan al menos
una restricción no derivable de la pregunta (filtro-respuesta, selector no pedido
o ancla equivocada). El patrón dominante sigue siendo la pregunta subdeterminada
del tipo *"¿qué X figura/aparece?"*.

Correcciones de fondo respecto de T-616A:

- **`pilot-001` v1 es ambiguo/multi-respuesta, no `aggregate`:** «tasa alta» no
  define umbral ni autoriza un argmax silencioso. La **reescritura** con «mayor»
  sí queda determinada: el dataset ya está restringido a Magdalena;
  `a_o=2024` rinde 30 municipios y el máximo, sin agregación, es Cerro de San
  Antonio 6.28 (único), no Zona Bananera 2.44.
- **`pilot-022` es `determined` con `wrong_anchor`, no `incompatible`.** El
  dataset sí contiene `codigo_tramo`; `codigo_tramo='55ST02'` devuelve 3 filas
  idénticas (administrador=1, calzada=1, categoria=2). El golden filtraba por la
  respuesta, no por el tramo.
- **`pilot-016` es caso ambiguo / dataset compatible / evidencia con ancla
  equivocada.** `noid` y `codigo_postal` son campos distintos; Rondón/Boyacá
  devuelve 2 filas (noid 877 urbano, noid 878 rural). El formato de
  `codigo_postal` (153.42 / 153.427) no queda semánticamente certificado por el
  tipo oficial publicado → `exclude_until_resolved`.
- **`pilot-038/039` son ambiguos/multi-respuesta; los datasets sí son
  compatibles.** Hay 74 690 / 14 734 observaciones, 373 / 358 estaciones y
  1 440 instantes distintos el día pedido. Estación+sensor+hora estaban ocultos
  en v1 → `exclude_until_resolved`; solo son aprobables si la pregunta incluye
  los discriminantes literalmente.
- **Los extremos con etiqueta y magnitud** (`pilot-001/002/003`, y el par
  etiqueta/valor de `pilot-034`) se separan en **dos hechos coordinados**:
  `TextualFact(argmax_label)` / `direct_text` para la etiqueta y
  `QuantitativeClaim(direct|derived)` para la magnitud. Nunca
  `fact_kind=quantitative` con `operation=argmax_label`.
- **`canonical_text_set` solo se usa con cardinalidad verificada ≤ 50** (límite
  duro real `MAX_NORMALIZED_VALUES`). Los conjuntos > 50 (`pilot-015`=239,
  `pilot-037`=61, y todos los "abiertos") se reescriben a un agregado o a un
  ancla, **nunca** a un conjunto textual.

Los **10 negativos son correctos**: abstención legítima, sin dato respondible en
el catálogo estructurado. Se recomienda conservarlos; única observación:
renombrar `pilot-048` (el `case_id` dice "corrupción" pero la pregunta trata
polarización en redes/NLP) **sin** alterar la guarda.

## 2. Rama, commit y SHA-256 de `golden-v1`

- Rama: `v2`
- Commit base contractual esperado: `34e6d048127290014f85765f0eaf325ac8062d56`.
  Al iniciar esta corrección, el `HEAD` real ya contenía un commit local de
  T-616A-R sobre esa base; se auditó el contenido real y se corrigió el mismo
  incremento, sin asumir que el commit preexistente era válido.
- SHA-256 de `backend/eval/golden/golden-v1.yaml` (inicial y final, **sin
  cambios**): `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`

## 3. Método (rigor exigido por la coordinación)

Para **cada uno de los 40 positivos**:

1. **Catálogo PostgreSQL local (transacción `READ ONLY` comprobada):** existencia, `api_active`,
   `eligibility_status`, `pii_risk_level`, `publisher_verification_status`,
   publicador/ID oficial, columnas y tipos reales, estado de embeddings/vectores
   léxicos, `row_count`, fechas de datos/corte/sincronización. No se escribe en
   PostgreSQL.
2. **Metadatos oficiales (datos.gov.co):** `GET /api/views/{id}.json` → nombre,
   entidad publicadora, `rowsUpdatedAt`, columnas y tipos Socrata. HTTP 200 en
   los 40.
3. **Consulta oficial derivable:** perfil de `count(*)`, no nulos y
   `count(distinct …)`, más proyección canónica completa y paginada, aplicando
   **solo** las restricciones literales/inequívocas de la pregunta (más la regla
   de selección propuesta). Nunca se reutilizan los filtros-respuesta de
   `golden-v1`. Se registran parámetros/URL, conteo físico, cardinalidad de
   proyección, perfil de nulos/distintos, multiplicidades/duplicados,
   selección/empates y hashes SHA-256 de las respuestas. Sólo se persiste una
   vista previa cuando la proyección completa tiene ≤20 tuplas; no se vuelcan
   filas masivas ni datos personales.
4. **Regla de confianza:** `high` solo con catálogo local + metadatos oficiales +
   consulta ejecutada + cardinalidad + regla comprobadas y **cero evidencia
   material faltante**. `medium`/`low` cuando falta una comprobación no central o
   cuando algo puede cambiar clasificación/respuesta/compatibilidad.

No se ejecutó ningún LLM ni el agente. No se ejecutó la suite golden.

## 4. Tres niveles de diagnóstico (nuevos campos)

Cada positivo declara explícitamente (`t616a-case-audit.json`):

- `case_compatibility` ∈ {compatible, ambiguous, incompatible, unverified}: si la
  pregunta puede evaluarse normativamente.
- `dataset_compatibility` ∈ {compatible, incompatible, unverified}: si el dataset
  contiene la información necesaria.
- `golden_v1_evidence_validity` ∈ {valid, wrong_anchor, hidden_constraint, stale,
  unverified}: si la URL/hecho congelado demuestra realmente la respuesta.

Una URL incorrecta **no** convierte el caso en incompatible; un dataset
compatible **no** significa que la pregunta determine una respuesta.

| Nivel | Distribución (40 positivos) |
|---|---|
| `case_compatibility` | compatible 19 · ambiguous 21 · incompatible 0 |
| `dataset_compatibility` | compatible 40 |
| `golden_v1_evidence_validity` | valid 5 · hidden_constraint 30 · wrong_anchor 2 · stale 3 |

## 5. Conteos finales

### 5.1 Clasificación primaria

| Clasificación | Casos |
|---|---|
| `determined` | 9 (005, 006, 007, 013, 020, 021, 022, 030, 034) |
| `aggregate` | 3 (002, 003, 004) |
| `multi_response` | 28 (incluye 001, 016, 038 y 039) |
| `incompatible` | 0 |
| `abstention` (negativos) | 10 |
| **Total** | **50** |

### 5.2 Estado de aprobación (positivos)

| Estado | Casos |
|---|---|
| `ready_for_human_approval` | 28 |
| `needs_human_decision` | 9 (003, 004, 011, 012, 014, 024, 029, 033, 036) |
| `exclude_until_resolved` | 3 (016, 038, 039) |

### 5.3 Confianza (positivos)

| Confianza | Casos |
|---|---|
| `high` | 38 |
| `medium` | 2 (014 «consolidado» sin definir; 016 formato `codigo_postal`) |
| `low` | 0 |

Ningún `high` coexiste con `missing_evidence` material (validado por el script).

### 5.4 Veredicto sobre `golden-v1`

| Veredicto | Casos |
|---|---|
| `retain_semantics` | 15 (5 positivos: 006, 007, 013, 020, 034 + 10 negativos) |
| `broaden_acceptable_answers` | 7 (002, 003, 018, 028, 031, 032, y 005) |
| `rewrite_case` | 25 |
| `exclude_until_resolved` | 3 (016, 038, 039) |
| **Total** | **50** |

## 6. Matriz `fact_kind` / operación (dominio real)

Fuente de verdad: `app.quality.grounded_facts` (T-615). Embebida y **validada
automáticamente** por `t616a_audit.py --check`.

| `fact_kind` | Operaciones permitidas | Restricción clave |
|---|---|---|
| `textual` (`TextualFact`) | `direct_text`, `value_presence`, `category_selection`, `argmax_label`, `argmin_label`, `canonical_text_set` | `argmax_label`/`argmin_label`: 2 columnas (etiqueta, métrica) + `tie_policy=reject`; `canonical_text_set`: 1 columna, ≤ 50 valores; resto: 1 columna |
| `quantitative` (`QuantitativeClaim`) | `direct`, `derived` | `derived` exige `formula`; `raw_value` numérico; nunca una etiqueta |

**Prohibido** (el validador lo rechaza): `fact_kind=quantitative` con
`operation=argmax_label`; `canonical_text_set` con cardinalidad no verificada o
> 50; operaciones inexistentes (p.ej. `lookup_multi`).

**Regla de coordinación de extremos:** un extremo que presenta etiqueta y
magnitud produce **dos** objetos coordinados —`TextualFact(argmax_label|argmin_label)`
para la etiqueta y `QuantitativeClaim(direct|derived)` para la magnitud— sobre el
mismo dataset, la misma evidencia y las mismas filas. Aplicado a `pilot-001`
(municipio + tasa), `pilot-002` (departamento + suma), `pilot-003` (evento +
suma). El validador exige el par cuando hay un extremo textual.

Distribución materializada de los **59 hechos propuestos** (59/59 con
`source_query`, `observed_at` y `data_cutoff_at`):

| `fact_kind` / operación | Cantidad |
|---|---:|
| textual / `argmax_label` | 3 |
| textual / `direct_text` | 8 |
| textual / `category_selection` | 10 |
| textual / `canonical_text_set` | 14 |
| textual / `value_presence` | 3 |
| quantitative / `direct` | 14 |
| quantitative / `derived` | 7 |

## 7. Política para las preguntas multirrespuesta (28 casos)

Revisión individual (no se usa `canonical_text_set` por defecto). Decisión por
caso según cardinalidad **verificada**:

- **`bounded_set` (9):** 011 (21 códigos), 017 (6 clases/2 niveles), 018
  (2 concesiones/3 operadores), 019 (12 sociedades/2 tipos), 028 (2/2), 029
  (2 fuentes), 031 (2 tipos), 032 (2 estados), 035 (4 componentes/8 regímenes).
  Todos con cardinalidad ≤ 50 verificada y `canonical_text_set` por columna.
- **`rewrite` (16):** 001 («tasa alta» → «mayor»), 008 (anclar año → determinado), 012 (anclar vigencia), 014
  (definir «consolidado»), 015 (239 puestos → conteo), 023/025/026/027 (anclar
  entidad nombrada), 024 (precisar alcance ETC), 033 (pregunta degenerada → conteo),
  036 (sensible → agregado por departamento), 037 (61 estaciones → conteo),
  040/041/042 (anclar empresa). Ninguno usa conjunto textual > 50.
- **`exclude` (3):** 016 (semántica de `codigo_postal` sin certificar) y 038/039
  (día sin estación/hora; reescritura todavía no aprobada).

Regla estricta aplicada: nunca primera fila incidental, ni cualquier fila
compatible, ni `LIMIT 1` sin orden total, ni filtros construidos con la respuesta.

## 8. Correcciones obligatorias (§5 del encargo)

| Caso | Corrección aplicada (verificada 2026-07-18) |
|---|---|
| `pilot-001` | V1 ambiguo/multi-respuesta: «tasa alta» no autoriza argmax. La reescritura con «mayor» queda determinada (no aggregate): máximo real Cerro de San Antonio 6.28, único; no se conserva Zona Bananera 2.44. Etiqueta = `argmax_label` textual; magnitud = `QuantitativeClaim direct`; `tie_policy=reject`. |
| `pilot-016` | `noid`≠`codigo_postal`. Rondón/Boyacá → 2 filas (877 urbano, 878 rural). El esquema/tipo oficial está persistido, pero no certifica la semántica de 153.42/153.427 → `exclude_until_resolved`, confianza `medium`. No se crea automáticamente un `canonical_text_set`. |
| `pilot-022` | `case=compatible`, `dataset=compatible`, `gv1=wrong_anchor`, `determined`. Filtro futuro = `codigo_tramo=55ST02` (3 filas duplicadas idénticas documentadas). No se usa el filtro circular administrador/calzada/categoria. |
| `pilot-038/039` | Caso ambiguo/multi-respuesta, dataset compatible. La pregunta actual no selecciona estación/hora entre 74 690 / 14 734 observaciones (373/358 estaciones, 1 440 instantes). Se auditaron candidatos concretos: estación 0054050010/sensor 0240/13:50 → 0 mm; estación 0026195501/sensor 0068/03:35 → 15.85716 °C. Esos discriminantes están en las preguntas reescritas, no se usan para justificar v1, y los casos permanecen `exclude_until_resolved` hasta aprobación. |

## 9. Tabla de preguntas propuestas para `golden-v2` (40 positivos)

Etiquetas abreviadas; la pregunta v2 completa y su justificación están en
`golden_v2_question_proposal` / `question_change_rationale` del JSON. `regla` =
decisión multirrespuesta o clasificación primaria.

| caso | tema v1 | cambio | regla | estado |
|---|---|---|---|---|
| 001 | tasa deserción Magdalena 2024 | rewrite | multi_response → argmax explícito | ready |
| 002 | departamento más homicidios | clarify | aggregate | ready |
| 003 | eventos mayor volumen | clarify | aggregate | needs_human_decision |
| 004 | ejecución sector Justicia 2023 | rewrite | aggregate | needs_human_decision |
| 005 | planta por sexo MinRelExt | clarify | determined | ready |
| 006 | cargos planta CDA Caldas | retain | determined | ready |
| 007 | deserción Antioquia 2011 | retain | determined | ready |
| 008 | limpieza urbana Villamaría | rewrite | rewrite (anclar año) | ready |
| 011 | intervención acción contra minas | rewrite | bounded_set (21) | needs_human_decision |
| 012 | hallazgos auditoría Contraloría | rewrite | rewrite (vigencia) | needs_human_decision |
| 013 | tipo/nombre APP PRY00062 | retain | determined (textual) | ready |
| 014 | código/municipio consolidado Bogotá | rewrite | rewrite (def #TODOS) | needs_human_decision |
| 015 | puesto de votación Medellín | rewrite | rewrite (conteo) | ready |
| 016 | identificador postal Rondón | rewrite | exclude | exclude_until_resolved |
| 017 | clase/nivel terminal Cali | rewrite | bounded_set (6/2) | ready |
| 018 | concesión/operador férreo 13-10-2023 | rewrite | bounded_set (2/3) | ready |
| 019 | sociedad portuaria Barranquilla | rewrite | bounded_set (12/2) | ready |
| 020 | DIVIPOLA Medellín | retain | determined (textual) | ready |
| 021 | socializadas Alcalá enero 2018 | rewrite | determined (anclar año) | ready |
| 022 | características tramo 55ST02 | rewrite | determined (wrong_anchor) | ready |
| 023 | códigos EVA Boyacá | rewrite | rewrite (anclar mun.) | ready |
| 024 | ETC de Antioquia 2024 | rewrite | rewrite (alcance ETC) | needs_human_decision |
| 025 | municipio/código educ. 2024 | rewrite | rewrite (anclar mun.) | ready |
| 026 | paridad matrícula depto/año | rewrite | rewrite (anclar depto) | ready |
| 027 | paridad étnica depto/año | rewrite | rewrite (anclar depto) | ready |
| 028 | fuente/situación DONACIONES | rewrite | bounded_set (2/2) | ready |
| 029 | fuente gastos enero 2019 | rewrite | bounded_set (2) | needs_human_decision |
| 030 | municipio Amazonas conciliadores | clarify | determined (único) | ready |
| 031 | tipo desmovilización Nariño | rewrite | bounded_set (2) | ready |
| 032 | situación penitenciaria Medellín | rewrite | bounded_set (2) | ready |
| 033 | fecha venta GNV sept-2025 | rewrite | rewrite (conteo) | needs_human_decision |
| 034 | capacidad Jepirachi | retain | determined | ready |
| 035 | componente/régimen afiliaciones 2017 | rewrite | bounded_set (4/8) | ready |
| 036 | departamento delitos sexuales 31-05-2026 | rewrite | rewrite (agregado sensible) | needs_human_decision |
| 037 | estación AMVA | rewrite | rewrite (conteo, 61) | ready |
| 038 | estación/sensor precipitación 11-02-2019 | rewrite | ambiguous / multi_response | exclude_until_resolved |
| 039 | estación/sensor temperatura 21-01-2020 | rewrite | ambiguous / multi_response | exclude_until_resolved |
| 040 | empresa/año suspensión servicio | rewrite | rewrite (anclar empresa) | ready |
| 041 | empresa/NUECA ECA | rewrite | rewrite (anclar empresa) | ready |
| 042 | empresa/NUSD disposición final | rewrite | rewrite (anclar empresa) | ready |

Estados: `ready` = `ready_for_human_approval`. No se materializa ninguna pregunta
en `golden-v2`.

## 10. Negativos (10)

Todos `retain_semantics`, `expected_status=no_evidence`, confianza `high`. Clases
de incapacidad y qué constituiría fabricación en `t616a-case-audit.json`
(`incapacity_class`, `abstention_reason`, `would_be_fabrication`):

- predicción futura: 009, 043
- causalidad sin diseño: 010, 044
- privacidad / datos personales: 045
- tiempo real: 046
- contrafactual / simulación (ABM/redes): 047
- NLP / redes no estructurado: 048
- consejo clínico individual: 049
- dato inexistente: 050

Observación (no bloqueante): renombrar `pilot-048` a
`pilot-048-negativo-polarizacion-redes` en `golden-v2` (el `case_id` menciona
"corrupción"/"ranking" pero la pregunta trata polarización en redes/NLP),
**sin** cambiar la semántica de la guarda.

## 11. Decisiones humanas pendientes

1. **Excluir o reformular** (bloqueantes): 016 (certificar `codigo_postal`);
   038/039 ya tienen candidatos concretos con estación+sensor+hora y valor
   verificado, pero requieren aprobación humana antes de dejar de excluirse.
2. **Diseño de agregados/cortes:** 002/003/005 ya usan cortes concretos y
   requieren aprobación sobre su política de actualización; 003 propone top-1;
   004 propone la fila preagregada `Total` del corte de cierre (apropiación
   4 526 836 158 739,00 COP; pagos 3 233 457 359 631,73 COP); 036 mantiene
   pendiente el agregado sensible y su guarda de privacidad.
3. **Definiciones/alcance:** 014 («consolidado» = `#TODOS`?); 024 (ETC
   departamental vs municipales); 011 (conjunto de 21 vs ancla); 029/033
   (preguntas degeneradas).
4. **Contrato (Juan Camilo + coordinador):** aprobar el esquema `acceptable_facts`
   discriminado por `fact_kind`; autorizar la migración de casos textuales a
   `TextualFact`; renombrar `pilot-048`.

## 12. Esquema `acceptable_facts` propuesto (corregido)

Cerrado, versionado, discriminado por `fact_kind`, compatible con el dominio real,
capaz de expresar varias respuestas válidas sin comodines. Cada hecho declara:
`fact_kind`; `operation` válida (matriz §6); `allowed_datasets`;
`input_constraints` (solo derivables de la pregunta); `selection_rule`;
`columns`; `value_or_set`; `tolerance` (cuantitativo, justificada);
`normalization_profile` (textual); `tie_policy`; `observed_at`; `temporal_cut` /
`data_cutoff_at`; `expected_cardinality`; `duplicate_policy`; `source_query`
reproducible. Prohibidos: `"acceptable_values": "a determinar"`, «cualquier fila
compatible», listas sin cardinalidad, tolerancias sin base, operaciones no
implementadas. Un hecho con cualquier campo sin determinar **no es aprobable**
para T-616B (por eso 016/038/039 quedan `exclude_until_resolved`).

La salida validada no conserva marcadores `<…>` ni descripciones del tipo
«conjunto de N» en lugar de valores: los `canonical_text_set` materializan la
lista oficial completa y el script exige que su longitud coincida con
`expected_cardinality`. Los candidatos bloqueados 016/038/039 también registran
los valores observados concretos; su exclusión responde a semántica/aprobación,
no a que falte rellenar un campo.

## 13. Reproducibilidad y validaciones

- `uv run python scripts/t616a_audit.py --refresh-live-evidence` → reconstruye el
  manifiesto v2 desde PostgreSQL en transacción `READ ONLY` y Socrata oficial.
- `uv run python scripts/t616a_audit.py --check` → OK (golden-v1 50/40/10,
  SHA-256 intacto, JSON válido, matriz `fact_kind`/operación consistente,
  manifiesto consistente).
- `uv run python scripts/t616a_audit.py --verify-live` → reproduce los **40/40**
  positivos y falla si cambia catálogo, esquema, cardinalidad, proyección,
  nulos, duplicados, selección, empate o hash.
- `uv run pytest -q tests/test_eval_loader.py tests/test_grounded_facts_contract.py tests/test_eval_metrics.py`
  → **52 passed**.
- `uv run pytest -q -m "not integration"` → **865 passed, 121 deselected**.
- `uv run ruff check .` y `uv run ruff format --check scripts/t616a_audit.py`
  → OK.

## 14. Confirmaciones

- `golden-v1.yaml` intacto byte a byte (SHA-256 idéntico al inicial).
- `golden-v2.yaml` **no** creado. `GOLDEN_V2_PROPOSAL.md` conserva su rango
  informativo.
- No se ejecutó ningún LLM ni el agente. No se ejecutó la suite golden.
- T-616 permanece **abierta**; T-616B y T-617 **no** iniciadas.

## 15. Deuda separada T-402

T-402 continúa abierta en `tasks.md` y no se mezcló con esta auditoría. La
recomendación es cerrarla, si procede, mediante una tarea y commit separados
que verifiquen sus propios criterios de aceptación y una corrida real; no usar
T-616A-R como evidencia sustitutiva ni iniciar ese cierre desde este alcance.
