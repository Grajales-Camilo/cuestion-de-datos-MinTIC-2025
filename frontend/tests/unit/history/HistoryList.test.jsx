import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HistoryList } from "../../../components/history/HistoryList";
import { DELETE_RUN_WARNING } from "../../../components/history/DeleteRunDialog";

function makeRun(overrides = {}) {
  return {
    runId: "run-1",
    question: "¿Cuál es la cobertura educativa en Antioquia?",
    status: "completed",
    summary: "Completada",
    contextHint: null,
    createdAt: "2026-07-27T10:00:00.000Z",
    updatedAt: "2026-07-27T10:05:00.000Z",
    lastEventId: 8,
    ...overrides,
  };
}

function baseProps(overrides = {}) {
  return {
    runs: [makeRun()],
    onRerun: vi.fn(),
    onRefine: vi.fn(),
    onDelete: vi.fn(async () => ({ ok: true })),
    onResume: vi.fn(),
    isDeletingRun: () => false,
    ...overrides,
  };
}

describe("HistoryList — superficie primaria", () => {
  it("muestra pregunta, estado, fecha y resumen; nunca runId ni token", () => {
    render(<HistoryList {...baseProps()} />);
    expect(screen.getByText("¿Cuál es la cobertura educativa en Antioquia?")).toBeInTheDocument();
    expect(screen.getByText("Completada")).toBeInTheDocument();
    expect(screen.queryByText("run-1")).not.toBeInTheDocument();
  });

  it("lista vacía: mensaje sin errores", () => {
    render(<HistoryList {...baseProps({ runs: [] })} />);
    expect(screen.getByText(/Todavía no has hecho ninguna investigación/)).toBeInTheDocument();
  });
});

describe("HistoryList — Reejecutar y Refinar", () => {
  it("Reejecutar llama onRerun(runId)", async () => {
    const user = userEvent.setup();
    const onRerun = vi.fn();
    render(<HistoryList {...baseProps({ onRerun })} />);
    await user.click(screen.getByRole("button", { name: "Reejecutar" }));
    expect(onRerun).toHaveBeenCalledWith("run-1");
  });

  it("Refinar llama onRefine(runId)", async () => {
    const user = userEvent.setup();
    const onRefine = vi.fn();
    render(<HistoryList {...baseProps({ onRefine })} />);
    await user.click(screen.getByRole("button", { name: "Refinar" }));
    expect(onRefine).toHaveBeenCalledWith("run-1");
  });
});

describe("HistoryList — Reanudar", () => {
  it("solo aparece para corridas en curso", () => {
    render(<HistoryList {...baseProps({ runs: [makeRun({ status: "completed" })] })} />);
    expect(screen.queryByRole("button", { name: "Reanudar" })).not.toBeInTheDocument();
  });

  it("aparece y llama onResume(runId) para una corrida streaming", async () => {
    const user = userEvent.setup();
    const onResume = vi.fn();
    render(<HistoryList {...baseProps({ runs: [makeRun({ status: "streaming", summary: "En curso" })], onResume })} />);
    await user.click(screen.getByRole("button", { name: "Reanudar" }));
    expect(onResume).toHaveBeenCalledWith("run-1");
  });
});

describe("HistoryList — borrado con confirmación", () => {
  it("exige confirmación explícita antes del DELETE real", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn(async () => ({ ok: true }));
    render(<HistoryList {...baseProps({ onDelete })} />);

    await user.click(screen.getByRole("button", { name: "Borrar esta investigación" }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByText(DELETE_RUN_WARNING)).toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Borrar de forma irreversible" }));
    expect(onDelete).toHaveBeenCalledWith("run-1");
  });

  it("Cancelar en el modal no llama onDelete", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    render(<HistoryList {...baseProps({ onDelete })} />);

    await user.click(screen.getByRole("button", { name: "Borrar esta investigación" }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("un resultado de borrado fallido muestra un mensaje seguro, sin retirar el registro", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn(async () => ({ ok: false, reason: "unauthorized" }));
    render(<HistoryList {...baseProps({ onDelete })} />);

    await user.click(screen.getByRole("button", { name: "Borrar esta investigación" }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Borrar de forma irreversible" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("ya no es válido"));
    expect(screen.getByText("¿Cuál es la cobertura educativa en Antioquia?")).toBeInTheDocument();
  });
});

describe("HistoryList — registro con credencial vencida", () => {
  it("no ofrece Reanudar ni Borrar; muestra aviso de inaccesibilidad", () => {
    render(<HistoryList {...baseProps({ runs: [makeRun({ status: "streaming", credentialExpired: true })] })} />);
    expect(screen.queryByRole("button", { name: "Reanudar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Borrar esta investigación" })).not.toBeInTheDocument();
    expect(screen.getByText(/Ya no se puede acceder/)).toBeInTheDocument();
  });
});
