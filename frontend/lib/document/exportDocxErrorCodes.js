/**
 * Códigos de error de la exportación DOCX (F6-02B), en un módulo contractual
 * liviano SIN importar `docx` ni `exportDocxTree.js`. `ExportDocumentButton.jsx`
 * importa esto de forma ESTÁTICA para traducir errores a español sin que eso
 * arrastre la carga estática de `docx` (~500 KB) al bundle de `/app`. El
 * exportador real (`exportDocx.js`) reexporta el mismo objeto — una sola
 * fuente de verdad, nunca dos listas de códigos que puedan divergir.
 */
export const EXPORT_DOCX_ERROR_CODES = Object.freeze({
  INVALID_DOCUMENT: "INVALID_DOCUMENT",
  UNSUPPORTED_TEMPLATE: "UNSUPPORTED_TEMPLATE",
  SENSITIVE_DATA_DETECTED: "SENSITIVE_DATA_DETECTED",
  GENERATION_FAILED: "GENERATION_FAILED",
});
