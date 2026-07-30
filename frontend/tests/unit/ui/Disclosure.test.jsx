import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Disclosure } from "../../../components/ui/Disclosure";

describe("Disclosure", () => {
  it("empieza cerrado por defecto: aria-expanded=false y panel oculto", () => {
    render(
      <Disclosure summary="Ver detalle técnico">
        <p>Contenido secundario</p>
      </Disclosure>
    );
    const button = screen.getByRole("button", { name: "Ver detalle técnico" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Contenido secundario")).not.toBeVisible();
  });

  it("un botón real con aria-controls apuntando al panel — operable con teclado (Enter/Espacio nativos)", async () => {
    const user = userEvent.setup();
    render(
      <Disclosure summary="Ver detalle técnico">
        <p>Contenido secundario</p>
      </Disclosure>
    );
    const button = screen.getByRole("button", { name: "Ver detalle técnico" });
    const controlsId = button.getAttribute("aria-controls");
    expect(controlsId).toBeTruthy();
    expect(document.getElementById(controlsId)).toContainElement(screen.getByText("Contenido secundario"));

    button.focus();
    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Contenido secundario")).toBeVisible();

    await user.keyboard(" ");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("defaultOpen=true empieza expandido", () => {
    render(
      <Disclosure summary="Resumen" defaultOpen>
        <p>Ya visible</p>
      </Disclosure>
    );
    expect(screen.getByRole("button", { name: "Resumen" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Ya visible")).toBeVisible();
  });
});
