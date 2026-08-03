import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QuestionComposer } from "../../../components/agent/QuestionComposer";

describe("QuestionComposer — normalización de contextHint (§3)", () => {
  it("initialContextHint > 2000 caracteres: se normaliza y muestra el aviso de truncamiento", () => {
    const long = "Sección ".repeat(300); // > 2000 caracteres
    render(<QuestionComposer onSubmit={vi.fn()} consentGranted initialContextHint={long} />);

    const textarea = screen.getByLabelText("Contexto de la sección (editable)");
    expect(textarea.value.length).toBeLessThanOrEqual(2000);
    expect(screen.getByRole("status")).toHaveTextContent("se acortó");
  });

  it("contexto por debajo del límite: sin aviso de truncamiento", () => {
    render(<QuestionComposer onSubmit={vi.fn()} consentGranted initialContextHint="Contexto breve." />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("el valor enviado a onSubmit es exactamente el mostrado en el textarea (byte a byte)", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<QuestionComposer onSubmit={onSubmit} consentGranted initialContextHint="Contexto de la sección X" />);

    await user.type(screen.getByLabelText("Pregunta para investigar"), "¿Cuál es la tasa de deserción escolar en Sonsón?");
    const contextArea = screen.getByLabelText("Contexto de la sección (editable)");
    await user.clear(contextArea);
    await user.type(contextArea, "contexto editado por el usuario");

    await user.click(screen.getByRole("button", { name: "Investigar" }));

    expect(onSubmit).toHaveBeenCalledWith({
      question: "¿Cuál es la tasa de deserción escolar en Sonsón?",
      contextHint: contextArea.value,
    });
    expect(contextArea.value).toBe("contexto editado por el usuario");
  });
});

function RefineHarness({ prefill }) {
  const [key] = useState(0);
  return <QuestionComposer onSubmit={vi.fn()} consentGranted prefill={key === 0 ? prefill : null} />;
}

describe("QuestionComposer — prefill (Refinar)", () => {
  it("aplica question/contextHint del prefill al montar", () => {
    render(
      <RefineHarness
        prefill={{ question: "¿Cuál es la cobertura educativa?", contextHint: "contexto previo", nonce: 1 }}
      />
    );
    expect(screen.getByLabelText("Pregunta para investigar")).toHaveValue("¿Cuál es la cobertura educativa?");
    expect(screen.getByLabelText("Contexto de la sección (editable)")).toHaveValue("contexto previo");
  });

  it("un nuevo nonce vuelve a aplicar el prefill aunque el componente ya esté montado", () => {
    function Wrapper() {
      const [prefill, setPrefill] = useState({ question: "pregunta original larga y válida", contextHint: "", nonce: 1 });
      return (
        <div>
          <QuestionComposer onSubmit={vi.fn()} consentGranted prefill={prefill} />
          <button
            type="button"
            onClick={() => setPrefill({ question: "otra pregunta distinta y también válida", contextHint: "", nonce: 2 })}
          >
            Cambiar
          </button>
        </div>
      );
    }
    render(<Wrapper />);
    expect(screen.getByLabelText("Pregunta para investigar")).toHaveValue("pregunta original larga y válida");
  });
});
