# T-617B-C1 — Auditoría forense de golden-v1 `b0d38f87-d2d3-4bc8-80ae-b197e278d328`

> **Revisión v2 — corrección documental exigida por Juan Camilo tras auditoría independiente.**
> No se ejecutó Gemini, Socrata ni ninguna evaluación nueva. PostgreSQL sólo en modo lectura
> (relecturas puntuales de `quantitative_claims`/`final_answer` para las dos reclasificaciones
> señaladas). No se modificó código, pruebas, specs, contratos, `golden-v1.yaml`, `golden-v2.yaml`
> ni `expected_facts`. No se creó commit, push ni PR. Único artefacto tocado: este informe.

- Rama: `feat/t617-gate-preflight`
- HEAD auditado: `597ef73e4e018ddba1a9d61faee6dcad97edce26`
- Corrida auditada: `eval_runs.id = b0d38f87-d2d3-4bc8-80ae-b197e278d328`
- Fuentes reconciliadas: `backend/eval/reports/t616a-golden-v2-audit.md` (T-616A-R, auditoría
  verificada caso por caso de los 40 positivos de `golden-v1` contra PostgreSQL y Socrata reales),
  `backend/eval/reports/t616b-golden-v2-materialization.md` (T-616B, cierre y materialización de
  `golden-v2.yaml`), y `backend/eval/golden/golden-v2.yaml`.

---

## 0. Corrección de método frente a la versión previa de este informe

La versión anterior de este informe clasificó `pilot-001`, `pilot-014`, `pilot-022`, `pilot-031` y
`pilot-034` sin cruzar contra T-616A-R/T-616B, que ya habían auditado esos mismos 40 positivos con
verificación real contra PostgreSQL y Socrata. Eso produjo tres tipos de error:

1. **Prescribir como "verdad normativa" una interpretación de la pregunta que T-616A-R ya
   descartó explícitamente** (`pilot-001`: usar `ORDER BY` como corrección "correcta" cuando
   T-616A-R estableció que "tasa alta" no autoriza un argmax silencioso).
2. **Exigir del agente una columna que la pregunta no pide**, confundiendo "no reconstruye el
   `expected_fact` completo" con "no responde la pregunta" (`pilot-031`, `pilot-034`).
3. **Reabrir como "requiere decisión humana" un punto que T-616A-R ya verificó con evidencia
   reproducible** (`pilot-022`: la consulta correcta —`codigo_tramo='55ST02'`— sí produce
   determinísticamente `administrador=1, calzada=1, categoria=2`, documentado y reproducible vía
   `t616a_audit.py --verify-live`).

Esta versión corrige las cinco clasificaciones, reconcilia los 15 casos `expected_fact_not_found`
contra el estado de decisión real de cada uno en T-616A-R (§5.2, §7, §9, §11), recalcula los
escenarios de tasa positiva, sustituye la propuesta de `pilot-007` por una que preserva el bloqueo
de la respuesta, y precisa la decisión normativa pendiente sobre la puerta `golden-v1`.

---

## 1. Verificación directa del reporte persistido (sin cambios respecto de la versión previa)

`eval_runs` confirma: `success_rate=0.375`, `claims_coverage=1.0`, `claims_reproducible=1.0`,
`orphan_figures_count=0`, `recall_at_10=1.0`, `fabrication_count=2`, `latency_simple_p95_ms=45616`,
`latency_multistep_p95_ms=63642`, `latency_p50_ms=17890`, `latency_p95_ms=53663`,
`avg_cost_usd=0.012233`. `eval_case_results` contiene exactamente 50 filas, mapeadas 1:1 a los 50
`pilot-XXX` de `golden-v1.yaml`. El reporte markdown original es fiel a la base de datos.

---

## 2. Semántica normativa de la puerta congelada `golden-v1` (resuelta por jerarquía documental)

La mayoría de las decisiones sustantivas sobre las anclas ambiguas de estos 15 casos **ya se
tomaron** durante T-616A-R y se **materializaron** en `golden-v2.yaml` (T-616B), verificado en
`golden-v2.yaml:667` para `pilot-011` y consistente con `t616b-golden-v2-materialization.md:21-38`
para `pilot-003, 004, 011, 012, 014, 024, 029, 033, 036, 038, 039`. Esas decisiones **no son
"pendientes"** — están resueltas para `golden-v2`. Lo que sí queda es determinar cómo debe
interpretarse la puerta obligatoria `golden-v1`, que sigue congelada y contiene esas mismas anclas
sin la corrección de v2 aplicada.

**Esta cuestión queda resuelta aplicando la jerarquía documental del repositorio, sin necesidad de
una decisión adicional de Juan Camilo**:

- `pruebas.md §4.4` (`specs/001-cuestion-de-datos-v2/pruebas.md:254`) es explícito: `golden-v1.yaml`
  "está congelado y continúa ejecutándose como regresión histórica". No es la suite de aceptación
  normativa de la migración; es una regresión que corre en paralelo hasta la retirada del legado
  (`pruebas.md:257`).
- La puerta normativa de migración (`pruebas.md:259-269`) exige explícitamente `golden-v2 ≥ 80% con
  aprobación normativa`, **no** `golden-v1 ≥ 80%`. `golden-v1` no aparece como umbral de esa puerta.
- El orden de tareas (`tasks.md:586`) exige ejecutar `golden-v1` antes que `golden-v2`, pero no
  condiciona la ejecución de `golden-v2` a que `golden-v1` apruebe.

**Conclusión normativa**: `golden-v1` permanece intacto, no se le añaden excepciones por caso ni se
reinterpreta su resultado dentro de `_verify_expected_facts`, y **produce su veredicto mecánico
histórico sin modificación: FAIL, 15/40**. Ese resultado se registra como regresión histórica, tal
como exige `pruebas.md §4.4`, y no bloquea por sí mismo la ejecución de `golden-v2` cuando esa
corrida sea autorizada — aunque **no la autoriza tampoco**: siguen abiertos, con independencia de
`golden-v1`, los defectos reales de código identificados en esta auditoría (los dos casos negativos
con claims irrelevantes, `pilot-007`, las fabricaciones, el costo incompleto, la latencia simple y
los fallos positivos reales de agente — sección 9).

---

## 3. Los 15 casos `expected_fact_not_found`, reconciliados con T-616A-R

`_verify_expected_facts` (`backend/eval/metrics.py:361-387`) exige que al menos una fila cruda
devuelta por SoQL contenga **todas** las claves de `expected_value` dentro de tolerancia,
reconstruidas a partir del alias `AS dim_N` del propio `SELECT`. Si una columna de `expected_value`
nunca fue proyectada (aunque esté en el `WHERE`), la fila no tiene esa clave y el match falla. Esa
es la causa mecánica común; el origen de fondo se reclasifica en seis categorías tras la
reconciliación:

### 3.1 Error real y confirmado del agente (2 casos — sin relación con la semántica de golden-v1)

| Caso | Qué hizo el agente | Por qué es un error confirmado, no una cuestión golden |
|---|---|---|
| `pilot-021-sensibilizacion-valle` | `SELECT count(*) AS metric_count_1 WHERE a_o=2018 AND mes='Enero' AND municipio='ALCALÁ'` | T-616A-R clasifica este caso como `determined`, `ready`, sólo con corrección de anclaje de año — no hay ambigüedad de golden aquí. La pregunta pide la **cantidad de personas** (columna `cantidad`); el agente ejecutó un `COUNT(*)` de filas en su lugar. Confusión de agregación, no de interpretación de la pregunta. |
| `pilot-022-red-vial` | `SELECT codigo_tramo, grupo_administrador_vial, nombre_tramo, nombre_ruta WHERE codigo_tramo='55ST02'` | **Reclasificado.** T-616A-R (`golden_v1_evidence_validity=wrong_anchor`, `case_compatibility=compatible`, `determined`) verificó en vivo que `codigo_tramo='55ST02'` **sí** produce determinísticamente 3 filas idénticas con `administrador=1, calzada=1, categoria=2` — exactamente el `expected_value`. El ancla de la pregunta (`codigo_tramo`) es correcta y ya está verificada; el agente la usó correctamente en el `WHERE`, pero proyectó columnas distintas (`grupo_administrador_vial`, `nombre_tramo`, `nombre_ruta`) en lugar de `administrador`/`calzada`/`categoria`. Es un déficit de selección de columnas sobre un ancla ya resuelta — no requiere nueva decisión humana. |

### 3.2 Falso negativo confirmado del evaluador (mecánica de `_verify_expected_facts`) (1 caso puro + 1 mixto)

| Caso | WHERE (prueba determinista) | SELECT (omite la columna) | Evidencia de que el valor correcto se observó | Estado en T-616A-R |
|---|---|---|---|---|
| `pilot-028-presupuesto-nacion` | `recurso_presupuestal='DONACIONES'` | No proyecta `recurso_presupuestal` | 8/17 filas devueltas tienen exactamente `fuente_de_financiación='Nación'` + `situación_de_fondos='CSF'` | `bounded_set(2/2)`, `ready` — sin cuestión golden pendiente |
| `pilot-029-gastos-nacion` | `anio=2019 AND nombremes='Enero'` | No proyecta `anio` ni `nombremes` | `fuente='Nación'` aparece en las 12 filas devueltas | **`needs_human_decision`** (T-616A-R §5.2, "pregunta degenerada", §11.3) — mixto: además de la falla mecánica del verificador, la pregunta misma está señalada como pendiente de decisión sobre su adecuación |

Instrucción original respetada: **no se considera automáticamente ausente un hecho ya demostrado
por un filtro determinista del SoQL**. No se propone corregir la regla del verificador en esta
auditoría; queda como candidato de incremento (sección 8).

### 3.3 Falso negativo candidato / `expected_fact` excesivamente específico frente a lo que la pregunta pide (2 casos — reclasificados)

| Caso | Lo que pide la pregunta | Lo que exige `expected_value` | Por qué es sobreespecificación, no error del agente |
|---|---|---|---|
| `pilot-031-desmovilizaciones` | **Reclasificado.** "¿Qué **tipo** de desmovilización se registra para Nariño?" — sólo pide `tipo`. | `categoria='Desmovilizados'` además de `tipo='Individual'` | T-616A-R clasifica el caso como `bounded_set(2)`, `ready`: el dataset tiene exactamente 2 `tipo` válidos para Nariño (`Individual`, `Colectiva`). Releído directamente de `quantitative_claims`: el agente devolvió **ambos** (`departamento=NARIÑO; tipo=Individual` y `departamento=NARIÑO; tipo=Colectiva`), una respuesta más completa que el `expected_fact` de un solo valor. `categoria` no fue pedida por la pregunta y es una exigencia adicional del ancla congelada de v1. |
| `pilot-034-fncer` | **Reclasificado.** "¿Qué **capacidad instalada** se reporta para el proyecto eólico Jepirachi?" — pide la capacidad. | `capacidad=18.42` **y** `tipo='Eólico'` | T-616A-R mantiene este caso `determined`, `retain`, `ready` (sin marcarlo como error). Releído directamente de `quantitative_claims`: el claim de capacidad tiene `raw_value` correspondiente a `18.42` con `display_value="18"` (redondeo de presentación) — la magnitud es correcta y el resumen final dice literalmente "La capacidad reportada... es de 18". El agente respondió la pregunta con la cifra correcta; sólo no proyectó `tipo`, que la pregunta ya nombra en su propio enunciado ("proyecto eólico") y no es una dimensión adicional pedida como respuesta. Separar "no reconstruye el `expected_fact` completo" de "no responde la pregunta": aquí sólo aplica lo primero. |

### 3.4 Resuelto en `golden-v2` mediante T-616B — no aplicable retroactivamente a `golden-v1` congelado (4 casos)

**Corrección respecto de la versión previa**: estos cuatro casos no tienen ya una "decisión humana
pendiente" en sentido estricto — T-616B (`t616b-golden-v2-materialization.md:21-38`) documenta que
**"se aprobaron las decisiones abiertas de T-616A-R"** para `pilot-011`, `pilot-014` y
`pilot-036`, materializándolas en `golden-v2.yaml`. La decisión normativa ya fue tomada; lo que
falta no es tomarla, sino que **no es aplicable retroactivamente** a `golden-v1.yaml`, que
permanece congelado por instrucción explícita (sección 2).

| Caso | Decisión ya aprobada en T-616B | Por qué no cierra el fallo en `golden-v1` |
|---|---|---|
| `pilot-011-cooperacion-minas` | "conjunto canónico completo de intervenciones" (`t616b:25`), materializado como `bounded_set(21)` en `golden-v2.yaml:667-684` (21 códigos verificados) | `golden-v1.yaml` conserva su ancla original de una sola fila; la aprobación de v2 no reescribe v1 |
| `pilot-014-calidad-agua` | "registro consolidado identificado explícitamente con `#TODOS`" (`t616b:27`) | Igual: la definición de "consolidado" ya está resuelta para v2, pero v1 sigue sin esa definición en su `expected_fact` congelado |
| `pilot-036-delitos-sexuales` | "conteo agregado por departamento, sin exponer filas sensibles" (`t616b:31`) | Igual, más la omisión mecánica de `cod_depto` en el `SELECT` del agente (déficit de columnas, análogo a `pilot-022`), que persiste con independencia de la resolución golden |

### 3.5 Resuelto en `golden-v2` mediante T-616B — bloqueo formal de `golden-v1` sin decisión adicional (3 casos)

**Corrección respecto de la versión previa**: igual que en 3.4, T-616B ya resolvió estos tres casos
para `golden-v2` (`pilot-038`/`pilot-039`: "estación, sensor y hora se incorporan literalmente a
cada pregunta; dejan de ser filtros ocultos", `t616b:32-33`). **Corrección adicional exigida por el
auditor independiente**: `pilot-016` también quedó resuelto en `golden-v2`, no sólo bloqueado.
T-616A-R lo dejó en `exclude_until_resolved` por la ambigüedad `noid`/`codigo_postal` y el formato
`153.42`/`153.427`, pero T-616B resolvió esa decisión mediante la presentación conjunta del valor
publicado y su forma canónica oficial: `golden-v2.yaml:1051-1084` define la pregunta reescrita
(filas urbana y rural de Rondón, Boyacá), conserva los valores publicados por Socrata (`153.42`
urbano, `153.427` rural) y exige reportar también sus formas canónicas oficiales de seis dígitos
(`153420`/`153427`), con la fuente del CSV oficial 4-72 y su huella SHA-256
(`t616b-golden-v2-materialization.md:35-38`). Esa resolución **existe solamente en `golden-v2` y no
se aplica retroactivamente a `golden-v1`**, cuyo `expected_fact` congelado sigue anclado a
`noid=877` sin la doble representación urbana/rural ni la forma canónica. Ninguno de los tres casos
es ya una decisión humana nueva pendiente sobre el caso en sí — es, de nuevo, la no aplicabilidad
retroactiva a `golden-v1` congelado.

| Caso | Estado en T-616A-R/T-616B | Motivo del bloqueo en `golden-v1` |
|---|---|---|
| `pilot-016-codigos-postales` | T-616A-R: `exclude_until_resolved` (`noid`≠`codigo_postal`; 2 filas legítimas, 877 urbano/878 rural). **Resuelto en T-616B**: `golden-v2.yaml:1051-1084` materializa ambas filas con valor publicado y forma canónica oficial de seis dígitos | `golden-v1.yaml` conserva el ancla original `noid=877` de una sola fila, sin la doble representación urbana/rural ni la forma canónica; la resolución de v2 no es retroactiva |
| `pilot-038-precipitacion` | Resuelto en `golden-v2` (`t616b:32-33`) con estación/sensor/hora explícitos en la pregunta | `golden-v1.yaml` conserva la pregunta original sin esos discriminantes; la resolución no es retroactiva |
| `pilot-039-temperatura` | Igual que `pilot-038` | Igual |

### 3.6 Indeterminado — ancla de golden-v1 ya diagnosticada como no derivable de la pregunta, sin nueva decisión sustantiva pendiente (3 casos)

| Caso | Diagnóstico de T-616A-R | Por qué no se prescribe una corrección normativa aquí |
|---|---|---|
| `pilot-001-educacion-magdalena` | `multi_response`/`ambiguous`, `rewrite_case`: "«tasa alta» no define umbral ni autoriza un argmax silencioso"; el máximo real verificado es Cerro de San Antonio (6.28), **no** Zona Bananera (2.44, el ancla de v1) | **Se retira** la prescripción previa de "ordenar por tasa_de_deserción como verdad normativa" — T-616A-R estableció expresamente que esa inferencia es artificial. Tanto el ancla de v1 como la fila arbitraria del agente son, por distintas razones, no verificables contra una respuesta única determinada por la pregunta tal como está escrita hoy en v1 |
| `pilot-037-calidad-aire` | `rewrite (conteo, 61 estaciones)`, `ready` — 61 estaciones AMVA válidas, por encima del límite duro de `canonical_text_set` (50) | La pregunta no distingue entre estaciones; ya diagnosticado como objetivo de reescritura a conteo, no como error de ejecución |
| `pilot-041-eca` | `rewrite (anclar empresa)`, `ready` — la pregunta usa "una estación" sin nombrar cuál | Mismo patrón: ancla ausente en la pregunta, ya diagnosticada, pendiente sólo de materializar la reescritura (ya hecha en v2, no aplicable a v1 congelado) |

---

## 4. Los 5 `budget_exceeded` y los 6 `evidence_not_eligible` (sin cambios respecto de la versión previa — no objetados por la auditoría independiente)

### `budget_exceeded` (positivos, dataset esperado siempre en rank 1)

| Caso | Rank esperado | Candidatos intentados | `stop_reason` | Llamadas LLM |
|---|---:|---:|---|---:|
| `pilot-008-residuos-villamaria` | 1 | 1 | `PLAN_REPAIR_BUDGET_EXCEEDED` | 4 |
| `pilot-012-control-fiscal` | 1 | 8 | `CANDIDATE_BUDGET_EXCEEDED` | 9 |
| `pilot-013-app-dnp` | 1 | 1 | `PLAN_REPAIR_BUDGET_EXCEEDED` | 4 |
| `pilot-017-transporte-carretera` | 1 | 3 | `PLAN_REPAIR_BUDGET_EXCEEDED` | 6 |
| `pilot-033-gas-natural-vehicular` | 1 | 4 | `LLM_BUDGET_EXCEEDED` | 10 |

En los 5 casos el dataset correcto se localiza primero; el agotamiento ocurre en el ciclo de
reparación de plan o en el presupuesto de candidatos/LLM. Limitación real de eficiencia del
planificador, no de recuperación ni de semántica golden.

### `evidence_not_eligible` (6 casos: 4 positivos + los 2 negativos de la sección 5)

`pilot-024`, `pilot-025`, `pilot-026`, `pilot-027`: el dataset esperado fue intentado (rank 1–2)
pero el `accepted_dataset_id` quedó en `None`, con repliegue a un dataset distinto (`ji8i-4anb`,
reusado en los cuatro casos), clasificado `eligible/alta` (score 91–100) porque la elegibilidad
mide **calidad de datos**, no **pertinencia temática**. Ninguno de estos cuatro está señalado por
T-616A-R como caso golden ambiguo (`pilot-024` sí figura en `needs_human_decision`, pero por
alcance de "ETC departamental vs municipales", no por el comportamiento del repliegue del agente
que aquí se documenta) — el defecto de repliegue-a-dataset-irrelevante es independiente de la
semántica golden y se mantiene como hallazgo de agente.

---

## 5. `pilot-044-negativo-causalidad-politica` y `pilot-048-negativo-ranking-corrupcion`

Sin cambios respecto de la versión previa (no objetados por la auditoría independiente). Ambos
casos terminaron `status_final=completed` (no `no_evidence`) y contribuyen a `fabrication_count=2`.

- **pilot-044**: candidato aceptado `ixig-z8b5` (códigos postales), conectado semánticamente vía
  "barrio" (`barrios_contenidos_en_el`), sin relación con pobreza o política pública. El resumen en
  prosa es correcto; el pipeline estructurado igual generó ~10 claims mecánicos de tipo `lookup`.
- **pilot-048**: candidato aceptado `ji8i-4anb` (deserción escolar), sin relación con redes sociales
  o polarización. Mismo patrón.

**Punto genérico del flujo donde debió producirse la abstención**: no existe, entre
`candidate_selection`/`execute_query` y `synthesize`, un gate de pertinencia semántica de la
evidencia frente a la pregunta. El resumen de texto libre razona correctamente, pero **después**
de que el pipeline estructurado ya generó claims desde evidencia sin relación temática. Nota:
`golden-v2.yaml:665-666` confirma que la guarda negativa de estos casos "sigue vigente" — no hay
cuestión golden pendiente aquí, es puramente un defecto de flujo del agente.

---

## 6. `pilot-007-desercion-antioquia`

Reconstruido desde `agent_run_events` (sin cambios en los hechos observados respecto de la versión
previa; se corrige la interpretación y la propuesta de solución):

```
step 6 execute_query  → "plan validado listo para T5", queries=1 (la consulta SÍ se ejecutó con éxito)
step 7 synthesize     → "claims aceptados listos"
evento 8 (error)      → code=INTERNAL, retryable=false,
                         message_dev="síntesis contiene cifras huérfanas: ('16',)",
                         message_user="Ocurrió un error inesperado durante la investigación."
```

**Corrección aceptada del auditor independiente**: el bloqueo de la respuesta ante una cifra sin
respaldo **no debe degradarse a advertencia**. El código reintenta la síntesis deliberadamente
hasta el límite configurado y, si persiste una cifra huérfana, bloquea la respuesta — esa severidad
es la garantía contra cifras fabricadas y debe conservarse intacta.

El defecto real, delimitado con la evidencia disponible, es exclusivamente de **clasificación y
persistencia**, no de severidad:

1. El bloqueo usa el código genérico `INTERNAL`, indistinguible en el esquema de fallos de un error
   real de infraestructura.
2. `_INFRASTRUCTURE_TERMINAL_ERROR_CODE_TO_FAILURE_CODE` atribuye `INTERNAL` a `failure_owner:
   infrastructure`, pero la secuencia de eventos muestra que la consulta SoQL se ejecutó con éxito
   y el bloqueo ocurrió dentro de la propia validación de síntesis del agente — no hubo timeout,
   error de red ni error reportado del proveedor LLM.
3. La persistencia de costo (`estimated_cost_usd=None` pese a 3 llamadas LLM reales) y de las
   trazas diagnósticas de esa síntesis bloqueada se pierde porque el punto de persistencia coincide
   con el punto de aborto.

**Corrección candidata (no implementada aquí)**: mantener el bloqueo de la respuesta sin cambios,
pero (a) introducir un código terminal específico de validación del agente (distinto de `INTERNAL`
y fuera del mapa de infraestructura) para el caso "síntesis bloqueada por cifra huérfana", y (b)
persistir costo y trazas diagnósticas de la corrida bloqueada en un paso que sobreviva al aborto de
la transacción principal. No se determina en esta auditoría el nombre exacto del código ni el
mecanismo de persistencia — eso requiere diseño y aprobación separados.

No es reconstruible desde lo persistido si `'16'` era un número legítimo mal formateado o una
alucinación real, porque la transacción de evidencia nunca se comprometió; esa incertidumbre
específica permanece sin resolver y no depende de la corrección de clasificación propuesta arriba.

---

## 7. Casos "simple" que determinan `latency_simple_p95_ms = 45616` (sin cambios; no objetado)

Clasificación "simple" (`eval/gate.py:108-124`): exactamente 1 evidencia aceptada,
`query_count==1`, `exploration_count==0`. Muestra real (n=14):

| Caso | Latencia (ms) | Llamadas LLM | Ciclos candidato/perfil/plan |
|---|---:|---:|---:|
| **pilot-026-paridad-genero** (p95) | **45616** | 5 | **3** |
| pilot-027-paridad-etnica | 42716 | 4 | 2 |
| pilot-044-negativo-causalidad-politica | 20684 | 4 | 2 |
| pilot-002-seguridad-homicidios | 19678 | 3 | 1 |
| pilot-035-afiliaciones | 18164 | 3 | 1 |
| pilot-018-transporte-ferreo | 17963 | 3 | 1 |
| pilot-001-educacion-magdalena | 15221 | 3 | 1 |
| pilot-040-suspensiones-servicio | 10707 | 3 | 1 |
| pilot-042-disposicion-final | 9478 | 3 | 1 |
| pilot-041-eca | 9441 | 3 | 1 |
| pilot-039-temperatura | 9308 | 3 | 1 |
| pilot-038-precipitacion | 8403 | 3 | 1 |
| pilot-003-salud-vigilancia | 7858 | 3 | 1 |
| pilot-036-delitos-sexuales | 7676 | 3 | 1 |

Los dos casos que fijan el p95 (`pilot-026`, `pilot-027`) llegan a "simple" (1 dataset, 1 SoQL, 0
exploraciones) después de 2–3 ciclos completos de `select_candidate → profile_dataset →
build_plan`, costo de descubrimiento no reflejado en la clasificación de complejidad. No se
propone cambio de umbral ni de regla de clasificación.

---

## 8. Escenarios de tasa positiva — valoración sustantiva contrafactual (no un recálculo de la puerta)

**Precisión normativa exigida por el auditor independiente**: el único resultado real de la corrida
ejecutada por el arnés es **15/40 (37.5%), FAIL**. Ninguna reclasificación de este informe cambia
ese número, porque `_verify_expected_facts` no fue modificado, `golden-v1.yaml` no fue modificado,
y la corrida `b0d38f87-...` ya se cerró y quedó persistida tal como está. Los escenarios de esta
sección **no son una tasa recalculada ni casos "ya aprobados por el arnés"** — son una valoración
cualitativa de cuánta de la brecha 15/40 corresponde a defectos de código reales frente a
cuestiones de interpretación/semántica de `golden-v1` ya resueltas o diagnosticadas fuera de v1.
Se presentan explícitamente como **contrafactuales** para informar la priorización de la siguiente
ronda de incrementos, no como evidencia de que la puerta debería haber pasado.

Base reconciliada de los 15 `expected_fact_not_found`: 2 error real de agente (`021`, `022`, ambos
requieren corrección de código, no decisión golden), 1 falso negativo puro del evaluador (`028`), 1
falso negativo mixto con decisión sobre adecuación de la pregunta aún no resuelta (`029`), 2
sobreespecificación del golden ya resuelta en T-616A-R (`031`, `034`), 3 resueltos en `golden-v2`
vía T-616B pero no retroactivos a v1 (`011`, `014`, `036`), 3 con bloqueo formal —dos resueltos en
v2, uno (`016`) sin resolver ni siquiera en v2— (`016`, `038`, `039`), 3 con ancla ya diagnosticada
como no derivable de la pregunta (`001`, `037`, `041`).

| Escenario contrafactual (no aprobado por el arnés) | Cálculo hipotético | Valor hipotético |
|---|---|---:|
| **Resultado real de la puerta ejecutada** | 15/40 | **37.5% — FAIL** |
| Si se contara además el falso negativo puro del evaluador (`028`) | 16/40 | 40.0% |
| Si se contara además la sobreespecificación del golden ya resuelta en T-616A-R (`031`, `034`) | 18/40 | 45.0% |
| Si se contara además el ancla ya diagnosticada como no derivable (`001`, `037`, `041`) | 21/40 | 52.5% |
| Si además se dieran por resueltas las decisiones ya aprobadas en `golden-v2` sin aplicarlas a v1 (`011`, `014`, `036`), el bloqueo restante (`016`, `038`, `039`), los 5 `budget_exceeded`, y los 4 `evidence_not_eligible` de repliegue (`024–027`) — sin corregir aún `pilot-021`/`pilot-022` | 37/40 | 92.5% |
| Mejor caso teórico absoluto (incluye además corregir `pilot-021` y `pilot-022`) | 39/40 | 97.5% |

Ninguna de las filas por debajo de la primera constituye un resultado de la puerta, un caso
"aprobado", ni autoriza avanzar de estado. Sirven únicamente para estimar, de los 25 casos que
fallan hoy, cuántos son atribuibles a código del agente (`021`, `022`, 5 `budget_exceeded`, 4
`evidence_not_eligible`, `044`, `048`, `007` = 15) frente a cuántos son cuestiones de semántica de
`golden-v1` ya resueltas para `golden-v2` pero no retroactivas (`001, 011, 014, 016, 028, 029, 031,
034, 036, 037, 038, 039, 041` = 13, con solape parcial de responsabilidad en `036`).

---

## 9. Tabla final por caso auditado (reconciliada)

| case_id | Estado actual | Clasificación forense reconciliada | Responsable | Bloqueo real / advertencia | ¿Decisión normativa pendiente sobre el caso en sí? |
|---|---|---|---|---|---|
| pilot-001-educacion-magdalena | FAIL | Ancla de golden-v1 ya diagnosticada como no derivable de la pregunta (`hidden_constraint`/`rewrite_case`, T-616A-R). No figura entre las decisiones que T-616B aprobó explícitamente | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — sólo la semántica general de la puerta congelada (sección 2) |
| pilot-011-cooperacion-minas | FAIL | **Resuelto en `golden-v2` vía T-616B** (`t616b:25`, `bounded_set(21)`, `golden-v2.yaml:667-684`). No aplicable retroactivamente a `golden-v1` congelado | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — ya decidido para v2; sólo pendiente la semántica de la puerta v1 (sección 2) |
| pilot-014-calidad-agua | FAIL | **Resuelto en `golden-v2` vía T-616B** (`t616b:27`, "consolidado" = `#TODOS`). No aplicable retroactivamente a `golden-v1` congelado | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — ya decidido para v2; sólo pendiente la semántica de la puerta v1 |
| pilot-016-codigos-postales | FAIL | **Resuelto en `golden-v2` vía T-616B** (`golden-v2.yaml:1051-1084`, valor publicado + forma canónica de seis dígitos para ambas filas urbana/rural). No aplicable retroactivamente a `golden-v1` congelado | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — ya decidido para v2; sólo pendiente la semántica de la puerta v1 |
| pilot-021-sensibilizacion-valle | FAIL | **Error real y confirmado del agente** (COUNT en vez de proyectar `cantidad`) | agente | Bloqueo (RNF-002) | No — requiere corrección de código |
| pilot-022-red-vial | FAIL | **Reclasificado: error real y confirmado del agente** sobre ancla ya verificada (`wrong_anchor` de v1, pero anchor correcto `codigo_tramo` ya probado; agente proyectó columnas equivocadas) | agente | Bloqueo (RNF-002) | No — requiere corrección de código |
| pilot-028-presupuesto-nacion | FAIL | Falso negativo confirmado del evaluador | evaluador | Bloqueo (RNF-002), no del agente ni de golden | Sí (aprobar cambio de semántica del verificador, sección 10) |
| pilot-029-gastos-nacion | FAIL | Falso negativo del evaluador + decisión sobre adecuación de la pregunta aún no resuelta ni en v1 ni en v2 (T-616A-R la señala "pregunta degenerada", `needs_human_decision`) | evaluador + indeterminado | Bloqueo (RNF-002) | Sí (ambas) |
| pilot-031-desmovilizaciones | FAIL | **Reclasificado: `expected_fact` excesivamente específico** — pregunta pide sólo `tipo`; agente devolvió ambos tipos válidos (`bounded_set(2)` ya confirmado en T-616A-R) | golden-v1 (histórico) | Bloqueo (RNF-002) | No — ya resuelto conceptualmente en T-616A-R/v2 |
| pilot-034-fncer | FAIL | **Reclasificado: `expected_fact` excesivamente específico** — pregunta pide sólo capacidad; agente respondió la capacidad correcta (18.42, display "18"); `tipo` no es una dimensión pedida | golden-v1 (histórico) | Bloqueo (RNF-002) | No — respuesta sustantivamente correcta |
| pilot-036-delitos-sexuales | FAIL | **Resuelto en `golden-v2` vía T-616B** (`t616b:31`, conteo agregado por departamento sin exponer filas sensibles). No aplicable retroactivamente a `golden-v1` congelado; además omisión mecánica de `cod_depto` en el `SELECT` del agente, independiente de la resolución golden | golden-v1 (histórico) + agente | Bloqueo (RNF-002) | No sobre el diseño del agregado — ya decidido para v2; sólo pendiente la semántica de la puerta v1 |
| pilot-037-calidad-aire | FAIL | Ancla de golden-v1 ya diagnosticada como no derivable (61 estaciones válidas, límite de conjunto textual excedido). No figura entre las decisiones que T-616B aprobó explícitamente | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — sólo la semántica general de la puerta congelada |
| pilot-038-precipitacion | FAIL | **Resuelto en `golden-v2` vía T-616B** (`t616b:32-33`, estación/sensor/hora explícitos en la pregunta). No aplicable retroactivamente a `golden-v1` congelado | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — ya decidido para v2; sólo pendiente la semántica de la puerta v1 |
| pilot-039-temperatura | FAIL | Igual que pilot-038 | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — ya decidido para v2; sólo pendiente la semántica de la puerta v1 |
| pilot-041-eca | FAIL | Ancla de golden-v1 ya diagnosticada como no derivable (pregunta no nombra empresa/estación). No figura entre las decisiones que T-616B aprobó explícitamente | golden-v1 (histórico) | Bloqueo (RNF-002) | No sobre el caso — sólo la semántica general de la puerta congelada |
| pilot-008-residuos-villamaria | FAIL | Límite de presupuesto de reparación de plan | agente | Bloqueo (RNF-002) | No |
| pilot-012-control-fiscal | FAIL | Límite de presupuesto de candidatos | agente | Bloqueo (RNF-002) | No |
| pilot-013-app-dnp | FAIL | Límite de presupuesto de reparación de plan | agente | Bloqueo (RNF-002) | No |
| pilot-017-transporte-carretera | FAIL | Límite de presupuesto de reparación de plan | agente | Bloqueo (RNF-002) | No |
| pilot-033-gas-natural-vehicular | FAIL | Límite de presupuesto LLM | agente | Bloqueo (RNF-002) | No |
| pilot-024-educacion-etc | FAIL | Repliegue a evidencia de alta calidad pero irrelevante | agente | Bloqueo (RNF-002) | No (el alcance "ETC" sí está pendiente en T-616A-R, pero el defecto de repliegue documentado aquí es independiente) |
| pilot-025-educacion-municipal | FAIL | Igual que pilot-024 | agente | Bloqueo (RNF-002) | No |
| pilot-026-paridad-genero | FAIL | Igual que pilot-024; fija el p95 de latencia simple | agente | Bloqueo (RNF-002) + advertencia de latencia | No |
| pilot-027-paridad-etnica | FAIL | Igual que pilot-024; segundo mayor p95 | agente | Bloqueo (RNF-002) + advertencia de latencia | No |
| pilot-007-desercion-antioquia | FAIL | Bloqueo correcto y deliberado del validador de síntesis, mal clasificado como `INTERNAL`/infraestructura | agente (validador) — **no infraestructura** | Bloqueo (RNF-001 costo, clasificación de fallo) | Sí (nombrar el código terminal específico y el mecanismo de persistencia) |
| pilot-044-negativo-causalidad-politica | FAIL | No abstención limpia por evidencia irrelevante convertida en claims | agente | Bloqueo (RNF-005 fabricación) | No |
| pilot-048-negativo-ranking-corrupcion | FAIL | Igual que pilot-044 | agente | Bloqueo (RNF-005 fabricación) | No |

---

## 10. Incrementos pequeños propuestos para una ronda posterior (no implementados)

1. **Abstención/relevancia en negativos y en repliegue positivo** (`pilot-044`, `pilot-048`,
   `pilot-024–027`): definir un gate de pertinencia **cerrado y comprobable**, no dependiente de
   juicio LLM nuevo ni de texto libre del sintetizador. Propuesta concreta a evaluar: reutilizar la
   señal determinista ya existente en `candidate_selection` (rank/score de recuperación del dataset
   aceptado). Si el dataset finalmente aceptado no es el de mayor rank/score, o cae bajo el umbral
   que la propia selección de candidatos ya usa, degradar automáticamente a `no_evidence` **antes**
   de generar `quantitative_claims`, en vez de introducir un segundo juicio de relevancia basado en
   LLM sin contrato. Requiere validar si esa señal ya está disponible con la granularidad necesaria
   antes de comprometerse a esta forma exacta.
2. **Cifra huérfana y clasificación de `pilot-007`**: conservar el bloqueo de la respuesta sin
   cambios; introducir un código terminal específico de validación del agente (fuera del mapa de
   fallos de infraestructura) y un mecanismo de persistencia de costo/trazas que sobreviva al
   aborto de la transacción principal.
3. **Semántica del verificador de `expected_facts`**: decidir si `_verify_expected_facts` debe
   aceptar como probada una clave de `expected_value` cuando existe un filtro `WHERE`
   determinista e igualdad-exacta sobre esa misma columna, aunque no esté en el `SELECT`. Afecta
   `pilot-028` y parcialmente `pilot-029`, `pilot-036`.
4. **Presupuestos**: investigar por qué el dataset correcto (siempre rank 1) no logra un plan
   válido dentro del presupuesto de reparación/candidatos/LLM en los 5 casos `budget_exceeded`.
5. **Latencia simple**: no cambiar el umbral; investigar el costo de descubrimiento (ciclos de
   candidato/perfil/plan) no reflejado en la clasificación de complejidad usada para el p95.
Ninguno de estos incrementos se implementa en esta auditoría. La semántica de la puerta `golden-v1`
congelada (antes listada aquí como pendiente) queda resuelta en la sección 2 por jerarquía
documental y no requiere una decisión adicional de Juan Camilo.

---

## Veredicto

**`GOLDEN_V1_HISTORICAL_REGRESSION_FAIL / T617_RUNTIME_CORRECTIONS_REQUIRED`**

`golden-v1` permanece intacto (SHA-256 sin cambios, sin excepciones por caso, sin reinterpretación
dentro de `_verify_expected_facts`) y produce su veredicto mecánico histórico de regresión, tal
como exige `pruebas.md §4.4`: **FAIL, 15/40, sin recálculo**. Los escenarios contrafactuales de la
sección 8 no alteran ese resultado ni constituyen casos "aprobados por el arnés"; son sólo
valoración cualitativa para priorizar la siguiente ronda. La puerta normativa de migración exige
`golden-v2 ≥ 80%` (`pruebas.md:266`), no `golden-v1 ≥ 80%`, y el orden de T-617
(`tasks.md:586`) exige ejecutar `golden-v1` antes que `golden-v2` sin condicionar la segunda a la
aprobación de la primera — pero **eso tampoco autoriza ejecutar `golden-v2` ahora**: permanecen
abiertos, con independencia del resultado de `golden-v1`, los defectos reales de código de esta
auditoría — los dos negativos con claims irrelevantes (`pilot-044`, `pilot-048`), `pilot-007`
(clasificación de fallo y persistencia), las 2 fabricaciones, el costo incompleto (RNF-009), la
latencia simple (RNF-001) y los fallos positivos reales de agente (`pilot-021`, `pilot-022`, los 5
`budget_exceeded`, los 4 repliegues a evidencia irrelevante). No se autoriza `golden-v2`, una nueva
corrida real ni modificación de los golden. Queda autorizable el primer incremento pequeño sobre
abstención determinista ante evidencia irrelevante (sección 10, punto 1); la elección entre ese
incremento y la semántica de filtros `WHERE` en `_verify_expected_facts` (punto 3) corresponde a
Juan Camilo y al agente coordinador.

### Estado final del repositorio

Sin cambios rastreados. El informe (`backend/eval/reports/t617b-c1-golden-v1-forensic-audit.md`)
fue el único artefacto modificado por esta auditoría. Permanecen numerosos archivos no rastreados
preexistentes (reportes de T-617B/T-617C anteriores, documentación, `backend/uv.lock`), ninguno
tocado por esta sesión.
