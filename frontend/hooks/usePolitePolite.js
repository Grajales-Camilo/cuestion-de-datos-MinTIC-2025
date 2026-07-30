import { useEffect, useRef, useState } from "react";
import { RUN_STATUS, isTerminalRunStatus } from "../lib/agent/runStates";

/**
 * Cola agrupada para la región `aria-live="polite"` del copiloto
 * (`implementation-plan.md` §8.1, R-09): anuncia el arranque una vez,
 * agrupa los pasos en curso a lo sumo un resumen cada `throttleMs` (por
 * defecto 5000 ms), y anuncia el desenlace (terminal, desconexión o
 * desenganche) de inmediato, sin esperar la ventana de throttle. Nunca
 * anuncia cada `ping` ni cada evento técnico — solo observa `state.status`
 * y el conteo de `state.steps`.
 *
 * `timers` es inyectable (reloj falso en pruebas): `{ now, setTimeout,
 * clearTimeout }`. Todos los timers se limpian al desmontar.
 */
const THROTTLE_MS = 5000;

const REAL_TIMERS = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (id) => clearTimeout(id),
};

function terminalMessage(state) {
  switch (state.status) {
    case RUN_STATUS.COMPLETED:
      // Mismo texto que `TerminalPanel.terminalMessage` (RF-501/RNF-007,
      // hallazgo de revisión manual F8-02): el anuncio en vivo debe decir
      // el RESULTADO, no solo que "algo terminó" — quien usa lector de
      // pantalla no tiene el panel visible para deducirlo por su cuenta.
      return "La investigación terminó con evidencia verificada.";
    case RUN_STATUS.NO_EVIDENCE:
      return "La investigación terminó sin evidencia suficiente.";
    case RUN_STATUS.INTERRUPTED:
      return "La investigación se interrumpió en el servidor. Se conserva lo verificado hasta ahora.";
    case RUN_STATUS.FAILED:
      return state.error?.messageUser ?? "La investigación no pudo completarse.";
    case RUN_STATUS.DETACHED:
      return "Dejaste de seguir esta investigación. Sigue ejecutándose en el servidor.";
    case RUN_STATUS.DISCONNECTED:
      return "Se perdió la conexión con la investigación.";
    default:
      return "";
  }
}

export function usePolitePolite({ state, throttleMs = THROTTLE_MS, timers = REAL_TIMERS }) {
  const [message, setMessage] = useState("");

  // -Infinity, no 0: con un reloj real da igual, pero con un reloj falso
  // que arranca en 0 (como en las pruebas), `0` haría parecer que el
  // primer anuncio real ya está "dentro de la ventana" de throttle.
  const lastAnnouncedAtRef = useRef(-Infinity);
  const pendingTimerRef = useRef(null);
  const prevStatusRef = useRef(null);
  const lastSeenStepCountRef = useRef(0);

  function clearPending() {
    if (pendingTimerRef.current !== null) {
      timers.clearTimeout(pendingTimerRef.current);
      pendingTimerRef.current = null;
    }
  }

  function announceNow(text) {
    clearPending();
    lastAnnouncedAtRef.current = timers.now();
    setMessage(text);
  }

  /** Reemplaza cualquier resumen pendiente por el más reciente: agrupa
   * varios pasos llegados dentro de la misma ventana en un solo anuncio. */
  function scheduleGrouped(text) {
    clearPending();
    const elapsed = timers.now() - lastAnnouncedAtRef.current;
    const wait = Math.max(0, throttleMs - elapsed);
    pendingTimerRef.current = timers.setTimeout(() => {
      pendingTimerRef.current = null;
      lastAnnouncedAtRef.current = timers.now();
      setMessage(text);
    }, wait);
  }

  useEffect(() => {
    const prevStatus = prevStatusRef.current;
    prevStatusRef.current = state.status;

    // Arranque de una corrida NUEVA (incluida una segunda investigación en
    // el mismo montaje del hook, tras `reset()`/un terminal previo): se
    // detecta por la transición hacia `creating`, no por una bandera de
    // "ya se anunció una vez", para que cada corrida real tenga su propio
    // anuncio de inicio.
    if (state.status === RUN_STATUS.CREATING && prevStatus !== RUN_STATUS.CREATING) {
      lastSeenStepCountRef.current = 0;
      announceNow("Comenzó una nueva investigación.");
      return;
    }

    if (isTerminalRunStatus(state.status) || state.status === RUN_STATUS.DETACHED || state.status === RUN_STATUS.DISCONNECTED) {
      lastSeenStepCountRef.current = state.steps.length;
      announceNow(terminalMessage(state));
      return;
    }

    if (state.status === RUN_STATUS.STREAMING && state.steps.length > lastSeenStepCountRef.current) {
      lastSeenStepCountRef.current = state.steps.length;
      const last = state.steps[state.steps.length - 1];
      const text = `Paso ${state.steps.length} de la investigación: ${last.displayMessage}`;
      const elapsed = timers.now() - lastAnnouncedAtRef.current;
      if (elapsed >= throttleMs) {
        announceNow(text);
      } else {
        scheduleGrouped(text);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, state.steps.length]);

  useEffect(() => clearPending, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { message };
}
