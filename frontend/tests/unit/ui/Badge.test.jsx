import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "../../../components/ui/Badge";

describe("Badge — el significado nunca depende solo del color", () => {
  it.each([
    ["verified", "Verificado"],
    ["no_evidence", "Sin evidencia elegible"],
    ["interrupted", "Interrumpido"],
    ["warning", "Advertencia"],
    ["failed", "Fallido"],
  ])("status=%s muestra texto visible (%s) además de un icono", (status, expectedText) => {
    render(<Badge status={status} />);
    expect(screen.getByText(expectedText)).toBeInTheDocument();
    // El icono SVG de lucide-react se marca aria-hidden; sigue presente en el DOM.
    const badge = screen.getByText(expectedText).closest("span");
    expect(badge.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("no_evidence usa tratamiento neutral (azul), nunca la clase de error", () => {
    render(<Badge status="no_evidence" />);
    const badge = screen.getByText("Sin evidencia elegible").closest("span");
    expect(badge.className).toMatch(/bg-cdt-blue-50/);
    expect(badge.className).not.toMatch(/bg-cdt-error/);
  });

  it("failed usa la clase de error, no la de éxito ni advertencia", () => {
    render(<Badge status="failed" />);
    const badge = screen.getByText("Fallido").closest("span");
    expect(badge.className).toMatch(/bg-cdt-error/);
  });

  it("acepta texto propio en vez del label por defecto", () => {
    render(<Badge status="verified">Dato verificado con Socrata</Badge>);
    expect(screen.getByText("Dato verificado con Socrata")).toBeInTheDocument();
  });

  it("un status desconocido lanza en vez de mostrarse en silencio", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Badge status="inventado" />)).toThrow();
    spy.mockRestore();
  });
});
