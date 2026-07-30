import { ReactNodeViewRenderer } from "@tiptap/react";
import { EvidenceCitationNodeBase } from "../../../../lib/document/evidenceCitationNode.js";
import { EvidenceCitationNodeView } from "../EvidenceCitationNodeView.jsx";

/**
 * Capa React del nodo atómico de cita de evidencia (T-504, RF-103):
 * extiende `EvidenceCitationNodeBase` (puro, `lib/document/`) ÚNICAMENTE
 * para añadir el `NodeView` interactivo — nunca redefine atributos,
 * comandos ni la guarda transaccional, que viven exclusivamente en la base
 * compartida (evita dos esquemas manuales que puedan divergir; ver prueba
 * de paridad en `tests/unit/document/schemaParity.test.js`).
 */
export const EvidenceCitationNode = EvidenceCitationNodeBase.extend({
  addNodeView() {
    return ReactNodeViewRenderer(EvidenceCitationNodeView);
  },
});

export default EvidenceCitationNode;
