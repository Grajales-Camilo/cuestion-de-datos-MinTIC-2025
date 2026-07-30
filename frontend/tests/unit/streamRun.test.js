import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { streamRun } from "../../lib/sse/streamRun.js";

const BASE_URL = "http://localhost:8000";
const TOKEN = "cdt_rt_9f8a7b6c5d4e3f2a1b0c";
const encoder = new TextEncoder();

function sseBytes(text) {
  return encoder.encode(text);
}

/** Stream controlable: se puede encolar/errar/cerrar desde fuera y expone
 * si `cancel()` fue invocado (para verificar liberación del lock). */
function makeControllableStream() {
  let controllerRef;
  let cancelled = false;
  const stream = new ReadableStream({
    start(controller) {
      controllerRef = controller;
    },
    cancel() {
      cancelled = true;
    },
  });
  return {
    stream,
    enqueue: (bytes) => controllerRef.enqueue(bytes),
    close: () => controllerRef.close(),
    error: (err) => controllerRef.error(err),
    get cancelled() {
      return cancelled;
    },
  };
}

function sseResponse(streamHandle, status = 200) {
  return new Response(streamHandle.stream, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorEnvelope(code, retryable = false) {
  return {
    error: {
      code,
      status: "failed",
      message_user: `mensaje seguro para ${code}`,
      message_dev: `detalle técnico ${code}`,
      retryable,
    },
  };
}

/** Un evento completo, ya cerrado: para pruebas donde el cierre limpio del
 * cuerpo (con o sin terminal) es justo lo que se quiere ejercitar. */
function closedStream(text) {
  const handle = makeControllableStream();
  handle.enqueue(sseBytes(text));
  handle.close();
  return handle;
}

/** Un evento entregado SIN cerrar el productor: necesario para comprobar que
 * `streamRun` llama a `reader.cancel()` de verdad — un `cancel()` sobre un
 * stream que el productor ya cerró es un no-op que no dispara el callback
 * `cancel` del origen subyacente (comportamiento nativo verificado). */
function openStream(text) {
  const handle = makeControllableStream();
  handle.enqueue(sseBytes(text));
  return handle;
}

const RUN_RESULT = { run_id: "r1", status: "completed" };

/** Enruta por URL: `/agent/stream/` va a `streamHandler`, `/agent/runs/` a la
 * respuesta de reconciliación (o `runsHandler` si se da). Registra llamadas. */
function routedFetch(streamHandler, runsHandler = () => jsonResponse(200, RUN_RESULT)) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url: String(url), options });
    const u = String(url);
    if (u.includes("/v2/agent/stream/")) return streamHandler(u, options, calls);
    if (u.includes("/v2/agent/runs/")) return runsHandler(u, options, calls);
    throw new Error(`URL inesperada en el doble de prueba: ${u}`);
  };
  fn.calls = calls;
  fn.streamCalls = () => calls.filter((c) => c.url.includes("/v2/agent/stream/"));
  return fn;
}

/** Handler de stream que hace fallar las primeras `failures` conexiones (con
 * `failureResponse`, por defecto un fallo de red) y luego entrega `handle`. */
function failThenSucceed(failures, handle, failureResponse) {
  let seen = 0;
  return () => {
    seen += 1;
    if (seen <= failures) {
      if (failureResponse) return failureResponse();
      throw new TypeError("Failed to fetch");
    }
    return sseResponse(handle);
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("streamRun · transporte y encabezados", () => {
  it("1. envía Authorization: Bearer y Accept: text/event-stream; el token nunca aparece en la URL", async () => {
    const handle = closedStream('id: 1\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImpl = routedFetch((url, options) => {
      expect(url).toBe(`${BASE_URL}/v2/agent/stream/r1`);
      expect(url).not.toContain(TOKEN);
      expect(options.headers.Authorization).toBe(`Bearer ${TOKEN}`);
      expect(options.headers.Accept).toBe("text/event-stream");
      expect(options.headers["Last-Event-ID"]).toBeUndefined();
      return sseResponse(handle);
    });

    const result = await streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
    });

    expect(result.finalStatus).toBe("terminal");
    for (const call of fetchImpl.calls) expect(call.url).not.toContain(TOKEN);
  });

  it("2. Last-Event-ID está ausente en la conexión inicial y presente al reconectar", async () => {
    // La primera conexión entrega el evento 1 y luego el cuerpo se cierra
    // sin terminal (condición real de transporte que dispara reconexión);
    // así lastSeq=1 queda establecido antes de reconectar.
    const first = closedStream('id: 1\nevent: step\ndata: {"n":1}\n\n');
    const second = closedStream('id: 2\nevent: answer\ndata: {"status":"completed"}\n\n');
    let firstHeaders;
    let secondHeaders;
    let seen = 0;
    const fetchImpl = routedFetch((url, options) => {
      seen += 1;
      if (seen === 1) {
        firstHeaders = options.headers;
        return sseResponse(first);
      }
      secondHeaders = options.headers;
      return sseResponse(second);
    });

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
      random: () => 0,
    });

    await vi.advanceTimersByTimeAsync(2000);
    const result = await promise;

    expect(result.finalStatus).toBe("terminal");
    expect(firstHeaders["Last-Event-ID"]).toBeUndefined();
    expect(secondHeaders["Last-Event-ID"]).toBe("1");
    expect(fetchImpl.streamCalls()).toHaveLength(2);
  });

  it("3. lee los chunks Uint8Array del reader mediante el parser existente", async () => {
    const handle = closedStream(
      'id: 1\nevent: step\ndata: {"node":"start"}\n\n' +
        'id: 2\nevent: answer\ndata: {"status":"completed","claims":[]}\n\n'
    );
    const fetchImpl = routedFetch(() => sseResponse(handle));
    const onEvent = vi.fn();

    const result = await streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent,
      onStatus: vi.fn(),
      fetchImpl,
    });

    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent.mock.calls[0][0].json).toEqual({ node: "start" });
    expect(onEvent.mock.calls[1][0].json).toEqual({ status: "completed", claims: [] });
    expect(result.terminalEvent.json.status).toBe("completed");
  });
});

describe("streamRun · secuencia y deduplicación", () => {
  it("4. descarta eventos duplicados sin llamar onEvent", async () => {
    const handle = closedStream(
      'id: 1\nevent: step\ndata: {"n":1}\n\n' +
        'id: 1\nevent: step\ndata: {"n":1}\n\n' + // duplicado exacto
        'id: 2\nevent: answer\ndata: {"status":"completed"}\n\n'
    );
    const fetchImpl = routedFetch(() => sseResponse(handle));
    const onEvent = vi.fn();

    await streamRun({ baseUrl: BASE_URL, runId: "r1", token: TOKEN, onEvent, onStatus: vi.fn(), fetchImpl });

    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent.mock.calls.map((c) => c[0].id)).toEqual(["1", "2"]);
  });

  it("5. detecta un hueco de secuencia, lo entrega y dispara reconciliación", async () => {
    const handle = closedStream(
      'id: 1\nevent: step\ndata: {"n":1}\n\n' +
        'id: 3\nevent: step\ndata: {"n":3}\n\n' + // salta el 2
        'id: 4\nevent: answer\ndata: {"status":"completed"}\n\n'
    );
    const fetchImpl = routedFetch(() => sseResponse(handle));
    const onStatus = vi.fn();

    const result = await streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus,
      fetchImpl,
    });

    expect(onStatus).toHaveBeenCalledWith({ type: "gap", expected: 2, received: 3 });
    expect(result.reconciliation).toEqual({ ok: true, run: RUN_RESULT });
    expect(fetchImpl.calls.some((c) => c.url.includes("/v2/agent/runs/r1"))).toBe(true);
  });

  it("6. un comentario ': ping' actualiza el heartbeat pero no llama onEvent", async () => {
    const handle = closedStream(
      ": ping\n\n" + 'id: 1\nevent: answer\ndata: {"status":"completed"}\n\n'
    );
    const fetchImpl = routedFetch(() => sseResponse(handle));
    const onEvent = vi.fn();
    const onStatus = vi.fn();

    await streamRun({ baseUrl: BASE_URL, runId: "r1", token: TOKEN, onEvent, onStatus, fetchImpl });

    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent.mock.calls[0][0].comment).toBeUndefined();
    expect(onStatus).toHaveBeenCalledWith({ type: "heartbeat" });
  });
});

describe("streamRun · reconexión y backoff", () => {
  it("7. el backoff sigue 500→1000→2000→4000→8000→8000 con reloj falso", async () => {
    const fetchImpl = routedFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    const onStatus = vi.fn();

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus,
      fetchImpl,
      random: () => 0, // jitter controlado a 0 para una aserción exacta
    });

    await vi.advanceTimersByTimeAsync(500 + 1000 + 2000 + 4000 + 8000 + 8000 + 1000);
    const result = await promise;

    expect(result.finalStatus).toBe("disconnected");
    const delays = onStatus.mock.calls
      .filter((c) => c[0].type === "reconnecting")
      .map((c) => c[0].delayMs);
    expect(delays).toEqual([500, 1000, 2000, 4000, 8000, 8000]);
  });

  it("7b. el jitter usa random() y nunca produce un delay negativo o NaN", async () => {
    const fetchImpl = routedFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    const onStatus = vi.fn();

    // random() devuelve 0.995 → jitter = floor(0.995*100) = 99 en cada intento
    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus,
      fetchImpl,
      random: () => 0.995,
    });
    // 6 reintentos × (base + 99 ms de jitter) + margen
    await vi.advanceTimersByTimeAsync(23500 + 6 * 99 + 1000);
    await promise;
    const delays = onStatus.mock.calls
      .filter((c) => c[0].type === "reconnecting")
      .map((c) => c[0].delayMs);
    expect(delays).toEqual([599, 1099, 2099, 4099, 8099, 8099]); // base + 99, nunca negativo ni NaN

    // random() patológico (negativo/NaN/Infinity) nunca debe producir un
    // delay inválido: se acota a jitter=0, y el backoff sigue siendo el base.
    for (const pathological of [() => -5, () => NaN, () => Infinity]) {
      const fetchImpl2 = routedFetch(() => {
        throw new TypeError("Failed to fetch");
      });
      const onStatus2 = vi.fn();
      const promise2 = streamRun({
        baseUrl: BASE_URL,
        runId: "r1",
        token: TOKEN,
        onEvent: vi.fn(),
        onStatus: onStatus2,
        fetchImpl: fetchImpl2,
        random: pathological,
      });
      await vi.advanceTimersByTimeAsync(23500 + 1000);
      await promise2;
      const reconnecting = onStatus2.mock.calls.filter((c) => c[0].type === "reconnecting");
      for (const call of reconnecting) {
        expect(Number.isFinite(call[0].delayMs)).toBe(true);
        expect(call[0].delayMs).toBeGreaterThanOrEqual(0);
      }
      expect(reconnecting.map((c) => c[0].delayMs)).toEqual([500, 1000, 2000, 4000, 8000, 8000]);
    }
  });

  it("8. se detiene tras seis reintentos con estado disconnected, sin bucle infinito, y reconcilia igual", async () => {
    const fetchImpl = routedFetch(() => {
      throw new TypeError("Failed to fetch");
    });

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
      random: () => 0,
    });

    await vi.advanceTimersByTimeAsync(30000);
    const result = await promise;

    expect(result.finalStatus).toBe("disconnected");
    expect(result.attempts).toBe(6);
    expect(fetchImpl.streamCalls()).toHaveLength(7); // 1 inicial + 6 reintentos
    // Hubo reconexiones ⇒ se reconcilia igual, sin dejar de ser "disconnected".
    expect(result.reconciliation).toEqual({ ok: true, run: RUN_RESULT });
    expect(fetchImpl.calls.at(-1).url).toBe(`${BASE_URL}/v2/agent/runs/r1`);
  });

  it("9. 401, 404 y 422 no se reintentan: terminan de inmediato como client_error", async () => {
    for (const [status, code] of [
      [401, "UNAUTHORIZED"],
      [404, "RUN_NOT_FOUND"],
      [422, "VALIDATION_ERROR"],
    ]) {
      const fetchImpl = routedFetch(() => jsonResponse(status, errorEnvelope(code)));
      const result = await streamRun({
        baseUrl: BASE_URL,
        runId: "r1",
        token: TOKEN,
        onEvent: vi.fn(),
        onStatus: vi.fn(),
        fetchImpl,
      });

      expect(result.finalStatus).toBe("client_error");
      expect(result.error.code).toBe(code);
      expect(fetchImpl.calls).toHaveLength(1);
    }
  });

  it("10. un 5xx y un fallo de red sí se reintentan", async () => {
    const handleA = closedStream('id: 1\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImplA = routedFetch(
      failThenSucceed(1, handleA, () => jsonResponse(503, errorEnvelope("SOCRATA_TIMEOUT", true)))
    );
    const promiseA = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl: fetchImplA,
      random: () => 0,
    });
    await vi.advanceTimersByTimeAsync(2000);
    const resultA = await promiseA;
    expect(resultA.finalStatus).toBe("terminal");
    expect(fetchImplA.streamCalls()).toHaveLength(2);

    const handleB = closedStream('id: 1\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImplB = routedFetch(failThenSucceed(1, handleB));
    const promiseB = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl: fetchImplB,
      random: () => 0,
    });
    await vi.advanceTimersByTimeAsync(2000);
    const resultB = await promiseB;
    expect(resultB.finalStatus).toBe("terminal");
    expect(fetchImplB.streamCalls()).toHaveLength(2);
  });
});

describe("streamRun · heartbeat, cancelación y terminales", () => {
  it("11. un timeout de 45s sin bytes cancela el reader y reconecta", async () => {
    const stalled = makeControllableStream(); // nunca encola ni cierra
    const revived = closedStream('id: 1\nevent: answer\ndata: {"status":"completed"}\n\n');
    let seen = 0;
    const fetchImpl = routedFetch(() => {
      seen += 1;
      return seen === 1 ? sseResponse(stalled) : sseResponse(revived);
    });

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
      random: () => 0,
    });

    await vi.advanceTimersByTimeAsync(45000 + 500 + 1000);
    const result = await promise;

    expect(stalled.cancelled).toBe(true);
    expect(stalled.stream.locked).toBe(false);
    expect(result.finalStatus).toBe("terminal");
    expect(fetchImpl.streamCalls()).toHaveLength(2);
  });

  it("12. abortar produce detached sin evento terminal ni DELETE", async () => {
    const stalled = makeControllableStream();
    const fetchImpl = routedFetch(() => sseResponse(stalled));
    const controller = new AbortController();
    const onStatus = vi.fn();

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus,
      fetchImpl,
      signal: controller.signal,
    });

    await vi.advanceTimersByTimeAsync(10);
    controller.abort();
    const result = await promise;

    expect(result.finalStatus).toBe("detached");
    expect(onStatus).toHaveBeenCalledWith({ type: "detached" });
    expect(fetchImpl.calls).toHaveLength(1); // ninguna llamada de reconciliación ni DELETE
    expect(fetchImpl.calls[0].options.method === undefined || fetchImpl.calls[0].options.method === "GET").toBe(
      true
    );
    expect(stalled.cancelled).toBe(true);
    expect(stalled.stream.locked).toBe(false);
  });

  it("13. un evento answer cierra el reader (libera el lock)", async () => {
    // Stream SIN cerrar por el productor: así reader.cancel() es una
    // cancelación real y dispara el callback `cancel` del origen.
    const handle = openStream('id: 1\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImpl = routedFetch(() => sseResponse(handle));

    const result = await streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
    });

    expect(result.terminalEvent.event).toBe("answer");
    expect(handle.cancelled).toBe(true); // callback cancel() del origen
    expect(handle.stream.locked).toBe(false); // releaseLock() en finally
  });

  it("14. un evento error cierra el reader (libera el lock)", async () => {
    const handle = openStream(
      'id: 1\nevent: error\ndata: {"error":{"code":"RUN_TIMEOUT","status":"failed","message_user":"x","message_dev":"y","retryable":false}}\n\n'
    );
    const fetchImpl = routedFetch(() => sseResponse(handle));

    const result = await streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
    });

    expect(result.terminalEvent.event).toBe("error");
    expect(handle.cancelled).toBe(true);
    expect(handle.stream.locked).toBe(false);
  });
});

describe("streamRun · reconciliación, token y limpieza", () => {
  it("15. reconcilia con GET /v2/agent/runs/{runId} tras al menos una reconexión", async () => {
    const handle = closedStream('id: 2\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImpl = routedFetch(failThenSucceed(1, handle));

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
      random: () => 0,
    });
    await vi.advanceTimersByTimeAsync(2000);
    const result = await promise;

    expect(result.finalStatus).toBe("terminal");
    expect(result.reconciliation).toEqual({ ok: true, run: RUN_RESULT });
    expect(fetchImpl.calls.at(-1).url).toBe(`${BASE_URL}/v2/agent/runs/r1`);
  });

  it("16. el token nunca aparece en URLs, estados, errores ni en el resultado final", async () => {
    const handle = closedStream('id: 2\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImpl = routedFetch(
      failThenSucceed(1, handle, () => jsonResponse(503, errorEnvelope("SOCRATA_TIMEOUT", true)))
    );
    const onStatus = vi.fn();

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus,
      fetchImpl,
      random: () => 0,
    });
    await vi.advanceTimersByTimeAsync(2000);
    const result = await promise;

    for (const call of fetchImpl.calls) {
      expect(call.url).not.toContain(TOKEN);
    }
    const statusDump = JSON.stringify(onStatus.mock.calls);
    expect(statusDump).not.toContain(TOKEN);
    expect(JSON.stringify(result)).not.toContain(TOKEN);
  });

  it("17. no deja timers ni locks huérfanos al finalizar", async () => {
    const handle = openStream('id: 1\nevent: answer\ndata: {"status":"completed"}\n\n');
    const fetchImpl = routedFetch(() => sseResponse(handle));

    await streamRun({
      baseUrl: BASE_URL,
      runId: "r1",
      token: TOKEN,
      onEvent: vi.fn(),
      onStatus: vi.fn(),
      fetchImpl,
    });

    expect(handle.cancelled).toBe(true);
    expect(handle.stream.locked).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });
});
