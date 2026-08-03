import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { FileDown } from "lucide-react";
import { Button } from "../ui/Button";
import { LiveRegion } from "../ui/LiveRegion";
import { EXPORT_DOCX_ERROR_CODES } from "../../lib/document/exportDocxErrorCodes";

/**
 * Acción directa "Exportar en Word (.docx)" (F6-02B, RF-102/RF-103). Un solo
 * formato existe hoy — no hay dropdown ni menú con una opción disfrazada de
 * varias. Carga `exportDocx.js` (y `docx`, ~500 KB) con `import()` dinámico
 * SOLO al pulsar el botón: importar este archivo NUNCA debe arrastrar esa
 * carga — por eso los mensajes de error se traducen desde
 * `exportDocxErrorCodes.js` (módulo liviano, sin `docx`), no desde
 * `exportDocx.js`.
 *
 * Exporta `documentModel` tal cual llega por props (el estado React actual
 * de `/app`), nunca el último sobre guardado en `localStorage`: una edición
 * hecha justo antes del clic debe quedar en el archivo, y la exportación
 * sigue disponible aunque el autoguardado esté fallando (es precisamente su
 * vía de recuperación).
 */
const ERROR_MESSAGES = {
  [EXPORT_DOCX_ERROR_CODES.INVALID_DOCUMENT]:
    "No pudimos exportar porque el documento tiene un problema interno. No se descargó ningún archivo.",
  [EXPORT_DOCX_ERROR_CODES.UNSUPPORTED_TEMPLATE]: "Esta plantilla todavía no se puede exportar en Word.",
  [EXPORT_DOCX_ERROR_CODES.SENSITIVE_DATA_DETECTED]:
    "No pudimos exportar porque el documento contiene información sensible. Revísalo antes de intentarlo de nuevo.",
};
const DEFAULT_ERROR_MESSAGE = "No pudimos preparar el documento. Intenta de nuevo.";

const STATUS = Object.freeze({ IDLE: "idle", EXPORTING: "exporting", SUCCESS: "success", ERROR: "error" });

/** Mismo patrón que `triggerJsonDownload` en `DocumentPersistenceStatus.jsx`:
 * URL temporal → clic en un enlace fuera de pantalla → enlace retirado →
 * URL revocada EXACTAMENTE una vez, todo de forma síncrona. */
function triggerDocxDownload(blob, filename) {
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
 * `ref` expone únicamente `click()` (RF-105): el menú global Archivo >
 * Descargar dispara el mismo botón real en vez de reimplementar el
 * `import()` dinámico y el manejo de errores — un solo camino de
 * exportación, dos formas de llegar a él.
 */
export const ExportDocumentButton = forwardRef(function ExportDocumentButton({ documentModel }, ref) {
  const [state, setState] = useState({ status: STATUS.IDLE, errorCode: null });
  // Guarda INMEDIATA (además de `disabled` vía `loading`): un segundo clic
  // en el mismo tick, antes de que React aplique el nuevo render, no debe
  // iniciar una segunda operación.
  const isExportingRef = useRef(false);
  const mountedRef = useRef(true);
  const buttonRef = useRef(null);

  useImperativeHandle(ref, () => ({
    click() {
      buttonRef.current?.click();
    },
  }));

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const handleExport = useCallback(async () => {
    if (isExportingRef.current) return;
    isExportingRef.current = true;
    setState({ status: STATUS.EXPORTING, errorCode: null });

    try {
      const exportModule = await import("../../lib/document/exportDocx.js");
      if (!mountedRef.current) return;

      const result = await exportModule.exportDocumentToDocx(documentModel);
      if (!mountedRef.current) return;

      if (result.ok) {
        triggerDocxDownload(result.blob, result.filename);
        setState({ status: STATUS.SUCCESS, errorCode: null });
      } else {
        setState({ status: STATUS.ERROR, errorCode: result.code });
        buttonRef.current?.focus();
      }
    } catch {
      // `import()` rechazado (red/chunk) u otro fallo inesperado: mismo
      // mensaje genérico que un `GENERATION_FAILED`, nunca el error nativo.
      if (!mountedRef.current) return;
      setState({ status: STATUS.ERROR, errorCode: null });
      buttonRef.current?.focus();
    } finally {
      isExportingRef.current = false;
    }
  }, [documentModel]);

  const isExporting = state.status === STATUS.EXPORTING;
  const announcement = state.status === STATUS.SUCCESS ? "Documento descargado." : "";
  const errorMessage =
    state.status === STATUS.ERROR ? (ERROR_MESSAGES[state.errorCode] ?? DEFAULT_ERROR_MESSAGE) : null;

  return (
    <div className="flex flex-col items-start gap-cdt-2">
      <Button ref={buttonRef} type="button" variant="secondary" loading={isExporting} onClick={handleExport}>
        <FileDown className="h-4 w-4" aria-hidden="true" focusable="false" />
        {isExporting ? "Preparando documento…" : "Exportar en Word (.docx)"}
      </Button>
      <LiveRegion message={announcement} />
      {errorMessage ? (
        <p role="alert" className="text-cdt-xs text-cdt-error">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
});

ExportDocumentButton.displayName = "ExportDocumentButton";
