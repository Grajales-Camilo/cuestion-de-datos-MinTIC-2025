import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DOCUMENT_STORAGE_STATUS,
  loadStoredDocument,
  saveStoredDocument,
} from "../lib/document/documentStorage";
import { validateDocumentModel } from "../lib/document/documentModel";

/**
 * Estado pequeño para UI (F6-01, PARTE 3). `idle` cubre tanto "nada
 * persistido todavía" como "se aisló una copia corrupta/inválida y se
 * decidió abrir un documento nuevo" — ninguno de los dos es un error, y
 * `notice` (ver más abajo) trae el detalle para el aviso no bloqueante.
 */
export const DOCUMENT_AUTOSAVE_STATUS = Object.freeze({
  LOADING: "loading",
  IDLE: "idle",
  SAVING: "saving",
  SAVED: "saved",
  ERROR: "error",
  FUTURE_VERSION: "future_version",
});

const DEFAULT_DEBOUNCE_MS = 5000;

// Referencia de función ESTABLE entre renders (a diferencia de un valor por
// defecto de parámetro escrito inline, que crearía un closure nuevo en cada
// llamada al hook): `persist`/`notifyChange` dependen de `now` — si su
// identidad cambiara en cada render, perderían memoización sin motivo.
function defaultNow() {
  return Date.now();
}

function defaultStorage() {
  return typeof window !== "undefined" ? window.localStorage : null;
}

/**
 * Restaura `cdd.doc.v1` ANTES de habilitar el autoguardado (barrera F6-01,
 * PARTE 2) y después persiste con debounce cada cambio real (PARTE 3). No
 * posee el documento en memoria: expone `restoredDocument` una sola vez,
 * justo tras la restauración, para que el llamador (`pages/app.js`) siembre
 * su propio estado; cada cambio posterior de ese estado se reporta de vuelta
 * llamando a `notifyChange(document)`.
 *
 * La barrera vive en `readyRef`, no en el llamador: `notifyChange` ignora
 * en silencio cualquier llamada anterior a que la restauración termine, y
 * permanece cerrada para siempre si se detecta una versión futura o una
 * migración fallida (esa clave sigue siendo autoritativa; no se sobrescribe).
 *
 * Sobrevive a React Strict Mode: la restauración real ocurre como mucho una
 * vez por instancia de componente (`hasRestoredRef`), aunque React invoque
 * el efecto dos veces en desarrollo; el timer de debounce es único
 * (`timerRef`), y el desmontaje limpia ese timer y vacía de forma síncrona
 * un cambio pendiente sin persistir (navegación fuera de `/app` en la SPA).
 * El cierre real de pestaña/navegador no garantiza que React ejecute esa
 * limpieza — ese caso queda cubierto solo por el debounce ≤5 s, no por el
 * flush de desmontaje.
 */
export function useDocumentAutosave({
  storage = defaultStorage(),
  debounceMs = DEFAULT_DEBOUNCE_MS,
  now = defaultNow,
} = {}) {
  const [state, setState] = useState({
    status: DOCUMENT_AUTOSAVE_STATUS.LOADING,
    restoredDocument: null,
    notice: null, // { reason: "corrupt"|"invalid"|"unavailable"|"future_version"|"migration_failed", raw?, diagnosticKey? } | null
    blockedEnvelope: null, // sobre íntegro sin abrir (future_version / migration_failed), para ofrecer descarga
    error: null,
  });

  const hasRestoredRef = useRef(false);
  const timerRef = useRef(null);
  const lastSerializedRef = useRef(null);
  // Último SOBRE completo persistido con éxito (no solo el `document`): es la
  // única fuente de `createdAt` estable entre autoguardados sucesivos (F6-01
  // PARTE 4). Nunca se reconstruye releyendo `storage` en cada cambio — se
  // actualiza exactamente al restaurar y tras cada escritura EXITOSA.
  const lastPersistedEnvelopeRef = useRef(null);
  const pendingDocumentRef = useRef(null);
  const readyRef = useRef(false);

  // Restauración real: como mucho una vez por instancia, ver docstring.
  useEffect(() => {
    if (hasRestoredRef.current) return;
    hasRestoredRef.current = true;

    const result = loadStoredDocument(storage, { now });

    if (result.status === DOCUMENT_STORAGE_STATUS.OK) {
      lastSerializedRef.current = JSON.stringify(result.document);
      lastPersistedEnvelopeRef.current = result.envelope;
      readyRef.current = true;
      setState({
        status: DOCUMENT_AUTOSAVE_STATUS.SAVED,
        restoredDocument: result.document,
        notice: null,
        blockedEnvelope: null,
        error: null,
      });
      return;
    }

    if (
      result.status === DOCUMENT_STORAGE_STATUS.FUTURE_VERSION ||
      result.status === DOCUMENT_STORAGE_STATUS.MIGRATION_FAILED
    ) {
      // `readyRef` nunca pasa a true en esta rama: `notifyChange` ignorará
      // cambios indefinidamente mientras dure esta sesión de página.
      setState({
        status: DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION,
        restoredDocument: null,
        notice: { reason: result.status },
        blockedEnvelope: result.envelope,
        error: null,
      });
      return;
    }

    // EMPTY, CORRUPT, INVALID o UNAVAILABLE: no hay documento recuperable,
    // pero SÍ se decide explícitamente que no existe uno — el llamador abre
    // un documento libre nuevo y el autoguardado queda habilitado desde ya.
    // Sin sobre anterior: la primera escritura real fijará `createdAt` de
    // cero (ver `persist`/`saveStoredDocument`).
    lastSerializedRef.current = null;
    lastPersistedEnvelopeRef.current = null;
    readyRef.current = true;
    const notice =
      result.status === DOCUMENT_STORAGE_STATUS.CORRUPT || result.status === DOCUMENT_STORAGE_STATUS.INVALID
        ? { reason: result.status, raw: result.raw, diagnosticKey: result.diagnosticKey }
        : result.status === DOCUMENT_STORAGE_STATUS.UNAVAILABLE
          ? { reason: result.status }
          : null;
    setState({
      status: DOCUMENT_AUTOSAVE_STATUS.IDLE,
      restoredDocument: null,
      notice,
      blockedEnvelope: null,
      error: null,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- se ejecuta como mucho una vez de verdad (`hasRestoredRef`); `storage`/`now` son estables por contrato del llamador (igual que `useConsent`).
  }, []);

  const persist = useCallback(
    (document) => {
      setState((previous) => ({ ...previous, status: DOCUMENT_AUTOSAVE_STATUS.SAVING }));
      // `previousEnvelope` es SIEMPRE el último sobre persistido con éxito
      // (o `null` en la primera escritura real): es lo único que le permite
      // a `saveStoredDocument` conservar `createdAt` entre autoguardados
      // sucesivos, sin releer `storage` en cada cambio (F6-01 PARTE 4).
      const result = saveStoredDocument(storage, document, {
        now,
        previousEnvelope: lastPersistedEnvelopeRef.current,
      });
      if (result.ok) {
        lastSerializedRef.current = JSON.stringify(document);
        lastPersistedEnvelopeRef.current = result.envelope;
        pendingDocumentRef.current = null;
        setState((previous) => ({ ...previous, status: DOCUMENT_AUTOSAVE_STATUS.SAVED, error: null }));
      } else {
        // El almacén conserva su último valor válido intacto (`safeWriteJson`
        // nunca escribe parcialmente): no se toca `lastSerializedRef` NI
        // `lastPersistedEnvelopeRef`, así que el próximo cambio real (incluso
        // repetir el mismo contenido que acaba de fallar) vuelve a
        // intentarlo con el mismo `createdAt` de referencia.
        setState((previous) => ({ ...previous, status: DOCUMENT_AUTOSAVE_STATUS.ERROR, error: result.reason }));
      }
      return result;
    },
    [storage, now]
  );

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const notifyChange = useCallback(
    (document) => {
      if (!readyRef.current) return; // barrera load-before-save

      const validation = validateDocumentModel(document);
      if (!validation.ok) {
        pendingDocumentRef.current = null;
        clearTimer();
        setState((previous) => ({ ...previous, status: DOCUMENT_AUTOSAVE_STATUS.ERROR, error: "invalid_document" }));
        return;
      }

      const serialized = JSON.stringify(document);
      if (serialized === lastSerializedRef.current) return; // sin cambios reales: no reescribe

      pendingDocumentRef.current = document;
      clearTimer();
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        const pending = pendingDocumentRef.current;
        if (pending !== null) persist(pending);
      }, debounceMs);
    },
    [clearTimer, debounceMs, persist]
  );

  const dismissNotice = useCallback(() => {
    setState((previous) => ({ ...previous, notice: null }));
  }, []);

  useEffect(
    () => () => {
      clearTimer();
      if (readyRef.current && pendingDocumentRef.current !== null) {
        // Mismo `previousEnvelope` que `persist`: el vaciado de desmontaje
        // tampoco puede fabricar un `createdAt` nuevo.
        saveStoredDocument(storage, pendingDocumentRef.current, {
          now,
          previousEnvelope: lastPersistedEnvelopeRef.current,
        });
        pendingDocumentRef.current = null;
      }
    },
    [clearTimer, storage, now]
  );

  return useMemo(
    () => ({
      status: state.status,
      restoredDocument: state.restoredDocument,
      notice: state.notice,
      blockedEnvelope: state.blockedEnvelope,
      error: state.error,
      isRestoring: state.status === DOCUMENT_AUTOSAVE_STATUS.LOADING,
      notifyChange,
      dismissNotice,
    }),
    [state, notifyChange, dismissNotice]
  );
}
