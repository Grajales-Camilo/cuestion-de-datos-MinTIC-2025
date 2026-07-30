import { Node } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import { validateDocumentContentJson } from "./documentContentValidation.js";
import {
  buildManualEntryAttrs,
  validateManualEntryAttrs,
} from "./manualEntry.js";

function storedAttribute(defaultValue = null) {
  return { default: defaultValue, rendered: false };
}

function buildCommandPayload(payload, options) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return payload;
  return {
    ...payload,
    manualEntryId: payload.manualEntryId ?? options.createManualEntryId(),
    createdAt: payload.createdAt ?? options.createCreatedAt(),
  };
}

function documentWithCandidateManualEntry(documentJson, attrs) {
  return {
    ...documentJson,
    content: [
      ...(Array.isArray(documentJson.content) ? documentJson.content : []),
      { type: "manualEntry", attrs },
    ],
  };
}

/**
 * Nodo puro compartido por el esquema headless y el editor visual. Es
 * atómico, de bloque y no tiene ruta `parseHTML`: el pegado HTML no puede
 * fabricar aportes manuales (T-506, RF-102/RF-103, Arts. I y V).
 */
export const ManualEntryNodeBase = Node.create({
  name: "manualEntry",
  group: "block",
  atom: true,
  selectable: true,
  draggable: false,

  addOptions() {
    return {
      createManualEntryId: () => globalThis.crypto?.randomUUID?.() ?? null,
      createCreatedAt: () => new Date().toISOString(),
    };
  },

  addAttributes() {
    return {
      manualEntryId: storedAttribute(),
      value: storedAttribute(),
      text: storedAttribute(),
      source: storedAttribute(),
      url: storedAttribute(),
      date: storedAttribute(),
      createdAt: storedAttribute(),
    };
  },

  parseHTML() {
    return [];
  },

  renderHTML() {
    return ["div", { "data-manual-entry": "true", contenteditable: "false" }];
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        filterTransaction(transaction) {
          return validateDocumentContentJson(transaction.doc.toJSON()).ok;
        },
      }),
    ];
  },

  addCommands() {
    return {
      insertManualEntry:
        (payload) =>
        ({ commands, state }) => {
          try {
            const result = buildManualEntryAttrs(buildCommandPayload(payload, this.options));
            if (!result.ok) return false;

            const candidateDocument = documentWithCandidateManualEntry(
              state.doc.toJSON(),
              result.attrs,
            );
            if (!validateDocumentContentJson(candidateDocument).ok) return false;

            // El aporte se agrega al final del documento. Así una selección
            // atómica existente (por ejemplo, una evidenceCitation) nunca se
            // reemplaza al abrir el formulario desde la sección.
            return commands.insertContentAt(state.doc.content.size, {
              type: this.name,
              attrs: result.attrs,
            });
          } catch {
            return false;
          }
        },
    };
  },
});

// Se importa en pruebas/consumidores que necesitan la misma validación de
// atributos sin conocer la implementación del nodo.
export { validateManualEntryAttrs };

export default ManualEntryNodeBase;
