import { forwardRef, useImperativeHandle, useMemo, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import { FileText } from "lucide-react";
import { EMPTY_DOCUMENT_JSON, validateDocumentEditorJson } from "../../../lib/document/documentSchema.js";
import { createVisualDocumentEditorExtensions } from "./visualExtensions.js";
import { EditorToolbar } from "./EditorToolbar";

// Reexportados para no romper la API pública existente
// (`components/canvas/editor` sigue exportando ambos símbolos). La fuente
// real y pura vive en `lib/document/documentSchema.js` — este archivo la
// consume, nunca al revés (F5-03A-R1).
export { EMPTY_DOCUMENT_JSON, validateDocumentEditorJson };

const ReadyDocumentEditor = forwardRef(function ReadyDocumentEditor(
  { initialContent, onChange, onFocus, onActivity, headingId, heading, description, ariaLabel },
  ref,
) {
  const [, setToolbarRevision] = useState(0);
  const editor = useEditor({
    extensions: createVisualDocumentEditorExtensions(),
    content: initialContent,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-label": ariaLabel,
        "aria-multiline": "true",
        class:
          "min-h-[28rem] max-w-none break-words px-cdt-5 py-cdt-6 text-cdt-base leading-relaxed text-cdt-slate-900 outline-none sm:px-cdt-8 " +
          "[&_h2]:mb-cdt-3 [&_h2]:mt-cdt-8 [&_h2]:text-cdt-title [&_h2]:font-cdt-bold [&_h2]:text-cdt-blue-900 " +
          "[&_h3]:mb-cdt-2 [&_h3]:mt-cdt-6 [&_h3]:text-cdt-lg [&_h3]:font-cdt-bold [&_h3]:text-cdt-blue-900 " +
          "[&_h4]:mb-cdt-2 [&_h4]:mt-cdt-5 [&_h4]:text-cdt-base [&_h4]:font-cdt-bold [&_h4]:text-cdt-blue-900 " +
          "[&_p]:my-cdt-3 [&_blockquote]:my-cdt-5 [&_blockquote]:rounded-cdt-md [&_blockquote]:bg-cdt-blue-50 [&_blockquote]:p-cdt-4 " +
          "[&_ul]:my-cdt-3 [&_ul]:list-disc [&_ul]:pl-cdt-6 [&_ol]:my-cdt-3 [&_ol]:list-decimal [&_ol]:pl-cdt-6",
      },
    },
    onUpdate({ editor: currentEditor }) {
      const json = currentEditor.getJSON();
      if (validateDocumentEditorJson(json).ok) onChange?.(json);
      setToolbarRevision((value) => value + 1);
      onActivity?.();
    },
    onSelectionUpdate() {
      setToolbarRevision((value) => value + 1);
      onActivity?.();
    },
    onFocus() {
      onFocus?.();
      onActivity?.();
    },
  });

  useImperativeHandle(
    ref,
    () => ({
      getJSON() {
        return editor?.getJSON() ?? structuredClone(initialContent);
      },
      insertEvidenceCitation(payload) {
        if (!editor) return false;
        const inserted = editor.commands.insertEvidenceCitation(payload);
        if (inserted) editor.commands.focus("end");
        return inserted;
      },
      insertManualEntry(payload) {
        if (!editor) return false;
        const inserted = editor.commands.insertManualEntry(payload);
        if (inserted) editor.commands.focus("end");
        return inserted;
      },
      focus() {
        return editor?.commands.focus("end") ?? false;
      },
      // "Investigar esta sección" (F5-03A/RF-104): si el usuario tiene texto
      // seleccionado en ESTA sección al hacer clic, ese fragmento —no la
      // sección completa— es el que debe llenar el contexto. `textBetween`
      // ya inserta el mismo separador de bloque ("\n") que
      // `extractSectionText` usa para nodos de bloque, así que el texto
      // resultante es consistente con el de la sección completa.
      getSelectedText() {
        if (!editor) return "";
        const { from, to, empty } = editor.state.selection;
        if (empty) return "";
        return editor.state.doc.textBetween(from, to, "\n", "\n");
      },
      // Escape hatch deliberado para el menú global Archivo/Editar/Formato
      // (RF-105): expone el editor Tiptap real de ESTA sección para que un
      // control fuera del árbol de esta sección pueda ejecutar comandos
      // (negrita, alinear, deshacer…) y leer `isActive()`/`can()` sobre la
      // sección que tiene el foco. Nunca se usa para leer/mutar el
      // documento fuera de los métodos ya expuestos arriba.
      getEditor() {
        return editor ?? null;
      },
    }),
    [editor, initialContent],
  );

  return (
    <section aria-labelledby={headingId} className="min-w-0">
      <div className="mb-cdt-3 flex items-center gap-cdt-3">
        <FileText className="h-6 w-6 text-cdt-blue-700" aria-hidden="true" focusable="false" />
        <div>
          <h2 id={headingId} className="text-cdt-title font-cdt-bold text-cdt-blue-900">
            {heading}
          </h2>
          <p className="text-cdt-sm text-cdt-slate-600">{description}</p>
        </div>
      </div>
      <div className="min-w-0 overflow-hidden rounded-cdt-lg border border-cdt-blue-100 bg-cdt-white focus-within:border-cdt-blue-500 focus-within:ring-2 focus-within:ring-cdt-blue-500 focus-within:ring-offset-2">
        <EditorToolbar editor={editor} />
        <EditorContent editor={editor} />
      </div>
    </section>
  );
});

const DEFAULT_HEADING_ID = "document-heading";
const DEFAULT_HEADING = "Documento de trabajo";
const DEFAULT_DESCRIPTION = "Redacta e integra evidencia trazable en el mismo lienzo.";

/**
 * API pública: `getJSON()`, `insertEvidenceCitation(payload)`,
 * `insertManualEntry(payload)` y `focus()`.
 * El contenido autoritativo siempre sale de `editor.getJSON()`.
 *
 * `headingId`/`heading`/`description`/`ariaLabel` son opcionales: sus
 * valores por defecto reproducen exactamente el documento único de F5-02.
 * `DocumentSections` (F5-03A) los sobrescribe por sección para que cada
 * instancia tenga un `id` y un nombre accesible propios — dos `<h2
 * id="document-heading">` en la misma página violarían unicidad de `id` y
 * confundirían a un lector de pantalla.
 */
export const DocumentEditor = forwardRef(function DocumentEditor(
  {
    initialContent = EMPTY_DOCUMENT_JSON,
    onChange,
    onFocus,
    onActivity,
    headingId = DEFAULT_HEADING_ID,
    heading = DEFAULT_HEADING,
    description = DEFAULT_DESCRIPTION,
    ariaLabel = DEFAULT_HEADING,
  },
  ref,
) {
  const validation = useMemo(
    () => validateDocumentEditorJson(initialContent),
    [initialContent],
  );

  if (!validation.ok) {
    return (
      <section aria-labelledby={headingId} className="rounded-cdt-lg border border-cdt-error bg-cdt-white p-cdt-5">
        <h2 id={headingId} className="text-cdt-title font-cdt-bold text-cdt-blue-900">
          {heading}
        </h2>
        <p role="alert" className="mt-cdt-3 text-cdt-sm text-cdt-error">
          No pudimos abrir el documento porque su contenido no es válido. El documento no se cargó.
        </p>
      </section>
    );
  }

  return (
    <ReadyDocumentEditor
      ref={ref}
      initialContent={initialContent}
      onChange={onChange}
      onFocus={onFocus}
      onActivity={onActivity}
      headingId={headingId}
      heading={heading}
      description={description}
      ariaLabel={ariaLabel}
    />
  );
});

DocumentEditor.displayName = "DocumentEditor";
