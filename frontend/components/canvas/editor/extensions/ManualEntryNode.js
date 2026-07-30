import { ReactNodeViewRenderer } from "@tiptap/react";
import { ManualEntryNodeBase } from "../../../../lib/document/manualEntryNode.js";
import { ManualDataEntryNodeView } from "../ManualDataEntryNodeView.jsx";

/**
 * Capa visual del nodo manualEntry. Atributos, comando y guarda permanecen
 * en ManualEntryNodeBase para conservar paridad exacta con headless.
 */
export const ManualEntryNode = ManualEntryNodeBase.extend({
  addNodeView() {
    return ReactNodeViewRenderer(ManualDataEntryNodeView);
  },
});

export default ManualEntryNode;
