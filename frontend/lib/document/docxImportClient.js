import {
  DOCX_IMPORT_ERROR_CODES,
  DOCX_IMPORT_MAX_BYTES,
  DocxImportError,
} from "./docxImportPolicy.js";
import { convertMammothHtmlToDocument } from "./docxImportHtml.js";

export const DOCX_IMPORT_TIMEOUT_MS = 20_000;

export function createDocxImportWorker() {
  return new Worker(new URL("./docxImport.worker.js", import.meta.url));
}

function validateFileBeforeRead(file) {
  if (!file || typeof file.name !== "string" || !/\.docx$/iu.test(file.name)) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.INVALID_EXTENSION);
  }
  if (!Number.isSafeInteger(file.size) || file.size <= 0) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.EMPTY_FILE);
  }
  if (file.size > DOCX_IMPORT_MAX_BYTES) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.FILE_TOO_LARGE);
  }
}

/** Orquesta el worker cancelable. No contiene `fetch`, XHR, WebSocket ni
 * ninguna otra superficie de red. */
export async function analyzeDocxFile(
  file,
  { workerFactory = createDocxImportWorker, timeoutMs = DOCX_IMPORT_TIMEOUT_MS, signal } = {},
) {
  validateFileBeforeRead(file);
  if (signal?.aborted) throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED);
  const arrayBuffer = await file.arrayBuffer();
  if (signal?.aborted) throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED);
  const metadata = { name: file.name, size: file.size, type: file.type ?? "" };
  const worker = workerFactory();

  const converted = await new Promise((resolve, reject) => {
    let settled = false;
    let timeoutId;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      signal?.removeEventListener("abort", handleAbort);
      worker.terminate();
      callback(value);
    };
    const handleAbort = () => finish(reject, new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED));
    timeoutId = window.setTimeout(() => {
      finish(reject, new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED));
    }, timeoutMs);

    worker.addEventListener("message", (event) => {
      if (event.data?.type === "success") finish(resolve, event.data.result);
      else finish(reject, new DocxImportError(event.data?.code ?? DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED));
    });
    worker.addEventListener("error", () => {
      finish(reject, new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED));
    });
    if (signal?.aborted) handleAbort();
    else signal?.addEventListener("abort", handleAbort, { once: true });
    if (settled) return;
    worker.postMessage({ arrayBuffer, metadata }, [arrayBuffer]);
  });

  const result = convertMammothHtmlToDocument(converted.html, {
    filename: file.name,
    warnings: converted.warnings,
  });
  return {
    ...result,
    file: { name: file.name, size: file.size, type: file.type ?? "" },
  };
}
