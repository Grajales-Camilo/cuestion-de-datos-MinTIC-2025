import { validateEvidenceCitationDocumentJson } from "./evidenceCitation.js";
import {
  MANUAL_ENTRY_ERROR_CODES,
  validateManualEntryAttrs,
} from "./manualEntry.js";

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * Guarda documental única para las dos familias de nodos atómicos. La
 * validación existente de EvidenceCitation sigue siendo la fuente de sus
 * invariantes; aquí se añade manualEntry y su unicidad en todo el documento.
 */
export function validateDocumentContentJson(json, { seenManualEntryIds = new Set() } = {}) {
  const citationValidation = validateEvidenceCitationDocumentJson(json);
  if (!citationValidation.ok) return citationValidation;

  function visit(node) {
    if (!isPlainObject(node)) {
      return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_DOCUMENT_JSON };
    }

    if (node.type === "manualEntry") {
      const validation = validateManualEntryAttrs(node.attrs);
      if (!validation.ok) return validation;
      if (seenManualEntryIds.has(node.attrs.manualEntryId)) {
        return {
          ok: false,
          code: MANUAL_ENTRY_ERROR_CODES.DUPLICATE_MANUAL_ENTRY_ID,
        };
      }
      seenManualEntryIds.add(node.attrs.manualEntryId);
    }

    if (node.content !== undefined) {
      if (!Array.isArray(node.content)) {
        return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_DOCUMENT_JSON };
      }
      for (const child of node.content) {
        const result = visit(child);
        if (!result.ok) return result;
      }
    }

    return { ok: true };
  }

  return visit(json);
}
