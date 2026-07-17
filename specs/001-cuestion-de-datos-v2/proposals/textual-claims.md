# Propuesta T-615 — Hechos textuales de primera clase

> **Estado: PROPUESTA PARA REVISIÓN — SIN VIGENCIA NORMATIVA NI
> IMPLEMENTACIÓN.**
>
> Fecha de auditoría: 2026-07-16. Rama auditada: `v2`. Commit auditado:
> `f7cc283e5fd3a7b1247d7dbd04a9d0a661766142`.
>
> Esta propuesta no autoriza código, migraciones, cambios de base de datos,
> `golden-v2`, cambios de métricas, retiro del legado ni modificación de
> `golden-v1`. Solo adquiere vigencia si la coordinación aprueba la enmienda
> T-615 y autoriza por separado el primer incremento de implementación.

## 1. Problema comprobado

El contrato vigente solo reconoce `QuantitativeClaim`. El constructor real
`backend/app/quality/claims.py` acepta valores numéricos `direct` o `derived`;
el persistidor escribe únicamente `quantitative_claims`; la síntesis y el
evaluador detectan cifras huérfanas, no afirmaciones textuales huérfanas.

El runtime determinista intenta salvar filas de consulta textual mediante
`_lookup_presence_specs`: toma una columna textual, aplica `count` sobre una
fila y produce un claim cuantitativo derivado con valor `1`. Aunque la
descripción contiene el texto observado, el valor persistido no prueba ese
texto. Esta representación contradice el límite de T-615: una etiqueta,
categoría, entidad, municipio, estado o nombre no puede convertirse en
`raw_value=1` ni en otra magnitud ficticia.

El alcance es material:

- `golden-v1` tiene 40 casos positivos.
- 36 contienen al menos un valor textual esperado.
- 9 dependen solo de valores textuales:
  `pilot-013-app-dnp`, `pilot-015-puestos-electorales`,
  `pilot-017-transporte-carretera`, `pilot-018-transporte-ferreo`,
  `pilot-019-trafico-portuario`, `pilot-028-presupuesto-nacion`,
  `pilot-031-desmovilizaciones`, `pilot-032-situacion-penitenciaria` y
  `pilot-035-afiliaciones`.
- Los cuatro positivos puramente numéricos son
  `pilot-005-empleo-publico`, `pilot-006-planta-entidad`,
  `pilot-007-desercion-antioquia` y `pilot-022-red-vial`.

Que un caso pase hoy no demuestra integridad textual. En particular,
`pilot-013-app-dnp` pasa mediante el conteo de presencia descrito arriba.

## 2. Decisión propuesta

Se propone un concepto común **interno**, **hecho fundamentado**, con dos
variantes discriminadas y persistencias separadas. Este concepto no cambia la
forma pública vigente de `claims[]`:

```text
GroundedFact
├── QuantitativeClaim  (fact_kind = "quantitative")
└── TextualFact        (fact_kind = "textual")
```

`QuantitativeClaim` conserva sin cambios su semántica `direct|derived`, su DSL,
su `raw_value` numérico, formato, unidad, redondeo y guarda RNF-003. No se
reutiliza su tabla para texto.

`TextualFact` prueba una salida textual mediante una operación cerrada,
evidencia elegible, filas y columnas existentes, valores fuente conservados,
normalización versionada y hash reproducible. No contiene campos numéricos
ficticios ni permite texto inventado por el LLM.

Se elige una tabla nueva `textual_facts` porque:

1. conserva las restricciones fuertes de `quantitative_claims`;
2. evita columnas numéricas anulables o un JSON polimórfico difícil de
   restringir;
3. permite rollback por componente;
4. mantiene los históricos cuantitativos sin backfill semántico;
5. hace explícita la retención y la evaluación de cada tipo.

### 2.1 Opciones de persistencia comparadas

| Opción | Evaluación | Decisión |
|---|---|---|
| A — Tabla nueva `textual_facts` | Añade una entidad con checks propios y combina ambos tipos en API. No toca filas ni constraints cuantitativos. | **Propuesta elegida.** Se usa `facts` y no `claims` en el nombre para distinguir la semántica, aunque cumple la opción de tabla separada. |
| B — Tabla genérica unificada | Exige migrar históricos, hacer anulables campos incompatibles, rehacer FK/retención y aceptar un downgrade de alto riesgo. | Descartada: rompe aislamiento y no ofrece una ventaja necesaria. |
| C — Extender `quantitative_claims` | Obliga a usar nulos/centinelas o un JSON abierto y hace falso el nombre y los invariantes numéricos. | Descartada por incorrección metodológica y riesgo sobre RNF-003. |

## 3. Operaciones textuales cerradas

`operation` solo puede tomar estos valores en la primera versión:

| Operación | Semántica | Cardinalidad fuente |
|---|---|---|
| `direct_text` | Copia un valor textual de una celda identificada. | Una fila, una columna. |
| `value_presence` | Prueba que un valor textual normalizado está presente en la columna declarada dentro de las filas referenciadas. | Una o más filas, una columna. |
| `category_selection` | Selecciona una etiqueta bajo filtros y orden explícitos ya materializados en la consulta. | Una fila ganadora, una columna de etiqueta. |
| `argmax_label` | Devuelve la etiqueta asociada al máximo de una columna métrica. | Una o más filas; columna de etiqueta y métrica. |
| `argmin_label` | Devuelve la etiqueta asociada al mínimo de una columna métrica. | Una o más filas; columna de etiqueta y métrica. |
| `canonical_text_set` | Produce una colección textual deduplicada y ordenada canónicamente desde varias filas. | Una o más filas, una columna. |

No se adopta el nombre genérico `presence`: `value_presence` nombra qué se
prueba. No se adopta `categorical_selection`: `category_selection` es más
breve sin perder precisión. `canonical_text_set` cubre de forma explícita el
texto derivado de varias filas; no se sobrecarga `direct_text`.

No existen operaciones abiertas, expresiones textuales arbitrarias ni
funciones suministradas por el LLM. Una operación desconocida se rechaza.

### 3.1 Parámetros por operación

- `direct_text`: `source_row_indexes` tiene exactamente un elemento y
  `columns_used`, uno.
- `value_presence`: el objetivo literal procede de un filtro explícito del
  `QueryPlan` validado, nunca de una elección posterior del LLM. Exige
  `target_raw`, `target_normalized` y una columna; prueba que existe al menos
  una coincidencia y presenta el representante fuente canónico.
- `category_selection`: no recibe un objetivo. Exige exactamente una de las
  reglas cerradas `unique_normalized_value` (una sola categoría distinta) o
  `first_by_validated_order` (primera fila de una consulta con `ORDER BY`
  total y `LIMIT` explícitos en el `QueryPlan`). Cero o varias ganadoras
  rechazan el hecho; el LLM no elige categorías.
- `argmax_label` / `argmin_label`: exigen `label_column`, `metric_column` y
  `tie_policy="reject"`. La métrica debe ser numérica y finita. Si dos filas
  empatan en el extremo, no se elige por orden incidental: el hecho se
  rechaza como ambiguo.
- `canonical_text_set`: deduplica por valor normalizado y ordena por
  `normalized_value ASC`, con desempate por valor bruto UTF-8. No conserva el
  orden incidental de Socrata. `display_value` une los valores presentados
  con la secuencia literal `"; "`; esa transformación forma parte de
  `textual-fact-v1` y se recomputa en el verificador.

Todas las operaciones eliminan `null` solo cuando su regla permite varias
filas; después rechazan si no queda valor. Una celda vacía tras `text-es-v1`
siempre es error. Máximo: 100 filas fuente y 50 valores normalizados distintos;
excederlo produce `textual_cardinality_exceeded`, no truncamiento silencioso.
Los duplicados normalizados usan como representante el menor valor bruto por
orden de bytes UTF-8 después de NFC.

| Operación | Entradas y regla determinista | Salida | Errores/abstención | Ejemplo genérico |
|---|---|---|---|---|
| `direct_text` | Un índice y una columna. | Copia literal de la celda. | Nulo, vacío, fila/columna inválida o cardinalidad distinta de 1. | Una celda `"Activo"` produce `"Activo"`. |
| `value_presence` | Objetivo literal del `QueryPlan`, una columna y ≥1 filas; igualdad por normalizado. | Representante fuente de las coincidencias. | Objetivo ausente o más de un representante bruto incompatible. | Objetivo `"rural"` coincide con `"Rural"`. |
| `category_selection` | Una columna; regla `unique_normalized_value` o `first_by_validated_order`. | Única categoría ganadora. | Cero/varias ganadoras, orden no total o regla libre. | Un único valor distinto produce esa categoría. |
| `argmax_label` | Columna etiqueta + métrica finita; `tie_policy=reject`. | Etiqueta de máximo único. | Nulo/no numérico, máximo empatado o etiqueta vacía. | Métricas 2 y 5 seleccionan la etiqueta de 5. |
| `argmin_label` | Igual a anterior para mínimo. | Etiqueta de mínimo único. | Nulo/no numérico, mínimo empatado o etiqueta vacía. | Métricas 2 y 5 seleccionan la etiqueta de 2. |
| `canonical_text_set` | Una columna y ≥1 filas; deduplicación y orden canónicos. | Valores unidos por `"; "`. | Conjunto vacío o límites excedidos. | `["B", "a", "B"]` produce el orden canónico de `"a"; "B"`. |

## 4. Modelo lógico de `TextualFact`

```json
{
  "fact_id": "uuid",
  "fact_kind": "textual",
  "fact": "El municipio observado es Medellín.",
  "operation": "direct_text",
  "evidence_id": "uuid",
  "dataset_id": "abcd-1234",
  "source_row_indexes": [0],
  "columns": ["municipio"],
  "raw_values": ["Medellín"],
  "normalized_values": ["medellín"],
  "display_value": "Medellín",
  "normalization_profile": "text-es-v1",
  "operation_params": {},
  "algorithm_version": "textual-fact-v1",
  "source_hash": "sha256:..."
}
```

El `dataset_id` es obligatorio en la representación pública y se obtiene de
la evidencia referenciada. En persistencia no se duplica: la FK
`evidence_id → evidence_results` lo determina y evita divergencias. El
constructor debe recibir y materializar ese `dataset_id` dentro del hash.

`raw_values` y `normalized_values` son listas aun para operaciones unitarias,
de modo que la estructura cubre `canonical_text_set` sin tipos alternos. Ninguna
lista puede estar vacía. `display_value` tampoco puede ser vacío.

## 5. Normalización y presentación

El perfil único inicial es `text-es-v1`:

1. decodificar como UTF-8 válido;
2. normalizar Unicode a NFC;
3. convertir CRLF/CR a LF;
4. reemplazar secuencias de espacios Unicode internos por un espacio ASCII;
5. recortar espacio al inicio y al final;
6. aplicar `casefold` solo a `normalized_values`;
7. conservar tildes, `ñ`, signos y puntuación;
8. rechazar `null`, cadena vacía y texto vacío tras normalizar.

`display_value` usa los pasos 1 a 5 y conserva caja, tildes y puntuación de la
fuente. No aplica `title case`, no elimina acentos y no traduce etiquetas.
`normalized_values` sirve para igualdad/deduplicación; nunca sustituye el
valor mostrado. Una búsqueda tolerante a tildes pertenece a recuperación o a
la consulta, no a la reproducción del hecho.

## 6. Procedencia, orden, hash e inmutabilidad

`source_row_indexes` siempre se valida contra
`evidence_results.rows` y se canonicaliza ascendente en el material de hash.
Los índices son cero-basados y no se permite el centinela `-1` para hechos
textuales. Todas las columnas declaradas deben existir en todas las filas que
la operación usa.

El formato versionado es `sha256-jcs-v1:<64 hex minúsculos>`: SHA-256 sobre
los bytes UTF-8 de JSON canonicalizado conforme a RFC 8785 (JCS). El objeto
raíz contiene exactamente:

```text
{
  algorithm_version,
  operation,
  normalization_profile,
  dataset_id,
  canonical_soql,
  source_row_indexes,
  rows_subset_canonical,
  columns_used,
  raw_values,
  normalized_values,
  display_value,
  operation_params
}
```

Las claves del objeto y de `operation_params` se ordenan por JCS; no se
permiten números no finitos. Enteros, booleanos y `null` usan la representación
JSON de RFC 8785. Las cadenas se serializan con escapes JSON, en Unicode NFC,
sin alterar caja salvo dentro de `normalized_values`. Los arrays preservan el
orden semántico: `source_row_indexes` es ascendente, único y cero-basado;
`columns_used` sigue el orden definido por la operación; `raw_values` y
`normalized_values` mantienen correspondencia posicional; los conjuntos usan
el orden de `canonical_text_set`. `rows_subset_canonical` contiene solo las
columnas usadas, una fila por índice canónico. `canonical_soql` es la consulta
ya canonicalizada por el ejecutor.

No incluye `run_id`, `evidence_id`, `fact_id`, timestamps ni texto libre del
LLM. Cambiar una fila, columna, valor, regla, normalización, consulta o versión
cambia el hash. Una futura regla requiere nuevo prefijo/`algorithm_version`;
los verificadores antiguos no reinterpretan hashes nuevos.

En v1 no se separan identidad y presentación: `display_value` forma parte del
material porque la garantía auditada incluye reproducción literal. Una mejora
meramente editorial crea una nueva versión y hash; esta decisión favorece una
sola prueba verificable sobre dos identidades parcialmente solapadas.

Después de construir un hecho, el `EvidenceResult`, su `canonical_soql` y sus
filas fuente quedan congelados: no se actualizan; una corrección crea nueva
evidencia y nuevos hechos. El orden obligatorio es: persistir y congelar
evidencia → validar calidad → construir y recomputar hechos → persistirlos en
la misma transacción lógica → validar el plan de síntesis → renderizar →
evaluar/recomputar → copiar únicamente métricas y fingerprints → aplicar
retención por cascade. Tras la retención, el fingerprint permite comparar,
pero no recalcular sin filas; no se afirma lo contrario. La persistencia
operativa conserva hasta el vencimiento solo dataset, consulta, índices,
columnas, parámetros, versión, hash y valores estrictamente necesarios; OE3
conserva algoritmo, operación y hash, nunca filas, texto ni valores personales.

## 7. Persistencia propuesta

Tabla nueva `textual_facts`:

| Campo | Regla propuesta |
|---|---|
| `id` | uuid PK; `fact_id` público. |
| `run_id` | uuid FK → `agent_runs` ON DELETE CASCADE. |
| `evidence_id` | uuid FK → `evidence_results` ON DELETE CASCADE, NOT NULL. |
| `fact_text` | text NOT NULL; generado por plantilla determinista. |
| `operation` | text NOT NULL con CHECK del enum cerrado. |
| `source_row_indexes` | int[] NOT NULL y no vacío. |
| `columns_used` | text[] NOT NULL y no vacío. |
| `raw_values` | text[] NOT NULL y no vacío. |
| `normalized_values` | text[] NOT NULL y no vacío. |
| `display_value` | text NOT NULL y no vacío. |
| `normalization_profile` | text NOT NULL, inicialmente `text-es-v1`. |
| `operation_params` | jsonb NOT NULL; estructura validada por operación. |
| `algorithm_version` | text NOT NULL, inicialmente `textual-fact-v1`. |
| `source_hash` | text NOT NULL, formato `sha256-jcs-v1:<64 hex minúsculos>`. |

Índices: `run_id`, `evidence_id` y `source_hash`. `source_hash` no es UNIQUE:
dos corridas pueden probar el mismo hecho. Las restricciones específicas por
operación se validan en el modelo tipado y en el constructor determinista;
los checks relacionales cubren enum, no vacíos y formato del hash.

Retención y RF-803 incluyen `textual_facts` en el mismo borrado por cascade
que claims cuantitativos. `eval_case_results` conserva solo fingerprints
hash, nunca `fact_text`, valores fuente ni filas.

La migración propuesta no tiene backfill: una corrida histórica sin hechos
textuales permanece exactamente como fue persistida y no se “reconstruye” a
partir de su narrativa. El `upgrade` crea solo tabla, checks e índices; antes
del `downgrade` se desactiva la emisión textual y se verifica que no haya
escrituras activas. El `downgrade` elimina únicamente `textual_facts` y sus
índices; como destruye sus filas, exige backup/confirmación operacional si ya
hubo uso, pero no altera `quantitative_claims`, evidencias ni corridas.

## 8. Contrato API y compatibilidad

La compatibilidad elegida separa tres capas:

- **Dominio interno:** `GroundedFact` es unión discriminada por
  `fact_kind=quantitative|textual`.
- **Persistencia:** `quantitative_claims` y `textual_facts` permanecen tablas
  separadas; no se backfillean ni reinterpretan registros históricos.
- **API pública v2:** `claims` y `partial_claims` conservan exactamente su
  esquema cuantitativo actual y no reciben `claim_kind`. Se añaden los campos
  optativos y aditivos `textual_facts` y `partial_textual_facts`, ausentes o
  `[]` cuando no aplican. Sus elementos llevan `fact_kind="textual"`.

Los históricos sin campos textuales se interpretan como
`textual_facts=[]`; sus claims siguen siendo cuantitativos por pertenecer a
`claims`, sin inferencia estructural ni reescritura. Unificar tipos dentro de
`claims` requeriría una nueva versión pública y no pertenece a T-615.

No encontrar un consumidor no demuestra compatibilidad. Antes de activar
texto deben pasar snapshots byte/forma de respuestas cuantitativas actuales,
OpenAPI diff sin cambios dentro de `claims.items`, históricos sin campos
nuevos, clientes estrictos que ignoran el campo raíz aditivo, SSE parcial y
respuestas textual/mixta. Un cliente que rechace propiedades raíz nuevas
requiere negociación/versionado antes de activación; ese hallazgo bloquea
T-615G, no se oculta.

## 9. Síntesis y ausencia de hechos huérfanos

Comprobar que una frase libre “suena factual” no es una garantía medible. Por
eso la primera versión propuesta no permite al LLM redactar valores
textuales factuales libremente:

El LLM devuelve exclusivamente este esquema cerrado:

```json
{
  "schema_version": "grounded-synthesis-plan-v1",
  "segments": [{
    "segment_id": "s1",
    "connector": "sin_conector",
    "template": "fact_statement",
    "fact_refs": [{"fact_kind": "textual", "id": "uuid"}]
  }],
  "closing": "sin_cierre"
}
```

`connector` ∈ `sin_conector|ademas|por_otra_parte|en_conjunto`;
`template` ∈ `fact_statement|subject_fact|comparison_pair`; `closing` ∈
`sin_cierre|limitacion_disponibilidad|advertencia_calidad`. Los únicos IDs
seleccionables son claims/facts persistidos de la corrida, aceptados y ligados
a evidencia elegible. `comparison_pair` exige dos referencias compatibles;
las demás, una. El LLM no devuelve prosa ni valores.

Un **segmento factual** es toda cláusula que afirma como resultado un valor,
entidad, categoría, estado, periodo, comparación o cifra del dataset. El
renderer produce el segmento completo desde la plantilla versionada,
metadatos seguros y `display_value` literal; no parafrasea el valor. Conectores
y cierres son plantillas fijas no factuales y no admiten argumentos libres.

ID desconocido/no elegible, referencia repetida, incompatibilidad de plantilla,
segmento duplicado, enum/campo extra, JSON inválido o valor alterado rechazan
todo el plan y permiten como máximo la reparación presupuestada vigente. Si
no hay hechos elegibles, o se agota la reparación, se renderiza una plantilla
de abstención (`no_evidence` o `insufficient_evidence`) sin afirmaciones
factuales. Nunca se entrega un plan parcial.

Ejemplo válido: un `fact_statement` con un ID textual aceptado; el renderer
inserta exactamente su `display_value`. Ejemplos inválidos: incluir
`"texto":"la categoría es X"`, citar un UUID ajeno, repetir el mismo ID en dos
segmentos o usar `comparison_pair` con una sola referencia.

El texto explicativo no factual queda limitado a plantillas versionadas:
alcance, advertencia de calidad, limitación y ausencia de evidencia. Los
campos libres del modelo no pueden introducir entidades, categorías,
lugares, fechas o estados como hechos. Ampliar esa libertad exigiría una
nueva decisión y una métrica que pruebe el límite.

No se convierten en hechos: títulos y botones de interfaz, nombres de campos
mostrados como encabezados, conectores, instrucciones de uso, mensajes
técnicos, códigos internos, texto de citas que solo identifica la fuente,
advertencias de calidad/privacidad, limitaciones metodológicas y narrativa
que no afirma un valor del dataset. Una etiqueta pasa a ser hecho cuando la
respuesta la presenta como resultado verificable (“el municipio es…”), no
por el solo hecho de aparecer como encabezado o metadato.

## 10. Métricas propuestas

RF-602 debe reportar por separado, sin promedios que oculten un fallo:

| Métrica | Puerta |
|---|---|
| `quantitative_claims_coverage` | 1.0, sin cambiar RNF-003. |
| `quantitative_claims_reproducible` | 1.0. |
| `orphan_figures_count` | 0. |
| `textual_fact_reference_coverage` | 1.0: todo segmento factual referencia un hecho textual aceptado. |
| `textual_facts_reproducible` | 1.0: operación, filas, columnas, normalización, valor y hash se recomputan. |
| `textual_fact_display_match` | 1.0: el texto insertado coincide con `display_value`/plantilla. |
| `orphan_factual_segments_count` | 0. |
| `invalid_textual_operation_count` | 0. |

La puerta compuesta `grounded_fact_integrity` es una conjunción: todas las
guardas aplicables deben pasar. Un promedio no puede compensar una cifra
huérfana con un hecho textual correcto ni viceversa.

RNF-003 permanece literal e intacto. Se propone RF-210 y RNF-013 para el
nuevo tipo; ningún cambio reduce la trazabilidad cuantitativa.

## 11. Pruebas mínimas antes de activar la funcionalidad

Unitarias:

- `direct_text` válido; columna inexistente, fila fuera de rango, `null` y
  vacío rechazados.
- NFC, espacios, caja, tildes, `ñ` y puntuación según `text-es-v1`.
- `value_presence` positivo y ausencia rechazada.
- `category_selection` con regla reproducible y filtro oculto rechazado.
- `argmax_label`/`argmin_label` válidos; métrica no numérica y empate
  rechazados.
- `canonical_text_set` estable ante distinto orden de entrada y duplicados.
- hash igual entre corridas equivalentes; distinto al cambiar cualquier
  material semántico.
- operación desconocida rechazada.
- regresión completa de claims cuantitativos y RNF-003.

Persistencia/integración:

- escritura/lectura exacta de ambas variantes;
- FK, cascade por evidencia/corrida y borrado RF-803/retención;
- rollback de migración sin tocar `quantitative_claims`;
- lectura de respuestas históricas cuantitativas;
- API y SSE con lista mixta y discriminador;
- ninguna fila de `eval_case_results` conserva texto o valores fuente.

Aceptación:

- positivo exclusivamente textual sin `raw_value=1`;
- respuesta mixta (etiqueta + cifra) con ambos hechos;
- texto derivado de varias filas;
- empate que termina en rechazo/abstención controlada;
- síntesis que intenta referenciar un hecho inexistente, bloqueada;
- `pilot-013` solo puede considerarse cubierto por T-615 cuando persista y
  reproduzca sus valores textuales, no por conteo de presencia.

Evaluación/golden:

- T-615 no crea ni cambia suites.
- T-616 audita los 50 casos y propone `acceptable_facts` discriminados por
  `fact_kind: quantitative|textual`.
- Un hecho textual esperado debe declarar operación, valores normalizados,
  columnas, regla de selección y alternativas aceptables cuando la pregunta
  no determina una única respuesta.
- `golden-v1.yaml` permanece byte a byte intacto.

## 12. Casos y fallos: atribución correcta

La falta de hechos textuales no debe absorber fallos de otra capa:

| Caso/patrón | Clasificación actual |
|---|---|
| 36 positivos con valores textuales | Cobertura futura T-615; el pase actual no garantiza integridad textual. |
| `pilot-013-app-dnp` | Déficit textual enmascarado por `count=1`. |
| `pilot-012-control-fiscal` | Recuperación ya corregida; fallo posterior por presupuesto/selección de candidatos, no por T-615. |
| `pilot-021-sensibilizacion-valle` | Plan/consulta incorrecta: `count(*)=1` en vez de `cantidad=65`; no es falta textual ni golden. |
| `pilot-022-red-vial` | Resuelto en el smoke final de T-614; no usarlo como justificación de T-615. |
| `pilot-038-precipitacion` | Golden ambiguo: la hora `13:50` no está determinada por la pregunta; corresponde a T-616. |
| Otros desacuerdos de la corrida completa | Permanecen `undetermined` hasta auditoría T-616; no atribuirlos automáticamente al agente, al golden ni a T-615. |

## 13. Discrepancias registradas

1. El grafo MCP no devolvió relaciones de llamada para varios símbolos del
   pipeline ni ubicó correctamente la aceptación determinista. La inspección
   de archivos reales confirmó esas relaciones y
   `backend/tests/integration/test_deterministic_agent_acceptance.py`.
   Prevalece el repositorio real.
2. `spec.md` RF-201 y `plan.md` fijan 14 pasos por defecto, mientras
   `contracts/agent-tools.md`, `pruebas.md` y `quickstart.md` conservaban 10.
   La enmienda alinea esos documentos inferiores a 14 sin cambiar código ni
   convertir la corrección editorial en parte de la semántica textual.
3. El contrato REST describe claims con detalle, pero los esquemas Pydantic
   actuales usan diccionarios abiertos. T-615B debe cerrar los modelos antes
   de emitir la nueva variante.

## 14. Secuencia de implementación propuesta

La descomposición ejecutable T-615A…T-615J vive en `tasks.md`. Sus reglas
globales son:

- cada incremento requiere autorización explícita;
- migración, modelos, constructor, síntesis y evaluación no se mezclan en un
  único cambio;
- cada incremento conserva rollback y la suite cuantitativa;
- T-616 y T-617 siguen bloqueadas;
- el runtime legado no se retira;
- la aprobación documental no equivale a autorización de código.

## 15. Gate de aprobación

La coordinación debe aprobar o devolver explícitamente:

1. tabla separada `textual_facts`;
2. enum de seis operaciones;
3. perfil `text-es-v1`;
4. empate `reject` en extremos;
5. hash y procedencia;
6. unión discriminada en `claims`;
7. síntesis factual por plantillas e identificadores;
8. métricas sin promediar fallos;
9. esquema conceptual de `acceptable_facts` para T-616;
10. secuencia T-615A…T-615J.

Hasta esa decisión, todo lo anterior permanece como propuesta.
