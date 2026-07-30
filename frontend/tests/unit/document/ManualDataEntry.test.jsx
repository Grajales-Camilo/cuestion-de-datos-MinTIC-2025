import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ManualDataEntry } from "../../../components/canvas/ManualDataEntry";

function Harness({ onSubmit = vi.fn(() => true), initialValues = null }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="cdt-v2">
      <button type="button" onClick={() => setOpen(true)}>
        Abrir aporte manual
      </button>
      <ManualDataEntry
        open={open}
        onClose={() => setOpen(false)}
        onSubmit={onSubmit}
        sectionTitle="Sección sintética"
        initialValues={initialValues}
      />
    </div>
  );
}

async function openForm(user) {
  const trigger = screen.getByRole("button", { name: "Abrir aporte manual" });
  await user.click(trigger);
  await screen.findByRole("dialog", { name: "Agregar dato manual" });
  return trigger;
}

describe("ManualDataEntry — F7-02A, RF-102, ESC-08, RNF-007/RNF-012", () => {
  it("prellena solo fuente y URL, muestra por_que como contexto y permite editar", async () => {
    const user = userEvent.setup();
    const initialValues = {
      entidad: "Entidad pública sintética",
      url: "https://datos.example.gov.co/fuente",
      por_que: "Puede contener el indicador solicitado.",
    };
    render(<Harness initialValues={initialValues} />);
    await openForm(user);

    expect(screen.getByLabelText("Valor (opcional)")).toHaveValue("");
    expect(screen.getByLabelText("Texto o descripción (opcional)")).toHaveValue("");
    expect(screen.getByLabelText(/^Fuente/)).toHaveValue(initialValues.entidad);
    expect(screen.getByLabelText("URL de la fuente (opcional)")).toHaveValue(initialValues.url);
    expect(screen.getByLabelText("Fecha de la fuente (opcional)")).toHaveValue("");
    expect(screen.getByText(initialValues.por_que)).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/^Fuente/));
    await user.type(screen.getByLabelText(/^Fuente/), "Entidad editada por el usuario");
    expect(screen.getByLabelText(/^Fuente/)).toHaveValue("Entidad editada por el usuario");
  });

  it("expone campos accesibles y conserva el valor literal", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(() => true);
    render(<Harness onSubmit={onSubmit} />);
    await openForm(user);

    await user.type(screen.getByLabelText("Valor (opcional)"), "17,50 unidades");
    await user.type(screen.getByLabelText(/^Fuente/), "Fuente sintética");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ value: "17,50 unidades", source: "Fuente sintética" }),
    );
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty("manualEntryId");
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty("createdAt");
  });

  it("requiere fuente y al menos valor o texto", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(() => true);
    render(<Harness onSubmit={onSubmit} />);
    await openForm(user);

    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));
    expect(screen.getByText("Escribe un valor o una descripción.")).toBeInTheDocument();
    expect(screen.getByText("La fuente es obligatoria.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Valor (opcional)"), "dato sintético");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));
    expect(screen.getByText("La fuente es obligatoria.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rechaza URL insegura con mensaje fijo y no inserta", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(() => true);
    render(<Harness onSubmit={onSubmit} />);
    await openForm(user);

    await user.type(screen.getByLabelText("Texto o descripción (opcional)"), "Descripción sintética");
    await user.type(screen.getByLabelText(/^Fuente/), "Fuente sintética");
    await user.type(screen.getByLabelText("URL de la fuente (opcional)"), "javascript:alert(1)");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));

    expect(screen.getByText("La URL debe ser una dirección HTTPS segura y absoluta.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("muestra un mensaje seguro ante token y nunca filtra el contenido", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(() => true);
    render(<Harness onSubmit={onSubmit} />);
    await openForm(user);

    const token = "cdt_rt_manual_sintetico_no_debe_persistir";
    await user.type(screen.getByLabelText("Texto o descripción (opcional)"), token);
    await user.type(screen.getByLabelText(/^Fuente/), "Fuente sintética");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));

    expect(
      screen.getByText("No pudimos guardar el aporte porque contiene información sensible."),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).not.toHaveTextContent(token);
    expect(screen.getByLabelText("Texto o descripción (opcional)")).toHaveValue(token);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("cancelar y Escape no insertan y restauran el foco al disparador", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(() => true);
    render(<Harness onSubmit={onSubmit} />);
    const trigger = await openForm(user);

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog", { name: "Agregar dato manual" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(onSubmit).not.toHaveBeenCalled();

    await openForm(user);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Agregar dato manual" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("mantiene el formulario abierto cuando la inserción falla", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(() => false);
    render(<Harness onSubmit={onSubmit} />);
    await openForm(user);

    await user.type(screen.getByLabelText("Valor (opcional)"), "dato sintético");
    await user.type(screen.getByLabelText(/^Fuente/), "Fuente sintética");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog", { name: "Agregar dato manual" })).toBeInTheDocument();
    expect(screen.getByText("No pudimos guardar el aporte. El documento no cambió.")).toBeInTheDocument();
  });

  it.each([
    ["devuelve un valor distinto de true", vi.fn(() => "ok")],
    ["no recibe una función", null],
  ])("no declara éxito si onSubmit %s", async (_caseName, onSubmit) => {
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);
    await openForm(user);

    await user.type(screen.getByLabelText("Valor (opcional)"), "dato sintético");
    await user.type(screen.getByLabelText(/^Fuente/), "Fuente sintética");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));

    expect(screen.getByRole("dialog", { name: "Agregar dato manual" })).toBeInTheDocument();
    expect(screen.getByText("No pudimos guardar el aporte. El documento no cambió.")).toBeInTheDocument();
  });
});
