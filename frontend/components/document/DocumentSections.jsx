import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { PenLine, Search } from "lucide-react";
import { DocumentEditor } from "../canvas/editor/DocumentEditor";
import { ManualDataEntry } from "../canvas/ManualDataEntry";
import { Button } from "../ui/Button";
import { deriveSectionContextHint, SECTION_CONTEXT_HINT_MAX_LENGTH } from "../../lib/document/sectionContextHint";
import { SectionInvestigateModal } from "./SectionInvestigateModal";
import { normalizeExternalSources } from "../../lib/agent/externalSources.js";

/**
 * Renderiza cada sección del documento (F5-03A, RF-104) con su propio
 * `DocumentEditor` (F5-02) y la acción "Investigar esta sección".
 *
 * API imperativa expuesta por `ref`, análoga a la de `DocumentEditor` pero
 * indexada por `sectionId`:
 * - `getSectionJSON(sectionId)`
 * - `insertEvidenceCitation(sectionId, payload)` — falla cerrado
 *   (`false`, sin insertar en ninguna otra sección) si `sectionId` no
 *   corresponde a una sección montada.
 * - `insertManualEntry(sectionId, payload)` — misma guarda por sección.
 * - `openManualEntry(sectionId, initialValues)` — abre el formulario solo
 *   si la sección existe y el prellenado sugerido vuelve a ser seguro.
 * - `focusSection(sectionId)`
 */
export const DocumentSections = forwardRef(function DocumentSections(
  { document, onSectionChange, onInvestigateSection, onManualEntryInserted, disabled = false },
  ref,
) {
  const editorRefs = useRef(new Map());
  const [activeSectionId, setActiveSectionId] = useState(null);
  const [manualDialog, setManualDialog] = useState(null);
  const [emptySectionId, setEmptySectionId] = useState(null);

  useImperativeHandle(
    ref,
    () => ({
      getSectionJSON(sectionId) {
        return editorRefs.current.get(sectionId)?.getJSON() ?? null;
      },
      insertEvidenceCitation(sectionId, payload) {
        const editorRef = editorRefs.current.get(sectionId);
        if (!editorRef) return false;
        return editorRef.insertEvidenceCitation(payload);
      },
      insertManualEntry(sectionId, payload) {
        const editorRef = editorRefs.current.get(sectionId);
        if (!editorRef) return false;
        return editorRef.insertManualEntry(payload);
      },
      openManualEntry(sectionId, initialValues) {
        if (!editorRefs.current.has(sectionId)) return false;
        const [safeInitialValues] = normalizeExternalSources([initialValues]);
        if (!safeInitialValues) return false;
        setManualDialog({ sectionId, initialValues: safeInitialValues });
        return true;
      },
      focusSection(sectionId) {
        return editorRefs.current.get(sectionId)?.focus() ?? false;
      },
    }),
    [],
  );

  function handleInvestigateClick(section) {
    setEmptySectionId(null);
    const hint = deriveSectionContextHint(section.content, { maxLength: SECTION_CONTEXT_HINT_MAX_LENGTH });
    if (hint.isEmpty) {
      setEmptySectionId(section.sectionId);
      return;
    }
    setActiveSectionId(section.sectionId);
  }

  function handleManualEntrySubmit(payload) {
    const sectionId = manualDialog?.sectionId;
    if (!sectionId) return false;
    const editorRef = editorRefs.current.get(sectionId);
    if (!editorRef) return false;
    const inserted = editorRef.insertManualEntry(payload);
    if (!inserted) return false;

    const updatedJson = editorRef.getJSON();
    if (updatedJson) onSectionChange?.(sectionId, updatedJson);
    setManualDialog(null);
    onManualEntryInserted?.(sectionId);
    window.requestAnimationFrame(() => editorRefs.current.get(sectionId)?.focus());
    return true;
  }

  const activeSection = document.sections.find((section) => section.sectionId === activeSectionId) ?? null;
  const activeContextHint = activeSection
    ? deriveSectionContextHint(activeSection.content, { maxLength: SECTION_CONTEXT_HINT_MAX_LENGTH })
    : null;

  return (
    <div className="flex flex-col gap-cdt-8">
      {document.sections.map((section) => {
        const headingId = `document-heading-${section.sectionId}`;
        return (
          <div key={section.sectionId} className="flex flex-col gap-cdt-3">
            <div className="flex flex-wrap items-center justify-between gap-cdt-3">
              <div className="min-w-0">
                <p className="text-cdt-xs font-cdt-bold uppercase tracking-wide text-cdt-blue-700">
                  {section.title}
                </p>
                {section.description ? (
                  <p className="text-cdt-xs text-cdt-slate-600">{section.description}</p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-cdt-2">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={disabled}
                  onClick={() => handleInvestigateClick(section)}
                >
                  <Search className="h-4 w-4" aria-hidden="true" focusable="false" />
                  Investigar esta sección
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setManualDialog({ sectionId: section.sectionId, initialValues: null })}
                >
                  <PenLine className="h-4 w-4" aria-hidden="true" focusable="false" />
                  Agregar dato manual
                </Button>
              </div>
            </div>

            {emptySectionId === section.sectionId ? (
              <p role="alert" className="text-cdt-xs text-cdt-error">
                Esta sección todavía no tiene contenido suficiente para investigar. Escribe algo de texto antes de
                continuar.
              </p>
            ) : null}

            <DocumentEditor
              ref={(node) => {
                if (node) editorRefs.current.set(section.sectionId, node);
                else editorRefs.current.delete(section.sectionId);
              }}
              initialContent={section.content}
              headingId={headingId}
              heading={section.title}
              description={section.description}
              ariaLabel={`Documento de trabajo: ${section.title}`}
              onChange={(json) => onSectionChange?.(section.sectionId, json)}
            />
          </div>
        );
      })}

      {activeSection ? (
        <SectionInvestigateModal
          sectionTitle={activeSection.title}
          contextHint={activeContextHint}
          onCancel={() => setActiveSectionId(null)}
          onConfirm={(question) => {
            const sectionId = activeSection.sectionId;
            const contextHint = activeContextHint.value;
            setActiveSectionId(null);
            onInvestigateSection?.({ question, contextHint }, sectionId);
          }}
        />
      ) : null}

      {manualDialog ? (
        <ManualDataEntry
          open
          sectionTitle={document.sections.find((section) => section.sectionId === manualDialog.sectionId)?.title}
          initialValues={manualDialog.initialValues}
          onClose={() => setManualDialog(null)}
          onSubmit={handleManualEntrySubmit}
        />
      ) : null}
    </div>
  );
});

DocumentSections.displayName = "DocumentSections";
