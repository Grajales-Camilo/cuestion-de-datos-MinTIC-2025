/**
 * Envoltorio defensivo sobre `Storage` (`sessionStorage`/`localStorage`).
 * Ningún error de almacenamiento (modo privado, cuota agotada, storage
 * inexistente en SSR, JSON corrupto) debe propagarse como excepción hacia
 * el llamador: `lib/session/*` depende de que estas funciones **nunca
 * lancen**, para que "un error de almacenamiento no pueda habilitar el
 * POST por accidente" (regla de `useConsent`) y para que un dato inválido
 * nunca se convierta silenciosamente en un reinicio del historial.
 */

function isQuotaExceededError(error) {
  if (!error) return false;
  // `QuotaExceededError` (Chrome/Safari) o `NS_ERROR_DOM_QUOTA_REACHED`
  // (Firefox, expuesto también como `QuotaExceededError` en navegadores
  // modernos, pero se comprueba el código legado 22 por compatibilidad).
  return (
    error.name === "QuotaExceededError" ||
    error.name === "NS_ERROR_DOM_QUOTA_REACHED" ||
    error.code === 22
  );
}

/** Lee y parsea JSON de `storage[key]`. Nunca lanza. */
export function safeReadJson(storage, key) {
  if (!storage) return { ok: true, value: null };
  let raw;
  try {
    raw = storage.getItem(key);
  } catch {
    return { ok: false, reason: "unavailable" };
  }
  if (raw === null || raw === undefined) {
    return { ok: true, value: null };
  }
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch {
    return { ok: false, reason: "corrupt", raw };
  }
}

/** Serializa y escribe JSON en `storage[key]`. Nunca lanza. */
export function safeWriteJson(storage, key, value) {
  if (!storage) return { ok: false, reason: "unavailable" };
  let serialized;
  try {
    serialized = JSON.stringify(value);
  } catch {
    return { ok: false, reason: "unserializable" };
  }
  try {
    storage.setItem(key, serialized);
    return { ok: true };
  } catch (error) {
    if (isQuotaExceededError(error)) {
      return { ok: false, reason: "quota_exceeded" };
    }
    return { ok: false, reason: "unavailable" };
  }
}

/** Elimina `storage[key]`. Nunca lanza. */
export function safeRemove(storage, key) {
  if (!storage) return { ok: false, reason: "unavailable" };
  try {
    storage.removeItem(key);
    return { ok: true };
  } catch {
    return { ok: false, reason: "unavailable" };
  }
}

/**
 * Aísla un valor crudo corrupto en una clave de diagnóstico
 * (`<key>.corrupt.<timestamp>`) antes de que el llamador reinicie la
 * clave original — preserva evidencia en vez de perder el dato en
 * silencio. Best-effort: si tampoco se puede escribir el diagnóstico
 * (cuota agotada), no se pierde ni se lanza; simplemente no queda copia.
 *
 * `sanitize` (opcional) se aplica al `raw` ANTES de escribirlo: un JSON
 * corrupto puede seguir conteniendo un token en texto plano (el parseo
 * falló, pero la subcadena del secreto sigue ahí) — el llamador que
 * maneja datos con credenciales (`runsStore.js`) debe pasar `redact()`
 * para que la copia de diagnóstico nunca sea una segunda ubicación
 * persistente del mismo secreto.
 */
export function isolateCorrupt(storage, key, raw, { now = () => Date.now(), sanitize } = {}) {
  if (!storage || typeof raw !== "string") return { ok: false };
  const diagnosticKey = `${key}.corrupt.${now()}`;
  const safeRaw = typeof sanitize === "function" ? sanitize(raw) : raw;
  try {
    storage.setItem(diagnosticKey, safeRaw);
    return { ok: true, diagnosticKey };
  } catch {
    return { ok: false };
  }
}

/**
 * Elimina todas las claves de `storage` cuyo nombre empiece por `prefix`
 * — usado para barrer copias de diagnóstico (`<key>.corrupt.<timestamp>`,
 * una por cada corrupción observada) cuando ya no hacen falta: tras
 * persistir con éxito un documento válido en esa misma clave, o al
 * limpiar el almacén por completo. Best-effort y nunca lanza; un fallo al
 * enumerar o borrar una clave no aborta el resto.
 */
export function removeKeysWithPrefix(storage, prefix) {
  if (!storage) return { ok: false, reason: "unavailable" };
  let keys;
  try {
    keys = [];
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (typeof key === "string" && key.startsWith(prefix)) keys.push(key);
    }
  } catch {
    return { ok: false, reason: "unavailable" };
  }
  let removed = 0;
  for (const key of keys) {
    try {
      storage.removeItem(key);
      removed += 1;
    } catch {
      // best-effort: se sigue con las demás claves.
    }
  }
  return { ok: true, removed };
}
