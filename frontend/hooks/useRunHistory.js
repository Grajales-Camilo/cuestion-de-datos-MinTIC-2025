import { useCallback, useMemo, useRef, useState } from "react";
import { createRunsStore } from "../lib/session/runsStore";
import { readRememberRuns, writeRememberRuns } from "../lib/session/rememberPreference";
import { createAgentClient } from "../lib/api/agentClient";
import { normalizeSectionId } from "../lib/agent/sectionId";

function defaultStorages() {
  if (typeof window === "undefined") return { sessionStorage: null, localStorage: null };
  return { sessionStorage: window.sessionStorage, localStorage: window.localStorage };
}

/** Traducción de `status` (cliente o del `GET /runs/{id}` crudo) a un
 * resumen en español claro para la superficie primaria del historial —
 * nunca un enum crudo (RNF-012). */
const STATUS_SUMMARY_ES = {
  idle: "Sin iniciar",
  creating: "Iniciando…",
  streaming: "En curso",
  running: "En curso",
  reconnecting: "Reconectando…",
  disconnected: "Sin conexión",
  detached: "Dejaste de seguirla",
  completed: "Completada",
  no_evidence: "Sin evidencia",
  interrupted: "Interrumpida",
  failed: "Fallida",
  deleted: "Borrada",
};

function summaryFor(status) {
  return STATUS_SUMMARY_ES[status] ?? "Estado desconocido";
}

/**
 * Historial de investigaciones de la sesión (RF-502) más el almacén de
 * credenciales (D-1, RF-801). No conoce `runReducer` ni `streamRun`: solo
 * traduce las notificaciones de `useAgentRun({ onLifecycle })` — recibidas
 * a través de `handleAgentLifecycle`, que el llamador conecta explícitamente
 * — a escrituras de `lib/session/runsStore.js`. `startRun`/`resumeRunTransport`
 * son las únicas dos funciones inyectadas para "reejecutar" y "reanudar":
 * este hook nunca llama `fetch` directamente ni conoce `agentClient` más
 * allá de `deleteRun`.
 */
export function useRunHistory({
  baseUrl,
  agentClient,
  startRun,
  resumeRunTransport,
  sessionStorage,
  localStorage,
} = {}) {
  const storages = useMemo(() => {
    const defaults = defaultStorages();
    return {
      sessionStorage: sessionStorage ?? defaults.sessionStorage,
      localStorage: localStorage ?? defaults.localStorage,
    };
  }, [sessionStorage, localStorage]);

  const store = useMemo(() => createRunsStore(storages), [storages]);
  const client = useMemo(() => agentClient ?? createAgentClient({ baseUrl }), [agentClient, baseUrl]);

  const [rememberRuns, setRememberRunsState] = useState(() => readRememberRuns(storages.localStorage));
  const [runs, setRuns] = useState(() => store.listPublic(rememberRuns));

  const refreshRuns = useCallback(
    (remember = rememberRuns) => {
      setRuns(store.listPublic(remember));
    },
    [store, rememberRuns]
  );

  /**
   * Cambia el opt-in: migra los registros del almacén anterior al nuevo
   * (nunca duplica) y SOLO si `store.migrate` confirma éxito verificado
   * persiste la preferencia y actualiza el estado de React. Si la
   * migración falla (cuota agotada, storage no disponible, o el borrado
   * del origen no se pudo completar), la preferencia y el estado
   * previos se conservan íntegros — nunca se declara "ya no se
   * recuerda" mientras un token pudiera seguir en `localStorage`.
   */
  const setRememberRuns = useCallback(
    (next) => {
      const boolNext = Boolean(next);
      const result = store.migrate(boolNext);
      if (!result.ok) {
        return { ok: false, reason: result.reason };
      }
      writeRememberRuns(storages.localStorage, boolNext);
      setRememberRunsState(boolNext);
      setRuns(result.records);
      return { ok: true };
    },
    [store, storages.localStorage]
  );

  /**
   * Frontera de entrada desde `useAgentRun({ onLifecycle })`. Traducción
   * pura de notificaciones de transporte a escrituras del store — nunca
   * contiene lógica de reducer, de streaming ni de `fetch`.
   */
  const handleAgentLifecycle = useCallback(
    (event) => {
      if (!event || typeof event.type !== "string" || !event.runId) return;

      if (event.type === "created") {
        store.upsert(rememberRuns, {
          runId: event.runId,
          token: event.token,
          tokenExpiresAt: event.tokenExpiresAt ?? null,
          question: event.question ?? "",
          contextHint: event.contextHint ?? null,
          // Metadato público (F5-03A-R1): nunca viaja junto al token en
          // ningún objeto propio de este hook — `getCredential` (el único
          // método de `runsStore` que expone el token) no lo conoce ni lo
          // necesita; `resumeRun` lo lee por separado de `runs` (saneado).
          // `normalizeSectionId` (F5-03A-R2) es redundante con el saneado
          // que `runsStore.upsert` ya aplica al escribir — deliberado: esta
          // es la frontera de entrada del evento lifecycle, y no depende de
          // que la implementación interna del store siga saneando mañana.
          sectionId: normalizeSectionId(event.sectionId),
          status: "streaming",
          summary: summaryFor("streaming"),
          lastEventId: 0,
        });
        refreshRuns();
        return;
      }

      if (event.type === "seq") {
        store.upsert(rememberRuns, { runId: event.runId, lastEventId: event.seq });
        refreshRuns();
        return;
      }

      if (event.type === "status" || event.type === "terminal") {
        store.upsert(rememberRuns, { runId: event.runId, status: event.status, summary: summaryFor(event.status) });
        refreshRuns();
        return;
      }

      if (event.type === "invalid") {
        if (event.httpStatus === 404) {
          // RUN_NOT_FOUND: la corrida ya no existe en el servidor — el
          // registro local se retira por completo, nunca solo el token.
          store.remove(rememberRuns, event.runId);
        } else {
          // 401: la credencial dejó de servir, pero no equivale a "la
          // corrida se borró" — solo se limpia el token.
          store.clearCredential(rememberRuns, event.runId);
        }
        refreshRuns();
      }
    },
    [store, rememberRuns, refreshRuns]
  );

  const rerun = useCallback(
    (runId) => {
      const record = runs.find((r) => r.runId === runId);
      if (!record || typeof startRun !== "function") return;
      // Nueva corrida: nunca reutiliza runId ni token del registro anterior.
      // Conserva la sección original tal como quedó registrada; si esa
      // sección ya no existe en el documento actual, la inserción de
      // evidencia de la corrida nueva falla cerrada más adelante (nunca se
      // valida la existencia aquí — este hook no conoce el documento).
      // `normalizeSectionId` (F5-03A-R2): `record` viene de `runs`, que ya
      // debería estar saneado por `runsStore.listPublic` — se reafirma aquí
      // igualmente, porque esta es la frontera donde `sectionId` entra al
      // argumento de `startRun` (→ `useAgentRun.start` → `state`).
      startRun({
        question: record.question,
        contextHint: record.contextHint ?? undefined,
        sectionId: normalizeSectionId(record.sectionId),
      });
    },
    [runs, startRun]
  );

  /** Precarga pregunta/contexto para editar antes de un nuevo envío — no
   * llama `startRun` por sí solo. */
  const refine = useCallback(
    (runId) => {
      const record = runs.find((r) => r.runId === runId);
      if (!record) return null;
      return { question: record.question, contextHint: record.contextHint ?? "" };
    },
    [runs]
  );

  // Guardia síncrona (ref, no estado) para que dos clics consecutivos antes
  // del primer `await` nunca produzcan dos DELETE del mismo runId.
  const deletingRef = useRef(new Set());
  const [, forceDeletingRerender] = useState(0);

  const isDeletingRun = useCallback((runId) => deletingRef.current.has(runId), []);

  const deleteRun = useCallback(
    async (runId) => {
      if (deletingRef.current.has(runId)) return { ok: false, reason: "already_in_flight" };

      const credential = store.getCredential(rememberRuns, runId);
      if (!credential) {
        // Sin credencial (vencida o ya limpiada por un 401 previo): no hay
        // forma segura de pedir el borrado; se informa sin afirmar éxito.
        return { ok: false, reason: "no_credential" };
      }

      deletingRef.current.add(runId);
      forceDeletingRerender((v) => v + 1);
      try {
        await client.deleteRun({ runId, token: credential.token });
        // 204 o 404 RUN_NOT_FOUND ya se normalizaron a éxito en agentClient.
        store.remove(rememberRuns, runId);
        refreshRuns();
        return { ok: true };
      } catch (error) {
        if (error?.httpStatus === 401) {
          store.clearCredential(rememberRuns, runId);
          refreshRuns();
          return { ok: false, reason: "unauthorized", error };
        }
        // Red o cualquier otro error real: el registro se conserva tal
        // cual estaba, nunca se retira antes de conocer el resultado.
        return { ok: false, reason: "error", error };
      } finally {
        deletingRef.current.delete(runId);
        forceDeletingRerender((v) => v + 1);
      }
    },
    [client, store, rememberRuns, refreshRuns]
  );

  const resumeRun = useCallback(
    (runId) => {
      const credential = store.getCredential(rememberRuns, runId);
      if (!credential || typeof resumeRunTransport !== "function") return;
      // `sectionId` se lee de `runs` (la lista pública que `runsStore`
      // devuelve con `sectionId` ya normalizado fail-closed, F5-03A-R2),
      // NUNCA de `credential` — el token y el `sectionId` nunca conviven en
      // el mismo objeto persistente ni de estado (F5-03A-R1). Se combinan
      // aquí SOLO como argumentos efímeros de esta llamada a
      // `resumeRunTransport`; `normalizeSectionId` se reaplica de todos
      // modos como frontera propia de este hook, no como sustituto del
      // saneado de `runsStore`.
      const record = runs.find((r) => r.runId === runId);
      resumeRunTransport({
        runId,
        token: credential.token,
        lastSeq: typeof credential.lastEventId === "number" ? credential.lastEventId : undefined,
        sectionId: normalizeSectionId(record?.sectionId),
      });
    },
    [store, rememberRuns, resumeRunTransport, runs]
  );

  return {
    runs,
    rememberRuns,
    setRememberRuns,
    rerun,
    refine,
    deleteRun,
    resumeRun,
    isDeletingRun,
    handleAgentLifecycle,
  };
}
