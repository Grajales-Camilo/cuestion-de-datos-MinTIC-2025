/**
 * Texto de cita en texto plano, compartido por `CitationBlock` (F4-02,
 * lectura) y `CopyCitationButton` (F4-02, portapapeles) — una sola fuente de
 * verdad para no divergir entre ambos consumidores, igual que
 * `describeCutoff.js` ya hace para el texto de corte. Puro: sin React, sin
 * `window`/`document`/`navigator`, determinista.
 */
import { describeCutoff, formatSpanishDate } from "./describeCutoff.js";

const NOT_AVAILABLE = "No disponible";

function textOrFallback(value) {
  return typeof value === "string" && value.trim() !== "" ? value : NOT_AVAILABLE;
}

function dateOrFallback(isoString) {
  return formatSpanishDate(isoString) ?? textOrFallback(isoString);
}

/**
 * @param {object} evidence - objeto Evidencia (`contracts/api-rest.md` §5).
 * @returns {string} cita completa en texto plano, lista para portapapeles o
 *   para renderizarse como texto (nunca HTML).
 */
export function buildCitationText(evidence) {
  const lines = [
    `Dataset: ${textOrFallback(evidence?.dataset_name)}`,
    `Publicador: ${textOrFallback(evidence?.publisher)}`,
    `Consulta SoQL: ${textOrFallback(evidence?.soql_query)}`,
    `Fecha de ejecución: ${dateOrFallback(evidence?.executed_at)}`,
    `URL: ${textOrFallback(evidence?.source_url)}`,
    `Fecha de actualización: ${dateOrFallback(evidence?.data_updated_at)}`,
    describeCutoff(evidence),
  ];
  return lines.join("\n");
}
