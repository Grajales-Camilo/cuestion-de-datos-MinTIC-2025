/**
 * Especificación determinista de gráfica de evidencia (RF-503,
 * `implementation-plan.md` §8.2 punto 6, divergencia D-4). Puro: sin
 * Chart.js, sin callbacks, sin red, sin DOM — solo deriva QUÉ graficar de
 * los datos ya presentes en `evidence`/`resolvedColumns`. Nunca agrega,
 * agrupa, ordena, redondea, rellena huecos ni calcula porcentajes o
 * tendencias: los valores replican EXACTAMENTE los de `evidence.rows`, en
 * el mismo orden — la misma garantía que ya cumplen `EvidenceTable` y
 * `toEvidenceCsv`. El único ChartSpec devuelto es completo; nunca parcial.
 */
import { isEligibleEvidence } from "./eligibility.js";

const ALLOWED_CHART_TYPES = new Set(["bar", "line"]);
// count(*)/count(campo)/count(distinct campo) (kind "count") y
// sum/avg/min/max (kind "metric") son las únicas formas que
// `resolveEvidenceColumns` clasifica con certeza numérica (regla 5,
// F4-03) — las únicas que pueden ocupar el eje de valores.
const METRIC_LIKE_KINDS = new Set(["metric", "count"]);
// Cadena numérica canónica: sin separadores de miles, sin notación
// científica, sin espacios — nunca se "adivina" un número.
const CANONICAL_NUMBER = /^-?(0|[1-9]\d*)(\.\d+)?$/;

/** `null` salvo que `value` sea ya un número finito o una cadena numérica
 * canónica. Cualquier otra forma (texto no numérico, `null`, `undefined`,
 * booleano, objeto, `NaN`, `Infinity`) invalida el valor. */
function toFiniteNumber(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!CANONICAL_NUMBER.test(trimmed)) return null;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * Resuelve una referencia `x`/`y` de `chart_suggestion` contra
 * `resolvedColumns`, aceptando tanto `column.key` (el alias real que usan
 * las `rows`, p. ej. `dim_4`) como `column.fieldName` (el nombre de columna
 * real que el contrato usa en su ejemplo normativo, p. ej. `a_o`) —
 * `chart_suggestion` es la autoridad semántica del backend sobre los ejes
 * (F4-03-R1), pero el runtime real puede seguir citando alias donde el
 * contrato cita nombres reales.
 *
 * Política fail-closed de desambiguación (F4-03-R2 — dos métricas
 * distintas, p. ej. `sum(valor)` y `avg(valor)`, resuelven el MISMO
 * `fieldName:"valor"`; adivinar cuál quiso decir la sugerencia mostraría
 * una serie incorrecta):
 * 1. Se busca primero por `column.key` (exacto). Con EXACTAMENTE una
 *    coincidencia, se usa esa — es la referencia más específica posible.
 * 2. Con CERO coincidencias por `key`, se busca por `column.fieldName`.
 *    Con EXACTAMENTE una coincidencia, se usa esa.
 * 3. Cualquier otro conteo (0 o ≥2 coincidencias, en cualquiera de las dos
 *    etapas) es AMBIGUO → `null`. Nunca se toma "la primera" coincidencia
 *    ambigua, ni se infiere la operación (`sum`/`avg`/…) desde el tipo de
 *    gráfica, las etiquetas, la posición o los valores — eso sería
 *    inventar semántica que el backend no declaró.
 *
 * Solo columnas `resolved:true` participan (regla 6: `unknown`/
 * `unresolved` nunca entra a una gráfica).
 */
function findColumnByRef(resolvedColumns, ref) {
  if (typeof ref !== "string") return null;
  const resolved = resolvedColumns.filter((column) => column?.resolved === true);

  const keyMatches = resolved.filter((column) => column.key === ref);
  if (keyMatches.length === 1) return keyMatches[0];
  if (keyMatches.length > 1) return null; // ambiguo incluso por key: fail-closed

  const fieldNameMatches = resolved.filter((column) => column.fieldName === ref);
  return fieldNameMatches.length === 1 ? fieldNameMatches[0] : null; // 0 o ≥2 → null
}

/** Extrae `{labels, values}` de `rows` para el par x/y ya validado —
 * literal, en el orden original de las filas, sin ninguna transformación
 * salvo la coerción numérica exigida de `values` (regla 8). Cualquier
 * valor de métrica nulo/ambiguo/no finito invalida la extracción COMPLETA
 * (nunca una serie parcial): se aborta en la primera fila inválida. */
function extractSeries(rows, xKey, yKey) {
  const labels = [];
  const values = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") return null;
    const numericValue = toFiniteNumber(row[yKey]);
    if (numericValue === null) return null;
    labels.push(row[xKey]);
    values.push(numericValue);
  }
  return { labels, values };
}

function buildSpec({ type, evidence, xColumn, yColumn, rows, source }) {
  const series = extractSeries(rows, xColumn.key, yColumn.key);
  if (!series || series.values.length === 0) return null;

  return {
    type,
    datasetName: typeof evidence.dataset_name === "string" ? evidence.dataset_name : null,
    xLabel: xColumn.label,
    yLabel: yColumn.label,
    labels: series.labels,
    values: series.values,
    source,
  };
}

/**
 * Valida `evidence.chart_suggestion` (`contracts/api-rest.md` §5, §9:
 * campos aditivos desconocidos se ignoran, nunca rompen al cliente).
 * Reglas propias de la sugerencia — DISTINTAS de las del fallback D-4
 * (F4-03-R1):
 * - `type`, `x` e `y` son obligatorios; cualquier otra propiedad (p. ej.
 *   `title`) se ignora y nunca se copia al `ChartSpec`.
 * - `type` debe estar en el conjunto soportado (`bar`/`line`).
 * - `x`/`y` deben resolver (por `key` o por `fieldName`,
 *   `findColumnByRef`) a columnas YA resueltas (regla 6) y DISTINTAS
 *   entre sí — comparadas por identidad real (`column.key`), no por la
 *   cadena cruda de la sugerencia, porque `x`/`y` pueden referirse a la
 *   misma columna con dos formas de nombrarla.
 * - `y` NO necesita clasificar como `metric`/`count`: la sugerencia del
 *   backend es la autoridad semántica sobre qué eje es cuál (a diferencia
 *   del fallback, que sí debe adivinar sin esa autoridad). Los valores de
 *   `y` igual deben ser numéricos canónicos y finitos en TODA fila
 *   (`extractSeries`/`toFiniteNumber`) — política de serie completa o
 *   `null`, sin excepción.
 */
function specFromSuggestion(evidence, resolvedColumns) {
  const suggestion = evidence?.chart_suggestion;
  if (!suggestion || typeof suggestion !== "object" || Array.isArray(suggestion)) return null;

  const { type, x, y } = suggestion;
  if (typeof type !== "string" || !ALLOWED_CHART_TYPES.has(type)) return null;
  if (typeof x !== "string" || typeof y !== "string") return null;

  const xColumn = findColumnByRef(resolvedColumns, x);
  const yColumn = findColumnByRef(resolvedColumns, y);
  if (!xColumn || !yColumn || xColumn.key === yColumn.key) return null;

  const rows = Array.isArray(evidence.rows) ? evidence.rows : [];
  return buildSpec({ type, evidence, xColumn, yColumn, rows, source: "chart_suggestion" });
}

/**
 * Fallback D-4 (`implementation-plan.md` §8.2 punto 6): se intenta
 * ÚNICAMENTE cuando `chart_suggestion` no produjo una especificación
 * utilizable. Exige que `resolveEvidenceColumns` haya producido
 * EXACTAMENTE una dimensión resuelta y EXACTAMENTE una métrica resuelta
 * (`metric` o `count`, regla 5) y al menos 3 filas — nunca se activa con
 * 0, 2 o más columnas candidatas de cada tipo: adivinar cuál de varias es
 * "la" dimensión o "la" métrica está prohibido. El tipo de gráfica es
 * `"bar"`: no hay ninguna sugerencia de tipo que replicar.
 */
function specFromFallback(evidence, resolvedColumns) {
  const rows = Array.isArray(evidence.rows) ? evidence.rows : [];
  if (rows.length < 3) return null;

  const dimensions = resolvedColumns.filter((c) => c?.resolved === true && c.kind === "dimension");
  const metrics = resolvedColumns.filter((c) => c?.resolved === true && METRIC_LIKE_KINDS.has(c?.kind));
  if (dimensions.length !== 1 || metrics.length !== 1) return null;

  return buildSpec({ type: "bar", evidence, xColumn: dimensions[0], yColumn: metrics[0], rows, source: "fallback" });
}

/**
 * @param {{evidence: object, resolvedColumns: Array<object>}} params
 *   `resolvedColumns` es la salida `.columns` de `resolveEvidenceColumns`.
 * @returns {{type:string, datasetName:string|null, xLabel:string,
 *   yLabel:string, labels:Array, values:number[], source:string}|null}
 *   ChartSpec mínimo y serializable (sin objetos de Chart.js ni
 *   callbacks), o `null` si no hay una especificación completa y
 *   verificable — NUNCA una especificación parcial.
 */
export function buildEvidenceChartSpec({ evidence, resolvedColumns }) {
  if (!evidence || typeof evidence !== "object") return null;
  if (!isEligibleEvidence(evidence)) return null;

  const columns = Array.isArray(resolvedColumns) ? resolvedColumns : [];
  return specFromSuggestion(evidence, columns) ?? specFromFallback(evidence, columns);
}
