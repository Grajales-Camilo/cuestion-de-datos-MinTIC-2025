/**
 * Valida una URL externa antes de que se convierta en un enlace navegable
 * (`CitationBlock`, F4-02-R1/F4-03). Solo acepta URLs ABSOLUTAS con
 * protocolo `https:` — rechaza `javascript:`, `data:`, `file:`,
 * `vbscript:`, URLs relativas o protocol-relative (`/ruta`, `//dominio`),
 * cualquier cadena no parseable como URL absoluta, y (F4-03) URLs con
 * credenciales embebidas (`https://usuario:clave@host/...`) — un vector de
 * phishing/exfiltración que una validación de solo-protocolo no detecta.
 * Nunca "arregla" una URL inválida: o es segura tal cual, o no hay enlace.
 * Puro: sin red, sin DOM.
 *
 * @param {unknown} value
 * @returns {string|null} la URL original si es segura, o `null`.
 */
export function getSafeExternalUrl(value) {
  if (typeof value !== "string" || value.trim() === "") return null;

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return null; // no absoluta o no parseable — nunca se intenta corregir
  }

  if (parsed.protocol !== "https:") return null;
  if (parsed.username !== "" || parsed.password !== "") return null;

  return value;
}
