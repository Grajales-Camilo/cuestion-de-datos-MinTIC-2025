import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { streamRun } from "../../lib/sse/streamRun.js";
import { createInitialRunState, RUN_STATUS } from "../../lib/agent/runStates.js";
import { runReducer } from "../../lib/agent/runReducer.js";

/**
 * Prueba de integración PURA de F2: conecta `streamRun` (transporte real,
 * red doble) con `runReducer` (estado real) exactamente como lo haría un
 * futuro hook de React — sin React, sin `fetch` real, sin hooks todavía. El
 * cableado vive únicamente aquí; ni `streamRun.js` ni `runReducer.js` se
 * tocan para esta prueba.
 */

const BASE_URL = "http://localhost:8000";
const TOKEN = "cdt_rt_9f8a7b6c5d4e3f2a1b0c";
const FIXTURE_PATH = path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt");

// Offsets de fin de cada uno de los 10 eventos reales del fixture,
// calculados sobre los bytes crudos (no sobre el string decodificado, para
// no desalinear por los caracteres acentuados).
// [1]:127 [2]:665 [3]:1203 [4]:1730 [5]:2275 [6]:2802 [7]:3342 [8]:3875 [9]:4417 [10]:8907
const END_EVENT_2 = 665;
const END_EVENT_5 = 2275;
const END_EVENT_10 = 8907;

function chunkIrregularly(bytes, pattern = [7, 53, 2, 19, 101, 4, 31, 11]) {
  const chunks = [];
  let i = 0;
  let p = 0;
  while (i < bytes.length) {
    const size = pattern[p % pattern.length];
    chunks.push(bytes.subarray(i, i + size));
    i += size;
    p += 1;
  }
  return chunks;
}

function makeChunkedStream(bytes) {
  let cancelled = false;
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunkIrregularly(bytes)) controller.enqueue(chunk);
      controller.close();
    },
    cancel() {
      cancelled = true;
    },
  });
  return {
    stream,
    get cancelled() {
      return cancelled;
    },
  };
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("integración F2 · streamRun → runReducer (sin React, sin red real)", () => {
  it("procesa el fixture real fragmentado irregularmente, con reconexión y 3 eventos repetidos, sin duplicar pasos", async () => {
    const raw = readFileSync(FIXTURE_PATH);

    // Conexión 1: eventos 1-5 (todos "step", sin terminal) → cierre normal
    // sin terminal, que streamRun ya trata como condición de reconexión.
    const firstStream = makeChunkedStream(raw.subarray(0, END_EVENT_5));
    // Conexión 2 (tras reconectar): eventos 3-10 — repite 3, 4 y 5, y trae
    // los eventos nuevos 6-10 (el último es el "answer" terminal real).
    const secondStream = makeChunkedStream(raw.subarray(END_EVENT_2, END_EVENT_10));

    let streamCalls = 0;
    const fetchCalls = [];
    const fetchImpl = async (url, options) => {
      fetchCalls.push({ url: String(url), options });
      const u = String(url);
      if (u.includes("/v2/agent/stream/")) {
        streamCalls += 1;
        return new Response(streamCalls === 1 ? firstStream.stream : secondStream.stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      if (u.includes("/v2/agent/runs/")) {
        // Reconciliación tras la reconexión: se responde con el estado
        // running real conocido en ese punto (sin inventar campos).
        return jsonResponse(200, { run_id: "e6ae9a62-3394-4eee-b9e4-c76a3adf9582", status: "running" });
      }
      throw new Error(`URL inesperada en el doble de prueba: ${u}`);
    };

    // --- Cableado de la integración (vive solo en esta prueba) ---
    let state = createInitialRunState({ question: "¿Cuál fue el promedio de deserción escolar…?" });
    let clock = 0;
    const tick = () => {
      clock += 1;
      return clock;
    };
    state = runReducer(state, { type: "RUN_REQUESTED", at: tick() });
    state = runReducer(state, {
      type: "RUN_CREATED",
      runId: "e6ae9a62-3394-4eee-b9e4-c76a3adf9582",
      at: tick(),
    });

    const onEvent = (event) => {
      state = runReducer(state, { type: "SSE_EVENT", event, at: tick() });
    };
    const onStatus = (status) => {
      if (status.type === "heartbeat") {
        state = runReducer(state, { type: "SSE_HEARTBEAT", at: tick() });
      } else if (status.type === "reconnecting") {
        state = runReducer(state, {
          type: "SSE_RECONNECTING",
          attempt: status.attempt,
          delayMs: status.delayMs,
          at: tick(),
        });
      } else if (status.type === "disconnected") {
        state = runReducer(state, { type: "SSE_DISCONNECTED", at: tick() });
      }
    };

    const promise = streamRun({
      baseUrl: BASE_URL,
      runId: "e6ae9a62-3394-4eee-b9e4-c76a3adf9582",
      token: TOKEN,
      onEvent,
      onStatus,
      fetchImpl,
      random: () => 0,
    });

    // Un único reintento (backoff de 500 ms) es todo lo que hace falta.
    await vi.advanceTimersByTimeAsync(2000);
    const result = await promise;

    // --- El transporte terminó limpio ---
    expect(result.finalStatus).toBe("terminal");
    expect(result.attempts).toBe(1);
    expect(streamCalls).toBe(2);
    expect(firstStream.cancelled).toBe(false); // se cerró solo (done), no se canceló
    expect(secondStream.stream.locked).toBe(false); // liberado tras el terminal
    expect(vi.getTimerCount()).toBe(0);

    // --- Cero pasos duplicados a pesar de repetir los eventos 3, 4 y 5 ---
    expect(state.steps).toHaveLength(9); // 9 eventos "step" reales, cada uno una sola vez
    const seqsSeen = state.steps.map((s) => s.seq);
    expect(new Set(seqsSeen).size).toBe(seqsSeen.length); // sin duplicados
    expect(seqsSeen).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);

    // --- Estado final: completed, con los datos reales del terminal ---
    expect(state.status).toBe(RUN_STATUS.COMPLETED);
    expect(state.lastSeq).toBe(10);
    expect(state.seenSeqs.size).toBe(10);
    expect(state.claims).toHaveLength(1);
    expect(state.claims[0].label_status).toBe("verified");
    expect(state.evidence).toHaveLength(1);
    expect(state.evidence[0].dataset_id).toBe("ji8i-4anb");

    // --- Se registró la reconexión real ---
    expect(state.reconnect.attempts).toBeGreaterThanOrEqual(1);

    // --- El token nunca aparece en el estado serializado ni en las URLs ---
    for (const call of fetchCalls) expect(call.url).not.toContain(TOKEN);
    const serialized = JSON.stringify(state, (key, value) => (value instanceof Set ? [...value] : value));
    expect(serialized).not.toContain(TOKEN);
    expect(/cdt_rt_[A-Za-z0-9_-]+/.test(serialized)).toBe(false);
  });
});
