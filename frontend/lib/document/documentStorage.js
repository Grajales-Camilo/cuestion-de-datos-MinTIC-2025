/**
 * Persistencia local del documento del canvas (F6-01, RF-102/RF-103, ESC-08).
 * Puro (sin React): reutiliza `lib/session/storage.js`
 * (`safeReadJson`/`safeWriteJson`/`isolateCorrupt`/`removeKeysWithPrefix`/
 * `safeRemove`) y `documentModel.js` (`validateDocumentModel`) — no duplica
 * ninguno de los dos esquemas.
 *
 * Forma del sobre persistido en `cdd.doc.v1`:
 * `{ schemaVersion, createdAt, updatedAt, document }`, donde `document` debe
 * pasar `validateDocumentModel()` completo. `schemaVersion` es la versión del
 * FORMATO DE ALMACENAMIENTO, deliberadamente separada de `document.version`
 * (`DOCUMENT_MODEL_VERSION` en `documentModel.js`): son dos preguntas
 * distintas ("¿cómo está envuelto en `localStorage`?" vs. "¿qué forma tiene
 * el modelo documental en sí?"). Se anida el modelo completo bajo `document`
 * en vez de aplanar sus campos en el sobre para no reimplementar aquí las
 * invariantes de secciones/plantilla que ya vive en `documentModel.js`.
 *
 * No hay ninguna versión histórica real de `cdd.doc.v1` anterior a este
 * incremento (F6-01 es la primera vez que el documento se persiste). Por eso
 * `migrateStoredDocument` deja el runner de migraciones ENCADENADAS listo
 * (con backup previo, fallo que conserva el original, idempotencia) pero sin
 * ningún paso registrado en producción: fabricar un "v0" sintético violaría
 * la prohibición de inventar evidencia histórica. Las pruebas que ejercen el
 * runner inyectan sus propias migraciones sintéticas, marcadas como tales.
 */

import {
  isolateCorrupt,
  removeKeysWithPrefix,
  safeReadJson,
  safeRemove,
  safeWriteJson,
} from "../session/storage.js";
import { redact } from "../api/redact.js";
import { validateDocumentModel } from "./documentModel.js";

export const DOCUMENT_STORAGE_KEY = "cdd.doc.v1";
export const DOCUMENT_STORAGE_SCHEMA_VERSION = 1;
export const DOCUMENT_STORAGE_CORRUPT_PREFIX = `${DOCUMENT_STORAGE_KEY}.corrupt.`;
export const DOCUMENT_STORAGE_BACKUP_PREFIX = `${DOCUMENT_STORAGE_KEY}.backup.`;

/**
 * Resultado de `loadStoredDocument`. Conjunto cerrado — el llamador debe
 * manejar los siete estados explícitamente, nunca asumir un octavo.
 */
export const DOCUMENT_STORAGE_STATUS = Object.freeze({
  EMPTY: "empty",
  OK: "ok",
  CORRUPT: "corrupt",
  INVALID: "invalid",
  FUTURE_VERSION: "future_version",
  MIGRATION_FAILED: "migration_failed",
  UNAVAILABLE: "unavailable",
});

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isValidIsoString(value) {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Date.parse(value));
}

function safeStringify(value) {
  try {
    return JSON.stringify(value);
  } catch {
    return null;
  }
}

/** Clona por valor vía JSON (nunca por referencia): un sobre ya validado
 * como `isPlainObject`/JSON-serializable, así que esto nunca pierde datos.
 * `null` solo si `value` no fuera serializable (no ocurre con un sobre real). */
function deepCloneJson(value) {
  const serialized = safeStringify(value);
  if (serialized === null) return null;
  try {
    return JSON.parse(serialized);
  } catch {
    return null;
  }
}

/**
 * Forma mínima del SOBRE, deliberadamente sin exigir todavía `document`: una
 * versión anterior real (si existiera) podría envolver el documento de otra
 * manera — es precisamente lo que una migración encadenada tendría que
 * poder leer antes de transformarlo. La forma completa (`document` como
 * objeto plano que además pasa `validateDocumentModel()`) solo se exige una
 * vez resuelto `schemaVersion === DOCUMENT_STORAGE_SCHEMA_VERSION`, sea
 * porque ya lo estaba o porque una migración lo dejó así.
 */
function isValidEnvelopeShape(envelope) {
  return (
    isPlainObject(envelope) &&
    Number.isInteger(envelope.schemaVersion) &&
    envelope.schemaVersion >= 0 &&
    isValidIsoString(envelope.createdAt) &&
    isValidIsoString(envelope.updatedAt)
  );
}

/**
 * Aísla un valor ya parseado pero semánticamente inválido (sobre mal
 * formado o `document` que no pasa `validateDocumentModel()`) usando el
 * mismo mecanismo que un JSON corrupto: se serializa, se redacta y se
 * escribe en `cdd.doc.v1.corrupt.<timestamp>`. La clave original NUNCA se
 * toca aquí — igual que `runsStore.readDoc`, queda intacta hasta la próxima
 * escritura real, así que un fallo de lectura nunca borra en silencio un
 * documento que en realidad sigue ahí.
 */
function isolateInvalidEnvelope(storage, envelope, now) {
  const raw = safeStringify(envelope);
  const isolated = raw !== null ? isolateCorrupt(storage, DOCUMENT_STORAGE_KEY, raw, { now, sanitize: redact }) : { ok: false };
  return {
    status: DOCUMENT_STORAGE_STATUS.INVALID,
    document: null,
    envelope: null,
    raw: raw !== null ? redact(raw) : null,
    diagnosticKey: isolated.diagnosticKey ?? null,
  };
}

/**
 * Aplica migraciones encadenadas e idempotentes desde `rawEnvelope.schemaVersion`
 * hasta `DOCUMENT_STORAGE_SCHEMA_VERSION`. Un sobre ya vigente es un no-op
 * inmediato (ni siquiera toca `storage`), lo que la hace idempotente por
 * construcción: aplicarla dos veces sobre su propio resultado produce el
 * mismo sobre sin efectos adicionales.
 *
 * Cuando SÍ hay una migración que ejecutar, el backup es una condición
 * previa verificada, no un best-effort (F6-01-R1, PARTE 2): se escribe, se
 * relee y se compara byte a byte contra el original ANTES de correr un solo
 * paso de la cadena. `safeWriteJson(...).ok` en `true` no basta por sí solo
 * — un `Storage` puede reportar éxito sin persistir de verdad (mismo riesgo
 * que ya documenta `runsStore.migrate`) — así que la verificación relee la
 * clave y exige igualdad estructural exacta. Cualquier fallo de esa
 * verificación aborta ANTES de tocar la cadena de migraciones: nunca se
 * clasifica un fallo de backup como una migración exitosa.
 *
 * Cada paso debe avanzar EXACTAMENTE una versión (`next.schemaVersion ===
 * current.schemaVersion + 1`): ni quedarse en la misma, ni retroceder, ni
 * saltar versiones (un paso 0→2 con `DOCUMENT_STORAGE_SCHEMA_VERSION === 1`
 * falla cerrado, nunca se acepta como si fuera 0→1). Al terminar la cadena
 * se reverifica que la versión final sea EXACTAMENTE la soportada.
 *
 * `migrations` es un mapa `{ [fromVersion]: (envelope, {now}) => nextEnvelope }`.
 * Vacío en producción (ver docstring del módulo). Un paso ausente, que
 * lance, que no avance exactamente una versión, o que deje una versión
 * final distinta de la soportada: la migración falla y `rawEnvelope`
 * original se devuelve intacto — el llamador no debe sobrescribir
 * `cdd.doc.v1` en ese caso. El backup ya escrito y verificado NUNCA se borra
 * automáticamente, ni aquí ni tras una migración exitosa (`clearStoredDocument`
 * solo lo hace ante un borrado deliberado del usuario).
 *
 * F6-02A PARTE 1.3: cada paso recibe una COPIA independiente de `current`,
 * nunca la referencia real. Un paso con bug que muta su propio argumento
 * (y luego lanza, se estanca, salta de versión o devuelve algo inválido) no
 * puede alterar `rawEnvelope` — que es exactamente lo que este runner
 * devuelve como "original intacto" en cada rama de fallo, y lo que el
 * llamador ofrece para descarga. Sin esta copia, la mutación se filtraba al
 * valor que se presentaba como pristino.
 *
 * @returns {{ok: true, envelope: object, migrated: boolean}|{ok: false, reason: string, envelope: object}}
 */
export function migrateStoredDocument(rawEnvelope, { migrations = {}, now = () => Date.now(), storage } = {}) {
  if (!isPlainObject(rawEnvelope) || !Number.isInteger(rawEnvelope.schemaVersion) || rawEnvelope.schemaVersion < 0) {
    return { ok: false, reason: "invalid_envelope", envelope: rawEnvelope };
  }
  if (rawEnvelope.schemaVersion === DOCUMENT_STORAGE_SCHEMA_VERSION) {
    return { ok: true, envelope: rawEnvelope, migrated: false };
  }
  if (rawEnvelope.schemaVersion > DOCUMENT_STORAGE_SCHEMA_VERSION) {
    return { ok: false, reason: "future_version", envelope: rawEnvelope };
  }

  const startVersion = rawEnvelope.schemaVersion;
  const backupKey = `${DOCUMENT_STORAGE_BACKUP_PREFIX}${startVersion}`;
  const rawEnvelopeStringified = safeStringify(rawEnvelope);

  const backupWrite = safeWriteJson(storage, backupKey, rawEnvelope);
  if (!backupWrite.ok) {
    return { ok: false, reason: "backup_write_failed", envelope: rawEnvelope };
  }
  const backupRead = safeReadJson(storage, backupKey);
  const backupVerified =
    backupRead.ok &&
    backupRead.value !== null &&
    rawEnvelopeStringified !== null &&
    safeStringify(backupRead.value) === rawEnvelopeStringified;
  if (!backupVerified) {
    return { ok: false, reason: "backup_verification_failed", envelope: rawEnvelope };
  }

  let current = deepCloneJson(rawEnvelope);
  if (current === null) {
    return { ok: false, reason: "invalid_envelope", envelope: rawEnvelope };
  }
  try {
    while (current.schemaVersion < DOCUMENT_STORAGE_SCHEMA_VERSION) {
      const step = migrations[current.schemaVersion];
      if (typeof step !== "function") {
        return { ok: false, reason: "no_migration_path", envelope: rawEnvelope };
      }
      // Copia defensiva: si `step` muta su argumento, muta la copia, nunca
      // `current` ni, por transitividad, `rawEnvelope` (F6-02A PARTE 1.3).
      const stepInput = deepCloneJson(current);
      const next = step(stepInput, { now });
      if (!isPlainObject(next) || next.schemaVersion !== current.schemaVersion + 1) {
        return { ok: false, reason: "migration_step_invalid", envelope: rawEnvelope };
      }
      current = next;
    }
  } catch {
    return { ok: false, reason: "migration_threw", envelope: rawEnvelope };
  }

  if (current.schemaVersion !== DOCUMENT_STORAGE_SCHEMA_VERSION) {
    return { ok: false, reason: "final_version_mismatch", envelope: rawEnvelope };
  }

  return { ok: true, envelope: current, migrated: true };
}

/**
 * Carga y valida `cdd.doc.v1`. Nunca lanza (delega en `safeReadJson`, que
 * tampoco lanza). Clasifica el resultado en `DOCUMENT_STORAGE_STATUS` — el
 * llamador (típicamente `useDocumentAutosave`) decide qué hacer en cada
 * caso, incluida la barrera de "no autoguardar antes de terminar de leer".
 *
 * @returns {{status: string, document: object|null, envelope: object|null, raw: string|null, diagnosticKey: string|null}}
 */
export function loadStoredDocument(storage, { now = () => Date.now(), migrations = {} } = {}) {
  const result = safeReadJson(storage, DOCUMENT_STORAGE_KEY);

  if (!result.ok) {
    if (result.reason === "corrupt") {
      const isolated = isolateCorrupt(storage, DOCUMENT_STORAGE_KEY, result.raw, { now, sanitize: redact });
      return {
        status: DOCUMENT_STORAGE_STATUS.CORRUPT,
        document: null,
        envelope: null,
        raw: redact(result.raw),
        diagnosticKey: isolated.diagnosticKey ?? null,
      };
    }
    return { status: DOCUMENT_STORAGE_STATUS.UNAVAILABLE, document: null, envelope: null, raw: null, diagnosticKey: null };
  }

  if (result.value === null) {
    return { status: DOCUMENT_STORAGE_STATUS.EMPTY, document: null, envelope: null, raw: null, diagnosticKey: null };
  }

  let envelope = result.value;

  if (!isValidEnvelopeShape(envelope)) {
    return isolateInvalidEnvelope(storage, envelope, now);
  }

  if (envelope.schemaVersion > DOCUMENT_STORAGE_SCHEMA_VERSION) {
    return {
      status: DOCUMENT_STORAGE_STATUS.FUTURE_VERSION,
      document: null,
      envelope,
      raw: null,
      diagnosticKey: null,
    };
  }

  if (envelope.schemaVersion < DOCUMENT_STORAGE_SCHEMA_VERSION) {
    const migration = migrateStoredDocument(envelope, { now, migrations, storage });
    if (!migration.ok) {
      return {
        status: DOCUMENT_STORAGE_STATUS.MIGRATION_FAILED,
        document: null,
        envelope,
        raw: null,
        diagnosticKey: null,
        reason: migration.reason,
      };
    }
    envelope = migration.envelope;
  }

  if (!isPlainObject(envelope.document)) {
    return isolateInvalidEnvelope(storage, envelope, now);
  }

  const modelValidation = validateDocumentModel(envelope.document);
  if (!modelValidation.ok) {
    return isolateInvalidEnvelope(storage, envelope, now);
  }

  // Sobre migrado con éxito EN MEMORIA: se persiste ya en forma vigente para
  // no repetir la migración en cada carga futura. F6-02A PARTE 1.2: esa
  // escritura ya NO es best-effort — si no prospera, la migración en su
  // conjunto se reporta como fallida (nunca "ok" sobre un documento que en
  // realidad no quedó guardado). El original sigue intacto en `storage`
  // (nunca se tocó esa clave hasta este punto), así que se devuelve tal cual.
  if (envelope !== result.value) {
    const persisted = saveStoredDocument(storage, envelope.document, { now, previousEnvelope: envelope });
    if (!persisted.ok) {
      return {
        status: DOCUMENT_STORAGE_STATUS.MIGRATION_FAILED,
        document: null,
        envelope: result.value,
        raw: null,
        diagnosticKey: null,
        reason: "migration_write_failed",
      };
    }
    envelope = persisted.envelope;
  }

  return { status: DOCUMENT_STORAGE_STATUS.OK, document: envelope.document, envelope, raw: null, diagnosticKey: null };
}

/**
 * Valida y persiste `document` como el sobre vigente. Nunca escribe un
 * documento inválido. Conserva `createdAt` del sobre anterior si se provee y
 * es una fecha ISO válida; en caso contrario usa `now()` para ambas fechas
 * (primera escritura).
 *
 * @returns {{ok: true, envelope: object}|{ok: false, reason: string, code?: string}}
 */
export function saveStoredDocument(storage, document, { now = () => Date.now(), previousEnvelope = null } = {}) {
  const validation = validateDocumentModel(document);
  if (!validation.ok) {
    return { ok: false, reason: "invalid_document", code: validation.code };
  }

  const nowIso = new Date(now()).toISOString();
  const createdAt =
    previousEnvelope && isValidIsoString(previousEnvelope.createdAt) ? previousEnvelope.createdAt : nowIso;

  const envelope = {
    schemaVersion: DOCUMENT_STORAGE_SCHEMA_VERSION,
    createdAt,
    updatedAt: nowIso,
    document,
  };

  const result = safeWriteJson(storage, DOCUMENT_STORAGE_KEY, envelope);
  if (!result.ok) {
    return { ok: false, reason: result.reason };
  }
  removeKeysWithPrefix(storage, DOCUMENT_STORAGE_CORRUPT_PREFIX);
  return { ok: true, envelope };
}

/** Borra el documento y todas sus claves de diagnóstico/backup relacionadas. */
export function clearStoredDocument(storage) {
  removeKeysWithPrefix(storage, DOCUMENT_STORAGE_CORRUPT_PREFIX);
  removeKeysWithPrefix(storage, DOCUMENT_STORAGE_BACKUP_PREFIX);
  return safeRemove(storage, DOCUMENT_STORAGE_KEY);
}

/**
 * Construye (de forma pura, sin tocar el DOM) el nombre de archivo y el
 * contenido JSON de una copia descargable de `value` (un sobre completo, un
 * documento, o cualquier valor serializable que se quiera entregar al
 * usuario). Quien dispara la descarga real en el navegador (Blob + enlace
 * temporal) vive en un componente, igual que `DownloadCsvButton.jsx` —
 * este módulo se mantiene libre de DOM.
 */
export function buildDocumentBackupPayload(value, { now = () => Date.now() } = {}) {
  const timestamp = new Date(now()).toISOString().replace(/[:.]/g, "-");
  return {
    filename: `cuestion-de-datos-documento-${timestamp}.json`,
    contents: JSON.stringify(value, null, 2),
  };
}

/**
 * Igual que `buildDocumentBackupPayload`, pero para un `raw` que YA es texto
 * (la copia diagnóstica redactada de un documento corrupto o inválido,
 * `loadStoredDocument(...).raw`): escribirlo con `JSON.stringify` lo
 * re-envolvería en comillas y lo escaparía. Se usa tal cual.
 */
export function buildRawBackupPayload(raw, { now = () => Date.now() } = {}) {
  const timestamp = new Date(now()).toISOString().replace(/[:.]/g, "-");
  return {
    filename: `cuestion-de-datos-documento-diagnostico-${timestamp}.json`,
    contents: typeof raw === "string" ? raw : JSON.stringify(raw, null, 2),
  };
}
