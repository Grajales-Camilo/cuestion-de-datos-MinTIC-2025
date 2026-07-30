import { getSchema } from "@tiptap/core";
import { validateDocumentContentJson } from "./documentContentValidation.js";
import { createDocumentEditorExtensions } from "./schema.js";

/**
 * Fuente compartida y PURA (sin React) del documento vacío y de la
 * validación del esquema cerrado (F5-02/F5-03A-R1). `DocumentEditor.jsx`
 * consume esto — no al revés — y lo reexporta para no romper su API
 * pública existente (`components/canvas/editor` sigue exportando
 * `EMPTY_DOCUMENT_JSON`/`validateDocumentEditorJson`).
 */
export const EMPTY_DOCUMENT_JSON = Object.freeze({
  type: "doc",
  content: [{ type: "paragraph" }],
});

let cachedDocumentSchema;

export function getDocumentSchema() {
  if (!cachedDocumentSchema) {
    cachedDocumentSchema = getSchema(createDocumentEditorExtensions());
  }
  return cachedDocumentSchema;
}

/**
 * Valida primero las invariantes F5-01 y después el esquema cerrado de
 * ProseMirror. No corrige ni carga parcialmente un documento inválido.
 */
export function validateDocumentEditorJson(json, options = {}) {
  const contentValidation = validateDocumentContentJson(json, options);
  if (!contentValidation.ok) return contentValidation;

  try {
    const documentNode = getDocumentSchema().nodeFromJSON(json);
    documentNode.check();
    return { ok: true };
  } catch {
    return { ok: false, code: "INVALID_DOCUMENT_SCHEMA" };
  }
}
