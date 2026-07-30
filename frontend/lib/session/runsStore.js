/**
 * Historial de investigaciones y credenciales de corrida (D-1, RF-502,
 * RF-801). `sessionStorage` es el almacén por defecto; `localStorage`
 * únicamente cuando el usuario activó "Recordar mis investigaciones en
 * este equipo" (`rememberRuns`). El mismo registro nunca vive en ambos
 * almacenes a la vez: togglear el opt-in migra, no duplica.
 *
 * El único método que puede devolver un `token` es `getCredential`,
 * explícito y acotado a un `runId`. Todo lo demás (`listPublic`, el valor
 * de retorno de `upsert`/`remove`/`migrate`) está saneado: sin `token`
 * (`toPublicRecord`) y con `sectionId` normalizado fail-closed
 * (`normalizeSectionId`, F5-03A-R2) — nunca puede filtrar un secreto
 * incrustado (p. ej. `"seccion-cdt_rt_..."`), venga de una acción propia,
 * de una llamada programática o de un `localStorage` manipulado a mano.
 */
import { isolateCorrupt, removeKeysWithPrefix, safeReadJson, safeRemove, safeWriteJson } from "./storage.js";
import { redact } from "../api/redact.js";
import { normalizeSectionId } from "../agent/sectionId.js";

export const RUNS_STORAGE_KEY = "cdd.runs.v1";
export const RUNS_SCHEMA_VERSION = 1;

/** Prefijo de TODAS las claves de diagnóstico de corrupción de este store
 * (una por corrupción observada: `cdd.runs.v1.corrupt.<timestamp>`) —
 * "las claves relacionadas" que deben limpiarse junto con la clave
 * principal, nunca solo esta última. */
const CORRUPT_KEY_PREFIX = `${RUNS_STORAGE_KEY}.corrupt.`;

function isValidRecord(rec) {
  return Boolean(
    rec &&
      typeof rec === "object" &&
      typeof rec.runId === "string" &&
      rec.runId.length > 0 &&
      typeof rec.question === "string" &&
      typeof rec.status === "string" &&
      typeof rec.createdAt === "string" &&
      typeof rec.updatedAt === "string"
  );
}

function isValidDoc(doc) {
  return Boolean(
    doc && typeof doc === "object" && doc.schemaVersion === RUNS_SCHEMA_VERSION && Array.isArray(doc.records)
  );
}

/**
 * Única forma pública de un registro: sin `token` y con `sectionId`
 * saneado fail-closed. Defensa en profundidad — el registro que llega aquí
 * debería venir ya normalizado desde `upsert` (ver más abajo), pero un
 * `localStorage` editado a mano fuera de este módulo también pasa por
 * aquí antes de exponerse.
 */
function toPublicRecord(rec) {
  // eslint-disable-next-line no-unused-vars -- se descarta intencionalmente
  const { token, ...pub } = rec;
  return { ...pub, sectionId: normalizeSectionId(pub.sectionId) };
}

function isExpired(rec, nowMs) {
  if (!rec.tokenExpiresAt) return false;
  const parsed = Date.parse(rec.tokenExpiresAt);
  return Number.isFinite(parsed) && parsed <= nowMs;
}

/**
 * Lee el documento de un `storage` concreto. Un JSON corrupto se aísla en
 * una clave de diagnóstico y NUNCA se sobrescribe de inmediato: la clave
 * original queda intacta hasta la próxima escritura real (`upsert`,
 * `remove`, `migrate`), así que no hay ventana en la que un fallo de
 * lectura borre en silencio un historial válido.
 *
 * El `raw` corrupto puede contener un token en texto plano aunque el
 * `JSON.parse` haya fallado (el parseo falla en cualquier punto, no
 * necesariamente después del secreto) — la copia de diagnóstico pasa por
 * `redact()` (mismo redactor que protege `console.*`/errores en
 * `lib/api/`) antes de escribirse, para que nunca se cree una segunda
 * ubicación persistente del mismo secreto.
 */
function readDoc(storage) {
  const result = safeReadJson(storage, RUNS_STORAGE_KEY);
  if (!result.ok) {
    if (result.reason === "corrupt") {
      isolateCorrupt(storage, RUNS_STORAGE_KEY, result.raw, { sanitize: redact });
    }
    return { records: [] };
  }
  if (result.value === null) return { records: [] };
  if (!isValidDoc(result.value)) return { records: [] };
  return { records: result.value.records.filter(isValidRecord) };
}

/**
 * Escribe el documento y, solo si la escritura tuvo éxito, barre
 * cualquier copia de diagnóstico de corrupción anterior de esta misma
 * clave (`cdd.runs.v1.corrupt.*`): un documento válido recién persistido
 * vuelve obsoleta cualquier copia de diagnóstico previa, y esa copia
 * podía contener un token redactado pero aun así no debe sobrevivir
 * indefinidamente sin motivo.
 */
function writeDoc(storage, records) {
  const result = safeWriteJson(storage, RUNS_STORAGE_KEY, { schemaVersion: RUNS_SCHEMA_VERSION, records });
  if (result.ok) {
    removeKeysWithPrefix(storage, CORRUPT_KEY_PREFIX);
  }
  return result;
}

/**
 * @param {{sessionStorage: Storage, localStorage: Storage, now?: () => number}} deps
 */
export function createRunsStore({ sessionStorage, localStorage, now = () => Date.now() }) {
  function activeStorage(rememberRuns) {
    return rememberRuns ? localStorage : sessionStorage;
  }

  /** Historial saneado: nunca incluye `token`. Registros vencidos se
   * marcan `credentialExpired: true` en vez de desaparecer, para que el
   * usuario siga viendo que la investigación ocurrió. */
  function listPublic(rememberRuns) {
    const { records } = readDoc(activeStorage(rememberRuns));
    const nowMs = now();
    return records.map((rec) => {
      const pub = toPublicRecord(rec);
      return isExpired(rec, nowMs) ? { ...pub, credentialExpired: true } : pub;
    });
  }

  /**
   * Único método que expone un `token`. Acotado por `runId`; nunca hay una
   * ruta que entregue todas las credenciales a la vez. Un registro vencido
   * devuelve `null`: su token nunca se reutiliza.
   */
  function getCredential(rememberRuns, runId) {
    const { records } = readDoc(activeStorage(rememberRuns));
    const rec = records.find((r) => r.runId === runId);
    if (!rec || !rec.token) return null;
    if (isExpired(rec, now())) return null;
    return {
      token: rec.token,
      lastEventId: typeof rec.lastEventId === "number" ? rec.lastEventId : null,
      tokenExpiresAt: rec.tokenExpiresAt ?? null,
    };
  }

  function upsert(rememberRuns, partialRecord) {
    const storage = activeStorage(rememberRuns);
    const { records } = readDoc(storage);
    const idx = records.findIndex((r) => r.runId === partialRecord.runId);
    const nowIso = new Date(now()).toISOString();

    // Saneado fail-closed EN LA ESCRITURA (F5-03A-R2), no solo al leer: si
    // `partialRecord` no trae `sectionId` (p. ej. una actualización de
    // `status`/`seq`), no se toca — nunca se inventa ni se sobrescribe el
    // valor ya guardado. Cuando sí lo trae, se normaliza ANTES de
    // persistir, así el documento guardado en `storage` nunca contiene un
    // `sectionId` con un secreto incrustado, sin importar el origen
    // (acción propia, llamada programática, o un valor ya corrupto que
    // llegara por error).
    const safePartialRecord = Object.prototype.hasOwnProperty.call(partialRecord, "sectionId")
      ? { ...partialRecord, sectionId: normalizeSectionId(partialRecord.sectionId) }
      : partialRecord;

    let next;
    if (idx === -1) {
      next = [
        ...records,
        {
          token: null,
          tokenExpiresAt: null,
          contextHint: null,
          summary: null,
          lastEventId: null,
          ...safePartialRecord,
          createdAt: safePartialRecord.createdAt ?? nowIso,
          updatedAt: nowIso,
        },
      ];
    } else {
      next = records.map((r, i) => (i === idx ? { ...r, ...safePartialRecord, updatedAt: nowIso } : r));
    }

    // `QuotaExceededError` u otro fallo de escritura: el almacén conserva
    // su contenido previo intacto (setItem nunca escribe parcialmente); se
    // devuelve igualmente el próximo estado calculado para que el hook
    // pueda reflejarlo en memoria sin perder el registro actual.
    const result = writeDoc(storage, next);
    return { records: next.map(toPublicRecord), persisted: result.ok };
  }

  function clearCredential(rememberRuns, runId) {
    const storage = activeStorage(rememberRuns);
    const { records } = readDoc(storage);
    const next = records.map((r) => (r.runId === runId ? { ...r, token: null, tokenExpiresAt: null } : r));
    writeDoc(storage, next);
    return next.map(toPublicRecord);
  }

  function remove(rememberRuns, runId) {
    const storage = activeStorage(rememberRuns);
    const { records } = readDoc(storage);
    const next = records.filter((r) => r.runId !== runId);
    writeDoc(storage, next);
    return next.map(toPublicRecord);
  }

  /**
   * Migración al togglear el opt-in: mueve los registros del almacén
   * anterior al nuevo autoritativo y limpia el anterior por completo. El
   * origen gana en conflicto de `runId` (es el más reciente por
   * construcción: el usuario acaba de togglear con ese almacén activo).
   *
   * Transaccional en el sentido que importa aquí — pérdida de datos y
   * persistencia residual del token son los dos fallos que no se pueden
   * permitir:
   *   1. Escribe primero en `to`. Si falla (cuota, storage no
   *      disponible), se detiene ahí: `from` queda intacto, `to` queda
   *      intacto, y se devuelve `ok: false` — el llamador NO debe
   *      cambiar la preferencia ni el estado de React, porque la
   *      migración no ocurrió.
   *   2. Si la escritura reporta éxito, se relee `to` y se verifica que
   *      contiene exactamente los registros esperados (incluido el
   *      `token` de cada uno) antes de tocar `from` — protege contra un
   *      `Storage` que reporte éxito sin persistir de verdad.
   *   3. Solo tras verificar `to` se limpia `from`. Si ese borrado
   *      falla, los datos NO se perdieron (ya están a salvo en `to`),
   *      pero el registro persiste en el almacén que se suponía debía
   *      quedar vacío — se informa `ok: false, reason: "cleanup_failed"`
   *      para que el llamador tampoco declare completado el opt-out
   *      (evita afirmar "ya no se recuerda" mientras un token sigue en
   *      `localStorage`).
   */
  function migrate(nextRememberRuns) {
    const from = activeStorage(!nextRememberRuns);
    const to = activeStorage(nextRememberRuns);
    if (from === to) return { ok: true, records: listPublic(nextRememberRuns) };

    const { records: fromRecords } = readDoc(from);
    const { records: toRecords } = readDoc(to);

    const merged = [...toRecords];
    for (const rec of fromRecords) {
      const idx = merged.findIndex((r) => r.runId === rec.runId);
      if (idx === -1) merged.push(rec);
      else merged[idx] = rec;
    }

    const writeResult = writeDoc(to, merged);
    if (!writeResult.ok) {
      return { ok: false, reason: writeResult.reason, records: listPublic(!nextRememberRuns) };
    }

    const verify = readDoc(to);
    const verified =
      verify.records.length === merged.length &&
      merged.every((rec) => verify.records.some((r) => r.runId === rec.runId && r.token === rec.token));
    if (!verified) {
      return { ok: false, reason: "verification_failed", records: listPublic(!nextRememberRuns) };
    }

    const cleanupResult = writeDoc(from, []);
    if (!cleanupResult.ok) {
      return { ok: false, reason: "cleanup_failed", records: merged.map(toPublicRecord) };
    }

    return { ok: true, records: merged.map(toPublicRecord) };
  }

  /** Limpia el documento y también cualquier copia de diagnóstico de
   * corrupción relacionada — nunca solo `cdd.runs.v1`. */
  function clearAll(rememberRuns) {
    const storage = activeStorage(rememberRuns);
    removeKeysWithPrefix(storage, CORRUPT_KEY_PREFIX);
    return safeRemove(storage, RUNS_STORAGE_KEY);
  }

  return { listPublic, getCredential, upsert, clearCredential, remove, migrate, clearAll };
}
