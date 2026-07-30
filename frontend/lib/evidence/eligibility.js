/**
 * Elegibilidad fail-closed de una evidencia
 * (`contracts/validacion-calidad.md` §3.1). SOLO
 * `quality.eligibility_status === "eligible"` puede sustentar claims,
 * mostrarse como hallazgo o graficarse. `blocked`/`diagnostic_only` nunca
 * se exponen al usuario; un `eligibility_status` ausente o desconocido NO
 * se asume elegible — falla cerrado ante cualquier valor no reconocido,
 * igual que cualquier otro. Fuente única para `EvidenceCard`,
 * `TerminalPanel` y `chartSpec.js` — antes duplicada localmente en los dos
 * primeros (F4-02-R1), centralizada aquí en F4-03. Puro: sin red, sin DOM.
 *
 * @param {object} evidence
 * @returns {boolean}
 */
export function isEligibleEvidence(evidence) {
  return evidence?.quality?.eligibility_status === "eligible";
}
