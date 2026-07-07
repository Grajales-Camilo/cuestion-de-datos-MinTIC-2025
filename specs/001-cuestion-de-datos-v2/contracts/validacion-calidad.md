# Contrato — Capa de Validación de Calidad de Datos

**Versión:** 1.0.0 · **Fecha:** 2026-07-06
**Implementa:** RF-401…404 · Constitución Art. I.4 · Módulo: `backend/app/quality/`

> Esta capa es **determinista**: mismas entradas ⇒ mismo puntaje. No usa LLM. Es la contribución técnica #3 de la propuesta de maestría (capa formal de validación que verifica esquema, completitud, temporalidad y trazabilidad antes de integrar datos a documentos de política pública).

---

## 1. Entrada

Un borrador de evidencia con: `dataset_id`, metadatos del catálogo (`data_updated_at`, `publisher`, `source_url`), la consulta `soql`, las columnas esperadas del plan del agente y las `rows` obtenidas.

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

1. **Base preferida — `data_cutoff_at`:** el corte estadístico inferido de los propios resultados (máximo valor del campo temporal presente en las filas: `periodo`, `a_o`, `fecha_corte`…), cuando exista y sea parseable.
2. **Fallback explícito — `data_updated_at`:** solo si no puede inferirse el corte; el detalle del check DEBE declarar qué base se usó (`basis: "data_cutoff_at" | "data_updated_at"`).

Edad = hoy − la base seleccionada.

| Edad del corte | Puntaje D3 |
|---|---|
| ≤ 12 meses | 100 |
| 12–24 meses | 70 |
| 24–48 meses | 40 |
| > 48 meses o desconocida | 15 |

Advertencia obligatoria en lenguaje claro cuando D3 ≤ 70 (ESC-05): *"Este dato tiene corte {fecha}; puede estar desactualizado."*

### D4 — Trazabilidad (20%)
| Check | Regla | Puntos |
|---|---|---|
| `traceability.source_complete` | `dataset_id`, nombre, `publisher`, `source_url` presentes y no vacíos. | 60 |
| `traceability.query_reproducible` | El SoQL guardado re-ejecutado es sintácticamente válido (no se re-ejecuta en runtime; se valida el registro). | 40 |

> El check de publicador oficial NO puntúa: es una regla dura de elegibilidad (§3). Una fuente no estatal no puede "compensar" con otras dimensiones.

## 3. Clasificación y comportamiento (RF-402/404)

| `score_total` | `classification` | Comportamiento del sistema |
|---|---|---|
| ≥ 75 | `alta` | Inserción normal. Badge azul. |
| 55–74 | `media` | Inserción normal + advertencias visibles. |
| 35–54 | `baja` | Advertencia destacada; el sintetizador debe mencionar la limitación en la narrativa. |
| < 35 | `no_recomendada` | NO se inserta automáticamente; requiere confirmación explícita con advertencia (RF-404). El sintetizador no puede usarla como sustento principal. |

Reglas duras adicionales (independientes del puntaje):
- `schema.non_empty_result` fallido ⇒ la evidencia no se presenta como hallazgo; se trata como "consulta sin resultados".
- D4 `source_complete` fallido ⇒ `no_recomendada` automática (Art. I.2: sin fuente completa no hay evidencia).
- **`traceability.publisher_official` fallido ⇒ evidencia RECHAZADA (no elegible).** Si el `publisher` no es identificable como entidad estatal (contra la lista de entidades oficiales del catálogo), la evidencia NO se presenta al usuario ni sustenta claims: el agente debe buscar una fuente oficial alternativa o reportar `no_evidence`, explicando que existía un dataset no gubernamental descartado. Coherente con Constitución Art. I (fuentes oficiales); admitir fuentes no oficiales pre-aprobadas requeriría enmienda constitucional.

## 4. Salida (objeto `quality`)

```json
{
  "score_total": 82,
  "classification": "alta",
  "validator_version": "1.0.0",
  "dimensions": {
    "schema":       {"score": 100, "checks": [{"check": "schema.columns_present", "passed": true, "detail": "3/3 columnas presentes"}]},
    "completeness": {"score": 60,  "checks": [{"check": "completeness.null_ratio", "passed": false, "detail": "12% de celdas vacías en 'desercion_media'"}]},
    "timeliness":   {"score": 70,  "checks": [{"check": "timeliness.data_age", "passed": true, "detail": "Corte estadístico inferido 2025-03-15 (~16 meses)", "basis": "data_cutoff_at"}]},
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
10. Temporalidad: corte inferible de los datos usa `data_cutoff_at`; sin campo temporal usa `data_updated_at` y el detalle declara `basis`.

## 6. Relación con las afirmaciones cuantitativas (RF-208)

Esta capa valida la **evidencia** (los datos recuperados como conjunto). La validación de las **cifras presentadas** es responsabilidad del modelo de afirmaciones cuantitativas (claims): herramienta T7 de [`agent-tools.md`](./agent-tools.md) y entidad `quantitative_claims` de `data-model.md`. Son complementarias y AMBAS obligatorias antes de la síntesis:

1. Ninguna evidencia llega al constructor de afirmaciones sin `quality_report` (Art. I.4).
2. Ningún claim se construye sobre evidencia clasificada `no_recomendada` como sustento principal (§3).
3. La clasificación de calidad de la evidencia fuente acompaña a cada claim en la presentación: un claim derivado de evidencia `baja` hereda la advertencia correspondiente en `warnings_user`.
