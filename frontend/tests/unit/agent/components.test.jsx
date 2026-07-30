import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConnectionStatus } from "../../../components/agent/ConnectionStatus";
import { IntentSummary } from "../../../components/agent/IntentSummary";
import { RunTimeline } from "../../../components/agent/RunTimeline";
import { TerminalPanel } from "../../../components/agent/TerminalPanel";
import { QuestionComposer } from "../../../components/agent/QuestionComposer";
import { CopilotPanel } from "../../../components/agent/CopilotPanel";
import { RUN_STATUS } from "../../../lib/agent/runStates";

describe("ConnectionStatus — cada estado con texto + icono, nunca solo color", () => {
  it.each([
    [RUN_STATUS.STREAMING, "En vivo"],
    [RUN_STATUS.RECONNECTING, /Reconectando/],
    [RUN_STATUS.DISCONNECTED, "Sin conexión"],
    [RUN_STATUS.DETACHED, "Dejaste de seguirla"],
  ])("status=%s muestra texto visible", (status, expected) => {
    render(<ConnectionStatus status={status} reconnectAttempt={2} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
    const container = screen.getByText(expected).closest("p, div");
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("disconnected ofrece una acción clara de reintento", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ConnectionStatus status={RUN_STATUS.DISCONNECTED} onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("IntentSummary", () => {
  it("nunca muestra null/undefined: sin intention, no renderiza nada", () => {
    const { container } = render(<IntentSummary intention={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("solo compone los fragmentos presentes, en español claro", () => {
    render(<IntentSummary intention={{ topic: "deserción escolar", territory: "Antioquia" }} />);
    expect(screen.getByText(/Entendí:/)).toBeInTheDocument();
    expect(screen.getByText("deserción escolar")).toBeInTheDocument();
    expect(screen.getByText("Antioquia")).toBeInTheDocument();
    expect(screen.queryByText("null")).not.toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
  });

  it("permite reformular", async () => {
    const user = userEvent.setup();
    const onReformulate = vi.fn();
    render(<IntentSummary intention={{ topic: "x" }} onReformulate={onReformulate} />);
    await user.click(screen.getByRole("button", { name: /reformular/ }));
    expect(onReformulate).toHaveBeenCalledTimes(1);
  });
});

describe("RunTimeline — sin duplicados, cualquier cantidad de pasos", () => {
  it("renderiza exactamente un <li> por seq único, sin importar la cantidad", () => {
    const steps = Array.from({ length: 13 }, (_, i) => ({
      seq: i + 1,
      node: "select_candidate",
      displayMessage: `Paso ${i + 1}`,
      detail: null,
    }));
    render(<RunTimeline steps={steps} status={RUN_STATUS.STREAMING} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(13);
  });

  it("no fija 9 pasos: funciona igual con 2 pasos", () => {
    const steps = [
      { seq: 1, node: "select_candidate", displayMessage: "Uno", detail: null },
      { seq: 2, node: "execute_query", displayMessage: "Dos", detail: null },
    ];
    render(<RunTimeline steps={steps} status={RUN_STATUS.STREAMING} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("sin pasos: no renderiza nada", () => {
    const { container } = render(<RunTimeline steps={[]} status={RUN_STATUS.IDLE} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("TerminalPanel — nunca enums crudos ni claims/evidence", () => {
  const safeSuggestion = {
    entidad: "Entidad oficial sintética",
    url: "https://datos.example.gov.co/recurso",
    por_que: "Puede contener el dato solicitado.",
  };

  it.each([
    [RUN_STATUS.COMPLETED, "evidencia verificada"],
    [RUN_STATUS.NO_EVIDENCE, "No se encontró evidencia elegible"],
    [RUN_STATUS.INTERRUPTED, "se interrumpió en el servidor"],
  ])("status=%s muestra un mensaje en español, sin claims/evidence", (status, expectedFragment) => {
    render(<TerminalPanel state={{ status, error: null }} onRestart={() => {}} />);
    expect(screen.getByText(new RegExp(expectedFragment))).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("failed muestra error.messageUser, nunca un código crudo", () => {
    render(
      <TerminalPanel
        state={{ status: RUN_STATUS.FAILED, error: { messageUser: "La fuente de datos no respondió a tiempo." } }}
        onRestart={() => {}}
      />
    );
    expect(screen.getByText("La fuente de datos no respondió a tiempo.")).toBeInTheDocument();
    expect(screen.queryByText(/SOCRATA_TIMEOUT/)).not.toBeInTheDocument();
  });

  it("estados no terminales (streaming) no renderizan nada", () => {
    const { container } = render(<TerminalPanel state={{ status: RUN_STATUS.STREAMING }} onRestart={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("no_evidence muestra solo sugerencias seguras y entrega la elegida", async () => {
    const user = userEvent.setup();
    const onAddManualSource = vi.fn(() => true);
    render(
      <TerminalPanel
        state={{
          status: RUN_STATUS.NO_EVIDENCE,
          noEvidenceReport: { external_sources: [safeSuggestion] },
        }}
        onRestart={() => {}}
        onAddManualSource={onAddManualSource}
      />,
    );

    expect(screen.getByRole("heading", { name: "Fuentes oficiales sugeridas" })).toBeInTheDocument();
    expect(screen.getByText(safeSuggestion.entidad)).toBeInTheDocument();
    expect(screen.getByText(safeSuggestion.por_que)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: `Abrir ${safeSuggestion.entidad}` })).toHaveAttribute("href", safeSuggestion.url);
    expect(screen.getByRole("link", { name: `Abrir ${safeSuggestion.entidad}` })).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: `Abrir ${safeSuggestion.entidad}` })).toHaveAttribute("rel", "noopener noreferrer");
    await user.click(screen.getByRole("button", { name: "Agregar manualmente" }));
    expect(onAddManualSource).toHaveBeenCalledWith(safeSuggestion);
  });

  it.each([
    [RUN_STATUS.NO_EVIDENCE, []],
    [RUN_STATUS.NO_EVIDENCE, [{ ...safeSuggestion, url: "javascript:alert(1)" }]],
    [RUN_STATUS.COMPLETED, [safeSuggestion]],
  ])("status=%s con fuentes %j no muestra la acción", (status, externalSources) => {
    render(
      <TerminalPanel
        state={{ status, noEvidenceReport: { external_sources: externalSources } }}
        onRestart={() => {}}
        onAddManualSource={() => true}
      />,
    );
    expect(screen.queryByRole("button", { name: "Agregar manualmente" })).not.toBeInTheDocument();
  });

  it("un secreto en clave aditiva no llega al DOM", () => {
    const secret = "cdt_rt_external_source_sintetico";
    const { container } = render(
      <TerminalPanel
        state={{
          status: RUN_STATUS.NO_EVIDENCE,
          noEvidenceReport: { external_sources: [{ ...safeSuggestion, metadata: secret }] },
        }}
        onRestart={() => {}}
        onAddManualSource={() => true}
      />,
    );
    expect(container).not.toHaveTextContent(secret);
    expect(screen.queryByRole("button", { name: "Agregar manualmente" })).not.toBeInTheDocument();
  });

  it("si no existe una sección válida orienta sin declarar inserción", async () => {
    const user = userEvent.setup();
    render(
      <TerminalPanel
        state={{
          status: RUN_STATUS.NO_EVIDENCE,
          noEvidenceReport: { external_sources: [safeSuggestion] },
        }}
        onRestart={() => {}}
        onAddManualSource={() => false}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Agregar manualmente" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Usa “Agregar dato manual” en la sección donde quieres incorporar el aporte.",
    );
  });
});

describe("QuestionComposer", () => {
  it("label visible asociado al textarea, pregunta obligatoria", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<QuestionComposer onSubmit={onSubmit} consentGranted />);
    const textarea = screen.getByLabelText("Pregunta para investigar");
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("obligatoria");
    await user.type(textarea, "corta");
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("con consentimiento y pregunta válida, envía question/contextHint acotados", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<QuestionComposer onSubmit={onSubmit} consentGranted initialContextHint="Sección: Diagnóstico" />);
    await user.type(screen.getByLabelText("Pregunta para investigar"), "¿Cuál es la tasa de deserción escolar en Sonsón?");
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    expect(onSubmit).toHaveBeenCalledWith({
      question: "¿Cuál es la tasa de deserción escolar en Sonsón?",
      contextHint: "Sección: Diagnóstico",
    });
  });

  it("bloquea el submit sin consentimiento, sin invocar onSubmit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<QuestionComposer onSubmit={onSubmit} consentGranted={false} />);
    await user.type(screen.getByLabelText("Pregunta para investigar"), "¿Cuál es la tasa de deserción escolar en Sonsón?");
    await user.click(screen.getByRole("button", { name: "Investigar" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

function CopilotHarness() {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Abrir copiloto
      </button>
      <CopilotPanel open={open} onClose={() => setOpen(false)} title="Copiloto">
        <p>Contenido del copiloto</p>
      </CopilotPanel>
    </div>
  );
}

function mockDesktop(matches) {
  window.matchMedia = (query) => ({
    matches,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  });
}

describe("CopilotPanel", () => {
  it("<1024px (drawer): botón de apertura revela el panel, Cerrar devuelve el foco", async () => {
    mockDesktop(false);
    const user = userEvent.setup();
    render(<CopilotHarness />);
    const openBtn = screen.getByRole("button", { name: "Abrir copiloto" });
    await user.click(openBtn);
    await screen.findByText("Contenido del copiloto");

    const closeBtn = screen.getByRole("button", { name: "Cerrar" });
    await user.click(closeBtn);
    expect(screen.queryByText("Contenido del copiloto")).not.toBeInTheDocument();
    expect(openBtn).toHaveFocus();
  });

  it("≥1024px (panel lateral): botón de apertura revela el panel, Cerrar copiloto devuelve el foco", async () => {
    mockDesktop(true);
    const user = userEvent.setup();
    render(<CopilotHarness />);
    const openBtn = screen.getByRole("button", { name: "Abrir copiloto" });
    await user.click(openBtn);
    expect(screen.getByText("Contenido del copiloto")).toBeVisible();

    const closeBtn = screen.getByRole("button", { name: "Cerrar copiloto" });
    await user.click(closeBtn);
    expect(screen.queryByText("Contenido del copiloto")).not.toBeInTheDocument();
    expect(openBtn).toHaveFocus();
  });
});
