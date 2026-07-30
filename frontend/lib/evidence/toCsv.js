/**
 * CSV seguro y reproducible de una evidencia (RF-501). Puro: no toca el
 * DOM, no crea `Blob`, no descarga nada — solo produce la cadena de
 * texto. Los encabezados son las etiquetas ya resueltas por
 * `resolveColumns.js`; las filas conservan los valores originales de
 * `evidence.rows` tal cual — sin redondear, reformatear ni recalcular
 * ninguna cifra (Art. I: la cifra mostrada es la del backend, nunca una
 * que el cliente recalculó).
 */
import { describeCutoff } from "./describeCutoff.js";

/** Excel/Sheets abren CSV asumiendo la codificación del sistema salvo que
 * el archivo empiece con esta marca — sin ella, tildes y "ñ" se rompen. */
const UTF8_BOM = "﻿";

/**
 * Caracteres cuya aparición como PRIMER carácter de una celda se
 * neutraliza antes de escribir el CSV (defensa contra "CSV injection" /
 * fórmulas de hoja de cálculo, guía OWASP "CSV Injection"):
 * - `=`, `+`, `-`, `@` — inician una fórmula en la mayoría de programas
 *   de hoja de cálculo al abrir un CSV.
 * - tabulación (`\t`) y retorno de carro (`\r`) — algunos analizadores de
 *   CSV/hoja de cálculo recortan espacio en blanco inicial antes de
 *   decidir si una celda es fórmula; un tabulador o retorno de carro
 *   inicial puede esconder un `=` real detrás de ese recorte.
 * - salto de línea (`\n`) — mismo riesgo que `\r`, incluido por
 *   completitud.
 * - variantes Unicode de ancho completo `＝ ＋ － ＠` (U+FF1D, U+FF0B,
 *   U+FF0D, U+FF20) — homóglifos que algunos programas normalizan a su
 *   forma ASCII antes de evaluar la celda.
 *
 * Esta lista es defensa en profundidad, no una garantía universal: el
 * comportamiento exacto de qué cuenta como fórmula varía entre programas
 * de hoja de cálculo (Excel, Google Sheets, LibreOffice…) y versiones; no
 * se afirma compatibilidad total con todos ellos.
 */
const FORMULA_TRIGGER_CHARS = new Set([
  "=", "+", "-", "@",
  "\t", "\r", "\n",
  "＝", "＋", "－", "＠",
]);

/**
 * Neutraliza inyección de fórmulas: un valor cuyo primer carácter está en
 * `FORMULA_TRIGGER_CHARS` se antepone con un apóstrofo — la convención
 * que Excel/Sheets interpretan como "texto literal, no fórmula", sin
 * alterar el resto del valor. Efecto secundario aceptado y documentado:
 * un número negativo legítimo (`-5.3`) también recibe el apóstrofo,
 * porque `-` es uno de los caracteres exigidos por la regla; el valor
 * numérico en sí no cambia. Se aplica a TODAS las celdas por igual —
 * encabezados, filas de datos y bloque de cita — a través de `csvCell`,
 * nunca solo a un subconjunto.
 */
function neutralizeFormula(text) {
  return text.length > 0 && FORMULA_TRIGGER_CHARS.has(text[0]) ? `'${text}` : text;
}

function csvCell(value) {
  const text = neutralizeFormula(value === null || value === undefined ? "" : String(value));
  const needsQuoting = /["\r\n,]/.test(text);
  const escaped = text.replace(/"/g, '""');
  return needsQuoting ? `"${escaped}"` : escaped;
}

/** Punto único de ensamblado de una fila: toda celda (encabezado, dato o
 * cita) pasa por `csvCell` → `neutralizeFormula`, así que ninguna de las
 * tres superficies puede quedar sin la misma protección. */
function csvRow(cells) {
  return cells.map(csvCell).join(",");
}

/**
 * @param {{evidence: object, resolvedColumns: Array<{key:string,label:string}>}} params
 * @returns {string} CSV completo (con BOM), listo para envolver en un
 *   `Blob` en un incremento posterior — este módulo no hace esa parte.
 */
export function toEvidenceCsv({ evidence, resolvedColumns }) {
  const columns = Array.isArray(resolvedColumns) ? resolvedColumns : [];
  const rows = Array.isArray(evidence?.rows) ? evidence.rows : [];

  const lines = [];
  lines.push(csvRow(columns.map((column) => column.label)));
  for (const row of rows) {
    lines.push(csvRow(columns.map((column) => (row ? row[column.key] : null))));
  }

  // Bloque de cita estable: fila en blanco de separación, luego pares
  // etiqueta/valor — la misma información que `CitationBlock` mostrará
  // (F4-02), para que el CSV siga siendo verificable sin abrir la app.
  lines.push("");
  lines.push(csvRow(["Dataset", evidence?.dataset_name ?? ""]));
  lines.push(csvRow(["Publicador", evidence?.publisher ?? ""]));
  lines.push(csvRow(["Consulta SoQL", evidence?.soql_query ?? ""]));
  lines.push(csvRow(["Fecha de ejecución", evidence?.executed_at ?? ""]));
  lines.push(csvRow(["URL", evidence?.source_url ?? ""]));
  lines.push(csvRow(["Fecha de actualización", evidence?.data_updated_at ?? ""]));
  lines.push(csvRow(["Corte estadístico", describeCutoff(evidence)]));

  return UTF8_BOM + lines.join("\r\n");
}
