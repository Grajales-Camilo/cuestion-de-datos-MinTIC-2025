import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConsentDialog, CONSENT_TITLE } from "../../../components/consent/ConsentDialog";

function renderDialog(props = {}) {
  return render(
    <ConsentDialog
      open
      draft={{ question: "¿Cuál es la tasa de deserción escolar en Sonsón?", contextHint: "contexto de la sección" }}
      rememberRuns={false}
      onRememberRunsChange={vi.fn()}
      onAccept={vi.fn()}
      onCancel={vi.fn()}
      {...props}
    />
  );
}

describe("ConsentDialog — texto literal D-9", () => {
  it("muestra el título exacto y los tres párrafos del texto aprobado", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: CONSENT_TITLE })).toBeInTheDocument();
    expect(
      screen.getByText(/Cuestión de Datos enviará y almacenará tu pregunta/)
    ).toBeInTheDocument();
    expect(screen.getByText(/se conservan hasta 90 días/)).toBeInTheDocument();
    expect(screen.getByText(/El documento completo en el que trabajas no se envía al servidor\./)).toBeInTheDocument();
  });

  it("muestra la pregunta exacta y el contexto exacto que se enviará", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByText("¿Cuál es la tasa de deserción escolar en Sonsón?")).toBeInTheDocument();
    expect(screen.getByLabelText("Contexto que se enviará (editable)")).toHaveValue("contexto de la sección");
  });

  it("el opt-in aparece desmarcado por defecto", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByRole("checkbox", { name: /Recordar mis investigaciones/ })).not.toBeChecked();
  });
});

describe("ConsentDialog — truncamiento", () => {
  it("un contextHint > 2000 caracteres muestra el aviso de truncamiento", async () => {
    const long = "palabra ".repeat(300);
    renderDialog({ draft: { question: "¿Pregunta válida y suficientemente larga?", contextHint: long } });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("se acortó");
  });
});

describe("ConsentDialog — aceptar y cancelar", () => {
  it("Aceptar e investigar llama onAccept con el contexto editado", async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();
    renderDialog({ onAccept });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    const contextArea = screen.getByLabelText("Contexto que se enviará (editable)");
    await user.clear(contextArea);
    await user.type(contextArea, "contexto editado en el modal");
    await user.click(screen.getByRole("button", { name: "Aceptar e investigar" }));

    expect(onAccept).toHaveBeenCalledWith({ contextHint: "contexto editado en el modal" });
  });

  it("Cancelar llama onCancel sin llamar onAccept", async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();
    const onCancel = vi.fn();
    renderDialog({ onAccept, onCancel });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onAccept).not.toHaveBeenCalled();
  });

  it("Escape llama onCancel (heredado de Modal)", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderDialog({ onCancel });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("el foco inicial nunca cae en 'Aceptar e investigar' (sin aceptación implícita)", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    const acceptButton = screen.getByRole("button", { name: "Aceptar e investigar" });
    expect(document.activeElement).not.toBe(acceptButton);
  });

  it("checkbox del opt-in invoca onRememberRunsChange", async () => {
    const user = userEvent.setup();
    const onRememberRunsChange = vi.fn();
    renderDialog({ onRememberRunsChange });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    await user.click(screen.getByRole("checkbox", { name: /Recordar mis investigaciones/ }));
    expect(onRememberRunsChange).toHaveBeenCalledWith(true);
  });
});

describe("ConsentDialog — cerrado", () => {
  it("open=false no renderiza el diálogo", () => {
    renderDialog({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
