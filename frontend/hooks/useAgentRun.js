import { useCallback, useEffect, useReducer, useRef } from "react";
import { runReducer } from "../lib/agent/runReducer";
import { createInitialRunState, isTerminalRunStatus } from "../lib/agent/runStates";
import { normalizeSectionId } from "../lib/agent/sectionId";
import { createAgentClient } from "../lib/api/agentClient";
import { streamRun as defaultStreamRun } from "../lib/sse/streamRun";

/**
 * Integra los módulos puros ya existentes (`agentClient`, `streamRun`,
 * `runReducer`) con React — no reimplementa ninguno de los tres. Es la
 * única fuente de verdad del estado de una corrida activa.
 *
 * Contrato:
 *   useAgentRun({ baseUrl, consentGranted, agentClient?, streamRunner?, onLifecycle? })
 *     → { state, start({ question, contextHint, sectionId }), resume({ runId, token, lastSeq, sectionId }), detach(), reset() }
 *
 * `sectionId` (F5-03A-R1) es un metadato cliente-only: nunca se envía al
 * backend (`agentClient.startRun` lo ignora), solo vive en `state.sectionId`
 * y en el evento `created`. Es la ÚNICA fuente de verdad para saber a qué
 * sección del documento pertenece la corrida actualmente presentada —
 * ningún estado global fuera de este hook debe sustituirla.
 *
 * `onLifecycle(event)` es la única frontera de salida hacia el exterior
 * (F3-7B, `useRunHistory`): notifica, sin persistir nada por sí misma,
 * - { type: "created", runId, token, tokenExpiresAt, question, contextHint, sectionId }
 * - { type: "seq", runId, seq }
 * - { type: "status", runId, status }
 * - { type: "terminal", runId, status }
 * - { type: "invalid", runId, httpStatus, code }
 * Los tres últimos se derivan declarativamente de `state` (efectos que
 * comparan con el valor anterior), nunca duplicando la lógica de
 * transición que ya vive en `runReducer`. Solo "created" e "invalid" se
 * emiten imperativamente, porque dependen del token o de un error que
 * nunca entra al reducer. El hook sigue sin escribir en
 * `sessionStorage`/`localStorage`: eso es responsabilidad exclusiva de
 * quien consume `onLifecycle`.
 *
 * Invariantes duros de este incremento:
 * - `useReducer(runReducer)` es la única máquina de estado real; el único
 *   añadido local es `LOCAL_RESET`, un action type que nunca sale de este
 *   archivo y que runReducer ni conoce ni necesita conocer (no se toca
 *   `lib/agent/runReducer.js`).
 * - `start()` se niega antes de cualquier POST si `consentGranted !== true`.
 * - `resume()` nunca llama `startRun` (POST): reconecta una corrida ya
 *   existente con su token y su `lastSeq` guardados — "no reinicia el
 *   trabajo del agente".
 * - El token de la corrida y el `AbortController` viven únicamente en
 *   refs: nunca entran al reducer, nunca a un `dispatch`, nunca a
 *   `console.*`. La única salida transitoria del token es el argumento de
 *   `onLifecycle({type:"created", token, ...})`, que nunca forma parte del
 *   valor `state` devuelto por este hook.
 * - `detach()` aborta el transporte local; nunca llama `deleteRun` (RF-209:
 *   desconectar no interrumpe la corrida en el servidor).
 * - Cleanup al desmontar aborta la lectura en curso y usa un guard
 *   (`mountedRef`) para que ningún `dispatch` posterior al desmontaje
 *   intente actualizar React.
 */

const LOCAL_RESET = "LOCAL_RESET";

function localReducer(state, action) {
  if (action.type === LOCAL_RESET) {
    return createInitialRunState({ question: "" });
  }
  return runReducer(state, action);
}

/**
 * Construye el mismo evento `{event:"error", json:{error:{...}}}` que
 * produciría el backend, a partir de un `ApiError` ya resuelto localmente
 * (fallo del POST inicial, un `getRun` fallido en `resume()`, o un
 * `finalStatus: "client_error"` de `streamRun` — 401/404/422 no
 * reintentables). Reutiliza `reduceErrorEvent` del reducer real vía la
 * acción `SSE_EVENT` estándar, en vez de inventar una acción nueva para un
 * caso que el reducer ya sabe modelar. `status` decide `interrupted` vs.
 * `failed`: un fallo de arranque o de transporte no reintentable siempre
 * es `failed` — nunca se inventa `interrupted`, que el contrato reserva
 * para el servidor.
 */
function syntheticErrorEvent(apiError, seq) {
  return {
    id: String(seq),
    event: "error",
    json: {
      error: {
        code: apiError.code,
        status: "failed",
        message_user: apiError.messageUser,
        message_dev: apiError.messageDev,
        retryable: apiError.retryable,
      },
    },
  };
}

export function useAgentRun({
  baseUrl,
  consentGranted,
  agentClient,
  streamRunner = defaultStreamRun,
  onLifecycle,
}) {
  const [state, dispatch] = useReducer(localReducer, undefined, () => createInitialRunState({ question: "" }));

  const clientRef = useRef(null);
  if (clientRef.current === null) {
    clientRef.current = agentClient ?? createAgentClient({ baseUrl });
  }

  const mountedRef = useRef(true);
  const abortControllerRef = useRef(null);
  const tokenRef = useRef(null); // nunca leído fuera de este hook, nunca despachado
  const startInFlightRef = useRef(false);

  const onLifecycleRef = useRef(onLifecycle);
  useEffect(() => {
    onLifecycleRef.current = onLifecycle;
  });

  const notify = useCallback((event) => {
    onLifecycleRef.current?.(event);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, []);

  const safeDispatch = useCallback((action) => {
    if (!mountedRef.current) return;
    dispatch(action);
  }, []);

  // "último seq confirmado" y "cambio de estado"/"estado terminal": se
  // derivan de `state`, nunca se recalculan a mano en cada punto de
  // despacho — un solo lugar que compara con el valor anterior evita que
  // `start()` y `resume()` dupliquen la misma lógica de notificación.
  const prevLastSeqRef = useRef(state.lastSeq);
  useEffect(() => {
    if (state.lastSeq === prevLastSeqRef.current) return;
    prevLastSeqRef.current = state.lastSeq;
    notify({ type: "seq", runId: state.runId, seq: state.lastSeq });
  }, [state.lastSeq, state.runId, notify]);

  const prevStatusRef = useRef(state.status);
  useEffect(() => {
    if (state.status === prevStatusRef.current) return;
    prevStatusRef.current = state.status;
    notify({ type: "status", runId: state.runId, status: state.status });
    if (isTerminalRunStatus(state.status)) {
      notify({ type: "terminal", runId: state.runId, status: state.status });
    }
  }, [state.status, state.runId, notify]);

  const notifyIfInvalid = useCallback(
    (runId, apiError) => {
      if (apiError && (apiError.httpStatus === 401 || apiError.httpStatus === 404)) {
        notify({ type: "invalid", runId, httpStatus: apiError.httpStatus, code: apiError.code });
      }
    },
    [notify]
  );

  /**
   * Fase compartida por `start()` y `resume()`: llama a `streamRunner` y
   * traduce su resultado a acciones del reducer. Ninguna de las dos
   * llamadas necesita repetir esta rama — la única diferencia entre ambas
   * es cómo se obtiene `runId`/`token` antes de llegar aquí.
   */
  const runStreamPhase = useCallback(
    async ({ runId, token, lastEventId, controller }) => {
      const result = await streamRunner({
        baseUrl,
        runId,
        token,
        lastEventId,
        onEvent: (event) => {
          safeDispatch({ type: "SSE_EVENT", event, at: Date.now() });
        },
        onStatus: (status) => {
          if (status.type === "heartbeat") {
            safeDispatch({ type: "SSE_HEARTBEAT", at: Date.now() });
          } else if (status.type === "reconnecting") {
            safeDispatch({
              type: "SSE_RECONNECTING",
              attempt: status.attempt,
              delayMs: status.delayMs,
              at: Date.now(),
            });
          } else if (status.type === "disconnected") {
            safeDispatch({ type: "SSE_DISCONNECTED", at: Date.now() });
          }
          // connecting/streaming/gap/reconciling/terminal/detached/transport_error
          // no tienen una acción 1:1 en el reducer — se resuelven abajo, a
          // partir del valor final de streamRunner().
        },
        signal: controller.signal,
      });

      if (!mountedRef.current) return;

      if (result.finalStatus === "terminal") {
        safeDispatch({ type: "SSE_EVENT", event: result.terminalEvent, at: Date.now() });
        if (result.reconciliation?.ok) {
          safeDispatch({ type: "RUN_RECONCILED", run: result.reconciliation.run, at: Date.now() });
        }
      } else if (result.finalStatus === "disconnected") {
        // onStatus ya despachó SSE_DISCONNECTED; aquí solo se aplica la
        // reconciliación defensiva si streamRun la obtuvo.
        if (result.reconciliation?.ok) {
          safeDispatch({ type: "RUN_RECONCILED", run: result.reconciliation.run, at: Date.now() });
        }
      } else if (result.finalStatus === "detached") {
        safeDispatch({ type: "RUN_DETACHED", at: Date.now() });
      } else if (result.finalStatus === "client_error") {
        notifyIfInvalid(runId, result.error);
        safeDispatch({
          type: "SSE_EVENT",
          event: syntheticErrorEvent(result.error, result.lastEventId + 1),
          at: Date.now(),
        });
      }
    },
    [baseUrl, safeDispatch, streamRunner, notifyIfInvalid]
  );

  const start = useCallback(
    async ({ question, contextHint, sectionId: rawSectionId = null } = {}) => {
      if (consentGranted !== true) return; // se niega antes de cualquier POST
      if (startInFlightRef.current) return; // una acción de usuario -> un POST

      // F5-03A-R2: se sanea ANTES de tocar el reducer, `notify()` o el
      // transporte — un `sectionId` sensible o inválido nunca llega a
      // `state`, al evento lifecycle `created` ni a `startRun`, sin
      // importar si quien llamó a `start()` es la UI, un `rerun()` sobre
      // un registro manipulado, o una llamada programática directa.
      const sectionId = normalizeSectionId(rawSectionId);

      startInFlightRef.current = true;

      abortControllerRef.current?.abort(); // guardia de un solo stream activo
      const controller = new AbortController();
      abortControllerRef.current = controller;
      tokenRef.current = null;

      // Feedback visual inmediato (RNF-008): se despacha antes de cualquier
      // `await`, en el mismo tick de la llamada. `sectionId` entra al
      // reducer aquí — un `startRun` que falla antes de obtener `runId`
      // nunca deja una asociación falsa: `RUN_REQUESTED` ya reinicia
      // `runId` a `null` (createInitialRunState), así que no hay ningún
      // `runId` presentable al que ese `sectionId` pudiera asociarse por
      // error.
      safeDispatch({ type: "RUN_REQUESTED", question, contextHint, sectionId, at: Date.now() });

      try {
        let created;
        try {
          created = await clientRef.current.startRun({ question, contextHint, signal: controller.signal });
        } catch (error) {
          if (error?.name === "AbortError") return;
          safeDispatch({ type: "SSE_EVENT", event: syntheticErrorEvent(error, 0), at: Date.now() });
          return;
        }

        if (controller.signal.aborted) return;
        tokenRef.current = created.token;
        safeDispatch({ type: "RUN_CREATED", runId: created.runId, sectionId, at: Date.now() });
        notify({
          type: "created",
          runId: created.runId,
          token: created.token,
          tokenExpiresAt: created.tokenExpiresAt ?? null,
          question,
          contextHint: contextHint ?? null,
          sectionId,
        });

        await runStreamPhase({ runId: created.runId, token: created.token, lastEventId: undefined, controller });
      } finally {
        startInFlightRef.current = false;
      }
    },
    [consentGranted, safeDispatch, notify, runStreamPhase]
  );

  /**
   * Reconecta una corrida ya existente con su token y su `lastSeq`
   * guardados — nunca llama `startRun`. Primero reconcilia contra
   * `GET /v2/agent/runs/{runId}` para saber si ya terminó mientras la
   * pestaña estaba cerrada (en cuyo caso no hay nada que transmitir) o si
   * sigue `running` (en cuyo caso continúa el stream desde `lastSeq`).
   *
   * `sectionId` se pasa explícito tanto a `RUN_CREATED` como a
   * `RUN_RECONCILED`, incluso si es `null`: reconstruye la asociación
   * runId→sectionId de la corrida que se reanuda. Pasarlo en las DOS
   * acciones (no solo en `RUN_CREATED`) es necesario porque `resume()` se
   * llama a menudo con el estado ACTUAL ya en un status terminal (p. ej.
   * tras reanudar una corrida distinta que ya completó) — la guarda de
   * transición del reducer (`ALLOWED_FROM_TERMINAL`) descarta `RUN_CREATED`
   * desde un terminal, así que solo `RUN_RECONCILED` (que sí está
   * permitido desde un terminal) llega a aplicarse; su reducer deriva
   * `sectionId` de la acción exactamente igual que ya deriva `runId` de
   * `run.run_id`, nunca solo de `state.sectionId` (F5-03A-R1).
   */
  const resume = useCallback(
    async ({ runId, token, lastSeq, sectionId: rawSectionId = null } = {}) => {
      if (!runId || !token) return;
      if (startInFlightRef.current) return;

      // F5-03A-R2: mismo saneado que `start()`, antes de cualquier
      // `dispatch`. Aunque `resumeRun` de `useRunHistory` ya normaliza su
      // propio argumento, `resume()` es una API pública de este hook y
      // puede llamarse programáticamente con cualquier valor.
      const sectionId = normalizeSectionId(rawSectionId);

      startInFlightRef.current = true;
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;
      tokenRef.current = token;

      try {
        let run;
        try {
          run = await clientRef.current.getRun({ runId, token, signal: controller.signal });
        } catch (error) {
          if (error?.name === "AbortError") return;
          notifyIfInvalid(runId, error);
          safeDispatch({
            type: "SSE_EVENT",
            event: syntheticErrorEvent(error, (typeof lastSeq === "number" ? lastSeq : 0) + 1),
            at: Date.now(),
          });
          return;
        }

        if (controller.signal.aborted) return;

        safeDispatch({ type: "RUN_CREATED", runId, sectionId, at: Date.now() });
        safeDispatch({ type: "RUN_RECONCILED", run, sectionId, at: Date.now() });

        if (run.status !== "running") return; // ya terminó: nada que transmitir

        await runStreamPhase({
          runId,
          token,
          lastEventId: typeof lastSeq === "number" ? lastSeq : run.last_event_seq,
          controller,
        });
      } finally {
        startInFlightRef.current = false;
      }
    },
    [safeDispatch, notifyIfInvalid, runStreamPhase]
  );

  /** Abort local: nunca DELETE (RF-209, desconectar no interrumpe la corrida). */
  const detach = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    abortControllerRef.current?.abort();
    tokenRef.current = null;
    startInFlightRef.current = false;
    safeDispatch({ type: LOCAL_RESET });
  }, [safeDispatch]);

  return { state, start, resume, detach, reset };
}
