# Contrato — Herramientas del Agente (tools)

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Consumidor:** grafo LangGraph (`backend/app/agent/`) · **Implementación:** `backend/app/tools/`

Cada herramienta es una función pura respecto de sus entradas (más I/O externo), con entrada/salida JSON validada por Pydantic. **Ninguna herramienta ejecuta escrituras en fuentes externas.**

Este contrato define dos categorías distintas:
- **T1–T5 — herramientas invocables por el enrutador LLM.** El LLM solo puede invocar estas cinco; cualquier otra invocación es un error de grafo.
- **T6–T8 — nodos deterministas obligatorios del pipeline.** NO son invocables por el LLM ni opcionales: el grafo los ejecuta siempre en su posición fija (T6 tras cada `ejecutar_soql` exitoso; T7 antes del sintetizador; T8 tras T3 cuando resuelve ≥2 territorios). Se especifican aquí porque comparten el formato de contrato entrada/salida.

Reglas comunes:
- Timeout externo 10 s, 1 reintento con backoff (Art. IV.4).
- Salida truncada al presupuesto indicado; nunca se pasa un dataset completo al contexto del LLM.
- Todo error retorna `{"ok": false, "error": {"code", "message"}}` — el grafo decide si reintenta, cambia de estrategia o termina.
- Cada invocación se persiste como `agent_steps` (RF-703).
- **Idempotencia (RF-209):** todas las herramientas son de solo lectura o deterministas; re-ejecutar un paso tras un reintento DEBE ser seguro y no producir efectos duplicados.

---

## T1 — `buscar_catalogo`
Búsqueda semántica de datasets (RF-203/302). Envuelve la consulta pgvector.

**Entrada**
```json
{"query": "recursos de cooperación internacional por municipio", "k": 8}
```
**Salida**
```json
{
  "ok": true,
  "results": [
    {
      "dataset_id": "2d3i-f9wd",
      "name": "Cooperación Internacional No Reembolsable",
      "publisher": "APC Colombia",
      "official_publisher_id": "apc-colombia",
      "publisher_verification_status": "verified",
      "description_snippet": "…primeros 300 chars…",
      "similarity": 0.84,
      "row_count": 15230,
      "data_updated_at": "2026-01-10T00:00:00Z",
      "latest_observed_cutoff_at": null,
      "pii_risk_level": "low",
      "eligibility_status": "eligible",
      "eligibility_reasons": [],
      "columns": [{"field_name": "monto_aporte_en_usd", "data_type": "number", "description": "Monto en USD"}]
    }
  ]
}
```
Límites: `k` ≤ 10; `columns` completo (el agente lo necesita para planear SoQL) pero `description` truncada. `data_updated_at` es actualización del portal; `latest_observed_cutoff_at` es solo una pista del catálogo y nunca debe presentarse como corte de la evidencia. Datasets `diagnostic_only` pueden aparecer con advertencia; el agente no debe pasar a T5 salvo que `eligibility_status="eligible"`.

## T2 — `perfilar_dataset`
Perfilado en vivo de un dataset antes de consultarlo: confirma columnas y obtiene valores de ejemplo reales. Reemplaza la fe ciega en metadatos (mitiga metadatos pobres, plan.md §9).

**Entrada**
```json
{"dataset_id": "2d3i-f9wd", "columns_of_interest": ["estado_intervencion", "fecha_inicial"]}
```
**Salida**
```json
{
  "ok": true,
  "dataset_id": "2d3i-f9wd",
  "total_rows_estimate": 15230,
  "latest_observed_cutoff_hint": {
    "latest_observed_cutoff_at": "2025-12-31T00:00:00Z",
    "method": "max_temporal_column",
    "column": "fecha_final",
    "confidence": 0.85,
    "inferred_at": "2026-07-06T14:22:31Z"
  },
  "profile": [
    {"field_name": "estado_intervencion", "data_type": "text",
     "distinct_sample": ["Finalizado", "Ejecución", "Suspendido"],
     "null_ratio": 0.02}
  ]
}
```
Implementación: `SELECT count(*)`, `SELECT DISTINCT col LIMIT 15` y conteo de nulos por columna solicitada (máx. 5 columnas por llamada). Actualiza `catalog_columns.null_ratio` como caché y solo actualiza `sample_values` para columnas `pii_risk_level=low`; para `medium/high/unknown`, `sample_values=[]`.
Debe implementarse con una o pocas consultas agregadas/concurrentes; no se permite una cascada secuencial que pueda romper RNF-001. Si identifica una columna temporal confiable, puede actualizar `catalog_datasets.latest_observed_cutoff_at` como pista; el corte normativo se calculará de nuevo sobre cada evidencia en T6. Si no hay pista, devuelve `latest_observed_cutoff_hint: null`.

## T3 — `resolver_geografia`
Resuelve nombres de lugares a códigos DIVIPOLA y variantes seguras de búsqueda (RF-202, ESC-01). Sucesor del `maestro_divipola.js` de v1.0, ahora sobre la tabla completa `divipola_entries` con matching difuso.

**Entrada**
```json
{"termino": "Carmen de Viboral"}
```
**Salida**
```json
{
  "ok": true,
  "matches": [
    {
      "code": "05148",
      "name": "EL CARMEN DE VIBORAL",
      "department_code": "05",
      "department_name": "ANTIOQUIA",
      "level": "municipality",
      "like_pattern": "%CARMEN DE VIBORAL%",
      "confidence": 0.93
    }
  ]
}
```
- Devuelve hasta 3 matches ordenados por confianza; el agente elige o pregunta.
- `like_pattern`: patrón con comodines para columnas de texto con tildes/variantes (equivale a `busqueda_segura` de v1.0, ahora generado por regla: vocales acentuables → `_`).

## T4 — `explorar_valores`
Descubre valores reales de una columna de texto para construir filtros correctos (heredada de v1.0, endurecida).

**Entrada**
```json
{"dataset_id": "thui-g47e", "columna": "nomindicador", "termino_busqueda": "cesárea"}
```
**Salida**
```json
{"ok": true, "values": ["Proporción de partos por cesárea"], "truncated": false}
```
- Interno: `SELECT DISTINCT columna WHERE upper(columna) LIKE upper('%…%') LIMIT 20`.
- `termino_busqueda` se sanitiza (escape de `'`, `%`, `_` literales) antes de interpolar (RNF-011).
- **Solo columnas de texto (hallazgo T-402, 2026-07-11):** antes de llamar a Socrata, valida `columna` contra `catalog_columns.data_type` (comparación insensible a mayúsculas). Si la columna es numérica, de fecha/hora o booleana, rechaza con `EXPLORAR_VALORES_NOT_TEXT` sin ejecutar la consulta — Socrata rechaza `upper(...)/LIKE` contra esos tipos con `query.soql.type-mismatch`, un error que el agente no puede autocorregir por sí solo. Para filtrar una columna no textual, el agente debe usar `ejecutar_soql` directamente con `=` o un rango. Si la columna no existe en el dataset, rechaza con `SOQL_UNKNOWN_COLUMN`.

## T5 — `ejecutar_soql`
Ejecuta la consulta final contra la SODA API (RF-207). **Única herramienta que trae datos masivos.**

**Entrada**
```json
{
  "dataset_id": "nudc-7mev",
  "soql": "SELECT a_o, avg(desercion) AS prom WHERE codigo_municipio='05756' GROUP BY a_o ORDER BY a_o DESC",
  "purpose": "Serie anual de deserción para Sonsón"
}
```
**Validación previa a la ejecución (guardia ESTRUCTURAL, RNF-011).** La guardia parsea la consulta a una representación estructurada (gramática SoQL) y valida contra lista blanca; una regex/lista negra puede complementarla como defensa en profundidad, pero NO es su núcleo:
1. **Una sola consulta:** exactamente una sentencia; cualquier separador de sentencias o construcción no reconocida por la gramática ⇒ rechazo `SOQL_FORBIDDEN`.
2. **Dataset autorizado:** `dataset_id` existe en `catalog_datasets` con `api_active = true`.
3. **Elegibilidad antes de Socrata:** `catalog_datasets.eligibility_status = "eligible"` y toda columna seleccionada tiene `eligibility_status="eligible"` o cumple la política `medium` agregada. Si el dataset/columna está `unknown`, `high`, `blocked` o requiere agregación y la consulta devuelve filas individuales ⇒ rechazo `EVIDENCE_NOT_ELIGIBLE` sin llamar a Socrata.
4. **Columnas existentes:** toda columna referenciada (SELECT/WHERE/GROUP BY/ORDER BY) existe en `catalog_columns` para ese dataset ⇒ si no, rechazo `SOQL_UNKNOWN_COLUMN` (con la lista de columnas válidas para autocorrección del agente).
5. **Cláusulas permitidas (lista blanca):** `SELECT`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, `LIMIT`, `OFFSET`. Nada más.
6. **Funciones permitidas (lista blanca):** agregación (`sum`, `avg`, `count`, `min`, `max`), texto (`upper`, `lower`, `like`), fecha (`date_extract_y`, `date_trunc_*`). Función fuera de lista ⇒ rechazo.
7. **`SELECT *` prohibido:** el agente debe nombrar columnas explícitas para minimizar datos y permitir validación de PII.
8. **Política `medium`:** si cualquier columna/dataset es `pii_risk_level="medium"`, el `SELECT` debe contener solo agregados y dimensiones no identificantes, incluir `count(*)` o agregado equivalente, y T6 verificará `aggregation_min_count >= 5` por fila. Sin eso ⇒ `PII_AGGREGATION_REQUIRED`.
9. **Límites de filas y desplazamiento:** sin `LIMIT` se inyecta `LIMIT 1000`; `LIMIT > 1000` se reduce a 1000; `OFFSET > 5000` se rechaza.
10. **Alias y literales:** alias permitidos solo en `SELECT` para expresiones/agregados y deben resolverse al validar `ORDER BY`; literales permitidos: strings escapados, números, booleanos y fechas ISO.
11. **Complejidad máxima:** ≤ 15 condiciones en `WHERE`, ≤ 5 columnas de agrupación, sin subconsultas anidadas.
12. **Canonicalización:** antes de persistir, la consulta se serializa en forma canónica (cláusulas en orden estándar, columnas validadas, `LIMIT` explícito, espacios y mayúsculas normalizados, alias resueltos).
13. **Defensa en profundidad (complementaria):** lista negra `INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT|;` como segundo cinturón tras el parseo.

**Salida**
```json
{
  "ok": true,
  "rows": [{"a_o": "2025", "prom": "3.2"}],
  "row_count": 6,
  "executed_at": "2026-07-06T14:22:31Z",
  "source_url": "https://www.datos.gov.co/d/nudc-7mev",
  "llm_view": {"rows_shown": 6, "note": "al contexto del LLM entran máx. 50 filas; el resto viaja directo a la Evidencia"}
}
```
**Errores específicos:** `SOQL_SYNTAX` (Socrata 400, incluye mensaje original para autocorrección del agente — máx. 2 autocorrecciones por consulta), `SOCRATA_TIMEOUT`, `DATASET_INACTIVE`, `EVIDENCE_NOT_ELIGIBLE`, `PII_AGGREGATION_REQUIRED`.

---

# Nodos deterministas del pipeline (no invocables por el LLM)

## T6 — `validar_evidencia`
Invoca la capa de calidad sobre un resultado de T5 (RF-401). Nodo determinista: no usa LLM. Implementado por el módulo `app/quality/` (tarea T-401).

**Entrada:** `{"evidence_draft": {…salida de T5 + dataset_id + soql…}}`
**Salida:** objeto `quality` completo según [`validacion-calidad.md`](./validacion-calidad.md) §4, incluyendo `eligibility_status`, `eligibility_reasons`, metadatos de corte inferido y política de filas/PII.

- El grafo la ejecuta SIEMPRE después de cada `ejecutar_soql` exitoso, antes del sintetizador. No es opcional ni invocable a discreción del LLM.

## T7 — `construir_afirmaciones`
Materializa las **afirmaciones cuantitativas** (claims, RF-208) a partir de evidencia validada. Nodo determinista: el cálculo lo hace código, NO el LLM. El nodo LLM especializado `claim_planner`, ejecutado después de la validación de calidad y separado del enrutador de herramientas, solo **propone** qué claims construir (columnas, fórmula y redondeo deseado); T7 los computa, verifica y registra en `quantitative_claims`. La representación de transporte del `claim_planner` puede usar `formula_json` para evitar un JSON Schema recursivo incompatible con el proveedor, pero antes de invocar T7 el backend DEBE parsearla y validarla contra la DSL recursiva completa que se muestra abajo. Implementado por `app/quality/claims.py` (tarea T-403).

**Entrada**
```json
{
  "evidence_id": "9a2b...",
  "claim_specs": [
    {
      "claim_type": "derived",
      "description": "Tasa de deserción 2025",
      "source_row_indexes": [0, 1],
      "columns": ["matriculados", "desertores"],
      "formula": {"op": "mul", "args": [{"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]}, {"const": 100}]},
      "unit": "%",
      "rounding": 1
    },
    {
      "claim_type": "direct",
      "description": "Matriculados 2025",
      "source_row_indexes": [0],
      "columns": ["matriculados"],
      "unit": "personas",
      "rounding": 0
    }
  ]
}
```
**Salida**
```json
{
  "ok": true,
  "claims": [
    {"claim_id": "7c1d...", "claim_type": "derived", "raw_value": 8.3721,
     "display_value": "8,4 %", "unit": "%", "rounding": 1,
     "formula": {"op": "mul", "args": [{"op": "div", "args": [{"col": "desertores"}, {"col": "matriculados"}]}, {"const": 100}]},
     "source_hash": "sha256:ab12...",
     "evidence_id": "9a2b...", "source_row_indexes": [0, 1], "columns": ["matriculados", "desertores"]}
  ],
  "rejected": [
    {"description": "…", "reason": "columna 'desertores' no existe en la evidencia / operando nulo / división por cero"}
  ]
}
```
**Reglas:**
- DSL de fórmulas: JSON, no texto libre. Nodos permitidos: `{"col": "<columna>"}`, `{"const": number}`, `{"agg": "sum|avg|count|min|max", "col": "<columna>"}`, y operaciones `{"op": "add|sub|mul|div|ratio|pct_change", "args": [...]}`. No hay funciones arbitrarias ni referencias fuera de `evidence_results.rows`.
- Operandos inexistentes, no numéricos, nulos o división por cero ⇒ claim rechazado con razón explícita.
- `display_value` se genera con formato es-CO (coma decimal, separador de miles) a partir de `raw_value` + `rounding` + `unit`.
- `source_hash` se calcula sobre JSON canónico UTF-8 con claves ordenadas y sin espacios: `{algorithm_version, dataset_id, canonical_soql, source_row_indexes, rows_subset_canonical, columns, formula_dsl_canonical, raw_value, unit, rounding}`. El prefijo visible es `sha256:<hex>`. No incluye `evidence_id`, `claim_id`, `run_id` ni timestamps de ejecución; esos identificadores pueden cambiar entre corridas sin cambiar el hash de contenido.
- Se considera “cifra” cualquier token numérico visible en español o formato internacional: enteros, decimales con coma o punto, porcentajes, monedas, magnitudes con separador de miles, años usados como valor analítico, rangos numéricos y tasas. No se consideran cifras: IDs técnicos (`dataset_id`, UUID), fechas completas en citas, códigos DIVIPOLA y números de sección si no expresan un dato sustantivo.
- **El sintetizador SOLO puede citar cifras a través de `display_value` de claims aceptados.** Una cifra en la narrativa sin `claim_id` asociado es un defecto bloqueante (verificado por el chequeo de groundedness, pruebas.md §4.2).

## T7b — `construir_hechos_textuales` — PROPUESTA T-615

> **PROPUESTA PARA REVISIÓN — NO IMPLEMENTADA NI VIGENTE.** No reemplaza T7
> ni autoriza código o migración. El contrato completo se fundamenta en
> `research.md` §27 y `proposals/textual-claims.md`.

Materializaría `TextualFact` a partir de evidencia elegible. Es un nodo
determinista separado: el LLM puede proponer una especificación tipada, pero
no normaliza, selecciona, desempata, calcula el hash ni redacta el valor
factual.

**Entrada propuesta**

```json
{
  "evidence_id": "9a2b...",
  "textual_fact_specs": [
    {
      "operation": "argmax_label",
      "source_row_indexes": [0, 1, 2],
      "columns": ["departamento", "total"],
      "operation_params": {
        "label_column": "departamento",
        "metric_column": "total",
        "tie_policy": "reject"
      }
    }
  ]
}
```

**Salida propuesta**

```json
{
  "ok": true,
  "facts": [
    {
      "fact_id": "8d2e...",
      "fact_kind": "textual",
      "fact": "El departamento con el valor máximo es Valle del Cauca.",
      "operation": "argmax_label",
      "evidence_id": "9a2b...",
      "dataset_id": "m8fd-ahd9",
      "source_row_indexes": [0, 1, 2],
      "columns": ["departamento", "total"],
      "raw_values": ["VALLE DEL CAUCA"],
      "normalized_values": ["valle del cauca"],
      "display_value": "VALLE DEL CAUCA",
      "normalization_profile": "text-es-v1",
      "operation_params": {
        "label_column": "departamento",
        "metric_column": "total",
        "tie_policy": "reject"
      },
      "algorithm_version": "textual-fact-v1",
      "source_hash": "sha256-jcs-v1:cd34..."
    }
  ],
  "rejected": []
}
```

**Reglas propuestas:**

- Enum cerrado:
  `direct_text|value_presence|category_selection|argmax_label|argmin_label|canonical_text_set`.
- `text-es-v1`: Unicode NFC, saltos/espacios canonicalizados, `casefold` solo
  para igualdad; tildes, `ñ`, caja de presentación y puntuación se conservan.
- `null`, vacío, fila fuera de rango, columna ausente, operación desconocida,
  métrica no numérica o regla no reproducible rechazan el hecho.
- `argmax_label` y `argmin_label` usan inicialmente
  `tie_policy="reject"`; un empate no se resuelve por orden incidental.
- `canonical_text_set` deduplica por valor normalizado y ordena
  canónicamente; no depende del orden accidental de respuesta.
- El hash incluye versión, operación, normalización, dataset, SoQL canónica,
  filas/subconjunto fuente, columnas, valores y parámetros. No incluye UUIDs
  de instancia, timestamps ni texto libre del LLM.
- `fact` se genera desde una plantilla determinista por operación. Está
  prohibido convertir una etiqueta o categoría en `raw_value=1`, `count=1` u
  otra cifra ficticia.
- Una evidencia `blocked`, `diagnostic_only` o `no_recomendada` no puede
  producir un hecho entregable automáticamente; aplica la misma puerta de
  elegibilidad que a T7.

**Contrato aprobado de síntesis factual (`grounded-synthesis-plan-v1`)**

El LLM solo puede devolver `schema_version`, `segments` y `closing`. Cada
segmento contiene `segment_id`, `connector`, `template` y `fact_refs` tipadas
por `fact_kind` e `id`; se prohíben campos libres. Enums:

- `connector`: `sin_conector|ademas|por_otra_parte|en_conjunto`;
- `template`: `fact_statement|subject_fact|comparison_pair`;
- `closing`: `sin_cierre|limitacion_disponibilidad|advertencia_calidad`.

Los IDs deben pertenecer a claims/facts persistidos, aceptados y de evidencia
elegible de la misma corrida. `comparison_pair` exige dos referencias
compatibles; las otras plantillas exigen una. El renderer produce toda cláusula
factual e inserta `display_value` literalmente. ID desconocido, duplicado,
incompatible, evidencia ausente/no elegible, enum/campo extra o JSON inválido
rechazan el plan completo. Agotada la reparación presupuestada se usa
`grounded-synthesis-fallback-v1`. Sin hechos elegibles se usa la abstención
`no_evidence`; `insufficient_evidence` queda reservada para una falla
operacional que impida certificar el conjunto permitido. Nunca se entrega
contenido factual parcial.

**Renderer literal `grounded-synthesis-renderer-v1`.** Para esta versión,
`atomic_clause` se obtiene únicamente del objeto persistido:

- claim cuantitativo: `"{claim}: {display_value}."`;
- hecho textual: `"{fact}"`, sin modificar ni volver a insertar su valor.

Las plantillas de segmento son literales:

- `fact_statement`: `"{atomic_clause}"`;
- `subject_fact`: `"Resultado verificado: {atomic_clause}"`;
- `comparison_pair`:
  `"Resultados relacionados: {atomic_clause_1} {atomic_clause_2}"`.

`comparison_pair` es presentación conjunta, no resta, cociente, orden ni
afirmación de superioridad. Sus dos referencias son compatibles si y solo si:

1. son distintas;
2. están persistidas y aceptadas en la misma corrida;
3. apuntan al mismo `evidence_id`;
4. esa evidencia es elegible.

Puede combinar dos claims, dos hechos textuales o uno de cada tipo. Unidad,
operación y tipo no son condiciones porque la plantilla no compara magnitudes.
Cualquier comparación matemática futura exige otra plantilla y contrato.

El conector se antepone literalmente al segmento ya renderizado:

- `sin_conector`: `""`;
- `ademas`: `"Además, "`;
- `por_otra_parte`: `"Por otra parte, "`;
- `en_conjunto`: `"En conjunto, "`.

El primer segmento exige `sin_conector`; los demás no pueden usarlo. Los
segmentos se unen con un espacio. El cierre se añade al final:

- `sin_cierre`: `""`;
- `limitacion_disponibilidad`:
  `" La respuesta se limita a la evidencia disponible."`;
- `advertencia_calidad`:
  `" La evidencia utilizada presenta una advertencia de calidad."`.

No se corrigen caja, puntuación ni espacios dentro de `claim`, `display_value`
o `fact`; si un objeto persistido no satisface su contrato, se rechaza antes de
renderizar.

**Fallback determinista `grounded-synthesis-fallback-v1`.** Ante error del
proveedor, plan inválido o reparación agotada, el código:

1. reúne solo claims y hechos persistidos, reverificados y elegibles;
2. ordena por `fact_kind` (`quantitative` antes de `textual`), `dataset_id`,
   `source_row_indexes`, `columns` y `source_hash`;
3. toma como máximo ocho objetos;
4. crea un `fact_statement` por objeto, con `sin_conector` para el primero y
   `ademas` para los siguientes;
5. usa `limitacion_disponibilidad` si había más de ocho objetos;
   en otro caso usa `advertencia_calidad` si alguna evidencia seleccionada
   tiene clasificación `baja`, y `sin_cierre` en los demás casos.

El fallback nunca genera `comparison_pair`, nunca recibe texto libre y pasa por
el mismo validador y renderer. Sin objetos elegibles termina `no_evidence`; no
fabrica un plan vacío.

## T8 — `comparabilidad_territorial`
Advierte cuando dos o más territorios resueltos por T3 en la misma corrida no son comparables entre sí (Cap. 9 del Handbook de CSS para Política, `docs/capitulos-css-politicas-publicas.md`). Nodo determinista: no usa LLM, no acepta invocación libre del enrutador. El grafo lo ejecuta automáticamente cuando T3 devuelve `divipola_code` de ≥2 territorios distintos en el mismo run. Implementado por `app/quality/territorial.py` sobre la tabla `territorio_tipologia` (tarea T-404).

**Entrada**
```json
{"divipola_codes": ["11001", "05148"]}
```
**Salida**
```json
{
  "ok": true,
  "comparable": false,
  "reasons": ["level_mismatch"],
  "territorios": [
    {"divipola_code": "11001", "level": "municipality", "tipologia_dnp": "Bogotá", "categoria_ley_617": "ESP"},
    {"divipola_code": "05148", "level": "municipality", "tipologia_dnp": "5", "categoria_ley_617": "6"}
  ]
}
```
**Reglas:**
- `reasons` es una lista de códigos fijos, NO texto libre: `level_mismatch` (un territorio es `department` y otro `municipality`) y/o `tipologia_gap` (las `tipologia_dnp` distan ≥3 posiciones en la escala municipal, o cualquiera de los dos está en `Bogotá`/`Ciudades grandes` mientras el otro no).
- Si algún `divipola_code` no tiene fila en `territorio_tipologia` (carga pendiente o territorio nuevo), se marca `comparable: null` con `reasons: ["sin_tipologia"]` — el sintetizador debe tratarlo igual que `false` para efectos de advertencia (no asumir comparabilidad ante datos faltantes).
- **La salida de T8 NUNCA contiene `poblacion` ni `ingresos_totales_cop`** (ver `data-model.md` §6, regla de uso de `territorio_tipologia`) — solo `tipologia_dnp`/`categoria_ley_617`/`level`, que el sintetizador puede mencionar como clasificación, nunca como cifra numérica citada.
- El sintetizador usa esta salida solo para decidir si agrega una frase de advertencia de comparabilidad; no genera una `quantitative_claim` (T7) a partir de ella.

---

## Presupuestos y política de uso (RF-201)

| Regla | Valor |
|---|---|
| Pasos totales máx. por corrida | 14 (configurable `AGENT_MAX_STEPS`; RF-201 y `research.md` §19) |
| Llamadas máx. a `ejecutar_soql` por corrida | 4 |
| Autocorrecciones de SoQL tras `SOQL_SYNTAX` | 2 por consulta |
| Filas al contexto LLM | ≤ 50 por consulta (resumen); Evidencia completa ≤ 1.000 |
| Al agotar presupuesto | transición forzada a sintetizador en modo `no_evidence` (RF-205) |

## Extensibilidad
Agregar una herramienta nueva requiere: (1) sección en este contrato, (2) esquema Pydantic, (3) pruebas unitarias + de contrato, (4) actualización del prompt del enrutador. Las cuatro cosas en el mismo PR.
