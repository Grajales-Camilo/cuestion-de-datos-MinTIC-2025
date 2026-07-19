# Contrato — Capa de Validación de Calidad de Datos

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Implementa:** RF-401…404 · Constitución Art. I.4 · Módulo: `backend/app/quality/`

> Esta capa es **determinista**: mismas entradas ⇒ mismo puntaje. No usa LLM. Es la contribución técnica #3 de la propuesta de maestría (capa formal de validación que verifica esquema, completitud, temporalidad y trazabilidad antes de integrar datos a documentos de política pública).

---

## 1. Entrada

Un borrador de evidencia con: `dataset_id`, metadatos del catálogo (`data_updated_at`, `publisher`, `official_publisher_id`, `publisher_verification_status`, `pii_risk_level`, `eligibility_status`, `eligibility_reasons`, `source_url`), columnas seleccionadas con su `pii_risk_level`, la consulta SoQL canonicalizada, las columnas esperadas del plan del agente y las `rows` obtenidas. La inferencia de `data_cutoff_at` se calcula sobre las `rows` de esta evidencia; no se toma de `catalog_datasets`.

La validación T6 produce dos resultados separados:
- **Elegibilidad:** decide si la evidencia puede usarse. Es binaria/operacional y no se compensa con puntaje.
- **Calidad:** puntúa esquema, completitud, temporalidad y trazabilidad solo para evidencias elegibles o diagnósticas.

## 2. Dimensiones, pesos y checks

Puntaje total = suma ponderada de las 4 dimensiones (cada dimensión 0–100).

| Dimensión | Peso | Qué protege |
|---|---|---|
| D1 Esquema | 25% | Que los datos tengan la forma que el agente cree que tienen. |
| D2 Completitud | 25% | Que no se cite una tabla llena de vacíos. |
| D3 Temporalidad | 30% | Que no se presente como actual un dato viejo. Es la dimensión de mayor peso porque es el error más dañino en política pública. |
| D4 Trazabilidad | 20% | Que la cita sea completa y verificable por un tercero. |

### D1 — Esquema (25%)
| Check | Regla | Puntos |
|---|---|---|
| `schema.columns_present` | Toda columna referenciada en el SELECT existe en las filas devueltas. | 40 |
| `schema.types_coherent` | Columnas usadas como numéricas (sum/avg/comparaciones) contienen valores parseables como número en ≥ 95% de filas no nulas. | 40 |
| `schema.non_empty_result` | `row_count > 0` cuando la consulta no es de existencia. Si 0 filas: D1 = 0 y advertencia obligatoria. | 20 |

### D2 — Completitud (25%)
| Check | Regla | Puntos |
|---|---|---|
| `completeness.null_ratio` | Proporción de celdas nulas/vacías en las columnas citadas: ≤ 5% ⇒ 100; ≤ 20% ⇒ 60; ≤ 50% ⇒ 30; > 50% ⇒ 0. | 60 |
| `completeness.placeholder_values` | Detección **contextual** de placeholders — nunca una lista universal, porque `"Total"` puede ser categoría legítima y `9`/`99` valores reales. Un valor solo se marca como placeholder si se cumple al menos una de: (a) coincide con un patrón configurado para ese dataset/columna (`quality/placeholders.yaml`); (b) la descripción de la columna en `catalog_columns` o su codebook indica que ese código significa "no aplica/no responde" (p. ej. `9`/`99` en columnas codificadas de encuesta); (c) es un candidato genérico (`"Default …"`, `"NO ESPECIFICA"`, `"-1"` en columnas de código) Y supera una proporción configurable de las celdas citadas (`PLACEHOLDER_MIN_RATIO`, default 30%). Sin placeholders confirmados ⇒ 40; con placeholders ⇒ 0 + advertencia que nombra el valor y la columna. | 40 |

### D3 — Temporalidad (30%)
La fecha de actualización del dataset NO es lo mismo que el corte estadístico de los datos (un dataset puede "actualizarse" hoy con cifras de hace tres años). Por eso:

1. **Base preferida — `data_cutoff_at`:** el corte estadístico inferido de los propios resultados de la evidencia (máximo valor del campo temporal presente en las filas: `periodo`, `a_o`, `fecha_corte`…), cuando exista y sea parseable.
2. **Fallback explícito — `data_updated_at`:** solo si no puede inferirse el corte; el detalle del check DEBE declarar qué base se usó (`basis: "data_cutoff_at" | "data_updated_at_fallback"`). Este fallback mide riesgo de desactualización, pero NO convierte `data_updated_at` en corte estadístico.

Edad = hoy − la base seleccionada.

| Edad del corte | Puntaje D3 |
|---|---|
| ≤ 12 meses | 100 |
| 12–24 meses | 70 |
| 24–48 meses | 40 |
| > 48 meses o desconocida | 15 |

Advertencia obligatoria en lenguaje claro cuando D3 ≤ 70 (ESC-05):
- Si `basis = "data_cutoff_at"`: *"Este dato tiene corte {fecha}; puede estar desactualizado."*
- Si `basis = "data_updated_at_fallback"`: *"El portal actualizó este dataset en {fecha}, pero no fue posible inferir el corte estadístico de las filas consultadas."*

### D4 — Trazabilidad (20%)
| Check | Regla | Puntos |
|---|---|---|
| `traceability.source_complete` | `dataset_id`, nombre, `publisher`, `source_url` presentes y no vacíos. | 60 |
| `traceability.query_reproducible` | El SoQL guardado re-ejecutado es sintácticamente válido (no se re-ejecuta en runtime; se valida el registro). | 40 |

> El check de publicador oficial NO puntúa: es una regla dura de elegibilidad (§3). Una fuente no estatal no puede "compensar" con otras dimensiones.

## 3. Elegibilidad y clasificación (RF-402/404)

### 3.1 Elegibilidad normativa

| `eligibility_status` | Significado | Comportamiento |
|---|---|---|
| `eligible` | Puede sustentar claims y narrativa. | Continúa a calidad y T7. |
| `diagnostic_only` | Puede mostrarse como descartada o revisada, pero no sustenta claims. | El agente busca alternativa; si no hay otra, alimenta `no_evidence_report.datasets_reviewed`. |
| `blocked` | No debe exponerse al usuario ni al LLM como filas. | Se descarta antes de T5 o inmediatamente en T6 si llegó por carrera. |

Reglas duras de elegibilidad:
- `publisher_verification_status != "verified"` ⇒ `diagnostic_only`; si es `private_or_non_official`, razón `publisher_private`; si no hay coincidencia o alias no único, razón `publisher_unknown`.
- `pii_risk_level = "unknown"` en dataset o columna seleccionada ⇒ `blocked` antes de ejecutar T5.
- `pii_risk_level = "high"` o `contains_personal_data=true` ⇒ `blocked`.
- `pii_risk_level = "medium"` ⇒ solo `eligible` si la consulta es agregada, usa columnas explícitas no identificantes, no devuelve filas individuales y cumple agregación mínima.
- Agregación mínima para `medium`: cada fila devuelta debe representar al menos 5 registros fuente (`count >= 5` o agregado equivalente verificable); no se permite devolver identificadores, nombres propios, direcciones, teléfonos, correos, documentos, coordenadas precisas u otros campos de reidentificación.

No existe revisión manual ad hoc durante la corrida. Si un humano reclasifica PII, debe actualizar metadatos versionados (`pii_reviewed_by`, `pii_reviewed_at`, `pii_review_source`, `pii_review_notes`) antes de que la ingesta o el perfilado lo considere elegible.

| `score_total` | `classification` | Comportamiento del sistema |
|---|---|---|
| ≥ 75 | `alta` | Inserción normal. Badge azul. |
| 55–74 | `media` | Inserción normal + advertencias visibles. |
| 35–54 | `baja` | Advertencia destacada; el sintetizador debe mencionar la limitación en la narrativa. |
| < 35 | `no_recomendada` | NO se inserta automáticamente; requiere confirmación explícita con advertencia (RF-404). El sintetizador no puede usarla como sustento principal. |

Reglas duras adicionales de calidad (independientes del puntaje):
- `schema.non_empty_result` fallido ⇒ la evidencia no se presenta como hallazgo; se trata como "consulta sin resultados".
- D4 `source_complete` fallido ⇒ `no_recomendada` automática (Art. I.2: sin fuente completa no hay evidencia).

### 3.1a Bloqueos y advertencias de suficiencia (RF-211)

La validación protege la confiabilidad de la evidencia; no certifica que la
consulta sea la mejor entre todas las consultas posibles. Una evidencia
elegible puede sustentar una respuesta suficientemente correcta aunque exista
una selección, filtro, orden, agregación o precisión mejorable.

Son bloqueos: cifras no reproducibles o fabricadas; dataset o fuente que no
sustenta la respuesta; contradicción material entre pregunta, filas y
conclusión; ausencia de trazabilidad; datos personales prohibidos; y fallos
sistemáticos que impiden evaluar la respuesta.

Son advertencias no bloqueantes cuando no alteran la conclusión material:
consulta mejorable; selección temporal no óptima; cobertura parcial declarada;
precisión menor a la deseable; y existencia de otra consulta potencialmente
superior. Si cualquiera de ellas cambia la respuesta, oculta un período
indispensable o impide verificar la afirmación, se considera contradicción u
omisión material y deja de ser una advertencia.

Esta distinción no cambia pesos, umbrales, `eligibility_status` ni la integridad
obligatoria de claims. Tampoco autoriza reglas específicas por caso.

### 3.2 Registro canónico de publicadores oficiales

La validación usa un fixture versionado cargado en `official_publishers` y `official_publisher_aliases`. `official_publishers` usa `id` como identificador estable; los alias viven en tabla separada con unicidad global solo para `alias_normalized` no ambiguos (`ambiguous=false`) mediante índice parcial o mecanismo equivalente. La normalización elimina tildes, convierte a mayúsculas, colapsa espacios y aplica solo alias explícitos del fixture. Universidades públicas, empresas industriales y comerciales del Estado, establecimientos públicos, alcaldías, gobernaciones y demás entidades estatales se aceptan únicamente si están en el registro o en sus alias verificados. Un alias ambiguo produce `publisher_verification_status="unknown"`, nunca asignación automática.

Entidades históricas: una entidad inactiva puede validar un dataset histórico solo si la fecha de publicación/actualización del portal cae dentro de su `valid_from`/`valid_until`, o si `successor_id` documenta continuidad institucional. Si no se puede establecer vigencia, queda `unknown`.

## 4. Salida (objeto `quality`)

```json
{
  "score_total": 82,
  "classification": "alta",
  "eligibility_status": "eligible",
  "eligibility_reasons": [],
  "validator_version": "1.0.0",
  "data_cutoff": {
    "data_cutoff_at": "2025-03-15T00:00:00Z",
    "method": "max_temporal_column",
    "column": "fecha_corte",
    "confidence": 0.9,
    "basis": "data_cutoff_at",
    "inferred_at": "2026-07-06T14:22:31Z"
  },
  "row_policy": {
    "contains_individual_rows": false,
    "aggregation_min_count": 12,
    "pii_policy": "low"
  },
  "dimensions": {
    "schema":       {"score": 100, "checks": [{"check": "schema.columns_present", "passed": true, "detail": "3/3 columnas presentes"}]},
    "completeness": {"score": 60,  "checks": [{"check": "completeness.null_ratio", "passed": false, "detail": "12% de celdas vacías en 'desercion_media'"}]},
    "timeliness":   {"score": 70,  "checks": [{"check": "timeliness.data_age", "passed": true, "detail": "Corte estadístico inferido de la evidencia: 2025-03-15 (~16 meses)", "basis": "data_cutoff_at"}]},
    "traceability": {"score": 100, "checks": [{"check": "traceability.source_complete", "passed": true, "detail": ""}]}
  },
  "warnings_user": [
    "El 12% de los registros de la columna 'deserción media' están vacíos; los promedios pueden variar.",
    "Este dato tiene corte marzo de 2025; puede estar desactualizado."
  ]
}
```

Requisitos del objeto:
- `warnings_user` SIEMPRE en español claro, sin nombres técnicos de checks (Art. V.5). El mapeo check→mensaje vive en `quality/messages_es.py`.
- `validator_version` sigue semver; cambiar pesos o umbrales ⇒ bump de versión menor y nota en CHANGELOG (reproducibilidad OE3).
- `eligibility_status` y `eligibility_reasons` son obligatorios aun cuando `classification` sea `alta`.
- La salida de T6 persiste los metadatos de corte, política de filas y razones de elegibilidad junto al `quality_report`.

## 5. Casos de prueba obligatorios del contrato

La suite `tests/unit/test_quality_*.py` debe cubrir como mínimo (ver pruebas.md §3):
1. Dataset fresco, completo, oficial ⇒ `alta`.
2. Corte > 48 meses ⇒ D3 = 15 y advertencia de desactualización.
3. Columna citada con 60% nulos ⇒ `completeness.null_ratio` = 0 puntos.
4. Valores placeholder confirmados por contexto (`"Default O_D_S"` en >30% de celdas; `9` en columna cuyo codebook lo define como "no aplica") ⇒ pérdida de los 40 puntos y advertencia.
5. **Falsos positivos evitados:** `"Total"` como categoría legítima pedida por el filtro y `9` como valor numérico real en una columna sin codebook NO se marcan como placeholders.
6. Resultado con 0 filas ⇒ regla dura de "consulta sin resultados".
7. Falta `source_url` ⇒ `no_recomendada` forzada.
8. `publisher` no estatal ⇒ evidencia rechazada (regla dura de §3), con explicación en el reporte.
9. Determinismo: misma entrada dos veces ⇒ objetos `quality` idénticos.
10. Temporalidad: corte inferible de las filas de la evidencia usa `data_cutoff_at`; sin campo temporal usa `data_updated_at_fallback` y el mensaje NO llama corte a la fecha de actualización.
11. Publicador oficial: nombre canónico, alias registrado, mayúsculas/tildes, publicador desconocido, publicador privado y entidad estatal válida con denominación abreviada.
12. Datos personales: `unknown` bloquea antes de T5; dataset/columna `high` se rechaza; `medium` exige agregación mínima `count >= 5`, columnas explícitas y ausencia de filas individuales; `low` permite continuar.
13. Elegibilidad vs calidad: evidencia estadísticamente `alta` pero con publicador `unknown` queda `diagnostic_only` y no genera claims.
14. Entidad histórica: publicador inactivo dentro de vigencia pasa; fuera de vigencia sin sucesor queda `unknown`.

## 6. Relación con las afirmaciones cuantitativas (RF-208)

Esta capa valida la **evidencia** (los datos recuperados como conjunto). La validación de las **cifras presentadas** es responsabilidad del modelo de afirmaciones cuantitativas (claims): herramienta T7 de [`agent-tools.md`](./agent-tools.md) y entidad `quantitative_claims` de `data-model.md`. Son complementarias y AMBAS obligatorias antes de la síntesis:

1. Ninguna evidencia llega al constructor de afirmaciones sin `quality_report` (Art. I.4).
2. Ningún claim se construye sobre evidencia clasificada `no_recomendada` como sustento principal (§3).
3. La clasificación de calidad de la evidencia fuente acompaña a cada claim en la presentación: un claim derivado de evidencia `baja` hereda la advertencia correspondiente en `warnings_user`.

**Separación explícita frente a `presentation_warnings` (RF-212, T-617C-A,
`research.md` §29):** `warnings_user` (este documento) evalúa la **evidencia
como conjunto** — score, elegibilidad, frescura, proporción de nulos — y se
hereda por todos los claims derivados de esa evidencia. `presentation_warnings`
(`contracts/api-rest.md` §4c) evalúa si **una cifra individual ya
presentada** tiene una etiqueta humana verificable derivada de metadatos
estructurados de su columna fuente, independientemente de la calidad de la
evidencia que la sustenta. Un claim puede tener `warnings_user` heredado de
su evidencia y, al mismo tiempo, `label_status="verified"` sin ninguna
entrada en `presentation_warnings` — o viceversa: evidencia `alta` sin
ninguna advertencia de calidad, pero con `label_status="ambiguous"` porque
su columna fuente no tiene un nombre/`display_name` que permita derivar una
etiqueta inequívoca. Ninguna implementación de T-617C debe fusionar ambos
campos, escribir advertencias de etiquetado en `warnings_user`, ni modificar
este documento (§1-§5, umbrales, checks, `validator_version`) para
producirlas.
