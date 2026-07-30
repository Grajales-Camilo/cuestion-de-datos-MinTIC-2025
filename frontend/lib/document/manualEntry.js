import { redact } from "../api/redact.js";
import { getSafeExternalUrl } from "../evidence/safeExternalUrl.js";

const MANUAL_ENTRY_KEYS = Object.freeze([
  "manualEntryId",
  "value",
  "text",
  "source",
  "url",
  "date",
  "createdAt",
]);
const MANUAL_ENTRY_KEY_SET = new Set(MANUAL_ENTRY_KEYS);
const MANUAL_ENTRY_INPUT_KEYS = Object.freeze(["value", "text", "source", "url", "date"]);
const MANUAL_ENTRY_INPUT_KEY_SET = new Set(MANUAL_ENTRY_INPUT_KEYS);

export const MANUAL_ENTRY_ERROR_CODES = Object.freeze({
  INVALID_ATTRIBUTES: "INVALID_ATTRIBUTES",
  INVALID_ATTRIBUTE_KEYS: "INVALID_ATTRIBUTE_KEYS",
  INVALID_MANUAL_ENTRY_ID: "INVALID_MANUAL_ENTRY_ID",
  MISSING_SOURCE: "MISSING_SOURCE",
  MISSING_VALUE_OR_TEXT: "MISSING_VALUE_OR_TEXT",
  INVALID_VALUE: "INVALID_VALUE",
  UNSAFE_URL: "UNSAFE_URL",
  INVALID_DATE: "INVALID_DATE",
  INVALID_CREATED_AT: "INVALID_CREATED_AT",
  SENSITIVE_DATA_DETECTED: "SENSITIVE_DATA_DETECTED",
  INVALID_DOCUMENT_JSON: "INVALID_DOCUMENT_JSON",
  DUPLICATE_MANUAL_ENTRY_ID: "DUPLICATE_MANUAL_ENTRY_ID",
});

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

function serializableValuesEqual(left, right) {
  if (Object.is(left, right)) return true;
  if (typeof left !== typeof right || left === null || right === null) return false;

  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => serializableValuesEqual(item, right[index]))
    );
  }

  if (typeof left !== "object") return false;
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key) => hasOwn(right, key) && serializableValuesEqual(left[key], right[key]),
    )
  );
}

/** Usa exclusivamente el redactor compartido. Cualquier excepción también
 * es sensible para este dominio: el resultado público nunca incluye el
 * payload ni el texto `[REDACTADO]`. */
function containsSensitiveData(value) {
  try {
    return !serializableValuesEqual(value, redact(value));
  } catch {
    return true;
  }
}

function isValidManualValue(value) {
  if (typeof value === "string") return value.trim() !== "";
  if (typeof value === "number") return Number.isFinite(value);
  return typeof value === "boolean";
}

function isValidCalendarDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;

  const parsed = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function isValidCreatedAt(value) {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)
  ) {
    return false;
  }

  const parsed = new Date(value);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString() === value;
}

function validateManualEntryInputValues(attrs) {
  if (!isNonEmptyString(attrs.source)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE };
  }

  const value = optionalValue(attrs.value);
  const text = optionalValue(attrs.text);
  if ((value === null || (typeof value === "string" && value.trim() === "")) &&
      (text === null || (typeof text === "string" && text.trim() === ""))) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.MISSING_VALUE_OR_TEXT };
  }
  if (value !== null && !isValidManualValue(value)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_VALUE };
  }
  if (text !== null && !isNonEmptyString(text)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_VALUE };
  }

  if (attrs.url !== undefined && attrs.url !== null && getSafeExternalUrl(attrs.url) === null) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.UNSAFE_URL };
  }
  if (attrs.date !== undefined && attrs.date !== null && !isValidCalendarDate(attrs.date)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_DATE };
  }

  return { ok: true };
}

function optionalValue(value) {
  return value === undefined ? null : value;
}

/**
 * Valida exclusivamente los atributos persistidos de un aporte manual.
 * No completa ni normaliza el objeto recibido; los errores son códigos
 * constantes y seguros (T-506, RF-102/RF-103, Arts. I y V).
 */
export function validateManualEntryAttrs(attrs) {
  if (!isPlainObject(attrs)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTES };
  }

  if (containsSensitiveData(attrs)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED };
  }

  if (Object.keys(attrs).some((key) => !MANUAL_ENTRY_KEY_SET.has(key))) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTE_KEYS };
  }

  if (!isNonEmptyString(attrs.manualEntryId)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_MANUAL_ENTRY_ID };
  }
  if (!isNonEmptyString(attrs.source)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE };
  }

  const inputValidation = validateManualEntryInputValues(attrs);
  if (!inputValidation.ok) return inputValidation;
  if (!isValidCreatedAt(attrs.createdAt)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_CREATED_AT };
  }

  return { ok: true };
}

/**
 * Validación de los cinco campos que el formulario puede recibir. No genera
 * ni expone `manualEntryId`/`createdAt`; el comando sigue siendo la única
 * autoridad para esos atributos (T-506, RF-102, Arts. I y V).
 */
export function validateManualEntryInput(payload) {
  if (!isPlainObject(payload)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTES };
  }
  if (containsSensitiveData(payload)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED };
  }
  if (Object.keys(payload).some((key) => !MANUAL_ENTRY_INPUT_KEY_SET.has(key))) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTE_KEYS };
  }

  return validateManualEntryInputValues(payload);
}

/**
 * Builder de lista blanca. Los opcionales ausentes se vuelven `null`, sin
 * tocar ningún valor que el usuario sí proporcionó.
 */
export function buildManualEntryAttrs(payload) {
  if (!isPlainObject(payload)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTES };
  }

  if (containsSensitiveData(payload)) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED };
  }

  const unknownKeys = Object.keys(payload).filter((key) => !MANUAL_ENTRY_KEY_SET.has(key));
  if (unknownKeys.length > 0) {
    return { ok: false, code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTE_KEYS };
  }

  const attrs = Object.fromEntries(
    MANUAL_ENTRY_KEYS.map((key) => [key, optionalValue(payload[key])]),
  );
  const validation = validateManualEntryAttrs(attrs);
  return validation.ok ? { ok: true, attrs } : validation;
}

export { MANUAL_ENTRY_KEYS };
