/**
 * Exportación DOCX del documento del canvas (F6-02A, RF-102/RF-103, ESC-08).
 * Núcleo puro y no visual: no monta React, no dispara la descarga en el DOM
 * (eso lo hará `ExportMenu.jsx` en F6-02B) y NUNCA envía el documento a un
 * servidor — el `.docx` se genera enteramente en el navegador con `Packer`.
 *
 * Entrada pública única: `exportDocumentToDocx(documentModel)`.
 *
 * Contrato de rechazo (fail-closed, sin reparar ni completar en silencio):
 * 1. `documentModel` debe pasar `validateDocumentModel` (misma fuente de
 *    verdad que `documentStorage.js` — no se reimplementa aquí ninguna regla
 *    de forma, de sección ni de `EvidenceCitation`).
 * 2. Solo se exporta `templateId` actualmente aprobado (lista independiente
 *    de la del validador, como segunda barrera si esa lista cambiara).
 * 3. Ningún dato sensible (`cdt_rt_*`, `token`/`authorization` como clave)
 *    puede aparecer en el contenido exportable — se reutiliza `redact()`
 *    (`lib/api/redact.js`), sin inventar un segundo patrón de token.
 * 4. Cualquier nodo no reconocido durante la construcción del árbol `docx`
 *    (`exportDocxTree.js`) aborta la exportación completa ANTES de llamar a
 *    `Packer`: nunca existe un Blob parcial.
 *
 * Los errores públicos son códigos fijos, nunca payloads, XML, JSON completo
 * ni el mensaje nativo de una excepción — ver `EXPORT_DOCX_ERROR_CODES`.
 *
 * IMPORTANTE (rendimiento, plan §15): este módulo importa `docx` (~500 KB) de
 * forma ESTÁTICA a propósito, porque ES el módulo que debe diferirse. Ningún
 * módulo cargado en el arranque de `/app` (`pages/app.js` ni nada que este
 * importe de forma estática) debe importar `exportDocx.js`: F6-02B deberá
 * cargarlo con `import("../../lib/document/exportDocx.js")` únicamente
 * cuando el usuario pida exportar.
 */

import { Packer } from "docx";
import { validateDocumentModel } from "./documentModel.js";
import { redact } from "../api/redact.js";
import { buildDocxDocument } from "./exportDocxTree.js";
import { EXPORT_DOCX_ERROR_CODES } from "./exportDocxErrorCodes.js";

export { EXPORT_DOCX_ERROR_CODES };

// Lista de exportación deliberadamente independiente de `FREE_TEMPLATE_ID`
// en `documentModel.js`: si ese archivo llegara a aceptar una plantilla
// nueva (MGA/plan de desarrollo, D-6) sin que este módulo se actualice para
// soportarla, la exportación debe seguir rechazando esa plantilla en vez de
// intentar generar un DOCX para un mapeo que no existe todavía.
const SUPPORTED_EXPORT_TEMPLATE_IDS = new Set(["libre"]);

const FALLBACK_FILENAME = "documento-cuestion-de-datos.docx";
const EXTENSION = ".docx";
// 255 bytes es el limite universal de un solo componente de nombre de
// archivo (NTFS, ext4, APFS). Es la longitud TOTAL documentada, incluida la
// extension -- la base util disponible es ese limite menos ".docx".
const MAX_FILENAME_LENGTH = 255;
const MAX_BASE_LENGTH = MAX_FILENAME_LENGTH - EXTENSION.length;
const WINDOWS_RESERVED_NAMES = new Set([
  "CON", "PRN", "AUX", "NUL",
  "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
  "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
]);

/** Windows considera reservado un nombre cuando el segmento ANTES DEL
 * PRIMER PUNTO coincide (sin distinguir mayusculas) con uno de los nombres
 * de dispositivo, sin importar cualquier extension o sufijo posterior:
 * `CON.txt`, `con.backup.final` y `CON` son todos invalidos; `CON1` y
 * `CON-1` no lo son (no coinciden exactamente). */
function hasReservedWindowsBaseName(base) {
  const firstSegment = base.split(".")[0].toUpperCase();
  return WINDOWS_RESERVED_NAMES.has(firstSegment);
}

/** Recorta `base` a `MAX_BASE_LENGTH` y vuelve a limpiar el borde derecho
 * (el corte pudo dejar un `-`/`.` colgando) -- deterministico: el mismo
 * titulo produce siempre el mismo recorte. Nunca deja el nombre vacio por
 * si solo: el llamador decide el fallback si el resultado queda vacio. */
function truncateBase(base) {
  if (base.length <= MAX_BASE_LENGTH) return base;
  return base.slice(0, MAX_BASE_LENGTH).replace(/[-.]+$/g, "");
}

/**
 * Deriva un nombre de archivo seguro desde el titulo del documento: sin
 * separadores de ruta, sin caracteres invalidos en Windows/macOS/Linux, sin
 * nombres reservados de Windows (con o sin extension/sufijo), con longitud
 * maxima acotada (`MAX_FILENAME_LENGTH`, incluida `.docx`) y sin terminar en
 * punto o espacio. Un titulo muy largo se trunca de forma deterministica; un
 * resultado vacio o inservible cae al fallback fijo. Nunca lanza ni inventa
 * contenido (hash, fecha) salvo el fallback ya existente.
 */
export function sanitizeExportFilename(title) {
  if (typeof title !== "string") return FALLBACK_FILENAME;

  const withoutDiacritics = title
    .trim()
    .normalize("NFD")
    .replace(new RegExp("[̀-ͯ]", "g"), "");

  let safe = withoutDiacritics
    .replace(/[\/:*?"<>|]/g, "-") // separadores de ruta + reservados de Windows
    .replace(new RegExp("[\u0000-\u001F]", "g"), "") // caracteres de control
    .replace(/\s+/g, "-")
    .replace(/[^A-Za-z0-9._-]/g, "")
    .replace(/-{2,}/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "");

  safe = truncateBase(safe);

  if (safe === "" || hasReservedWindowsBaseName(safe)) {
    return FALLBACK_FILENAME;
  }
  return `${safe}${EXTENSION}`;
}

/**
 * Detecta datos sensibles reutilizando el ÚNICO redactor compartido
 * (`redact()`): si redactar `value` produce un resultado distinto, algo
 * sensible estaba presente (patrón `cdt_rt_*` o una clave
 * `token`/`access_token`/`run_access_token`/`authorization`). No introduce
 * ningún patrón de token nuevo. Falla cerrado (`true`) si `value` no fuera
 * serializable — un documento ya validado por `validateDocumentModel` sí lo
 * es siempre, así que esta rama es puramente defensiva.
 */
function containsSensitiveData(value) {
  let original;
  let sanitized;
  try {
    original = JSON.stringify(value);
    sanitized = JSON.stringify(redact(value));
  } catch {
    return true;
  }
  return original !== sanitized;
}

/**
 * Genera el `.docx` de `documentModel` enteramente en el navegador.
 *
 * @param {unknown} documentModel — el `DocumentModel` completo (F5/F6).
 * @returns {Promise<
 *   {ok: true, blob: Blob, filename: string}
 *   | {ok: false, code: string}
 * >}
 */
export async function exportDocumentToDocx(documentModel) {
  const validation = validateDocumentModel(documentModel);
  if (!validation.ok) {
    return { ok: false, code: EXPORT_DOCX_ERROR_CODES.INVALID_DOCUMENT };
  }

  if (!SUPPORTED_EXPORT_TEMPLATE_IDS.has(documentModel.templateId)) {
    return { ok: false, code: EXPORT_DOCX_ERROR_CODES.UNSUPPORTED_TEMPLATE };
  }

  if (containsSensitiveData(documentModel)) {
    return { ok: false, code: EXPORT_DOCX_ERROR_CODES.SENSITIVE_DATA_DETECTED };
  }

  // Cualquier excepción aquí (nodo no reconocido, URL insegura de último
  // momento, o un fallo interno de `docx`) aborta ANTES de llamar a
  // `Packer`: nunca se construye un Blob parcial. El código público nunca
  // incluye `error.message` (podría contener fragmentos del documento).
  let docxDocument;
  try {
    docxDocument = buildDocxDocument(documentModel);
  } catch {
    return { ok: false, code: EXPORT_DOCX_ERROR_CODES.GENERATION_FAILED };
  }

  let blob;
  try {
    blob = await Packer.toBlob(docxDocument);
  } catch {
    return { ok: false, code: EXPORT_DOCX_ERROR_CODES.GENERATION_FAILED };
  }

  return { ok: true, blob, filename: sanitizeExportFilename(documentModel.title) };
}
