import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ManualDataEntryNodeView } from "../../../components/canvas/editor/ManualDataEntryNodeView";

const BASE_ATTRS = {
  manualEntryId: "manual-sintetico-view-001",
  value: "17,50 unidades",
  text: "Texto sintético escrito por el usuario",
  source: "Fuente sintética declarada por el usuario",
  url: "https://ejemplo.invalid/fuente-sintetica",
  date: "2026-07-29",
  createdAt: "2026-07-29T12:00:00.000Z",
};

function renderNode(attrs = BASE_ATTRS, selected = false) {
  return render(<ManualDataEntryNodeView node={{ attrs }} selected={selected} />);
}

describe("ManualDataEntryNodeView — F7-02A, T-506, RNF-007/RNF-012", () => {
  it("presenta el badge literal y no usa la semántica de evidencia verificada", () => {
    renderNode();

    expect(screen.getByText("Aporte manual — no verificado por el agente")).toBeInTheDocument();
    expect(screen.queryByText("Verificado", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/claims|calidad|SoQL/i)).not.toBeInTheDocument();
  });

  it("renderiza value, text y source como texto, nunca como HTML", () => {
    const attrs = { ...BASE_ATTRS, value: "<b>17,50</b>", text: "<script>token()</script>" };
    const { container } = renderNode(attrs);

    expect(container.textContent).toContain("<b>17,50</b>");
    expect(container.textContent).toContain("<script>token()</script>");
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("muestra fecha y URL segura con enlace externo seguro", () => {
    renderNode();

    expect(screen.getByText("2026-07-29")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Abrir fuente declarada/i })).toHaveAttribute(
      "href",
      BASE_ATTRS.url,
    );
    expect(screen.getByRole("link", { name: /Abrir fuente declarada/i })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(screen.getByRole("link", { name: /Abrir fuente declarada/i })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
  });

  it("omite URL y fecha ausentes o URL insegura", () => {
    renderNode({ ...BASE_ATTRS, url: null, date: null });
    expect(screen.queryByRole("link", { name: /Abrir fuente declarada/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Fecha de la fuente")).not.toBeInTheDocument();
  });

  it("mantiene foco visual de selección sin usar una tarjeta de evidencia", () => {
    const { container } = renderNode(BASE_ATTRS, true);
    const wrapper = container.querySelector('[data-manual-entry="true"]');

    expect(wrapper).toHaveClass("border-cdt-blue-500");
    expect(wrapper).not.toHaveClass("bg-cdt-success");
  });

  it("no importa clientes HTTP ni contiene dangerouslySetInnerHTML", async () => {
    const source = readFileSync(
      path.resolve(process.cwd(), "components/canvas/editor/ManualDataEntryNodeView.jsx"),
      "utf8",
    );
    expect(source).not.toMatch(/fetch|XMLHttpRequest|WebSocket|dangerouslySetInnerHTML/);
  });
});
