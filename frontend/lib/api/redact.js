/**
 * Redacta el token de corrida (RF-801) y cualquier valor asociado a una
 * clave sensible antes de que algo llegue a `console.*` o a un mensaje de
 * error. Es el único punto de redacción del cliente; no hace logging por sí
 * misma.
 *
 * - Sustituye cualquier ocurrencia del patrón `cdt_rt_[A-Za-z0-9_-]+`,
 *   aparezca donde aparezca dentro de una cadena.
 * - Sustituye por completo el valor de cualquier clave (sin distinguir
 *   mayúsculas) `token`, `access_token`, `run_access_token` o
 *   `authorization`, incluso si ese valor no calza con el patrón anterior
 *   (p. ej. un encabezado `Bearer ...` completo).
 * - Recorre strings, arrays y objetos anidados sin límite de profundidad.
 * - Nunca muta la entrada: siempre devuelve una copia.
 * - No lanza ante `null`, `undefined` u otros valores ordinarios.
 */

const TOKEN_PATTERN = /cdt_rt_[A-Za-z0-9_-]+/g;
const SENSITIVE_KEYS = new Set([
  "token",
  "access_token",
  "run_access_token",
  "authorization",
]);
const REDACTED = "[REDACTADO]";

export function redact(value) {
  return redactValue(value);
}

function redactValue(value) {
  if (typeof value === "string") return redactString(value);
  if (Array.isArray(value)) return value.map(redactValue);
  if (value !== null && typeof value === "object") return redactObject(value);
  return value;
}

function redactString(text) {
  return text.replace(TOKEN_PATTERN, REDACTED);
}

function redactObject(obj) {
  const out = {};
  for (const key of Object.keys(obj)) {
    out[key] = SENSITIVE_KEYS.has(key.toLowerCase())
      ? REDACTED
      : redactValue(obj[key]);
  }
  return out;
}
