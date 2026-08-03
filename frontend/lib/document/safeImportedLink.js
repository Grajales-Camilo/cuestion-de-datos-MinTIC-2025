/**
 * Enlaces procedentes de un DOCX aportado por el usuario (DOCX-IMPORT-01,
 * RNF-011). Solo se conservan HTTP/HTTPS absolutos, sin credenciales. Esta
 * política es deliberadamente distinta de la evidencia verificada, que exige
 * HTTPS: el texto importado sigue siendo contenido del usuario, nunca una
 * fuente Socrata ni una EvidenceCitation.
 */
export function getSafeImportedLink(value) {
  if (typeof value !== "string" || value.trim() === "") return null;

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
  if (parsed.username !== "" || parsed.password !== "") return null;
  return parsed.href;
}
