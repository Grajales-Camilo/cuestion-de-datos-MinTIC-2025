# T-616A — Auditoría de los 50 casos de `golden-v1` para una propuesta `golden-v2`

> **DOCUMENTO NO NORMATIVO — PROPUESTA DE AUDITORÍA.**
> No modifica `golden-v1.yaml`, ni `eval/metrics.py`, ni contratos, ni el runtime.
> No crea `golden-v2.yaml`. No cierra T-616 ni inicia T-616B/T-617. Toda
> recomendación queda pendiente de aprobación humana explícita.

La matriz estructurada y canónica de esta auditoría vive en
`backend/eval/reports/t616a-case-audit.json` (esquema `t616a-case-audit-v1`).
Este informe la resume para revisión humana; ante cualquier divergencia, el JSON
y el `golden-v1.yaml` real prevalecen.

---

## 1. Veredicto ejecutivo

`golden-v1` es una **línea histórica valiosa pero no apta como suite de exactitud
determinista** en su forma actual. De los 40 casos positivos, **37 contienen al
menos una restricción oculta material**: un filtro presente en `source_url` o en
`expected_value` que no se deriva de la pregunta. El patrón dominante (23 casos)
es la pregunta subdeterminada del tipo *"¿qué X figura en el registro?"*, donde
el golden congela una fila arbitraria entre muchas compatibles. Un subconjunto
más grave (4 casos) es **incompatible**: el filtro congelado ni siquiera se ancla
en el sujeto que pide la pregunta (p.ej. `pilot-022` filtra por `administrador`
/`calzada`/`categoria` en lugar del tramo `55ST02` solicitado; `pilot-038`/`039`
exigen una observación horaria oculta entre decenas de miles de filas del día).

Hallazgo señalado: **`pilot-001` congela un valor que contradice la lectura
natural de la pregunta** — pide una tasa de deserción "alta" (argmax), pero el
máximo real verificado es Cerro de San Antonio (6.28), no Zona Bananera (2.44)
que fija el golden. Esto coincide con lo ya documentado por el propio proyecto en
`research.md` §21.

Los **10 casos negativos son correctos**: todos exigen abstención legítima y
ninguno es respondible con el catálogo estructurado. Se recomienda conservarlos
sin cambios semánticos.

Conclusión: `golden-v2` es necesario y el contrato propuesto en
`GOLDEN_V2_PROPOSAL.md` (`input_constraints`, `selection_rule`,
`acceptable_facts`, `source_urls`, `observed_at`, `data_cutoff_at`) es el marco
correcto, complementado con hechos textuales de primera clase (`TextualFact`,
`proposals/textual-claims.md` §11). **No se autoriza aún ninguna materialización.**

## 2. Rama, commit y SHA-256 de `golden-v1`

- Rama: `v2`
- Commit base (HEAD inicial y final): `71578b8af2504d4545312b0e456436bbd0cf18fb`
- SHA-256 de `backend/eval/golden/golden-v1.yaml` (inicial y final, sin cambios):
  `ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`

## 3. Método de auditoría

1. Lectura completa de `golden-v1.yaml` (50 casos) y del stack evaluador real
   (`eval/loader.py`, `eval/metrics.py`, `eval/persistence.py`).
2. Lectura de la jerarquía documental relevante: `CLAUDE.md`, `GOLDEN_V2_PROPOSAL.md`,
   `proposals/textual-claims.md`, `research.md` §§21–27, `pruebas.md` §4.2,
   `tasks.md` T-616, constitución (Art. I, II, IV, VI).
3. Para cada caso, separación explícita de cuatro superficies: pregunta literal /
   exigencia de `golden-v1` / lo derivable de la fuente oficial / lo aceptable en
   una suite futura. Ninguna restricción se dedujo de la respuesta esperada.
4. Verificación de cardinalidad **read-only contra Socrata real** (WebFetch, sin
   LLM intermedio, sin escrituras) en 12 casos clave para distinguir "dato
   disponible" de "respuesta determinada". Solo se conservaron consultas
   reproducibles y conteos, nunca volcados de filas.
5. Clasificación primaria y veredicto por caso, con 10 controles anti-sobreajuste
   por caso (campo `overfit_checks` en el JSON).
6. Revisión adversaria final (§ revisión interna) y validación automática del JSON.

## 4. Fuentes consultadas

- `golden-v1.yaml` (read-only) y stack `eval/` real.
- API pública de datos.gov.co (Socrata), read-only, sin LLM. Consultas de conteo
  y de orden para 12 casos (ver columna "socrata" en la matriz y campo
  `socrata_query` por caso).
- Documentación interna del proyecto (specs, proposals, reports históricos ya
  persistidos, usados solo como diagnóstico).

No se consultó el catálogo PostgreSQL local (no verificado en esta sesión); la
elegibilidad local y el riesgo PII se marcan como "no re-verificados" donde aplica.

## 5. Limitaciones

- La elegibilidad local, el estado del publicador y el riesgo PII de los datasets
  **no se re-verificaron** contra PostgreSQL en esta sesión; se citan de las notas
  de `golden-v1` (verificadas por su autor el 2026-07-11).
- La verificación Socrata cubre 12/40 positivos; los 28 restantes se auditaron por
  estructura de la pregunta y de la URL congelada. Los conteos exactos de los no
  verificados quedan como `missing_evidence` por caso.
- Los valores numéricos observados en Socrata reflejan el estado del portal al
  **2026-07-18** y pueden diferir del snapshot 2026-07-11 de `golden-v1` (esperado
  en agregados vivos).
- No se ejecutó el agente ni ningún LLM. No se ejecutó la suite golden.

## 6. Conteos por clasificación primaria

| Clasificación | Casos |
|---|---|
| `determined` | 8 |
| `aggregate` | 5 |
| `multi_response` | 23 |
| `incompatible` | 4 |
| `abstention` (negativos) | 10 |
| **Total** | **50** |

## 7. Conteos por recomendación (veredicto sobre `golden-v1`)

| Veredicto | Casos |
|---|---|
| `retain_semantics` | 15 (5 positivos + 10 negativos) |
| `broaden_acceptable_answers` | 9 |
| `remove_hidden_constraint` | 2 |
| `rewrite_case` | 22 |
| `convert_to_abstention` | 0 |
| `exclude_until_resolved` | 2 |
| **Total** | **50** |

## 8. Casos con filtros ocultos (37)

Todos los positivos salvo `pilot-002`, `pilot-003` y `pilot-007`. Los demás fijan
en `source_url`/`expected_value` al menos una condición no derivable de la
pregunta. Subtipos:

- **Filtro = la propia respuesta** (circular): `pilot-001` (municipio),
  `pilot-012` (`hallazgos=12`), `pilot-013`/`pilot-020`/`pilot-034` (salida
  pinneada aunque el sujeto ya la determina), `pilot-021` (`cantidad=65`),
  `pilot-029` (`fuente=Nación`), y todos los `lookup_multi`.
- **Selector no pedido**: `pilot-004` (`descripción=Funcionamiento`, `mes`),
  `pilot-005` (orden implícito), `pilot-008` (`año`), `pilot-033` (día concreto),
  `pilot-038`/`039` (estación+sensor+hora).
- **Filtro que no corresponde al sujeto**: `pilot-016` (no filtra "Rondón"),
  `pilot-022` (no filtra "55ST02").

## 9. Casos multirrespuesta (23)

`pilot-011, 012, 014, 015, 017, 018, 019, 023, 024, 025, 026, 027, 028, 029, 030,
031, 033, 035, 036, 037, 040, 041, 042`. Todos admiten varias filas compatibles
con los filtros explícitos de la pregunta; requieren `acceptable_facts` (conjunto)
o una `selection_rule` declarada. Verificados en vivo como multirrespuesta:
`pilot-015` (239 puestos en Medellín), `pilot-037` (5825 filas AMVA).

## 10. Casos con empate / desempate material (7)

- **Argmax con `tie_policy=reject` necesario**: `pilot-001`, `pilot-002`,
  `pilot-003` (el extremo puede empatar; la política debe rechazar, no elegir por
  orden incidental).
- **Selección arbitraria entre miles ≈ empate no resuelto**: `pilot-015`,
  `pilot-037`, `pilot-038`, `pilot-039`.

## 11. Casos dependientes de corte temporal (7)

`pilot-002` y `pilot-003` (agregados acumulados que crecen), `pilot-005` ("último
mes disponible" avanza), `pilot-004` (corte de cierre 2023), `pilot-008` (año de
cargue), `pilot-012` (vigencia de auditoría), `pilot-021` (año 2018 omitido).
Todos exigen `data_cutoff_at` explícito en `golden-v2`.

## 12. Casos incompatibles (4)

- `pilot-016-codigos-postales`: la URL no filtra el municipio "Rondón" solicitado.
  Veredicto `remove_hidden_constraint`; anclar en Rondón o excluir.
- `pilot-022-red-vial`: filtra `administrador/calzada/categoría` en vez del tramo
  `55ST02`. Veredicto `remove_hidden_constraint`.
- `pilot-038-precipitacion`: 74 690 observaciones el 2019-02-11; exige
  estación+sensor+hora ocultos. Veredicto `exclude_until_resolved`.
- `pilot-039-temperatura`: 14 734 observaciones el 2020-01-21; mismo patrón.
  Veredicto `exclude_until_resolved`.

## 13. Negativos revisados (10)

Los 10 son guardas correctas y se recomienda `retain_semantics`. Clases de
incapacidad: predicción futura (`009`, `043`), causalidad sin diseño (`010`,
`044`), privacidad/datos personales (`045`), tiempo real (`046`),
contrafactual/simulación (`047`), NLP/redes no estructurado (`048`), consejo
clínico individual (`049`), dato inexistente (`050`). Cada uno especifica
`expected_status=no_evidence` y qué constituiría fabricación (JSON,
`negative_expectation`).

Observación menor (no bloqueante): el `case_id` `pilot-048-negativo-ranking-corrupcion`
no describe su pregunta real (polarización en redes / NLP). Es una discrepancia de
etiqueta, no de contenido; conviene renombrar en `golden-v2` sin alterar la guarda.

## 14. Matriz resumida de los 50 casos

Columnas: id · tipo · dataset · clasificación · veredicto · filtro_oculto ·
socrata_verif · confianza · revisión_humana.

| case_id | t | dataset | clasificación | veredicto | oculto | socrata | conf | rev |
|---|---|---|---|---|---|---|---|---|
| pilot-001-educacion-magdalena | pos | c4qb-ek68 | aggregate | rewrite_case | si | si | high | si |
| pilot-002-seguridad-homicidios | pos | m8fd-ahd9 | aggregate | broaden_acceptable_answers | no | si | high | si |
| pilot-003-salud-vigilancia | pos | 4hyg-wa9d | aggregate | broaden_acceptable_answers | no | si | high | si |
| pilot-004-justicia-presupuesto | pos | f4a5-ab9q | aggregate | rewrite_case | si | si | high | si |
| pilot-005-empleo-publico | pos | h8rs-jxum | determined | broaden_acceptable_answers | si | si | high | si |
| pilot-006-planta-entidad | pos | fvq4-wwtz | determined | retain_semantics | si | no | medium | no |
| pilot-007-desercion-antioquia | pos | ji8i-4anb | determined | retain_semantics | no | si | high | no |
| pilot-008-residuos-villamaria | pos | d7pt-p5fi | determined | broaden_acceptable_answers | si | no | medium | si |
| pilot-011-cooperacion-minas | pos | 2d3i-f9wd | multi_response | rewrite_case | si | no | high | si |
| pilot-012-control-fiscal | pos | wasc-xi4h | multi_response | rewrite_case | si | no | medium | si |
| pilot-013-app-dnp | pos | tmk8-iihq | determined | retain_semantics | si | si | high | no |
| pilot-014-calidad-agua | pos | nxt2-39c3 | multi_response | rewrite_case | si | no | low | si |
| pilot-015-puestos-electorales | pos | mv2e-prx5 | multi_response | rewrite_case | si | si | high | si |
| pilot-016-codigos-postales | pos | ixig-z8b5 | incompatible | remove_hidden_constraint | si | no | high | si |
| pilot-017-transporte-carretera | pos | eh75-8ah6 | multi_response | rewrite_case | si | no | high | si |
| pilot-018-transporte-ferreo | pos | 7atu-2b28 | multi_response | broaden_acceptable_answers | si | no | high | si |
| pilot-019-trafico-portuario | pos | 5r3g-zv5z | multi_response | rewrite_case | si | no | high | si |
| pilot-020-divipola | pos | gdxc-w37w | determined | retain_semantics | si | no | medium | no |
| pilot-021-sensibilizacion-valle | pos | 52mk-e3ug | aggregate | rewrite_case | si | si | high | si |
| pilot-022-red-vial | pos | ie7y-asdn | incompatible | remove_hidden_constraint | si | no | high | si |
| pilot-023-eva-agricultura | pos | 2pnw-mmge | multi_response | rewrite_case | si | no | high | si |
| pilot-024-educacion-etc | pos | sras-4t5p | multi_response | broaden_acceptable_answers | si | no | medium | si |
| pilot-025-educacion-municipal | pos | nudc-7mev | multi_response | rewrite_case | si | no | high | si |
| pilot-026-paridad-genero | pos | f5ai-gvqt | multi_response | rewrite_case | si | no | high | si |
| pilot-027-paridad-etnica | pos | mxqg-ytrw | multi_response | rewrite_case | si | no | high | si |
| pilot-028-presupuesto-nacion | pos | xjxk-qhsc | multi_response | broaden_acceptable_answers | si | no | medium | si |
| pilot-029-gastos-nacion | pos | 5phs-yqfw | multi_response | rewrite_case | si | no | high | si |
| pilot-030-conciliadores | pos | hjfm-ynaz | multi_response | rewrite_case | si | no | high | si |
| pilot-031-desmovilizaciones | pos | gkbc-gw7x | multi_response | broaden_acceptable_answers | si | no | medium | si |
| pilot-032-situacion-penitenciaria | pos | d76u-8x6w | determined | broaden_acceptable_answers | si | no | low | si |
| pilot-033-gas-natural-vehicular | pos | v8jr-kywh | multi_response | rewrite_case | si | no | high | si |
| pilot-034-fncer | pos | vy9n-w6hc | determined | retain_semantics | si | no | medium | no |
| pilot-035-afiliaciones | pos | 5xue-fyeb | multi_response | rewrite_case | si | no | high | si |
| pilot-036-delitos-sexuales | pos | bz43-8ahq | multi_response | rewrite_case | si | no | high | si |
| pilot-037-calidad-aire | pos | kekd-7v7h | multi_response | rewrite_case | si | si | high | si |
| pilot-038-precipitacion | pos | s54a-sgyg | incompatible | exclude_until_resolved | si | si | high | si |
| pilot-039-temperatura | pos | sbwg-7ju4 | incompatible | exclude_until_resolved | si | si | high | si |
| pilot-040-suspensiones-servicio | pos | cqs7-ti4m | multi_response | rewrite_case | si | no | high | si |
| pilot-041-eca | pos | y97c-tfd9 | multi_response | rewrite_case | si | no | high | si |
| pilot-042-disposicion-final | pos | 84tn-nnhf | multi_response | rewrite_case | si | no | high | si |
| pilot-009-negativo-proyeccion-futura | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-010-negativo-causalidad-barrial | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-043-negativo-pronostico-clima | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-044-negativo-causalidad-politica | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-045-negativo-dato-personal | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-046-negativo-tiempo-real | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-047-negativo-contrafactual | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-048-negativo-ranking-corrupcion | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-049-negativo-diagnostico-medico | neg | - | abstention | retain_semantics | no | no | high | no |
| pilot-050-negativo-dato-inexistente | neg | - | abstention | retain_semantics | no | no | high | no |

**Localización rápida:**
- Aprobables casi sin cambio (`retain_semantics`, positivos): `pilot-006, 007,
  013, 020, 034` (más los 10 negativos).
- Requieren ampliar respuestas (`broaden_acceptable_answers`): `pilot-002, 003,
  005, 008, 018, 024, 028, 031, 032`.
- Filtros ocultos: los 37 marcados "si".
- Incompatibilidades: `pilot-016, 022, 038, 039`.
- Baja confianza: `pilot-014, pilot-032`.

## 15. Fichas detalladas de cada caso

La ficha estructurada completa de los 50 casos (identidad, restricciones,
fuente, derivabilidad, cardinalidad, `proposed_acceptable_facts`,
`overfit_checks`, confianza y recomendación) está en
`t616a-case-audit.json`. A continuación, el hallazgo load-bearing por caso.

**Positivos**

- **pilot-001**: "tasa alta" ⇒ argmax; el máximo real es Cerro de San Antonio
  6.28, no Zona Bananera 2.44 (verificado). Reescribir como `argmax_label`.
- **pilot-002**: argmax por departamento correcto; Valle estable, total deriva.
  Fijar `data_cutoff_at`.
- **pilot-003**: argmax/top-N por evento correcto; "eventos" plural sugiere top-N;
  total deriva.
- **pilot-004**: 18 filas para `a_o=2023`+`sector justicia` (verificado); el golden
  añade `Funcionamiento`+`mes` ocultos. Declarar corte y categoría.
- **pilot-005**: "último mes" = 2026-03 (764/719) verificado; depende de orden
  implícito. Declarar `selection_rule`=máx fecha + `data_cutoff_at`.
- **pilot-006**: entidad nombrada ⇒ determinado; verificar unicidad de fila.
- **pilot-007**: fila única confirmada en vivo (3.97). Migrar tal cual.
- **pilot-008**: solo el municipio es explícito; año y empresa ocultos. Declarar año
  o admitir varias filas.
- **pilot-011**: "qué intervención" es abierto; codigo/fecha/objetivo son la
  respuesta. Conjunto o regla.
- **pilot-012**: filtra por el resultado (`hallazgos=12`). Determinar por vigencia.
- **pilot-013**: `PRY00062` ⇒ fila única (verificado). Migrar como `TextualFact`
  `direct_text`, no `count=1`.
- **pilot-014**: "municipio consolidado" sin definición operativa; el golden fija
  `#TODOS`. Baja confianza.
- **pilot-015**: 239 puestos en Medellín (verificado). Conjunto canónico.
- **pilot-016**: **incompatible**: la URL no filtra "Rondón". Anclar o excluir.
- **pilot-017/019/023/025/026/027/030/035/040/041/042**: patrón "qué X figura";
  fila arbitraria. Conjunto (`canonical_text_set`/`value_presence`) o regla.
- **pilot-018**: fecha explícita, pero concesión/operador ocultos. Ampliar a
  conjunto de operadores del día.
- **pilot-020**: `Medellín ⇒ 05001` determinado; quitar pinning; verificar
  granularidad (centros poblados).
- **pilot-021**: 2 filas para Alcalá/Enero (65 y 13, verificado); filtra
  `cantidad=65` y omite el año 2018. Anclar año + regla (suma o fila única).
- **pilot-022**: **incompatible**: filtra por salida, no por el tramo `55ST02`.
- **pilot-024**: "ETC de Antioquia" ambiguo (dpto vs municipales). Ampliar.
- **pilot-028/031**: salida pinneada bajo un filtro temático; ampliar a conjunto.
- **pilot-029**: filtra `fuente=Nación` (la respuesta). Reescribir.
- **pilot-032**: "qué situación" puede tener varios estados; quitar pinning del
  estado. Baja confianza (cardinalidad no verificada).
- **pilot-033**: solo el mes se pide; el golden fija un día. Conjunto de fechas.
- **pilot-034**: proyecto nombrado (Jepirachi) ⇒ determinado; quitar pinning.
- **pilot-036**: fecha no determina un único departamento; caso sensible ⇒ agregado
  por departamento con guarda de privacidad.
- **pilot-037**: 5825 filas AMVA (verificado); estación arbitraria. Conjunto.
- **pilot-038**: 74 690 observaciones el día (verificado); estación+sensor+hora
  ocultos. **Excluir hasta resolver**.
- **pilot-039**: 14 734 observaciones el día (verificado); mismo patrón.
  **Excluir hasta resolver**.

**Negativos (009, 010, 043–050)**: guardas correctas; `retain_semantics`;
`expected_status=no_evidence`; ver `negative_expectation` en el JSON.

## 16. Lista priorizada de decisiones humanas

**Prioridad 1 — Incompatibilidades y contradicción de respuesta (bloqueantes):**
1. `pilot-001`: decidir "alta" = argmax vs umbral; NO conservar Zona Bananera 2.44.
2. `pilot-022` y `pilot-016`: anclar la consulta en el sujeto (`55ST02` / Rondón) o
   excluir del alcance de exactitud.
3. `pilot-038` y `pilot-039`: excluir de exactitud o reformular con estación/hora, o
   convertir a `value_presence`.

**Prioridad 2 — Reescrituras estructurales (22 `rewrite_case`):**
4. Definir política general para el patrón "¿qué X figura?" (23 casos):
   `canonical_text_set`/`value_presence` vs `selection_rule` con orden total.
5. `pilot-004` y `pilot-021`: declarar corte temporal y regla de agregación;
   `pilot-021` además re-incluir el año 2018.

**Prioridad 3 — Ampliaciones y cortes (9 `broaden`):**
6. Fijar `data_cutoff_at` para agregados vivos (`pilot-002/003/005`).
7. Verificar cardinalidad de los 28 casos no verificados en vivo antes de congelar.

**Prioridad 4 — Contrato y decisiones de método (requieren Juan Camilo + coordinador):**
8. Aprobar/ajustar el esquema `acceptable_facts` discriminado por `fact_kind`.
9. Autorizar (o no) que casos determinados textuales migren a `TextualFact`.
10. Renombrar `pilot-048` (etiqueta engañosa) en `golden-v2`.

## 17. Propuesta de esquema para T-616B

Sobre el contrato de `GOLDEN_V2_PROPOSAL.md`, cada caso positivo declararía:

```yaml
- id: <case_id>
  seed: <int>
  case_type: positive
  question: <literal>
  category: <tipología>
  input_constraints: [<condiciones literales de la pregunta>]
  selection_rule:            # null solo si input_constraints identifican 1 fila
    kind: <unique_row|argmax_label|argmin_label|first_by_validated_order|
           category_selection|aggregate_sum|canonical_text_set|value_presence>
    order_by: [<col ...>]    # requerido para first_by_validated_order
    metric_column: <col>     # requerido para argmax/argmin/aggregate
    tie_policy: reject
  acceptable_facts:          # 1..N; pertenencia, no igualdad con fila arbitraria
    - fact_kind: quantitative|textual
      allowed_dataset: <id>
      operation: <direct|derived|argmax_label|...|direct_text|value_presence|
                  category_selection|canonical_text_set>
      columns: [<col ...>]
      constraints: [<solo input_constraints + selection_rule>]
      value_or_set: <valor | conjunto>
      tolerance: <solo si sustantiva>          # cuantitativo
      normalization_profile: text-es-v1        # textual
  source_urls: [<consultas que aplican SOLO input_constraints + selection_rule>]
  observed_at: <ISO-8601>
  data_cutoff_at: <corte del congelamiento>
```

Negativos: `case_type: negative`, `expected_status: no_evidence`,
`incapacity_class`, `abstention_reason`, `would_be_fabrication`. El evaluador
comprobaría pertenencia a `acceptable_facts` y que las `source_urls` no contengan
filtros ausentes de `input_constraints`/`selection_rule`.

## 18. Confirmación: no se creó `golden-v2`

No se creó `backend/eval/golden/golden-v2.yaml` ni ninguna suite ejecutable. Los
únicos artefactos son este informe, `t616a-case-audit.json` y el script read-only
`backend/scripts/t616a_audit.py`. `GOLDEN_V2_PROPOSAL.md` conserva su rango
informativo (no se modificó su naturaleza).

## 19. Confirmación: `golden-v1` intacto byte a byte

SHA-256 recalculado al cierre:
`ab546062767ce2046508489c169a270ae00ceb1515ff67bf92d472404630ff72`, idéntico al
inicial. `git diff` no reporta cambios en `golden-v1.yaml`.

## 20. Próxima acción exacta

Entregar esta auditoría a Juan Camilo y al agente coordinador para revisión.
**No** iniciar T-616B (materialización de `golden-v2.yaml`) ni T-617 hasta
aprobación normativa explícita, caso por caso, de las decisiones de §16. T-616
permanece abierta.

---

### Nota de revisión interna (adversaria)

Se revisaron los 50 casos buscando: filtros copiados de `source_url` (37
detectados y marcados), respuestas únicas sin desempate (argmax en `001/002/003`,
selección arbitraria en `015/037/038/039`), valores observados convertidos en
norma (rechazado: ninguna respuesta normativa se tomó de una corrida del agente;
las corridas históricas solo se usaron como diagnóstico), fechas/cortes no pedidos
(`004/005/008/021/033/038/039`), tolerancias arbitrarias (las tolerancias
propuestas se limitan a métricas numéricas con base sustantiva), datasets
favorecidos por historial (no: cada dataset se evaluó por la pregunta y la
fuente), hechos textuales representados como conteos (`013` señalado
explícitamente), positivos que deberían ser abstenciones (ninguno reclasificado a
negativo; `038/039` van a `exclude_until_resolved`, no a abstención), negativos
respondibles con datos estructurados (ninguno) y datos cambiados desde `golden-v1`
(agregados vivos, documentado). No se redujo el número de casos.
