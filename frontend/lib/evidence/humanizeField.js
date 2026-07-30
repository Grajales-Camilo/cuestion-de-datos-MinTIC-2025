/**
 * Convierte un nombre de columna real de Socrata (snake_case, minúsculas
 * casi siempre) en una etiqueta legible mínima. Puro, determinista, sin
 * interpretación semántica del contenido:
 *
 * - cambia guiones bajos por espacios;
 * - capitaliza únicamente la primera letra del resultado;
 * - corrige solo patrones de mojibake COMPROBADOS contra un caso real
 *   (tabla vacía por ahora — no hay ninguno verificado todavía). Añadir
 *   una entrada aquí exige una prueba que la respalde; no se fabrican
 *   correcciones especulativas.
 *
 * Nunca traduce el significado del campo (p. ej. no expande siglas ni
 * decide sinónimos): esa sería información inventada, prohibida por
 * `implementation-plan.md` §4.7 y el Art. I de la constitución.
 */

/** @type {Array<[string, string]>} pares [patrón_roto, corrección] */
const VERIFIED_MOJIBAKE_CORRECTIONS = [];

export function humanizeField(fieldName) {
  if (typeof fieldName !== "string") return "";
  const trimmed = fieldName.trim();
  if (trimmed === "") return "";

  let text = trimmed.toLowerCase().replace(/_/g, " ");
  for (const [broken, fixed] of VERIFIED_MOJIBAKE_CORRECTIONS) {
    text = text.split(broken).join(fixed);
  }

  return text.charAt(0).toUpperCase() + text.slice(1);
}
