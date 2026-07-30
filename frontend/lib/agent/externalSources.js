import { redact } from "../api/redact.js";
import { getSafeExternalUrl } from "../evidence/safeExternalUrl.js";

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

function valuesEqual(left, right) {
  if (Object.is(left, right)) return true;
  if (typeof left !== typeof right || left === null || right === null) return false;

  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => valuesEqual(item, right[index]))
    );
  }

  if (typeof left !== "object") return false;
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key) => Object.prototype.hasOwnProperty.call(right, key) && valuesEqual(left[key], right[key]),
    )
  );
}

function containsRedactionMarker(value) {
  if (typeof value === "string") return value.includes("[REDACTADO]");
  if (Array.isArray(value)) return value.some(containsRedactionMarker);
  if (value !== null && typeof value === "object") {
    return Object.values(value).some(containsRedactionMarker);
  }
  return false;
}

function containsSensitiveData(value) {
  try {
    const redacted = redact(value);
    return !valuesEqual(value, redacted) || containsRedactionMarker(redacted);
  } catch {
    return true;
  }
}

/**
 * Proyecta `no_evidence_report.external_sources` a un modelo seguro de UI.
 * Cada elemento se inspecciona completo antes de seleccionar sus tres campos;
 * los elementos inseguros se omiten y nunca se reparan (T-506, Art. I).
 * Puro: sin red, DOM, almacenamiento ni reloj.
 *
 * @param {unknown} input
 * @returns {{entidad: string, url: string, por_que: string}[]}
 */
export function normalizeExternalSources(input) {
  if (!Array.isArray(input)) return [];

  const normalized = [];
  for (const item of input) {
    if (!isPlainObject(item) || containsSensitiveData(item)) continue;
    if (!isNonEmptyString(item.entidad) || !isNonEmptyString(item.por_que)) continue;

    const safeUrl = getSafeExternalUrl(item.url);
    if (safeUrl === null) continue;

    normalized.push({
      entidad: item.entidad,
      url: safeUrl,
      por_que: item.por_que,
    });
  }
  return normalized;
}

/** Convierte una sugerencia ya segura en valores editables del formulario. */
export function toManualEntryInitialValues(source) {
  const [safeSource] = normalizeExternalSources([source]);
  if (!safeSource) return null;
  return {
    value: "",
    text: "",
    source: safeSource.entidad,
    url: safeSource.url,
    date: "",
    suggestionContext: safeSource.por_que,
  };
}
