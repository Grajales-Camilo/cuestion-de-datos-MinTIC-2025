/**
 * Normalización pura y fail-closed de `sectionId` (F5-03A-R2). Sin React,
 * sin `fetch`, sin acceso a `document`/almacenamiento — misma naturaleza
 * que `contextHint.js`. Única definición de las reglas: cada frontera que
 * necesita sanear `sectionId` (registros de `runsStore`, el evento
 * lifecycle `created`, `useRunHistory`, `useAgentRun`, las acciones del
 * reducer que lo aceptan) llama a esta función — nunca duplica su propia
 * expresión regular ni su propio criterio de "sensible".
 *
 * `sectionId` es un identificador cliente-only elegido por quien arma el
 * documento (F5-03A): no tiene un formato contractual propio, así que no
 * hay lista blanca de caracteres que aplicar. La única garantía exigible es
 * que nunca contenga ni pueda RECONSTRUIR un secreto — se reutiliza
 * `redact()` (el único detector de tokens del cliente) para esa prueba en
 * vez de inventar un segundo patrón que pudiera divergir.
 */

import { redact } from "../api/redact.js";

/**
 * @param {unknown} value
 * @returns {string|null}
 */
export function normalizeSectionId(value) {
  try {
    if (typeof value !== "string") return null; // cubre null/undefined/number/boolean/array/objeto
    if (value.trim() === "") return null;
    // Si `redact()` cambia el contenido, `value` incrusta (o reconstruye)
    // un secreto — se descarta por completo, nunca se conserva la versión
    // redactada ("[REDACTADO]" no es un sectionId válido).
    if (redact(value) !== value) return null;
    return value; // conservado exactamente, sin recortar espacios internos
  } catch {
    return null;
  }
}
