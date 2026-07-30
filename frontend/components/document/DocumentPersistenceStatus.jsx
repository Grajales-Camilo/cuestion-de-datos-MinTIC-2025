import { useCallback, useState } from "react";
import { AlertTriangle, Download, Info } from "lucide-react";
import { Button } from "../ui/Button";
import { LiveRegion } from "../ui/LiveRegion";
import { buildDocumentBackupPayload, buildRawBackupPayload } from "../../lib/document/documentStorage";
import { DOCUMENT_AUTOSAVE_STATUS } from "../../hooks/useDocumentAutosave";

const STATUS_LABEL = {
  [DOCUMENT_AUTOSAVE_STATUS.LOADING]: "Cargando tu documento…",
  [DOCUMENT_AUTOSAVE_STATUS.SAVING]: "Guardando…",
  [DOCUMENT_AUTOSAVE_STATUS.SAVED]: "Guardado",
};

// El aviso de descarga solo se concatena cuando el botón correspondiente
// SÍ va a renderizarse (currentDocument presente) — el mensaje nunca pide
// una acción que la interfaz no ofrece (F6-01-R1, PARTE 5).
const ERROR_MESSAGES = {
  quota_exceeded:
    "No se pudo guardar: se agotó el espacio de almacenamiento del navegador. Tus cambios siguen en esta pestaña.",
  unavailable:
    "No se pudo guardar: el almacenamiento local no está disponible en este navegador. Tus cambios siguen en esta pestaña.",
  invalid_document: "No se pudo guardar: el documento tiene un problema interno. Tus cambios siguen en esta pestaña.",
};
const DEFAULT_ERROR_MESSAGE = "No se pudo guardar el documento. Tus cambios siguen en esta pestaña.";
const DOWNLOAD_HINT = " Descarga una copia para no perderlos.";

// RF-101-02: ya no se abre automáticamente un documento nuevo cuando el
// guardado anterior está dañado o es inválido — el usuario elige una
// plantilla explícitamente (ver TemplatePicker en pages/app.js). Los
// mensajes de "corrupt"/"invalid" ya no afirman que un documento nuevo se
// abrió: seguiría siendo falso hasta que el usuario complete la elección.
const NOTICE_MESSAGES = {
  corrupt:
    "No se pudo leer el documento guardado anteriormente: estaba dañado. Se conservó una copia del original. Elige una plantilla para empezar un documento nuevo.",
  invalid:
    "El documento guardado anteriormente no es válido. Se conservó una copia del original. Elige una plantilla para empezar un documento nuevo.",
  unavailable:
    "No se pudo acceder al almacenamiento local de este navegador. Tus cambios solo estarán disponibles en esta pestaña.",
};

// Mensajes distintos a propósito (F6-01-R1, PARTE 5): `future_version` es un
// documento intacto de una versión futura; `migration_failed` es un intento
// de actualización que no se pudo verificar con seguridad. Confundirlos le
// haría creer al usuario que su documento actual está dañado cuando en
// realidad nunca se tocó.
const BLOCKED_MESSAGES = {
  future_version:
    "El documento fue creado con una versión más nueva de la aplicación. No se abrió ni se sobrescribió, para no perder información. Puedes seguir escribiendo en un documento nuevo, pero no se guardará automáticamente mientras esto siga así.",
  migration_failed:
    "No pudimos actualizar de forma segura el documento guardado. El original no fue reemplazado ni se abrió, para no perder información. Puedes seguir escribiendo en un documento nuevo, pero no se guardará automáticamente mientras esto siga así.",
};
const DEFAULT_BLOCKED_MESSAGE =
  "El documento guardado en este navegador no se pudo abrir de forma segura. No se sobrescribió, para no perder información.";

function triggerJsonDownload(filename, contents) {
  const blob = new Blob([contents], { type: "application/json;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** Botón de descarga compartido por los cuatro avisos (cuota/documento
 * inválido, corrupción/versión inválida al restaurar, versión futura,
 * migración fallida) — mismo patrón que `DownloadCsvButton.jsx`. Si
 * construir o disparar la descarga falla (p. ej. `value` no serializable),
 * lo atrapa y muestra un aviso en vez de dejar que el error escape del
 * manejador de clic y tumbe la página (F6-01-R1, PARTE 5). */
function DownloadBackupButton({ value, isRaw = false, label }) {
  const [failed, setFailed] = useState(false);

  const handleClick = useCallback(() => {
    try {
      const { filename, contents } = isRaw ? buildRawBackupPayload(value) : buildDocumentBackupPayload(value);
      triggerJsonDownload(filename, contents);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [value, isRaw]);

  return (
    <div className="flex flex-col gap-cdt-1">
      <Button type="button" variant="secondary" onClick={handleClick}>
        <Download className="h-4 w-4" aria-hidden="true" focusable="false" />
        {label}
      </Button>
      {failed ? (
        <p role="status" className="text-cdt-xs text-cdt-error">
          No se pudo preparar la descarga. Intenta de nuevo.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Indicador discreto de autoguardado (F6-01 PARTE 6) + avisos no modales de
 * corrupción, versión futura y cuota agotada (PARTE 4/5). La línea de estado
 * usa su propia región `aria-live="polite"` agrupada y solo cambia cuando el
 * estado real transiciona (`loading` → `saved`, `saving` → `saved`, …),
 * nunca por cada pulsación de teclado (frontend/AGENTS.md). Nunca renderiza
 * el texto crudo de un documento corrupto/inválido en el DOM: `notice.raw`
 * solo se usa como contenido de un archivo descargable, nunca como texto
 * visible.
 */
export function DocumentPersistenceStatus({
  status,
  error,
  notice,
  blockedEnvelope,
  currentDocument,
  onDismissNotice,
}) {
  const statusLabel = STATUS_LABEL[status] ?? null;
  const isError = status === DOCUMENT_AUTOSAVE_STATUS.ERROR;
  const isBlocked = status === DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION;

  return (
    <div className="flex flex-col gap-cdt-2">
      {statusLabel ? <LiveRegion visuallyHidden={false} message={statusLabel} /> : null}

      {isError ? (
        <div className="flex flex-wrap items-center gap-cdt-2">
          <p role="status" className="text-cdt-xs font-cdt-bold text-cdt-error">
            {(ERROR_MESSAGES[error] ?? DEFAULT_ERROR_MESSAGE) + (currentDocument ? DOWNLOAD_HINT : "")}
          </p>
          {currentDocument ? <DownloadBackupButton value={currentDocument} label="Descargar documento actual" /> : null}
        </div>
      ) : null}

      {isBlocked ? (
        <div className="flex flex-col gap-cdt-2 rounded-cdt-md border border-cdt-warning bg-cdt-blue-50 p-cdt-3">
          <p role="status" className="flex items-start gap-cdt-2 text-cdt-xs text-cdt-slate-900">
            <AlertTriangle
              className="mt-0.5 h-4 w-4 flex-shrink-0 text-cdt-warning"
              aria-hidden="true"
              focusable="false"
            />
            {BLOCKED_MESSAGES[notice?.reason] ?? DEFAULT_BLOCKED_MESSAGE}
          </p>
          {blockedEnvelope ? <DownloadBackupButton value={blockedEnvelope} label="Descargar archivo intacto" /> : null}
        </div>
      ) : null}

      {/* `!isBlocked`: future_version/migration_failed ya tienen su propio aviso arriba
          (F6-02A) — sin esta guarda se duplicaba con el genérico + "Entendido". */}
      {notice && !isBlocked ? (
        <div className="flex flex-col gap-cdt-2 rounded-cdt-md border border-cdt-blue-100 bg-cdt-blue-50 p-cdt-3">
          <p role="status" className="flex items-start gap-cdt-2 text-cdt-xs text-cdt-slate-900">
            <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-cdt-blue-700" aria-hidden="true" focusable="false" />
            {NOTICE_MESSAGES[notice.reason] ?? "Hubo un problema al recuperar el documento guardado anteriormente."}
          </p>
          <div className="flex flex-wrap items-center gap-cdt-2">
            {notice.raw ? <DownloadBackupButton value={notice.raw} isRaw label="Descargar copia recuperable" /> : null}
            {onDismissNotice ? (
              <Button type="button" variant="quiet" onClick={onDismissNotice}>
                Entendido
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
