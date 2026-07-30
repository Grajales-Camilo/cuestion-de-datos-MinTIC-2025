import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

describe("infraestructura de pruebas (F0)", () => {
  it("ejecuta aserciones de Vitest", () => {
    expect(1 + 1).toBe(2);
  });

  it("renderiza un componente React sobre jsdom con Testing Library", () => {
    render(<p>hola mundo</p>);
    expect(screen.getByText("hola mundo")).toBeInTheDocument();
  });
});
