import { Node } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { EvidenceCitationNodeBase } from "./evidenceCitationNode.js";
import { ManualEntryNodeBase } from "./manualEntryNode.js";

const ALLOWED_HEADING_LEVELS = Object.freeze([2, 3, 4]);

const RestrictedHeading = Node.create({
  name: "heading",
  content: "inline*",
  group: "block",
  defining: true,

  addAttributes() {
    return {
      level: {
        default: 2,
        rendered: false,
        validate(value) {
          if (!ALLOWED_HEADING_LEVELS.includes(value)) {
            throw new Error("UNSUPPORTED_HEADING_LEVEL");
          }
        },
      },
    };
  },

  parseHTML() {
    return ALLOWED_HEADING_LEVELS.map((level) => ({
      tag: `h${level}`,
      attrs: { level },
    }));
  },

  renderHTML({ node }) {
    const level = ALLOWED_HEADING_LEVELS.includes(node.attrs.level)
      ? node.attrs.level
      : 2;
    return [`h${level}`, 0];
  },

  addCommands() {
    return {
      setHeading:
        (attributes) =>
        ({ commands }) => {
          if (!ALLOWED_HEADING_LEVELS.includes(attributes?.level)) return false;
          return commands.setNode(this.name, attributes);
        },
      toggleHeading:
        (attributes) =>
        ({ commands }) => {
          if (!ALLOWED_HEADING_LEVELS.includes(attributes?.level)) return false;
          return commands.toggleNode(this.name, "paragraph", attributes);
        },
    };
  },
});

/**
 * Extensiones comunes del documento Tiptap de F5-01, sin el nodo de cita de
 * evidencia. No incluye Link, HTML arbitrario ni nodos de presentación
 * futuros. Compartida por la variante headless (este archivo) y la variante
 * visual (`components/canvas/editor/visualExtensions.js`), que le añade el
 * nodo de cita con su `NodeView` de React.
 */
export function createBaseDocumentExtensions() {
  return [
    StarterKit.configure({
      code: false,
      codeBlock: false,
      dropcursor: false,
      gapcursor: false,
      hardBreak: false,
      heading: false,
      horizontalRule: false,
      link: false,
      strike: false,
      // trailingNode NO se deshabilita (a diferencia del resto de esta
      // lista): hallazgo de revisión manual F8-02 — con esta extensión
      // apagada, un `evidenceCitation`/`manualEntry` (nodos atómicos,
      // `atom: true`) al final del documento no tenía ningún nodo de texto
      // detrás. `focus("end")` (ya usado tras cada inserción,
      // `DocumentEditor.jsx`) o `Ctrl+End` dejaban una SELECCIÓN DE NODO
      // sobre la cita, y escribir la REEMPLAZABA por completo — pérdida de
      // contenido real, reproducida y confirmada. `trailingNode` (bundle de
      // `@tiptap/starter-kit`, ninguna dependencia nueva) garantiza un
      // párrafo vacío después de cualquier nodo que no sea de texto, tanto
      // al escribir como al cargar un documento persistido que ya haya
      // quedado en ese estado.
      underline: false,
      undoRedo: false,
    }),
    RestrictedHeading,
  ];
}

/**
 * Extensiones completas, 100% puras (sin React): usa la base del nodo de
 * cita (`EvidenceCitationNodeBase`, sin `NodeView`). Es la fuente de verdad
 * del esquema cerrado para validación headless — `documentSchema.js` en
 * este mismo directorio, y por extensión `documentModel.js` — que nunca
 * debe importar nada bajo `components/`.
 */
export function createDocumentEditorExtensions(evidenceCitationOptions = {}) {
  return [
    ...createBaseDocumentExtensions(),
    EvidenceCitationNodeBase.configure(evidenceCitationOptions),
    ManualEntryNodeBase,
  ];
}
