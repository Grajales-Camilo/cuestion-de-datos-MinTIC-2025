/**
 * Orquestador del stream SSE de una corrida del agente
 * (`contracts/api-rest.md` §3, `docs/frontend-v2/implementation-plan.md`
 * §4.5). Conecta con `fetch()` + `response.body.getReader()` — nunca
 * `EventSource`, que no admite `Authorization` — deduplica y ordena eventos
 * por `id`, detecta huecos, reconecta con backoff ante fallos de transporte,
 * y reconcilia contra `GET /v2/agent/runs/{run_id}` cuando hizo falta.
 *
 * No decodifica texto por su cuenta: cada `value` del reader se entrega tal
 * cual (`Uint8Array`) a un `parseSseChunk.js` nuevo por conexión, que es el
 * único dueño del `TextDecoder`.
 *
 * Forma de `onStatus` (siempre estable, nunca datos sensibles; cualquier
 * `error` incluido es un `ApiError` ya redactado):
 *   { type: "connecting" }
 *   { type: "streaming", lastEventId }
 *   { type: "heartbeat" }
 *   { type: "gap", expected, received }
 *   { type: "reconnecting", attempt, delayMs, lastEventId }
 *   { type: "reconciling" }
 *   { type: "terminal", event }
 *   { type: "detached" }
 *   { type: "disconnected", attempts }
 *   { type: "transport_error", error }
 *
 * Forma del valor resuelto (decisión propia, no dictada por ningún
 * documento: el reducer futuro decide cómo consumirla):
 *   {
 *     finalStatus: "terminal" | "disconnected" | "detached" | "client_error",
 *     terminalEvent?: Event,   // solo si finalStatus === "terminal"
 *     error?: ApiError,        // solo si finalStatus === "client_error"
 *     lastEventId: number,
 *     attempts: number,
 *     reconciliation: null | { ok: true, run } | { ok: false, error },
 *   }
 *
 * `reconciliation` también se adjunta cuando `finalStatus === "disconnected"`
 * (si hubo al menos una reconexión o un hueco de secuencia) — nunca cuando
 * `finalStatus === "detached"` ni `"client_error"`.
 *
 * `random` (por defecto `Math.random`) alimenta el jitter del backoff:
 * `jitter = floor(random() * 100)`, siempre acotado a un entero >= 0 aunque
 * `random` devuelva algo patológico (NaN, negativo, Infinity). `now` se
 * conserva en la firma por compatibilidad aditiva; el jitter ya no lo usa.
 */
import { createSseParser } from "./parseSseChunk.js";
import { createAgentClient } from "../api/agentClient.js";
import { apiErrorFromEnvelope, networkApiError } from "../api/errors.js";

const HEARTBEAT_TIMEOUT_MS = 45000;
const BACKOFF_SCHEDULE_MS = [500, 1000, 2000, 4000, 8000, 8000];
const MAX_RETRIES = 6;
const NON_RETRYABLE_STATUSES = new Set([401, 404, 422]);
const JITTER_RANGE_MS = 100;

function isAbortError(error) {
  return Boolean(error) && error.name === "AbortError";
}

function makeAbortError() {
  const error = new Error("The operation was aborted");
  error.name = "AbortError";
  return error;
}

/** Acepta número o string; solo entero seguro >= 0, si no, `null`. */
function toSafeSeq(value) {
  if (typeof value === "number") {
    return Number.isSafeInteger(value) && value >= 0 ? value : null;
  }
  if (typeof value === "string" && /^\d+$/.test(value)) {
    const n = Number(value);
    return Number.isSafeInteger(n) ? n : null;
  }
  return null;
}

async function tryParseJson(response) {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

/**
 * Punto único de liberación del reader: cancela (si corresponde) y SIEMPRE
 * libera el lock en `finally`, incluso si `cancel()` falla o no hacía falta
 * (el productor ya cerró el cuerpo por su cuenta). Se ejecuta en terminal,
 * `done`, error de transporte, heartbeat vencido y abort — nunca deja el
 * `ReadableStream` bloqueado.
 */
async function closeReader(reader, { cancel: shouldCancel } = {}) {
  try {
    if (shouldCancel) {
      await reader.cancel();
    }
  } catch {
    // el cuerpo ya pudo haberse cerrado; no es un fallo real que reportar.
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ya liberado (p. ej. por el propio cancel() en algún entorno).
    }
  }
}

/** `jitter = floor(random() * 100)`, siempre un entero finito >= 0. */
function safeJitter(random) {
  const raw = Math.floor(random() * JITTER_RANGE_MS);
  return Number.isFinite(raw) && raw > 0 ? raw : 0;
}

/** Espera cancelable: rechaza de inmediato con AbortError si `signal` dispara. */
function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(makeAbortError());
      return;
    }
    const timer = setTimeout(() => {
      cleanup();
      resolve();
    }, ms);
    function onAbort() {
      cleanup();
      reject(makeAbortError());
    }
    function cleanup() {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * `reader.read()` con dos carreras: un timeout de heartbeat y la señal de
 * cancelación. Nunca deja el timer colgado tras resolver.
 */
function readWithHeartbeat(reader, timeoutMs, signal) {
  return new Promise((resolve, reject) => {
    let settled = false;

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve({ heartbeatExpired: true });
    }, timeoutMs);

    function onAbort() {
      if (settled) return;
      settled = true;
      cleanup();
      reject(makeAbortError());
    }

    function cleanup() {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }

    if (signal?.aborted) {
      onAbort();
      return;
    }
    signal?.addEventListener("abort", onAbort, { once: true });

    reader.read().then(
      (result) => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve({ heartbeatExpired: false, done: result.done, value: result.value });
      },
      (error) => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(error);
      }
    );
  });
}

export async function streamRun({
  baseUrl,
  runId,
  token,
  lastEventId,
  onEvent,
  onStatus,
  signal,
  fetchImpl = fetch,
  // eslint-disable-next-line no-unused-vars -- aceptado por compatibilidad aditiva de la API; el jitter ahora usa `random`, no `now`.
  now = Date.now,
  random = Math.random,
}) {
  let lastSeq = toSafeSeq(lastEventId) ?? 0;
  let hadReconnect = false;
  let hadGap = false;
  let attempts = 0;

  /** true si `event` era terminal (answer/error). Aplica dedupe/hueco/entrega. */
  function noteEvent(event) {
    const seq = toSafeSeq(event.id);
    const isTerminalType = event.event === "answer" || event.event === "error";

    if (seq === null) {
      // Violación controlada del stream (evento normal sin id válido): no
      // avanza lastSeq, no lanza, pero tampoco se descarta el dato en silencio.
      onEvent(event);
      return isTerminalType;
    }
    if (seq <= lastSeq) {
      return false; // duplicado: se descarta sin llamar onEvent
    }
    if (seq > lastSeq + 1) {
      onStatus({ type: "gap", expected: lastSeq + 1, received: seq });
      hadGap = true;
    }
    lastSeq = seq;
    onEvent(event);
    return isTerminalType;
  }

  /** Devuelve el evento terminal si aparece en `events`, si no `null`. */
  function processEvents(events) {
    for (const event of events) {
      if (event.comment) {
        onStatus({ type: "heartbeat" });
        continue;
      }
      if (event.incomplete) {
        // Un resto incompleto de flush() no es un evento válido; se ignora
        // aquí y la conexión se clasifica como condición de transporte por
        // el llamador (ver manejo de `done` más abajo).
        continue;
      }
      if (noteEvent(event)) return event;
    }
    return null;
  }

  async function attemptConnection() {
    if (signal?.aborted) return { kind: "aborted" };

    const url = `${baseUrl}/v2/agent/stream/${encodeURIComponent(runId)}`;
    const headers = {
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    };
    if (lastSeq > 0) headers["Last-Event-ID"] = String(lastSeq);

    let response;
    try {
      response = await fetchImpl(url, { headers, signal });
    } catch (error) {
      if (isAbortError(error)) return { kind: "aborted" };
      return { kind: "retry", reason: networkApiError(error) };
    }

    if (!response.ok) {
      const body = await tryParseJson(response);
      const apiError =
        body !== undefined
          ? apiErrorFromEnvelope(response.status, body)
          : networkApiError(`respuesta ${response.status} sin cuerpo JSON interpretable`);

      if (NON_RETRYABLE_STATUSES.has(response.status)) {
        throw apiError;
      }
      return { kind: "retry", reason: apiError };
    }

    if (!response.body) {
      return { kind: "retry", reason: networkApiError("la respuesta no incluyó cuerpo de stream") };
    }

    onStatus({ type: "streaming", lastEventId: lastSeq });

    const reader = response.body.getReader();
    const parser = createSseParser();
    let cancelOnExit = true; // false únicamente cuando el productor ya cerró (`done`)

    try {
      while (true) {
        if (signal?.aborted) {
          return { kind: "aborted" };
        }

        let readResult;
        try {
          readResult = await readWithHeartbeat(reader, HEARTBEAT_TIMEOUT_MS, signal);
        } catch (error) {
          if (isAbortError(error)) return { kind: "aborted" };
          return { kind: "retry", reason: networkApiError(error) };
        }

        if (readResult.heartbeatExpired) {
          return {
            kind: "retry",
            reason: networkApiError("se agotó el tiempo de espera del heartbeat (45s)"),
          };
        }

        if (readResult.done) {
          cancelOnExit = false; // el cuerpo ya se cerró por su cuenta: nada que cancelar
          const flushed = parser.flush();
          const hadIncomplete = flushed.some((event) => event.incomplete);
          const terminal = processEvents(flushed);
          if (terminal) return { kind: "terminal", event: terminal };
          return {
            kind: "retry",
            reason: networkApiError(
              hadIncomplete
                ? "el flujo terminó con datos incompletos sin un evento terminal"
                : "el flujo se cerró sin un evento terminal"
            ),
          };
        }

        const events = parser.push(readResult.value);
        const terminal = processEvents(events);
        if (terminal) {
          return { kind: "terminal", event: terminal };
        }
      }
    } finally {
      await closeReader(reader, { cancel: cancelOnExit });
    }
  }

  /**
   * `GET /v2/agent/runs/{runId}` solo si hubo al menos una reconexión o un
   * hueco de secuencia; nunca tras `detached`, nunca para 401/404/422
   * iniciales (esos ni siquiera llegan a llamar esta función).
   */
  async function maybeReconcile() {
    if (!hadReconnect && !hadGap) return null;
    onStatus({ type: "reconciling" });
    try {
      const client = createAgentClient({ baseUrl, fetchImpl });
      const run = await client.getRun({ runId, token, signal });
      return { ok: true, run };
    } catch (error) {
      return { ok: false, error };
    }
  }

  onStatus({ type: "connecting" });

  let terminalEvent = null;

  while (true) {
    let result;
    try {
      result = await attemptConnection();
    } catch (error) {
      // ApiError no reintentable (401/404/422): terminal del lado del
      // cliente, de inmediato — nunca se convierte en bucle de recuperación.
      onStatus({ type: "transport_error", error });
      return {
        finalStatus: "client_error",
        error,
        lastEventId: lastSeq,
        attempts,
        reconciliation: null,
      };
    }

    if (result.kind === "terminal") {
      terminalEvent = result.event;
      break;
    }

    if (result.kind === "aborted") {
      onStatus({ type: "detached" });
      return {
        finalStatus: "detached",
        lastEventId: lastSeq,
        attempts,
        reconciliation: null, // nunca se reconcilia tras un detached
      };
    }

    // result.kind === "retry"
    hadReconnect = true;
    onStatus({ type: "transport_error", error: result.reason });
    attempts += 1;
    if (attempts > MAX_RETRIES) {
      const reconciliation = await maybeReconcile();
      onStatus({ type: "disconnected", attempts: MAX_RETRIES });
      return {
        finalStatus: "disconnected",
        lastEventId: lastSeq,
        attempts: MAX_RETRIES,
        reconciliation,
      };
    }

    const baseDelay = BACKOFF_SCHEDULE_MS[Math.min(attempts - 1, BACKOFF_SCHEDULE_MS.length - 1)];
    const delayMs = baseDelay + safeJitter(random);
    onStatus({ type: "reconnecting", attempt: attempts, delayMs, lastEventId: lastSeq });

    try {
      await sleep(delayMs, signal);
    } catch {
      onStatus({ type: "detached" });
      return {
        finalStatus: "detached",
        lastEventId: lastSeq,
        attempts,
        reconciliation: null,
      };
    }
  }

  onStatus({ type: "terminal", event: terminalEvent });

  const reconciliation = await maybeReconcile();

  return {
    finalStatus: "terminal",
    terminalEvent,
    lastEventId: lastSeq,
    attempts,
    reconciliation,
  };
}
