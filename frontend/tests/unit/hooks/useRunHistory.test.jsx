import { describe, expect, it, vi } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRunHistory } from "../../../hooks/useRunHistory";

function makeMemoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
    get length() {
      return map.size;
    },
    key: (i) => [...map.keys()][i] ?? null,
  };
}

/** `setItem` siempre lanza `QuotaExceededError` — modela un destino de
 * migración que nunca acepta escrituras. */
function makeWriteThrowingStorage() {
  return {
    getItem: () => null,
    setItem: () => {
      const error = new Error("cuota agotada");
      error.name = "QuotaExceededError";
      throw error;
    },
    removeItem: () => {},
    length: 0,
    key: () => null,
  };
}

function makeDeps(overrides = {}) {
  return {
    sessionStorage: makeMemoryStorage(),
    localStorage: makeMemoryStorage(),
    agentClient: { deleteRun: vi.fn(async () => true) },
    startRun: vi.fn(),
    resumeRunTransport: vi.fn(),
    ...overrides,
  };
}

function Harness({ deps, onReady }) {
  const result = useRunHistory(deps);
  onReady?.(result);
  return (
    <div>
      <p data-testid="count">{result.runs.length}</p>
      <p data-testid="remember">{String(result.rememberRuns)}</p>
      <pre data-testid="runs">{JSON.stringify(result.runs)}</pre>
    </div>
  );
}

function seedCreatedRun(historyApi, overrides = {}) {
  act(() => {
    historyApi.handleAgentLifecycle({
      type: "created",
      runId: "run-1",
      token: "cdt_rt_secreto",
      tokenExpiresAt: null,
      question: "¿Cuál es la cobertura educativa en Antioquia?",
      contextHint: null,
      ...overrides,
    });
  });
}

describe("useRunHistory — historial público sin token", () => {
  it("runs nunca incluye el campo token, ni siquiera serializado", async () => {
    const deps = makeDeps();
    let api;
    render(<Harness deps={deps} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api);

    await waitFor(() => expect(screen.getByTestId("count")).toHaveTextContent("1"));
    expect(screen.getByTestId("runs").textContent).not.toContain("cdt_rt_secreto");
  });
});

describe("useRunHistory — recarga: historial saneado y lastEventId recuperados", () => {
  it("un segundo montaje sobre el mismo storage recupera question y lastEventId", async () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    let api1;
    render(<Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api1 = r; }} />);
    seedCreatedRun(api1);
    act(() => {
      api1.handleAgentLifecycle({ type: "seq", runId: "run-1", seq: 5 });
    });
    await waitFor(() => expect(api1.runs[0]?.lastEventId).toBe(5));

    let api2;
    render(<Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api2 = r; }} />);
    await waitFor(() => expect(api2.runs).toHaveLength(1));
    expect(api2.runs[0].lastEventId).toBe(5);
    expect(api2.runs[0].question).toBe("¿Cuál es la cobertura educativa en Antioquia?");
  });
});

describe("useRunHistory — opt-in", () => {
  it("desmarcado por defecto: los registros van a sessionStorage, no a localStorage", async () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    let api;
    render(<Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    expect(JSON.parse(sessionStorage.getItem("cdd.runs.v1")).records).toHaveLength(1);
    expect(localStorage.getItem("cdd.runs.v1")).toBeNull();
  });

  it("activar el opt-in migra los registros existentes a localStorage", async () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    let api;
    const { rerender } = render(
      <Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api = r; }} />
    );
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => {
      api.setRememberRuns(true);
    });
    rerender(<Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api = r; }} />);

    await waitFor(() => expect(JSON.parse(localStorage.getItem("cdd.runs.v1")).records).toHaveLength(1));
    expect(JSON.parse(sessionStorage.getItem("cdd.runs.v1")).records).toEqual([]);
  });

  it("desactivar el opt-in elimina el registro persistente de localStorage", async () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    let api;
    render(<Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api = r; }} />);
    act(() => api.setRememberRuns(true));
    seedCreatedRun(api);
    await waitFor(() => expect(JSON.parse(localStorage.getItem("cdd.runs.v1")).records).toHaveLength(1));

    act(() => api.setRememberRuns(false));

    expect(JSON.parse(localStorage.getItem("cdd.runs.v1")).records).toEqual([]);
    expect(JSON.parse(sessionStorage.getItem("cdd.runs.v1")).records).toHaveLength(1);
  });
});

describe("useRunHistory — reejecutar y refinar", () => {
  it("rerun(runId) llama startRun con la pregunta/contexto guardados, no con el token", async () => {
    const startRun = vi.fn();
    const deps = makeDeps({ startRun });
    let api;
    render(<Harness deps={deps} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api, { contextHint: "contexto original" });
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => api.rerun("run-1"));

    expect(startRun).toHaveBeenCalledWith({
      question: "¿Cuál es la cobertura educativa en Antioquia?",
      contextHint: "contexto original",
      sectionId: null,
    });
  });

  it("rerun(runId) conserva sectionId de la corrida original (F5-03A-R1)", async () => {
    const startRun = vi.fn();
    const deps = makeDeps({ startRun });
    let api;
    render(<Harness deps={deps} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api, { sectionId: "sec-1" });
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => api.rerun("run-1"));

    expect(startRun).toHaveBeenCalledWith(expect.objectContaining({ sectionId: "sec-1" }));
  });

  it("refine(runId) devuelve pregunta/contexto para editar, sin llamar startRun", async () => {
    const startRun = vi.fn();
    let api;
    render(<Harness deps={makeDeps({ startRun })} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    const prefill = api.refine("run-1");
    expect(prefill.question).toBe("¿Cuál es la cobertura educativa en Antioquia?");
    expect(startRun).not.toHaveBeenCalled();
  });
});

describe("useRunHistory — resumeRun (F5-03A-R1)", () => {
  it("resumeRun(runId) pasa sectionId a resumeRunTransport, leído de runs (nunca junto al token)", async () => {
    const resumeRunTransport = vi.fn();
    let api;
    render(<Harness deps={makeDeps({ resumeRunTransport })} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api, { sectionId: "sec-1" });
    act(() => {
      api.handleAgentLifecycle({ type: "seq", runId: "run-1", seq: 3 });
    });
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => api.resumeRun("run-1"));

    expect(resumeRunTransport).toHaveBeenCalledWith({
      runId: "run-1",
      token: "cdt_rt_secreto",
      lastSeq: 3,
      sectionId: "sec-1",
    });
  });

  it("resumeRun(runId) sin sectionId registrado pasa null, sin inventarlo", async () => {
    const resumeRunTransport = vi.fn();
    let api;
    render(<Harness deps={makeDeps({ resumeRunTransport })} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => api.resumeRun("run-1"));

    expect(resumeRunTransport).toHaveBeenCalledWith(expect.objectContaining({ sectionId: null }));
  });

  it("F5-03A-R2 — un evento lifecycle 'created' con sectionId sensible nunca sobrevive en runs", async () => {
    let api;
    render(<Harness deps={makeDeps()} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api, { sectionId: "seccion-cdt_rt_secreto" });
    await waitFor(() => expect(api.runs).toHaveLength(1));

    expect(api.runs[0].sectionId).toBeNull();
    expect(JSON.stringify(api.runs)).not.toContain("cdt_rt_secreto");
  });

  it("F5-03A-R2 — resumeRun con almacenamiento manipulado a mano pasa sectionId:null al transporte, sin tocar el token real", async () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeMemoryStorage();
    const poisonedDoc = {
      schemaVersion: 1,
      records: [
        {
          runId: "run-1",
          token: "cdt_rt_real",
          tokenExpiresAt: null,
          question: "¿Cuál es la cobertura educativa en Antioquia?",
          contextHint: null,
          sectionId: "seccion-cdt_rt_filtrado",
          status: "completed",
          summary: "Completada",
          lastEventId: 3,
          createdAt: "2026-07-28T00:00:00.000Z",
          updatedAt: "2026-07-28T00:00:00.000Z",
        },
      ],
    };
    sessionStorage.setItem("cdd.runs.v1", JSON.stringify(poisonedDoc));

    const resumeRunTransport = vi.fn();
    let api;
    render(
      <Harness
        deps={makeDeps({ sessionStorage, localStorage, resumeRunTransport })}
        onReady={(r) => { api = r; }}
      />
    );
    await waitFor(() => expect(api.runs).toHaveLength(1));
    expect(api.runs[0].sectionId).toBeNull(); // ya saneado al leer, no solo al escribir

    act(() => api.resumeRun("run-1"));

    expect(resumeRunTransport).toHaveBeenCalledWith({
      runId: "run-1",
      token: "cdt_rt_real", // la credencial real sigue disponible intacta
      lastSeq: 3,
      sectionId: null,
    });
  });
});

describe("useRunHistory — borrado", () => {
  it("DELETE exitoso: retira el registro del historial y del almacén", async () => {
    const deleteRunMock = vi.fn(async () => true);
    let api;
    render(
      <Harness deps={makeDeps({ agentClient: { deleteRun: deleteRunMock } })} onReady={(r) => { api = r; }} />
    );
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    let outcome;
    await act(async () => {
      outcome = await api.deleteRun("run-1");
    });

    expect(outcome).toEqual({ ok: true });
    expect(deleteRunMock).toHaveBeenCalledWith({ runId: "run-1", token: "cdt_rt_secreto" });
    await waitFor(() => expect(api.runs).toHaveLength(0));
  });

  it("401 en DELETE: conserva el registro pero limpia la credencial, no afirma borrado", async () => {
    const unauthorized = Object.assign(new Error("no autorizado"), { httpStatus: 401 });
    const deleteRunMock = vi.fn(async () => { throw unauthorized; });
    let api;
    render(
      <Harness deps={makeDeps({ agentClient: { deleteRun: deleteRunMock } })} onReady={(r) => { api = r; }} />
    );
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    let outcome;
    await act(async () => {
      outcome = await api.deleteRun("run-1");
    });

    expect(outcome).toEqual({ ok: false, reason: "unauthorized", error: unauthorized });
    expect(api.runs).toHaveLength(1); // el registro sigue existiendo
  });

  it("error de red en DELETE: conserva el registro tal cual estaba", async () => {
    const networkError = Object.assign(new Error("fallo de red"), { httpStatus: null });
    const deleteRunMock = vi.fn(async () => { throw networkError; });
    let api;
    render(
      <Harness deps={makeDeps({ agentClient: { deleteRun: deleteRunMock } })} onReady={(r) => { api = r; }} />
    );
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    let outcome;
    await act(async () => {
      outcome = await api.deleteRun("run-1");
    });

    expect(outcome.ok).toBe(false);
    expect(api.runs).toHaveLength(1);
  });

  it("doble clic: exactamente un DELETE real", async () => {
    let resolveDelete;
    const deleteRunMock = vi.fn(() => new Promise((resolve) => { resolveDelete = resolve; }));
    let api;
    render(
      <Harness deps={makeDeps({ agentClient: { deleteRun: deleteRunMock } })} onReady={(r) => { api = r; }} />
    );
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    let firstCall;
    let secondCall;
    await act(async () => {
      firstCall = api.deleteRun("run-1");
      secondCall = api.deleteRun("run-1"); // clic doble antes de que resuelva el primero
      resolveDelete(true);
      await Promise.all([firstCall, secondCall]);
    });

    expect(deleteRunMock).toHaveBeenCalledTimes(1);
    expect(await secondCall).toEqual({ ok: false, reason: "already_in_flight" });
  });
});

describe("useRunHistory — invalid (token inválido o corrida inexistente)", () => {
  it("401 durante el stream: limpia la credencial pero conserva el registro", async () => {
    let api;
    render(<Harness deps={makeDeps()} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => api.handleAgentLifecycle({ type: "invalid", runId: "run-1", httpStatus: 401 }));

    await waitFor(() => expect(api.runs).toHaveLength(1));
    expect(api.resumeRun("run-1")).toBeUndefined();
  });

  it("404 RUN_NOT_FOUND durante el stream: elimina el registro local", async () => {
    let api;
    render(<Harness deps={makeDeps()} onReady={(r) => { api = r; }} />);
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    act(() => api.handleAgentLifecycle({ type: "invalid", runId: "run-1", httpStatus: 404 }));

    await waitFor(() => expect(api.runs).toHaveLength(0));
  });
});

describe("F3-7B-R1 — setRememberRuns no miente sobre el estado si la migración falla", () => {
  it("localStorage no acepta escrituras: rememberRuns permanece false, el registro sigue en sessionStorage", async () => {
    const sessionStorage = makeMemoryStorage();
    const localStorage = makeWriteThrowingStorage();
    let api;
    render(
      <Harness deps={makeDeps({ sessionStorage, localStorage })} onReady={(r) => { api = r; }} />
    );
    seedCreatedRun(api);
    await waitFor(() => expect(api.runs).toHaveLength(1));

    let outcome;
    act(() => {
      outcome = api.setRememberRuns(true);
    });

    expect(outcome).toEqual({ ok: false, reason: "quota_exceeded" });
    // Nunca se declara el opt-in concedido si la migración no se completó.
    expect(api.rememberRuns).toBe(false);
    // El registro (con su credencial) sigue exactamente donde estaba.
    expect(api.runs).toHaveLength(1);
    expect(sessionStorage.getItem("cdd.runs.v1")).not.toBeNull();
  });
});
