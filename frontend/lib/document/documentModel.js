/**
 * Modelo documental versionado y puro (F5-03A, RF-101/RF-104). Sin React,
 * sin `fetch`, sin acceso a `document`/almacenamiento — igual que
 * `lib/document/evidenceCitation.js` y `lib/agent/contextHint.js`.
 *
 * Forma:
 * {
 *   version, templateId, title,
 *   sections: [{ sectionId, title, description?, content: ProseMirrorJSON }]
 * }
 *
 * Solo existe hoy la plantilla "libre": MGA y "plan de desarrollo" siguen
 * fuera de alcance (D-6 PENDIENTE, `implementation-plan.md` D-6). No se debe
 * fabricar el contenido de ninguna plantilla de dominio aquí.
 */

import { EMPTY_DOCUMENT_JSON, validateDocumentEditorJson } from "./documentSchema.js";

export const DOCUMENT_MODEL_VERSION = 1;
export const FREE_TEMPLATE_ID = "libre";

export const DOCUMENT_MODEL_ERROR_CODES = Object.freeze({
  INVALID_DOCUMENT: "INVALID_DOCUMENT",
  INVALID_VERSION: "INVALID_VERSION",
  INVALID_TEMPLATE_ID: "INVALID_TEMPLATE_ID",
  INVALID_TITLE: "INVALID_TITLE",
  INVALID_SECTIONS: "INVALID_SECTIONS",
  INVALID_SECTION_ID: "INVALID_SECTION_ID",
  DUPLICATE_SECTION_ID: "DUPLICATE_SECTION_ID",
  INVALID_SECTION_CONTENT: "INVALID_SECTION_CONTENT",
});

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

/**
 * Valida el documento completo. Una sola sección inválida invalida el
 * documento entero: no hay carga parcial (F5-03A, regla explícita).
 *
 * @param {unknown} doc
 * @returns {{ok: true}|{ok: false, code: string, sectionId?: string}}
 */
export function validateDocumentModel(doc) {
  if (!isPlainObject(doc)) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_DOCUMENT };
  }
  if (doc.version !== DOCUMENT_MODEL_VERSION) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_VERSION };
  }
  // Exclusivamente FREE_TEMPLATE_ID en DOCUMENT_MODEL_VERSION=1 (F5-03A-R1).
  // Comparación estricta, sin normalizar mayúsculas/espacios ni reparar el
  // valor: "plan-de-desarrollo", "mga" o cualquier variante quedan
  // rechazados explícitamente. D-6 sigue PENDIENTE — no se declaran aquí
  // IDs de plantillas futuras.
  if (doc.templateId !== FREE_TEMPLATE_ID) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_TEMPLATE_ID };
  }
  if (!isNonEmptyString(doc.title)) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_TITLE };
  }
  if (!Array.isArray(doc.sections) || doc.sections.length === 0) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS };
  }

  const seenSectionIds = new Set();
  const seenManualEntryIds = new Set();
  for (const section of doc.sections) {
    if (!isPlainObject(section)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS };
    }
    if (!isNonEmptyString(section.sectionId)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTION_ID };
    }
    if (seenSectionIds.has(section.sectionId)) {
      return {
        ok: false,
        code: DOCUMENT_MODEL_ERROR_CODES.DUPLICATE_SECTION_ID,
        sectionId: section.sectionId,
      };
    }
    seenSectionIds.add(section.sectionId);

    if (!isNonEmptyString(section.title)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS, sectionId: section.sectionId };
    }
    if (section.description !== undefined && !isNonEmptyString(section.description)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS, sectionId: section.sectionId };
    }

    const contentValidation = validateDocumentEditorJson(section.content, {
      seenManualEntryIds,
    });
    if (!contentValidation.ok) {
      return {
        ok: false,
        code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTION_CONTENT,
        sectionId: section.sectionId,
      };
    }
  }

  return { ok: true };
}

/**
 * Única plantilla real de este incremento. Una sección vacía, sin contenido
 * fabricado: el humano redacta, el agente no inventa estructura de dominio.
 */
export function createFreeTemplateDocument() {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: "Documento libre",
    sections: [
      {
        sectionId: "seccion-1",
        title: "Sección 1",
        content: structuredClone(EMPTY_DOCUMENT_JSON),
      },
    ],
  };
}
