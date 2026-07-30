import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TemplatePicker } from "../../../components/document/TemplatePicker";
import {
  APPROVED_TEMPLATE_IDS,
  FREE_TEMPLATE_ID,
  MGA_TEMPLATE_ID,
  PLAN_DE_DESARROLLO_TEMPLATE_ID,
} from "../../../lib/document/documentModel";

describe("TemplatePicker — RF-101-02", () => {
  it("renderiza exactamente las tres opciones aprobadas, con etiquetas visibles Libre/MGA/Plan de desarrollo", () => {
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);

    expect(screen.getByRole("radio", { name: /Libre/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^MGA/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Plan de desarrollo/ })).toBeInTheDocument();
  });

  it("ninguna opción empieza seleccionada", () => {
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
    }
  });

  it("el botón 'Crear documento' comienza deshabilitado", () => {
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Crear documento" })).toBeDisabled();
  });

  it("seleccionar por CLICK marca la opción, desmarca las demás, y habilita 'Crear documento'", async () => {
    const user = userEvent.setup();
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    const mgaRadio = screen.getByRole("radio", { name: /^MGA/ });
    await user.click(mgaRadio);

    expect(mgaRadio).toBeChecked();
    expect(screen.getByRole("radio", { name: /Libre/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Plan de desarrollo/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Crear documento" })).toBeEnabled();
  });

  it("seleccionar por TECLADO (flechas dentro del grupo nativo de radios) actualiza el estado accesible", async () => {
    const user = userEvent.setup();
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    const freeRadio = screen.getByRole("radio", { name: /Libre/ });
    freeRadio.focus();
    expect(freeRadio).toHaveFocus();

    // Flecha derecha dentro de un grupo nativo de radios (mismo `name`) mueve
    // el foco Y la selección al siguiente radio del grupo — comportamiento
    // del navegador, no reimplementado a mano.
    await user.keyboard("[ArrowRight]");

    const mgaRadio = screen.getByRole("radio", { name: /^MGA/ });
    expect(mgaRadio).toBeChecked();
    expect(mgaRadio).toHaveFocus();
    expect(freeRadio).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Crear documento" })).toBeEnabled();
  });

  it("confirmar llama a onCreateDocument UNA SOLA VEZ, con el templateId EXACTO de la opción elegida", async () => {
    const user = userEvent.setup();
    const onCreateDocument = vi.fn();
    render(<TemplatePicker onCreateDocument={onCreateDocument} />);

    await user.click(screen.getByRole("radio", { name: /Plan de desarrollo/ }));
    await user.click(screen.getByRole("button", { name: "Crear documento" }));

    expect(onCreateDocument).toHaveBeenCalledTimes(1);
    expect(onCreateDocument).toHaveBeenCalledWith(PLAN_DE_DESARROLLO_TEMPLATE_ID);
  });

  it.each([
    [/Libre/, FREE_TEMPLATE_ID],
    [/^MGA/, MGA_TEMPLATE_ID],
    [/Plan de desarrollo/, PLAN_DE_DESARROLLO_TEMPLATE_ID],
  ])("confirmar la opción '%s' llama a onCreateDocument con '%s'", async (namePattern, expectedId) => {
    const user = userEvent.setup();
    const onCreateDocument = vi.fn();
    render(<TemplatePicker onCreateDocument={onCreateDocument} />);

    await user.click(screen.getByRole("radio", { name: namePattern }));
    await user.click(screen.getByRole("button", { name: "Crear documento" }));

    expect(onCreateDocument).toHaveBeenCalledTimes(1);
    expect(onCreateDocument).toHaveBeenCalledWith(expectedId);
  });

  it("hacer click en el botón deshabilitado (sin selección previa) NUNCA llama a onCreateDocument", async () => {
    const user = userEvent.setup();
    const onCreateDocument = vi.fn();
    render(<TemplatePicker onCreateDocument={onCreateDocument} />);

    // Un botón `disabled` no dispara `click`/`submit` nativos; se verifica
    // de todos modos como regresión explícita del contrato "deshabilitado
    // hasta seleccionar".
    await user.click(screen.getByRole("button", { name: "Crear documento" }));

    expect(onCreateDocument).not.toHaveBeenCalled();
  });

  it("no acepta ni genera IDs legacy: los tres radios tienen EXACTAMENTE los valores de APPROVED_TEMPLATE_IDS, ningún otro", () => {
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    const values = screen.getAllByRole("radio").map((radio) => radio.value);
    expect(values.sort()).toEqual([...APPROVED_TEMPLATE_IDS].sort());
    expect(values).not.toContain("conpes");
    expect(values).not.toContain("policy_brief");
    expect(values).not.toContain("mga-legacy");
  });

  it("las tres opciones comparten el mismo `name` (mutuamente excluyentes, radiogroup real vía fieldset/legend)", () => {
    const { container } = render(<TemplatePicker onCreateDocument={vi.fn()} />);

    const radios = screen.getAllByRole("radio");
    const names = new Set(radios.map((radio) => radio.name));
    expect(names.size).toBe(1);

    const fieldset = container.querySelector("fieldset");
    expect(fieldset).not.toBeNull();
    expect(fieldset.querySelector("legend")).not.toBeNull();
    expect(fieldset.querySelector("legend").textContent).toMatch(/Elige una plantilla/);
  });

  it("la selección nunca depende solo del color: la opción elegida muestra un icono adicional visible", async () => {
    const user = userEvent.setup();
    render(<TemplatePicker onCreateDocument={vi.fn()} />);

    const mgaLabel = screen.getByRole("radio", { name: /^MGA/ }).closest("label");
    expect(mgaLabel.querySelector("svg")).toBeNull(); // sin seleccionar: sin icono

    await user.click(screen.getByRole("radio", { name: /^MGA/ }));

    expect(mgaLabel.querySelector("svg")).not.toBeNull(); // seleccionada: icono presente
  });
});
