import { describe, expect, it } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { usePolitePolite } from "../../../hooks/usePolitePolite";
import { createInitialRunState, RUN_STATUS } from "../../../lib/agent/runStates";

function makeFakeTimers() {
  let now = 0;
  let nextId = 1;
  const pending = new Map();
  return {
    timers: {
      now: () => now,
      setTimeout: (fn, ms) => {
        const id = nextId++;
        pending.set(id, { fn, at: now + ms });
        return id;
      },
      clearTimeout: (id) => {
        pending.delete(id);
      },
    },
    advance(ms) {
      now += ms;
      for (const [id, entry] of [...pending.entries()]) {
        if (entry.at <= now) {
          pending.delete(id);
          entry.fn();
        }
      }
    },
    pendingCount: () => pending.size,
  };
}

function Harness({ state, timers }) {
  const { message } = usePolitePolite({ state, timers });
  return <div data-testid="msg">{message}</div>;
}

function withSteps(state, count) {
  const steps = [];
  for (let i = 1; i <= count; i += 1) {
    steps.push({ seq: i, stepNumber: i, node: "select_candidate", displayMessage: `Paso ${i}`, detail: null, at: null });
  }
  return { ...state, steps };
}

describe("usePolitePolite", () => {
  it("anuncia el arranque de inmediato al pasar a creating", () => {
    const { timers } = makeFakeTimers();
    const idle = createInitialRunState({ question: "x" });
    const { rerender } = render(<Harness state={idle} timers={timers} />);
    expect(screen.getByTestId("msg")).toHaveTextContent("");

    const creating = { ...idle, status: RUN_STATUS.CREATING };
    act(() => rerender(<Harness state={creating} timers={timers} />));
    expect(screen.getByTestId("msg")).toHaveTextContent("Comenzó una nueva investigación.");
  });

  it("agrupa pasos: como máximo un resumen cada 5 s, no uno por paso", () => {
    const { timers, advance } = makeFakeTimers();
    const base = { ...createInitialRunState({ question: "x" }), status: RUN_STATUS.STREAMING };
    const { rerender } = render(<Harness state={withSteps(base, 0)} timers={timers} />);

    // Primer paso: se anuncia de inmediato (ventana vacía al inicio).
    act(() => rerender(<Harness state={withSteps(base, 1)} timers={timers} />));
    expect(screen.getByTestId("msg")).toHaveTextContent("Paso 1 de la investigación: Paso 1");

    // Segundo y tercer paso llegan dentro de la ventana de 5 s: no deben
    // anunciarse todavía, deben agruparse en un solo pendiente.
    act(() => rerender(<Harness state={withSteps(base, 2)} timers={timers} />));
    act(() => rerender(<Harness state={withSteps(base, 3)} timers={timers} />));
    expect(screen.getByTestId("msg")).toHaveTextContent("Paso 1 de la investigación: Paso 1");

    // Al cumplirse la ventana, se anuncia el resumen más reciente (paso 3),
    // no el paso 2 que quedó agrupado.
    act(() => advance(5000));
    expect(screen.getByTestId("msg")).toHaveTextContent("Paso 3 de la investigación: Paso 3");
  });

  it("anuncia el estado terminal de inmediato, sin esperar la ventana", () => {
    const { timers } = makeFakeTimers();
    const streaming = { ...withSteps(createInitialRunState({ question: "x" }), 1), status: RUN_STATUS.STREAMING };
    const { rerender } = render(<Harness state={streaming} timers={timers} />);
    act(() => rerender(<Harness state={streaming} timers={timers} />));

    const completed = { ...streaming, status: RUN_STATUS.COMPLETED };
    act(() => rerender(<Harness state={completed} timers={timers} />));
    expect(screen.getByTestId("msg")).toHaveTextContent("La investigación terminó con evidencia verificada.");
  });

  it("no_evidence es neutral, interrupted/failed/detached tienen su propio texto en español, sin enums crudos", () => {
    const { timers } = makeFakeTimers();
    const base = createInitialRunState({ question: "x" });
    const cases = [
      [RUN_STATUS.NO_EVIDENCE, "La investigación terminó sin evidencia suficiente."],
      [RUN_STATUS.INTERRUPTED, "La investigación se interrumpió en el servidor. Se conserva lo verificado hasta ahora."],
      [RUN_STATUS.DETACHED, "Dejaste de seguir esta investigación. Sigue ejecutándose en el servidor."],
      [RUN_STATUS.DISCONNECTED, "Se perdió la conexión con la investigación."],
    ];
    for (const [status, expectedText] of cases) {
      const { unmount } = render(<Harness state={{ ...base, status }} timers={timers} />);
      expect(screen.getByTestId("msg")).toHaveTextContent(expectedText);
      expect(screen.getByTestId("msg").textContent).not.toMatch(/[A-Z_]{4,}/);
      unmount();
    }
  });

  it("failed usa error.messageUser, nunca un texto crudo del backend", () => {
    const { timers } = makeFakeTimers();
    const base = createInitialRunState({ question: "x" });
    const failed = { ...base, status: RUN_STATUS.FAILED, error: { messageUser: "La fuente de datos no respondió a tiempo." } };
    render(<Harness state={failed} timers={timers} />);
    expect(screen.getByTestId("msg")).toHaveTextContent("La fuente de datos no respondió a tiempo.");
  });

  it("limpia el timer pendiente al desmontar (sin fugas)", () => {
    const { timers, pendingCount } = makeFakeTimers();
    const base = { ...createInitialRunState({ question: "x" }), status: RUN_STATUS.STREAMING };
    const { rerender, unmount } = render(<Harness state={withSteps(base, 1)} timers={timers} />);
    act(() => rerender(<Harness state={withSteps(base, 1)} timers={timers} />));
    act(() => rerender(<Harness state={withSteps(base, 2)} timers={timers} />)); // deja un timer agrupado pendiente
    expect(pendingCount()).toBeGreaterThan(0);
    unmount();
    expect(pendingCount()).toBe(0);
  });
});
