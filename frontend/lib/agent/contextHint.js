/**
 * Normalización pura de `contextHint` al límite del contrato
 * (`contracts/api-rest.md` §2: `context_hint` <= 2000 caracteres). Sin
 * React, sin `fetch`, sin acceso a `document`/almacenamiento.
 *
 * Corrige la pérdida de F3-7A: el valor que el usuario ve y edita en el
 * modal de consentimiento debe ser, byte a byte, el que recibe `startRun`
 * — nunca un truncamiento distinto hecho por otra ruta del código
 * (`maxLength` del `<textarea>` corta a mitad de palabra sin avisar).
 */

const DEFAULT_MAX_LENGTH = 2000;

/**
 * Un corte se considera "razonable" solo si conserva al menos la mitad del
 * límite. Evita que un espacio temprano (p. ej. en el carácter 3) produzca
 * un fragmento casi vacío cuando cortar a mitad de la primera palabra larga
 * habría sido más útil para el usuario.
 */
const MIN_REASONABLE_CUT_RATIO = 0.5;

/**
 * @param {string} rawText
 * @param {{maxLength?: number}} [options]
 * @returns {{value: string, truncated: boolean}}
 */
export function normalizeContextHint(rawText, { maxLength = DEFAULT_MAX_LENGTH } = {}) {
  const text = typeof rawText === "string" ? rawText : "";

  if (text.length <= maxLength) {
    return { value: text, truncated: false };
  }

  const hardCut = text.slice(0, maxLength);
  const lastSpace = hardCut.lastIndexOf(" ");
  const minReasonableCut = Math.floor(maxLength * MIN_REASONABLE_CUT_RATIO);

  if (lastSpace >= minReasonableCut) {
    return { value: hardCut.slice(0, lastSpace).trimEnd(), truncated: true };
  }

  // Sin límite de palabra razonable (p. ej. una cadena única sin espacios,
  // o cuyo único espacio cae demasiado pronto): corte duro seguro al límite
  // exacto de caracteres, nunca por encima de `maxLength`.
  return { value: hardCut, truncated: true };
}
