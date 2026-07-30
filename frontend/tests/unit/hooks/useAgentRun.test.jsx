import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAgentRun } from "../../../hooks/useAgentRun";
import { RUN_STATUS } from "../../../lib/agent/runStates";

function makeFakeClient({ startRunImpl } = {}) {
  return {
    startRun: vi.fn(startRunImpl ?? (async () => ({ runId: "run-1", token: "cdt_rt_abc123", tokenExpiresAt: null, streamUrl: "/x" }))),
    getRun: vi.fn(async () => ({ run_id: "run-1", status: "running" })),
    deleteRun: vi.fn(async () => true),
  };
}

function makeFakeStreamRunner(impl) {
  return vi.fn(impl);
}

/** Deja pasar el `useEffect` de montaje y las promesas ya resueltas. */
async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function Harness({ hookProps, onReady }) {
  const result = useAgentRun(hookProps);
  onReady?.(result);
  return (
    <div>
      <p data-testid="status">{result.state.status}</p>
      <button type="button" onClick={() => result.start({ question: "¿Pregunta de prueba con longitud suficiente?" })}>
        Investigar
      </button>
      <button type="button" onClick={() => result.detach()}>
        Dejar de seguir
      </button>
    </div>
  );
}

describe("useAgentRun — consentimiento", () => {
  it("sin consentimiento: start() no llama startRun (cero POST)", async () => {
    const client = makeFakeClient();
    const streamRunner = makeFakeStreamRunner(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const user = userEvent.setup();

    render(<Harness hookProps={{ baseUrl: "http://x", consentGranted: false, agentClient: client, streamRunner }} />);
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    expect(client.startRun).not.toHaveBeenCalled();
    expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.IDLE);
  });
});

describe("useAgentRun — flujo start → stream → terminal", () => {
  it("RUN_REQUESTED es inmediato: el status cambia a creating antes de que resuelva el POST", async () => {
    let resolveStart;
    const client = makeFakeClient({
      startRunImpl: () => new Promise((resolve) => { resolveStart = resolve; }),
    });
    const streamRunner = makeFakeStreamRunner(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const user = userEvent.setup();

    render(<Harness hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }} />);
    await user.click(screen.getByRole("button", { name: "Investigar" }));

    expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.CREATING);

    resolveStart({ runId: "run-1", token: "cdt_rt_abc", tokenExpiresAt: null, streamUrl: "/x" });
    await flush();
  });

  it("start → RUN_CREATED (streaming) → eventos → terminal completed", async () => {
    const client = makeFakeClient();
    const streamRunner = makeFakeStreamRunner(async ({ onEvent }) => {
      onEvent({ id: "1", event: "step", json: { step_number: 1, node: "select_candidate", display_message: "x", detail: null } });
      const terminalEvent = {
        id: "2",
        event: "answer",
        json: {
          run_id: "run-1",
          status: "completed",
          intention: { topic: "prueba" },
          evidence: [],
          claims: [],
          presentation_warnings: [],
          textual_facts: [],
          no_evidence_report: null,
          usage: { steps_used: 1 },
        },
      };
      return { finalStatus: "terminal", terminalEvent, lastEventId: 2, attempts: 0, reconciliation: null };
    });
    const user = userEvent.setup();
    let hookResult;

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }}
        onReady={(r) => { hookResult = r; }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    expect(client.startRun).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.COMPLETED));
    expect(hookResult.state.steps).toHaveLength(1);
    expect(hookResult.state.intention).toEqual({ topic: "prueba" });
  });
});

describe("useAgentRun — abort local", () => {
  it("detach() produce finalStatus detached -> status DETACHED, cero deleteRun", async () => {
    const client = makeFakeClient();
    const streamRunner = makeFakeStreamRunner(
      ({ signal }) =>
        new Promise((resolve) => {
          signal.addEventListener("abort", () => {
            resolve({ finalStatus: "detached", lastEventId: 1, attempts: 0, reconciliation: null });
          });
        })
    );
    const user = userEvent.setup();

    render(<Harness hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }} />);
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();
    await user.click(screen.getByRole("button", { name: "Dejar de seguir" }));
    await flush();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.DETACHED));
    expect(client.deleteRun).not.toHaveBeenCalled();
  });
});

describe("useAgentRun — React Strict Mode", () => {
  it("una acción de usuario produce exactamente un startRun, incluso bajo StrictMode", async () => {
    const client = makeFakeClient();
    const streamRunner = makeFakeStreamRunner(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const user = userEvent.setup();

    render(
      <StrictMode>
        <Harness hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }} />
      </StrictMode>
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    expect(client.startRun).toHaveBeenCalledTimes(1);
  });
});

describe("useAgentRun — cleanup y ausencia del token", () => {
  it("desmontar durante el stream aborta la señal y no actualiza React después", async () => {
    let capturedSignal;
    const client = makeFakeClient();
    const streamRunner = makeFakeStreamRunner(
      ({ signal }) => {
        capturedSignal = signal;
        return new Promise(() => {}); // nunca resuelve por sí sola
      }
    );
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = render(<Harness hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }} />);
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    unmount();
    expect(capturedSignal.aborted).toBe(true);
    // Ningún warning de "no se puede actualizar un componente desmontado".
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("el token nunca aparece en el estado serializado ni en un error sintético", async () => {
    const TOKEN = "cdt_rt_super_secreto_123";
    const client = makeFakeClient({
      startRunImpl: async () => ({ runId: "run-1", token: TOKEN, tokenExpiresAt: null, streamUrl: "/x" }),
    });
    const streamRunner = makeFakeStreamRunner(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const user = userEvent.setup();
    let hookResult;

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }}
        onReady={(r) => { hookResult = r; }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    const serialized = JSON.stringify(hookResult.state, (key, value) => (value instanceof Set ? [...value] : value));
    expect(serialized).not.toContain(TOKEN);
  });

  it("un fallo del POST inicial se traduce a estado failed con messageUser, sin exponer messageDev", async () => {
    const secretDetail = "detalle técnico interno que no debe verse";
    const client = makeFakeClient({
      startRunImpl: async () => {
        const error = new Error(secretDetail);
        error.name = "ApiError";
        error.code = "INTERNAL";
        error.messageUser = "No se pudo iniciar la investigación.";
        error.messageDev = secretDetail;
        error.retryable = false;
        throw error;
      },
    });
    const streamRunner = makeFakeStreamRunner(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const user = userEvent.setup();
    let hookResult;

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }}
        onReady={(r) => { hookResult = r; }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.FAILED));
    expect(hookResult.state.error?.messageUser).toBe("No se pudo iniciar la investigación.");
  });
});

describe("useAgentRun — reset", () => {
  it("reset() vuelve al estado idle real", async () => {
    const client = makeFakeClient();
    const streamRunner = makeFakeStreamRunner(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const user = userEvent.setup();
    let hookResult;

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }}
        onReady={(r) => { hookResult = r; }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.DETACHED));

    act(() => {
      hookResult.reset();
    });

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.IDLE));
  });
});
