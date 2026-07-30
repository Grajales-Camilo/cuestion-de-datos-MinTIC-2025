import noEvidenceFixture from "../../tests/fixtures/no-evidence.json";
import interruptedFixture from "../../tests/fixtures/interrupted.json";
import failedFixture from "../../tests/fixtures/failed.json";
import completedFixture from "../../tests/fixtures/completed-with-claims.json";

/**
 * Dobles de transporte para la muestra funcional de F3-7A en la galería
 * (`pages/_dev/ui.js`). Ningún escenario hace POST, SSE ni DELETE reales:
 * cada uno es una función `streamRunner`-compatible (misma forma que
 * `lib/sse/streamRun.js`) que reproduce eventos reales ya capturados en
 * `tests/fixtures/` con pausas cortas, para que la ruta central se vea
 * "vivir" sin red. El contenido (pasos, mensajes, cifras) es siempre de
 * una corrida real — nunca inventado; los escenarios de transporte puro
 * (reconectando/desconectado) sintetizan únicamente la SEÑAL de conexión,
 * reutilizando los mismos pasos reales como contenido.
 */

const STEP_DELAY_MS = 550;

function eventFromFixtureEntry(entry) {
  // La forma real de `events[]` en los fixtures (`{seq, event, data}`) es
  // exactamente la forma pre-parseada que produce `parseSseChunk.js`
  // (`{id, event, json}`) salvo el nombre de los campos.
  return { id: String(entry.seq), event: entry.event, json: entry.data };
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      const err = new Error("aborted");
      err.name = "AbortError";
      reject(err);
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        const err = new Error("aborted");
        err.name = "AbortError";
        reject(err);
      },
      { once: true }
    );
  });
}

/** Reproduce `events[]` de un fixture real, uno a uno, con pausa entre
 * cada uno. Si `signal` se aborta a mitad de camino, resuelve
 * `finalStatus: "detached"` — el mismo contrato que el `streamRun` real. */
async function playFixtureEvents(events, { onEvent, signal }) {
  let lastId = 0;
  for (const raw of events) {
    try {
      await wait(STEP_DELAY_MS, signal);
    } catch {
      return { finalStatus: "detached", lastEventId: lastId, attempts: 0, reconciliation: null };
    }
    const event = eventFromFixtureEntry(raw);
    lastId = Number(event.id) || lastId;
    onEvent(event);
  }
  const terminalEvent = eventFromFixtureEntry(events[events.length - 1]);
  return { finalStatus: "terminal", terminalEvent, lastEventId: lastId, attempts: 0, reconciliation: null };
}

/** Cliente falso: `startRun` resuelve casi de inmediato con un runId/token
 * de muestra (nunca reales, nunca usados fuera de esta demo). */
export function makeDemoAgentClient({ startDelayMs = 400 } = {}) {
  return {
    async startRun({ signal }) {
      await wait(startDelayMs, signal);
      return {
        runId: "demo-run-id",
        // Deliberadamente SIN el prefijo real `cdt_rt_` (RF-801): este
        // token nunca sale de la demo en memoria, pero llevar el prefijo
        // real haría que la auditoría de bundle (RNF-011,
        // scripts/audit-client-bundle.mjs) lo marcara como un posible
        // token de corrida filtrado en `.next/static/`.
        token: "demo-token-no-usar-nunca-real",
        tokenExpiresAt: null,
        streamUrl: "/v2/agent/stream/demo-run-id",
      };
    },
    async getRun() {
      return { run_id: "demo-run-id", status: "running" };
    },
    async deleteRun() {
      return true;
    },
  };
}

export const DEMO_SCENARIOS = {
  completado: {
    label: "Completado",
    streamRunner: ({ onEvent, signal }) => playFixtureEvents(completedFixture.events, { onEvent, signal }),
  },
  sin_evidencia: {
    label: "Sin evidencia",
    streamRunner: ({ onEvent, signal }) => playFixtureEvents(noEvidenceFixture.events, { onEvent, signal }),
  },
  interrumpido: {
    label: "Interrumpido",
    streamRunner: ({ onEvent, signal }) => playFixtureEvents(interruptedFixture.events, { onEvent, signal }),
  },
  fallido: {
    label: "Fallido",
    streamRunner: ({ onEvent, signal }) => playFixtureEvents(failedFixture.events, { onEvent, signal }),
  },
  streaming_largo: {
    label: "Streaming (sin terminar)",
    // Pasos reales, pero la promesa nunca resuelve por sí sola — para ver
    // el estado "streaming" en reposo. `detach()` real la corta (RF-209).
    streamRunner: async ({ onEvent, signal }) => {
      const events = completedFixture.events.filter((e) => e.event === "step");
      for (const raw of events) {
        try {
          await wait(STEP_DELAY_MS, signal);
        } catch {
          return { finalStatus: "detached", lastEventId: events.length, attempts: 0, reconciliation: null };
        }
        onEvent(eventFromFixtureEntry(raw));
      }
      return new Promise((resolve) => {
        signal?.addEventListener(
          "abort",
          () => resolve({ finalStatus: "detached", lastEventId: events.length, attempts: 0, reconciliation: null }),
          { once: true }
        );
      });
    },
  },
  reconectando: {
    label: "Reconectando (repite eventos, sin duplicar pasos)",
    // Demuestra un reconecte real: reproduce los primeros pasos, señala
    // "reconnecting", y al "reengancharse" reenvía un tramo que SE
    // SOLAPA con lo ya visto (como haría el servidor tras un
    // `Last-Event-ID`) antes de seguir con el resto hasta el terminal. El
    // dedupe real (`runReducer`, por `seq`) es responsable de que la ruta
    // central no muestre esos pasos dos veces — este escenario solo
    // reproduce eventos reales fragmentados, no fabrica una regla de
    // dedupe propia.
    streamRunner: async ({ onEvent, onStatus, signal }) => {
      const allEvents = completedFixture.events;
      const firstBatch = allEvents.slice(0, 4); // seq 1-4
      const secondBatch = allEvents.slice(2); // seq 3..15 (3-4 se repiten a propósito)

      for (const raw of firstBatch) {
        await wait(STEP_DELAY_MS, signal).catch(() => {});
        onEvent(eventFromFixtureEntry(raw));
      }

      onStatus({ type: "reconnecting", attempt: 1, delayMs: 800 });
      await wait(800, signal).catch(() => {});
      onStatus({ type: "streaming", lastEventId: 4 });

      let lastId = 4;
      for (const raw of secondBatch) {
        try {
          await wait(STEP_DELAY_MS, signal);
        } catch {
          return { finalStatus: "detached", lastEventId: lastId, attempts: 1, reconciliation: null };
        }
        const event = eventFromFixtureEntry(raw);
        lastId = Number(event.id) || lastId;
        onEvent(event);
      }
      const terminalEvent = eventFromFixtureEntry(allEvents[allEvents.length - 1]);
      return { finalStatus: "terminal", terminalEvent, lastEventId: lastId, attempts: 1, reconciliation: null };
    },
  },
  desconectado: {
    label: "Sin conexión",
    streamRunner: async ({ onEvent, onStatus, signal }) => {
      const events = completedFixture.events.filter((e) => e.event === "step").slice(0, 2);
      for (const raw of events) {
        await wait(STEP_DELAY_MS, signal).catch(() => {});
        onEvent(eventFromFixtureEntry(raw));
      }
      onStatus({ type: "disconnected", attempts: 6 });
      return { finalStatus: "disconnected", lastEventId: events.length, attempts: 6, reconciliation: null };
    },
  },
};
