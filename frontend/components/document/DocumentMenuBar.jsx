import { useRef, useState } from "react";
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  ClipboardPaste,
  Download,
  FilePlus2,
  FileUp,
  PenLine,
  Redo2,
  Undo2,
  X,
} from "lucide-react";
import {
  MenuBar,
  Menu,
  MenuItem,
  MenuCheckboxItem,
  MenuRadioItem,
  MenuGroup,
  MenuDivider,
} from "../ui/Menu";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { buildDocumentBackupPayload } from "../../lib/document/documentStorage";
import { FREE_TEMPLATE_ID, MGA_TEMPLATE_ID, PLAN_DE_DESARROLLO_TEMPLATE_ID } from "../../lib/document/documentModel";
import { DocxImportFlow } from "./DocxImportFlow";

const NEW_DOCUMENT_TEMPLATES = [
  { templateId: FREE_TEMPLATE_ID, label: "Documento libre" },
  { templateId: MGA_TEMPLATE_ID, label: "MGA" },
  { templateId: PLAN_DE_DESARROLLO_TEMPLATE_ID, label: "Plan de desarrollo" },
];

/** Mismo patrón que `triggerJsonDownload` de `DocumentPersistenceStatus.jsx`
 * y `triggerDocxDownload` de `ExportDocumentButton.jsx`: tercera copia
 * deliberada del mismo snippet de 8 líneas en vez de una abstracción
 * compartida — el proyecto ya repite este patrón en ambos archivos. */
function triggerBackupDownload(documentModel) {
  const { filename, contents } = buildDocumentBackupPayload(documentModel);
  const blob = new Blob([contents], { type: "application/json;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = filename;
  window.document.body.appendChild(link);
  link.click();
  window.document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Menú Archivo/Editar/Formato estilo Google Docs (RF-105). Opera sobre el
 * editor Tiptap de la sección con el foco más reciente
 * (`documentSectionsRef.current.getActiveEditor()`), nunca sobre una
 * sección fija: `editorActivityTick` fuerza releer ese estado en cada
 * cambio de foco/selección/contenido de CUALQUIER sección (ver
 * `DocumentSections.jsx`). "Nuevo" y "Descargar" duplican, sin quitarlos,
 * el selector de plantillas inicial y el botón "Exportar en Word"
 * existentes — son accesos adicionales al mismo camino real, no una
 * reimplementación. "Cerrar" NO borra nada de `localStorage`: solo vuelve
 * al selector de plantillas (`onCloseDocument`, ver `pages/app.js`); el
 * documento sigue autoguardado y reaparece si se recarga la página.
 */
export function DocumentMenuBar({
  documentModel,
  documentSectionsRef,
  editorActivityTick,
  exportButtonRef,
  onCreateDocument,
  onImportDocument,
  onCloseDocument,
  onFeedback,
}) {
  const [pendingTemplateId, setPendingTemplateId] = useState(null);
  const importFlowRef = useRef(null);
  const fileMenuTriggerRef = useRef(null);

  const activeEditor = documentSectionsRef.current?.getActiveEditor() ?? null;
  const isActive = (name, attrs) => activeEditor?.isActive(name, attrs) ?? false;
  const canRun = (name) => activeEditor?.can()[name]?.() ?? false;

  function run(fn) {
    if (!activeEditor) return;
    fn(activeEditor.chain().focus()).run();
  }

  async function handlePaste() {
    if (!activeEditor) return;
    try {
      const text = await navigator.clipboard.readText();
      if (text) activeEditor.chain().focus().insertContent(text).run();
    } catch {
      onFeedback?.("No se pudo pegar automáticamente en este navegador. Usa Ctrl+V.");
    }
  }

  function handleInsertManual() {
    const sectionId = documentSectionsRef.current?.getActiveSectionId();
    const opened = sectionId ? documentSectionsRef.current?.openManualEntry(sectionId, null) ?? false : false;
    if (!opened) {
      onFeedback?.("No pudimos abrir el formulario de aporte manual. Intenta desde el botón de la sección.");
    }
  }

  function confirmNewDocument() {
    const templateId = pendingTemplateId;
    setPendingTemplateId(null);
    if (templateId) onCreateDocument?.(templateId);
  }

  // `editorActivityTick` no se lee directamente: su único propósito es
  // cambiar en cada foco/selección/edición de CUALQUIER sección para forzar
  // el re-render que relee `activeEditor` arriba con estado fresco.
  void editorActivityTick;

  return (
    <>
      <MenuBar ariaLabel="Menú del documento" className="px-cdt-2 py-cdt-1">
        <Menu label="Archivo" triggerRef={fileMenuTriggerRef}>
          <MenuGroup label="Nuevo">
            {NEW_DOCUMENT_TEMPLATES.map((template) => (
              <MenuItem key={template.templateId} icon={FilePlus2} onSelect={() => setPendingTemplateId(template.templateId)}>
                {template.label}
              </MenuItem>
            ))}
          </MenuGroup>
          <MenuItem icon={FileUp} onSelect={() => importFlowRef.current?.selectFile()}>
            Importar documento (.docx)
          </MenuItem>
          <MenuDivider />
          <MenuItem icon={Download} onSelect={() => exportButtonRef?.current?.click()}>
            Descargar (.docx)
          </MenuItem>
          <MenuDivider />
          <MenuItem icon={X} onSelect={() => onCloseDocument?.()}>
            Cerrar
          </MenuItem>
        </Menu>

        <Menu label="Editar">
          <MenuItem icon={Undo2} disabled={!canRun("undo")} onSelect={() => run((chain) => chain.undo())}>
            Deshacer
          </MenuItem>
          <MenuItem icon={Redo2} disabled={!canRun("redo")} onSelect={() => run((chain) => chain.redo())}>
            Rehacer
          </MenuItem>
          <MenuItem icon={ClipboardPaste} disabled={!activeEditor} onSelect={handlePaste}>
            Pegar
          </MenuItem>
          <MenuItem icon={PenLine} onSelect={handleInsertManual}>
            Insertar dato manual
          </MenuItem>
        </Menu>

        <Menu label="Formato">
          <MenuGroup label="Texto">
            <MenuCheckboxItem checked={isActive("bold")} onSelect={() => run((chain) => chain.toggleBold())}>
              Negrita
            </MenuCheckboxItem>
            <MenuCheckboxItem checked={isActive("italic")} onSelect={() => run((chain) => chain.toggleItalic())}>
              Cursiva
            </MenuCheckboxItem>
            <MenuCheckboxItem
              checked={isActive("superscript")}
              onSelect={() => run((chain) => chain.toggleSuperscript())}
            >
              Superíndice
            </MenuCheckboxItem>
          </MenuGroup>
          <MenuDivider />
          <MenuGroup label="Párrafo">
            <MenuRadioItem checked={isActive("paragraph")} onSelect={() => run((chain) => chain.setParagraph())}>
              Texto normal
            </MenuRadioItem>
            <MenuRadioItem
              checked={isActive("heading", { level: 2 })}
              onSelect={() => run((chain) => chain.setHeading({ level: 2 }))}
            >
              Título
            </MenuRadioItem>
            <MenuRadioItem
              checked={isActive("heading", { level: 3 })}
              onSelect={() => run((chain) => chain.setHeading({ level: 3 }))}
            >
              Subtítulo
            </MenuRadioItem>
            <MenuRadioItem
              checked={isActive("heading", { level: 4 })}
              onSelect={() => run((chain) => chain.setHeading({ level: 4 }))}
            >
              Encabezado
            </MenuRadioItem>
          </MenuGroup>
          <MenuDivider />
          <MenuGroup label="Alinear">
            <MenuRadioItem
              checked={isActive({ textAlign: "left" })}
              onSelect={() => run((chain) => chain.setTextAlign("left"))}
            >
              <AlignLeft className="h-4 w-4" aria-hidden="true" focusable="false" /> Izquierda
            </MenuRadioItem>
            <MenuRadioItem
              checked={isActive({ textAlign: "center" })}
              onSelect={() => run((chain) => chain.setTextAlign("center"))}
            >
              <AlignCenter className="h-4 w-4" aria-hidden="true" focusable="false" /> Centro
            </MenuRadioItem>
            <MenuRadioItem
              checked={isActive({ textAlign: "right" })}
              onSelect={() => run((chain) => chain.setTextAlign("right"))}
            >
              <AlignRight className="h-4 w-4" aria-hidden="true" focusable="false" /> Derecha
            </MenuRadioItem>
            <MenuRadioItem
              checked={isActive({ textAlign: "justify" })}
              onSelect={() => run((chain) => chain.setTextAlign("justify"))}
            >
              <AlignJustify className="h-4 w-4" aria-hidden="true" focusable="false" /> Justificado
            </MenuRadioItem>
          </MenuGroup>
        </Menu>
      </MenuBar>

      <DocxImportFlow
        ref={importFlowRef}
        currentDocument={documentModel}
        onImport={onImportDocument}
        onFeedback={onFeedback}
        returnFocusRef={fileMenuTriggerRef}
      />

      <Modal
        open={pendingTemplateId !== null}
        onClose={() => setPendingTemplateId(null)}
        title="¿Reemplazar el documento actual?"
      >
        <p className="text-cdt-sm text-cdt-slate-600">
          Vas a empezar un documento nuevo. El documento actual dejará de mostrarse en esta pestaña; si no quieres
          perder lo que llevas escrito, descarga primero una copia.
        </p>
        <div className="mt-cdt-4 flex flex-wrap gap-cdt-2">
          <Button type="button" variant="secondary" onClick={() => triggerBackupDownload(documentModel)}>
            Descargar copia antes de continuar
          </Button>
        </div>
        <div className="mt-cdt-5 flex justify-end gap-cdt-2">
          <Button type="button" variant="quiet" onClick={() => setPendingTemplateId(null)}>
            Cancelar
          </Button>
          <Button type="button" variant="destructive" onClick={confirmNewDocument}>
            Reemplazar de todas formas
          </Button>
        </div>
      </Modal>
    </>
  );
}
