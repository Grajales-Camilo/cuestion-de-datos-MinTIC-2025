import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { FileText, LoaderCircle, ShieldCheck, TriangleAlert } from "lucide-react";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { analyzeDocxFile, createDocxImportWorker } from "../../lib/document/docxImportClient.js";
import { DOCX_IMPORT_ERROR_CODES } from "../../lib/document/docxImportPolicy.js";

const WARNING_LABELS = Object.freeze({
  TABLES_SIMPLIFIED: "Las tablas se convirtieron a filas de texto separadas por barras.",
  IMAGES_DISCARDED: "Las imágenes se descartaron.",
  HEADERS_FOOTERS_DISCARDED: "Los encabezados y pies de página se descartaron.",
  COMMENTS_DISCARDED: "Los comentarios se descartaron.",
  TRACK_CHANGES_SIMPLIFIED: "El control de cambios se simplificó al texto visible.",
  NOTES_SIMPLIFIED: "Las notas al pie o finales se simplificaron como texto normal.",
  EQUATIONS_DISCARDED: "Las ecuaciones se descartaron.",
  FIELDS_SIMPLIFIED: "Los campos dinámicos se conservaron solo como texto cuando fue posible.",
  EMBEDDED_OBJECTS_DISCARDED: "Los objetos incrustados se descartaron sin ejecutarlos.",
  UNSUPPORTED_STYLES_SIMPLIFIED: "Uno o más estilos no compatibles se simplificaron.",
  UNSAFE_LINKS_DISCARDED: "Uno o más enlaces inseguros se conservaron solo como texto.",
});

const ERROR_MESSAGES = Object.freeze({
  [DOCX_IMPORT_ERROR_CODES.INVALID_EXTENSION]: "Selecciona un archivo con extensión .docx.",
  [DOCX_IMPORT_ERROR_CODES.INVALID_MIME_TYPE]: "El tipo informado por el archivo no corresponde a un documento DOCX.",
  [DOCX_IMPORT_ERROR_CODES.EMPTY_FILE]: "El archivo está vacío y no se puede abrir.",
  [DOCX_IMPORT_ERROR_CODES.FILE_TOO_LARGE]: "El archivo supera el límite de 10 MiB.",
  [DOCX_IMPORT_ERROR_CODES.INVALID_SIGNATURE]: "El archivo no tiene la estructura interna de un DOCX válido.",
  [DOCX_IMPORT_ERROR_CODES.ENCRYPTED_DOCUMENT]: "El documento está cifrado o protegido y no se puede importar.",
  [DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT]: "El documento está corrupto o incompleto.",
  [DOCX_IMPORT_ERROR_CODES.UNSAFE_PACKAGE]: "El documento contiene una estructura interna insegura.",
  [DOCX_IMPORT_ERROR_CODES.EXTERNAL_RELATIONSHIP]: "El documento intenta usar un recurso externo no permitido.",
  [DOCX_IMPORT_ERROR_CODES.UNSUPPORTED_DOCUMENT_TYPE]: "El archivo no es un DOCX estándar sin macros.",
  [DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED]: "El documento excede los límites seguros de procesamiento.",
  [DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED]: "No se pudo convertir el contenido de este documento.",
});

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}

function documentHasContent(documentModel) {
  function hasContent(node) {
    if (!node || typeof node !== "object") return false;
    if (node.type === "evidenceCitation" || node.type === "manualEntry") return true;
    if (node.type === "text" && typeof node.text === "string" && node.text.trim()) return true;
    return Array.isArray(node.content) && node.content.some(hasContent);
  }

  return documentModel.sections.some((section) => hasContent(section.content));
}

function recognizedLabels(recognized) {
  const labels = [
    [recognized.headings, "encabezados"],
    [recognized.paragraphs, "párrafos"],
    [recognized.bold, "fragmentos en negrita"],
    [recognized.italic, "fragmentos en cursiva"],
    [recognized.orderedLists, "listas ordenadas"],
    [recognized.unorderedLists, "listas no ordenadas"],
    [recognized.links, "enlaces seguros"],
  ];
  return labels.filter(([count]) => count > 0).map(([count, label]) => `${count} ${label}`);
}

export const DocxImportFlow = forwardRef(function DocxImportFlow(
  { currentDocument, onImport, onFeedback, returnFocusRef },
  ref,
) {
  const fileInputRef = useRef(null);
  const abortRef = useRef(null);
  const preparedWorkerRef = useRef(null);
  const [state, setState] = useState({ status: "idle", result: null, error: null });

  const prepareWorker = useCallback(() => {
    if (typeof Worker !== "undefined" && !preparedWorkerRef.current) {
      preparedWorkerRef.current = createDocxImportWorker();
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    preparedWorkerRef.current?.terminate();
    preparedWorkerRef.current = null;
    prepareWorker();
    setState({ status: "idle", result: null, error: null });
  }, [prepareWorker]);

  useEffect(() => {
    // La descarga del código estático same-origin sucede al abrir el lienzo,
    // antes de cualquier acción de importación o acceso a un archivo.
    prepareWorker();
    return () => {
      abortRef.current?.abort();
      preparedWorkerRef.current?.terminate();
      preparedWorkerRef.current = null;
    };
  }, [prepareWorker]);

  useImperativeHandle(ref, () => ({
    selectFile() {
      if (!fileInputRef.current) return;
      // El Worker normalmente ya está preparado desde el montaje. Este
      // fallback solo cubre navegadores que hayan terminado el Worker antes
      // de abrir el selector; nunca recibe bytes hasta `change`.
      prepareWorker();
      fileInputRef.current.value = "";
      fileInputRef.current.click();
    },
  }), [prepareWorker]);

  async function handleFileChange(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ status: "processing", result: null, error: null });
    onFeedback?.("Analizando el documento localmente.");
    const preparedWorker = preparedWorkerRef.current;
    let preparedWorkerUsed = false;
    try {
      preparedWorkerRef.current = null;
      const result = await analyzeDocxFile(file, {
        signal: controller.signal,
        workerFactory: preparedWorker
          ? () => {
            preparedWorkerUsed = true;
            return preparedWorker;
          }
          : createDocxImportWorker,
      });
      if (controller.signal.aborted) return;
      abortRef.current = null;
      setState({ status: "summary", result, error: null });
      onFeedback?.("El documento se analizó localmente. Revisa el resumen antes de abrirlo.");
    } catch (error) {
      // Si el archivo falló en la validación de metadatos antes de que
      // `analyzeDocxFile` consumiera el Worker preparado, este componente
      // conserva la responsabilidad de terminarlo.
      if (preparedWorker && !preparedWorkerUsed) {
        preparedWorker.terminate();
      }
      if (controller.signal.aborted) return;
      abortRef.current = null;
      const message = ERROR_MESSAGES[error?.code] ?? ERROR_MESSAGES[DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED];
      setState({ status: "error", result: null, error: message });
      onFeedback?.(`Error de importación. ${message}`);
    }
  }

  function openDocument() {
    if (!state.result) return;
    if (documentHasContent(currentDocument)) {
      setState((previous) => ({ ...previous, status: "confirm" }));
      return;
    }
    onImport?.(state.result.model);
    onFeedback?.("El documento importado se abrió como documento libre.");
    reset();
  }

  function confirmReplacement() {
    if (!state.result) return;
    onImport?.(state.result.model);
    onFeedback?.("El documento actual se reemplazó por el documento importado.");
    reset();
  }

  const modalOpen = state.status !== "idle";
  const title =
    state.status === "processing"
      ? "Analizando documento"
      : state.status === "summary"
        ? "Resumen de importación"
        : state.status === "confirm"
          ? "¿Reemplazar el documento actual?"
          : "No se pudo importar el documento";
  const recognized = state.result ? recognizedLabels(state.result.recognized) : [];

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={handleFileChange}
      />
      <Modal open={modalOpen} onClose={reset} title={title} returnFocusRef={returnFocusRef} className="max-w-2xl">
        {state.status === "processing" ? (
          <div className="flex items-start gap-cdt-3" role="status">
            <LoaderCircle className="mt-0.5 h-5 w-5 animate-spin text-cdt-blue-700" aria-hidden="true" />
            <div>
              <p className="font-cdt-bold text-cdt-slate-900">Lectura local en curso</p>
              <p className="mt-cdt-1 text-cdt-sm text-cdt-slate-600">
                El archivo no se envía a Cuestión de Datos ni a servicios externos.
              </p>
            </div>
          </div>
        ) : null}

        {state.status === "summary" && state.result ? (
          <div className="space-y-cdt-5">
            <div className="flex items-start gap-cdt-3 rounded-cdt-lg bg-cdt-blue-50 p-cdt-4">
              <FileText className="mt-0.5 h-5 w-5 shrink-0 text-cdt-blue-700" aria-hidden="true" />
              <dl className="grid min-w-0 grid-cols-[auto_1fr] gap-x-cdt-3 gap-y-cdt-1 text-cdt-sm">
                <dt className="font-cdt-bold text-cdt-slate-900">Nombre</dt>
                <dd className="break-words text-cdt-slate-600">{state.result.file.name}</dd>
                <dt className="font-cdt-bold text-cdt-slate-900">Tamaño</dt>
                <dd className="text-cdt-slate-600">{formatBytes(state.result.file.size)}</dd>
                <dt className="font-cdt-bold text-cdt-slate-900">Tipo de documento</dt>
                <dd className="text-cdt-slate-600">Documento libre</dd>
              </dl>
            </div>

            <section aria-labelledby="recognized-content-heading">
              <h3 id="recognized-content-heading" className="font-cdt-bold text-cdt-slate-900">Contenido reconocido</h3>
              {recognized.length > 0 ? (
                <ul className="mt-cdt-2 list-disc space-y-cdt-1 pl-cdt-5 text-cdt-sm text-cdt-slate-600">
                  {recognized.map((label) => <li key={label}>{label}</li>)}
                </ul>
              ) : (
                <p className="mt-cdt-2 text-cdt-sm text-cdt-slate-600">No se reconoció texto editable.</p>
              )}
            </section>

            <section aria-labelledby="import-warnings-heading">
              <h3 id="import-warnings-heading" className="flex items-center gap-cdt-2 font-cdt-bold text-cdt-slate-900">
                {state.result.warnings.length > 0 ? (
                  <TriangleAlert className="h-5 w-5 text-cdt-warning" aria-hidden="true" />
                ) : (
                  <ShieldCheck className="h-5 w-5 text-cdt-success" aria-hidden="true" />
                )}
                Advertencias y simplificaciones
              </h3>
              {state.result.warnings.length > 0 ? (
                <ul className="mt-cdt-2 list-disc space-y-cdt-2 pl-cdt-5 text-cdt-sm text-cdt-slate-600">
                  {state.result.warnings.map((item) => (
                    <li key={item.code}>{WARNING_LABELS[item.code] ?? "Parte del formato se simplificó."}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-cdt-2 text-cdt-sm text-cdt-slate-600">
                  No se detectaron elementos que deban descartarse o simplificarse.
                </p>
              )}
            </section>

            <p className="text-cdt-sm text-cdt-slate-600">
              El contenido importado es texto aportado por ti. No se convertirá en evidencia verificada ni en citas de datos.
            </p>
            <div className="flex flex-wrap justify-end gap-cdt-2">
              <Button type="button" variant="quiet" onClick={reset}>Cancelar</Button>
              <Button type="button" onClick={openDocument}>Abrir como documento nuevo</Button>
            </div>
          </div>
        ) : null}

        {state.status === "confirm" ? (
          <div>
            <p className="text-cdt-sm text-cdt-slate-600">
              El documento actual contiene texto o aportes. Al continuar se reemplazará en esta pestaña por el DOCX importado.
              El archivo original permanecerá intacto.
            </p>
            <div className="mt-cdt-5 flex flex-wrap justify-end gap-cdt-2">
              <Button type="button" variant="quiet" onClick={() => setState((previous) => ({ ...previous, status: "summary" }))}>
                Volver al resumen
              </Button>
              <Button type="button" variant="destructive" onClick={confirmReplacement}>Sí, reemplazar</Button>
            </div>
          </div>
        ) : null}

        {state.status === "error" ? (
          <div>
            <p role="alert" className="text-cdt-sm text-cdt-error">{state.error}</p>
            <p className="mt-cdt-2 text-cdt-sm text-cdt-slate-600">El documento actual no cambió.</p>
            <div className="mt-cdt-5 flex justify-end">
              <Button type="button" onClick={reset}>Entendido</Button>
            </div>
          </div>
        ) : null}
      </Modal>
    </>
  );
});

DocxImportFlow.displayName = "DocxImportFlow";
