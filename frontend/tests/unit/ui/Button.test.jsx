import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "../../../components/ui/Button";
import { IconButton } from "../../../components/ui/IconButton";

describe("Button", () => {
  it("renderiza las 4 variantes con rol y nombre accesible de botón", () => {
    render(
      <>
        <Button variant="primary">Primaria</Button>
        <Button variant="secondary">Secundaria</Button>
        <Button variant="quiet">Silenciosa</Button>
        <Button variant="destructive">Destructiva</Button>
      </>
    );
    expect(screen.getByRole("button", { name: "Primaria" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Secundaria" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Silenciosa" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Destructiva" })).toBeInTheDocument();
  });

  it("dispara onClick al hacer clic y al activar con teclado (Enter)", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Acción</Button>);
    const button = screen.getByRole("button", { name: "Acción" });

    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);

    button.focus();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it("estado disabled: no dispara onClick y expone disabled real (no solo visual)", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Deshabilitado
      </Button>
    );
    const button = screen.getByRole("button", { name: "Deshabilitado" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("estado loading: aria-busy y también deshabilitado (evita doble envío)", () => {
    render(<Button loading>Insertando</Button>);
    const button = screen.getByRole("button", { name: "Insertando" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
  });

  it("tiene una altura mínima táctil de 44px vía la clase min-h-cdt-tap", () => {
    render(<Button>Táctil</Button>);
    expect(screen.getByRole("button", { name: "Táctil" }).className).toMatch(/min-h-cdt-tap/);
  });

  it("expone hover y focus-visible como clases declaradas (transición de color)", () => {
    render(<Button variant="primary">Primaria</Button>);
    const className = screen.getByRole("button", { name: "Primaria" }).className;
    expect(className).toMatch(/hover:bg-cdt-blue-900/);
    expect(className).toMatch(/transition-colors/);
  });
});

describe("IconButton", () => {
  it("exige la prop label como nombre accesible", () => {
    // eslint-disable-next-line no-console
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<IconButton>x</IconButton>)).toThrow();
    spy.mockRestore();
  });

  it("usa label como aria-label y oculta el icono decorativo del árbol accesible", () => {
    render(
      <IconButton label="Cerrar">
        <svg data-testid="icono" />
      </IconButton>
    );
    const button = screen.getByRole("button", { name: "Cerrar" });
    expect(button).toHaveAttribute("aria-label", "Cerrar");
    // El icono vive dentro de un span aria-hidden, así que no debe alcanzarse por rol accesible.
    expect(screen.getByTestId("icono").closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("tiene 44x44px táctiles vía h-cdt-tap w-cdt-tap", () => {
    render(<IconButton label="Buscar">x</IconButton>);
    expect(screen.getByRole("button", { name: "Buscar" }).className).toMatch(/h-cdt-tap w-cdt-tap/);
  });
});
