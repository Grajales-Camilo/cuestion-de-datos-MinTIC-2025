import { createBaseDocumentExtensions } from "../../../lib/document/schema.js";
import { EvidenceCitationNode } from "./extensions/EvidenceCitationNode.js";
import { ManualEntryNode } from "./extensions/ManualEntryNode.js";

/**
 * Extensiones del editor VISUAL (React): reutiliza la base pura de
 * `lib/document/schema.js` y añade el nodo de cita ya extendido con su
 * `NodeView` (`EvidenceCitationNode`, no la base). Esta es la única función
 * que debe alimentar `useEditor()` — la validación headless usa en cambio
 * `createDocumentEditorExtensions` de `lib/document/schema.js`.
 */
export function createVisualDocumentEditorExtensions(evidenceCitationOptions = {}) {
  return [
    ...createBaseDocumentExtensions(),
    EvidenceCitationNode.configure(evidenceCitationOptions),
    ManualEntryNode,
  ];
}
