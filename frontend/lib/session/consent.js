/**
 * Consentimiento versionado (D-9, RF-802). `localStorage`: el consentimiento
 * debe sobrevivir al cierre de la pestaña, para no volver a preguntar en
 * cada sesión mientras la versión del texto no cambie.
 *
 * Regla dura: ausente, corrupto o con una versión distinta de la vigente
 * equivalen exactamente a "no concedido". Esta función nunca infiere ni
 * fabrica una aceptación — solo la lee si el registro es válido y
 * corresponde a la versión pedida.
 */
import { isolateCorrupt, safeReadJson, safeRemove, safeWriteJson } from "./storage.js";

export const CONSENT_STORAGE_KEY = "cdd.consent.v1";
export const CONSENT_SCHEMA_VERSION = 1;

/** Versión vigente del texto de consentimiento (D-9/D-10, ADR-0006: subió a
 * 2 cuando el límite de `context_hint` pasó de 1.000 a 2.000 caracteres). */
export const CURRENT_CONSENT_VERSION = 2;

function isValidConsentDoc(doc) {
  return Boolean(
    doc &&
      typeof doc === "object" &&
      doc.schemaVersion === CONSENT_SCHEMA_VERSION &&
      Number.isInteger(doc.consentVersion) &&
      typeof doc.acceptedAt === "string" &&
      doc.acceptedAt.length > 0
  );
}

const NOT_GRANTED = Object.freeze({ granted: false, consentVersion: null, acceptedAt: null });

/**
 * @param {{storage: Storage, requiredVersion?: number}} params
 * @returns {{granted: boolean, consentVersion: number|null, acceptedAt: string|null}}
 */
export function readConsent({ storage, requiredVersion = CURRENT_CONSENT_VERSION } = {}) {
  const result = safeReadJson(storage, CONSENT_STORAGE_KEY);

  if (!result.ok) {
    if (result.reason === "corrupt") {
      // Se aísla para diagnóstico, pero nunca se inventa una aceptación a
      // partir de un registro que no se pudo interpretar.
      isolateCorrupt(storage, CONSENT_STORAGE_KEY, result.raw);
    }
    return NOT_GRANTED;
  }

  const doc = result.value;
  if (doc === null || !isValidConsentDoc(doc)) return NOT_GRANTED;
  if (doc.consentVersion !== requiredVersion) return NOT_GRANTED;

  return { granted: true, consentVersion: doc.consentVersion, acceptedAt: doc.acceptedAt };
}

/**
 * Registra la aceptación de `consentVersion`. No incluye pregunta,
 * contexto ni tokens — ver `lib/session/runsStore.js` para eso.
 */
export function writeConsent({ storage, consentVersion, now = () => new Date().toISOString() }) {
  const doc = {
    schemaVersion: CONSENT_SCHEMA_VERSION,
    consentVersion,
    acceptedAt: now(),
  };
  return safeWriteJson(storage, CONSENT_STORAGE_KEY, doc);
}

export function clearConsent(storage) {
  return safeRemove(storage, CONSENT_STORAGE_KEY);
}
