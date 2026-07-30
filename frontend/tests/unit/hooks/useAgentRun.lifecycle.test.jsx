import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useAgentRun } from "../../../hooks/useAgentRun";
import { RUN_STATUS } from "../../../lib/agent/runStates";

function makeFakeClient(overrides = {}) {
  return {
    startRun: vi.fn(
      overrides.startRunImpl ??
        (async () => ({ runId: "run-1", token: "cdt_rt_abc123", tokenExpiresAt: null, streamUrl: "/x" }))
    ),
    getRun: vi.fn(overrides.getRunImpl ?? (async () => ({ run_id: "run-1", status: "running" }))),
    deleteRun: vi.fn(async () => true),
  };
}

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
      <button type="button" onClick={() => result.resume({ runId: "run-1", token: "cdt_rt_guardado", lastSeq: 2 })}>
        Reanudar
      </button>
    </div>
  );
}

describe("useAgentRun — onLifecycle: created", () => {
  it("emite exactamente un evento created con el token, tras un start exitoso", async () => {
    const client = makeFakeClient();
    const streamRunner = vi.fn(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const onLifecycle = vi.fn();
    const user = userEvent.setup();

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner, onLifecycle }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    const createdCalls = onLifecycle.mock.calls.filter(([e]) => e.type === "created");
    expect(createdCalls).toHaveLength(1);
    expect(createdCalls[0][0]).toMatchObject({
      type: "created",
      runId: "run-1",
      token: "cdt_rt_abc123",
      question: "¿Pregunta de prueba con longitud suficiente?",
    });
  });
});

describe("useAgentRun — onLifecycle: status y terminal", () => {
  it("notifica cada cambio de estado y, al llegar a un terminal, también terminal", async () => {
    const client = makeFakeClient();
    const streamRunner = vi.fn(async ({ onEvent }) => {
      const terminalEvent = {
        id: "1",
        event: "answer",
        json: {
          run_id: "run-1",
          status: "completed",
          intention: null,
          evidence: [],
          claims: [],
          presentation_warnings: [],
          textual_facts: [],
          no_evidence_report: null,
          usage: null,
        },
      };
      return { finalStatus: "terminal", terminalEvent, lastEventId: 1, attempts: 0, reconciliation: null };
    });
    const onLifecycle = vi.fn();
    const user = userEvent.setup();

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner, onLifecycle }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.COMPLETED));

    const statusEvents = onLifecycle.mock.calls.map(([e]) => e).filter((e) => e.type === "status");
    expect(statusEvents.some((e) => e.status === RUN_STATUS.STREAMING)).toBe(true);
    expect(statusEvents.some((e) => e.status === RUN_STATUS.COMPLETED)).toBe(true);

    const terminalEvents = onLifecycle.mock.calls.map(([e]) => e).filter((e) => e.type === "terminal");
    expect(terminalEvents).toHaveLength(1);
    expect(terminalEvents[0].status).toBe(RUN_STATUS.COMPLETED);
  });
});

describe("useAgentRun — onLifecycle: seq", () => {
  it("notifica el último seq confirmado según avanza", async () => {
    const client = makeFakeClient();
    const streamRunner = vi.fn(async ({ onEvent }) => {
      onEvent({ id: "1", event: "step", json: { step_number: 1, node: "select_candidate", display_message: "x" } });
      onEvent({ id: "2", event: "step", json: { step_number: 2, node: "execute_query", display_message: "y" } });
      return { finalStatus: "detached", lastEventId: 2, attempts: 0, reconciliation: null };
    });
    const onLifecycle = vi.fn();
    const user = userEvent.setup();

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner, onLifecycle }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    // React puede agrupar (`batch`) los dos `dispatch` síncronos del mismo
    // `streamRunner` en un solo commit: lo que importa para persistir
    // `Last-Event-ID` es que la última notificación refleje el seq más
    // reciente confirmado, no que exista una notificación por evento.
    const seqValues = onLifecycle.mock.calls.map(([e]) => e).filter((e) => e.type === "seq").map((e) => e.seq);
    expect(seqValues.length).toBeGreaterThan(0);
    expect(seqValues.at(-1)).toBe(2);
  });
});

describe("useAgentRun — onLifecycle: invalid (token inválido o corrida inexistente)", () => {
  it("un error 401 durante el stream notifica invalid con httpStatus 401", async () => {
    const client = makeFakeClient();
    const unauthorized = Object.assign(new Error("no autorizado"), {
      name: "ApiError",
      code: "UNAUTHORIZED",
      httpStatus: 401,
      messageUser: "El acceso a esta investigación ya no es válido.",
      messageDev: "401",
      retryable: false,
    });
    const streamRunner = vi.fn(async () => ({
      finalStatus: "client_error",
      error: unauthorized,
      lastEventId: 0,
      attempts: 0,
      reconciliation: null,
    }));
    const onLifecycle = vi.fn();
    const user = userEvent.setup();

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner, onLifecycle }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    await flush();

    const invalidEvents = onLifecycle.mock.calls.map(([e]) => e).filter((e) => e.type === "invalid");
    expect(invalidEvents).toHaveLength(1);
    expect(invalidEvents[0]).toMatchObject({ runId: "run-1", httpStatus: 401 });
  });

  it("un 404 en getRun durante resume() notifica invalid, sin volver a llamar startRun", async () => {
    const notFound = Object.assign(new Error("no encontrado"), {
      name: "ApiError",
      code: "RUN_NOT_FOUND",
      httpStatus: 404,
      messageUser: "Esta investigación ya no está disponible.",
      messageDev: "404",
      retryable: false,
    });
    const client = makeFakeClient({ getRunImpl: async () => { throw notFound; } });
    const streamRunner = vi.fn();
    const onLifecycle = vi.fn();
    const user = userEvent.setup();

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner, onLifecycle }}
      />
    );
    await user.click(screen.getByRole("button", { name: "Reanudar" }));
    await flush();

    expect(client.startRun).not.toHaveBeenCalled();
    expect(streamRunner).not.toHaveBeenCalled();
    const invalidEvents = onLifecycle.mock.calls.map(([e]) => e).filter((e) => e.type === "invalid");
    expect(invalidEvents).toHaveLength(1);
    expect(invalidEvents[0]).toMatchObject({ runId: "run-1", httpStatus: 404 });
  });
});

describe("useAgentRun — resume()", () => {
  it("una corrida ya terminada (status distinto de running): reconcilia y no llama streamRunner", async () => {
    const client = makeFakeClient({
      getRunImpl: async () => ({
        run_id: "run-1",
        status: "completed",
        answer: { evidence: [], claims: [], presentation_warnings: [], textual_facts: [], usage: null },
      }),
    });
    const streamRunner = vi.fn();
    let hookResult;
    const user = userEvent.setup();

    render(
      <Harness hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }} onReady={(r) => { hookResult = r; }} />
    );
    await user.click(screen.getByRole("button", { name: "Reanudar" }));
    await flush();

    expect(client.startRun).not.toHaveBeenCalled();
    expect(streamRunner).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent(RUN_STATUS.COMPLETED));
    expect(hookResult.state.runId).toBe("run-1");
  });

  it("una corrida running: continúa el stream con el lastSeq guardado, sin POST", async () => {
    const client = makeFakeClient({ getRunImpl: async () => ({ run_id: "run-1", status: "running", last_event_seq: 2 }) });
    const streamRunner = vi.fn(async ({ lastEventId }) => {
      expect(lastEventId).toBe(2);
      return { finalStatus: "detached", lastEventId: 2, attempts: 0, reconciliation: null };
    });
    const user = userEvent.setup();

    render(<Harness hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }} />);
    await user.click(screen.getByRole("button", { name: "Reanudar" }));
    await flush();

    expect(client.startRun).not.toHaveBeenCalled();
    expect(streamRunner).toHaveBeenCalledTimes(1);
  });
});

describe("useAgentRun — F5-03A-R2: sectionId sensible nunca llega a state ni al evento lifecycle", () => {
  it("start() llamado programáticamente con sectionId sensible: state.sectionId y el evento created quedan en null", async () => {
    const client = makeFakeClient();
    const streamRunner = vi.fn(async () => ({ finalStatus: "detached", lastEventId: 0, attempts: 0, reconciliation: null }));
    const onLifecycle = vi.fn();
    let hookResult;

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner, onLifecycle }}
        onReady={(r) => { hookResult = r; }}
      />
    );

    await act(async () => {
      await hookResult.start({
        question: "¿Pregunta con longitud suficiente para pasar validación?",
        sectionId: "seccion-cdt_rt_secreto",
      });
    });
    await flush();

    expect(hookResult.state.sectionId).toBeNull();
    expect(JSON.stringify(hookResult.state)).not.toContain("cdt_rt_secreto");

    const createdEvent = onLifecycle.mock.calls.map(([e]) => e).find((e) => e.type === "created");
    expect(createdEvent).toBeDefined();
    expect(createdEvent.sectionId).toBeNull();
    expect(JSON.stringify(createdEvent).match(/cdt_rt_[A-Za-z0-9_-]+/g)).toEqual(["cdt_rt_abc123"]); // solo el token legítimo del evento `created`, no el sectionId envenenado
  });

  it("resume() llamado programáticamente con sectionId sensible: state.sectionId queda en null", async () => {
    const client = makeFakeClient({
      getRunImpl: async () => ({
        run_id: "run-1",
        status: "completed",
        answer: { evidence: [], claims: [], presentation_warnings: [], textual_facts: [], usage: null },
      }),
    });
    const streamRunner = vi.fn();
    let hookResult;

    render(
      <Harness
        hookProps={{ baseUrl: "http://x", consentGranted: true, agentClient: client, streamRunner }}
        onReady={(r) => { hookResult = r; }}
      />
    );

    await act(async () => {
      await hookResult.resume({ runId: "run-1", token: "cdt_rt_real", sectionId: "seccion-cdt_rt_secreto" });
    });
    await flush();

    expect(hookResult.state.runId).toBe("run-1");
    expect(hookResult.state.sectionId).toBeNull();
    expect(JSON.stringify(hookResult.state)).not.toContain("cdt_rt_secreto");
  });
});
