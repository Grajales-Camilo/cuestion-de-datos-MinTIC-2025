/**
 * Derivación de `context_hint` desde el contenido ProseMirror de una
 * sección (F5-03A, RF-104). Pura: sin React, sin `fetch`.
 *
 * Extrae ÚNICAMENTE el texto visible — nunca JSON crudo, atributos de
 * `evidenceCitation`, SoQL ni metadatos ocultos. `evidenceCitation` es un
 * nodo hoja sin `content` (invariante de `evidenceCitation.js`), así que
 * queda excluido por construcción: solo se recorren nodos `text`.
 */

import { normalizeContextHint } from "../agent/contextHint";

export const SECTION_CONTEXT_HINT_MAX_LENGTH = 1000;

// Tipos de nodo cuyos hijos son bloques (párrafos, otros bloques) y deben
// separarse con un salto de línea para no fusionar palabras de bloques
// distintos. Los demás tipos con `content` (párrafo, encabezado) contienen
// directamente corridas de texto en línea y se concatenan sin separador.
const BLOCK_CONTAINER_TYPES = new Set(["doc", "blockquote", "bulletList", "orderedList", "listItem"]);

function extractNodeText(node) {
  if (!node || typeof node !== "object") return "";
  if (node.type === "text") {
    return typeof node.text === "string" ? node.text : "";
  }
  if (!Array.isArray(node.content) || node.content.length === 0) return "";

  const childTexts = node.content.map(extractNodeText).filter((text) => text.length > 0);
  if (childTexts.length === 0) return "";

  return BLOCK_CONTAINER_TYPES.has(node.type) ? childTexts.join("\n") : childTexts.join("");
}

function collapseWhitespace(text) {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * @param {unknown} sectionContent - JSON ProseMirror de la sección (`doc`).
 * @returns {string} texto visible, con espacios normalizados.
 */
export function extractSectionText(sectionContent) {
  return collapseWhitespace(extractNodeText(sectionContent));
}

/**
 * @param {unknown} sectionContent
 * @param {{maxLength?: number}} [options]
 * @returns {{value: string, truncated: boolean, isEmpty: boolean}}
 */
export function deriveSectionContextHint(sectionContent, { maxLength = SECTION_CONTEXT_HINT_MAX_LENGTH } = {}) {
  const rawText = extractSectionText(sectionContent);
  const normalized = normalizeContextHint(rawText, { maxLength });
  return { ...normalized, isEmpty: normalized.value.trim().length === 0 };
}
