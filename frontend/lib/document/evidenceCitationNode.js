import { Node } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import { buildEvidenceCitationAttrs, validateEvidenceCitationDocumentJson } from "./evidenceCitation.js";

/**
 * Base PURA del nodo atómico de cita de evidencia (T-504, RF-103): atributos,
 * comandos, `parseHTML`/`renderHTML` y la guarda transaccional. Sin React,
 * sin `@tiptap/react`, sin `ReactNodeViewRenderer`. Es la fuente compartida
 * de esquema que usa tanto la validación headless (`lib/document/schema.js`,
 * `lib/document/documentSchema.js`) como el editor visual — que la extiende
 * SOLO para añadir el `NodeView` de React
 * (`components/canvas/editor/extensions/EvidenceCitationNode.js`). Ambas
 * capas comparten exactamente los mismos atributos e invariantes: nunca se
 * mantienen dos definiciones manuales que puedan divergir (prueba de
 * paridad en `tests/unit/document/schemaParity.test.js`).
 */

function storedAttribute(defaultValue = null) {
  return { default: defaultValue, rendered: false };
}

function buildCommandPayload(payload, options) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return payload;
  }

  return {
    ...payload,
    citationId: payload.citationId ?? options.createCitationId(),
    insertedAt: payload.insertedAt ?? options.createInsertedAt(),
  };
}

function documentWithCandidateCitation(documentJson, attrs) {
  return {
    ...documentJson,
    content: [...(Array.isArray(documentJson.content) ? documentJson.content : []), { type: "evidenceCitation", attrs }],
  };
}

export const EvidenceCitationNodeBase = Node.create({
  name: "evidenceCitation",
  group: "block",
  atom: true,
  selectable: true,
  draggable: false,

  addOptions() {
    return {
      createCitationId: () => globalThis.crypto?.randomUUID?.() ?? null,
      createInsertedAt: () => new Date().toISOString(),
    };
  },

  addAttributes() {
    return {
      citationId: storedAttribute(),
      runId: storedAttribute(),
      evidenceId: storedAttribute(),
      datasetId: storedAttribute(),
      datasetName: storedAttribute(),
      publisher: storedAttribute(),
      soqlQuery: storedAttribute(),
      executedAt: storedAttribute(),
      sourceUrl: storedAttribute(),
      dataUpdatedAt: storedAttribute(),
      dataCutoffAt: storedAttribute(),
      dataCutoffBasis: storedAttribute(),
      qualityScore: storedAttribute(),
      qualityClassification: storedAttribute(),
      eligibilityStatus: storedAttribute(),
      warningRequired: storedAttribute(false),
      claims: storedAttribute([]),
      insertedAt: storedAttribute(),
    };
  },

  parseHTML() {
    return [];
  },

  renderHTML() {
    return ["div", { "data-evidence-citation": "true", contenteditable: "false" }];
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        filterTransaction(transaction) {
          return validateEvidenceCitationDocumentJson(transaction.doc.toJSON()).ok;
        },
      }),
    ];
  },

  addCommands() {
    return {
      insertEvidenceCitation:
        (payload) =>
        ({ commands, state }) => {
          try {
            const result = buildEvidenceCitationAttrs(buildCommandPayload(payload, this.options));
            if (!result.ok) return false;

            const candidateDocument = documentWithCandidateCitation(state.doc.toJSON(), result.attrs);
            if (!validateEvidenceCitationDocumentJson(candidateDocument).ok) {
              return false;
            }

            return commands.insertContent({
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

export default EvidenceCitationNodeBase;
