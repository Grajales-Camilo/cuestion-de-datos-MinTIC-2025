import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Table } from "../../../components/ui/Table";

const COLUMNS = [{ key: "metric_avg_1", header: "metric_avg_1" }];
const ROWS = [{ metric_avg_1: "3.9660000000000000" }];

describe("Table", () => {
  it("expone un caption/nombre accesible", () => {
    render(<Table caption="1 fila devuelta por datos.gov.co" columns={COLUMNS} rows={ROWS} />);
    expect(screen.getByRole("table", { name: "1 fila devuelta por datos.gov.co" })).toBeInTheDocument();
  });

  it("usa encabezados semánticos con scope=col, no <div>", () => {
    render(<Table caption="Evidencia" columns={COLUMNS} rows={ROWS} />);
    const header = screen.getByRole("columnheader", { name: "metric_avg_1" });
    expect(header.tagName).toBe("TH");
    expect(header).toHaveAttribute("scope", "col");
  });

  it("renderiza las filas de datos reales sin transformarlas", () => {
    render(<Table caption="Evidencia" columns={COLUMNS} rows={ROWS} />);
    expect(screen.getByRole("cell", { name: "3.9660000000000000" })).toBeInTheDocument();
  });

  it("el contenedor tiene su propio scroll horizontal (overflow-x-auto), no la página", () => {
    const { container } = render(<Table caption="Evidencia" columns={COLUMNS} rows={ROWS} />);
    expect(container.firstChild.className).toMatch(/overflow-x-auto/);
  });

  it("admite render personalizado por columna", () => {
    render(
      <Table
        caption="Con render"
        columns={[{ key: "x", header: "X", render: (row) => `valor: ${row.x}` }]}
        rows={[{ x: 42 }]}
      />
    );
    expect(screen.getByRole("cell", { name: "valor: 42" })).toBeInTheDocument();
  });

  it("sin caption ni aria-label/aria-labelledby: lanza en vez de renderizar sin nombre accesible", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Table columns={COLUMNS} rows={ROWS} />)).toThrow();
    spy.mockRestore();
  });

  it("acepta aria-label como alternativa a caption, sin duplicarlo también en la tabla anidada", () => {
    render(<Table aria-label="Evidencia sin caption visible" columns={COLUMNS} rows={ROWS} />);
    const region = screen.getByRole("region", { name: "Evidencia sin caption visible" });
    expect(region).toBeInTheDocument();
    // La tabla anidada no debe repetir el mismo aria-label: sin caption,
    // no tiene nombre accesible propio (el nombre vive en la región).
    const table = screen.getByRole("table");
    expect(table).not.toHaveAttribute("aria-label");
  });

  it("el contenedor desplazable es una región enfocable por teclado (role=region, tabIndex=0)", async () => {
    const user = userEvent.setup();
    render(<Table caption="Evidencia" columns={COLUMNS} rows={ROWS} />);
    const region = screen.getByRole("region", { name: "Evidencia" });
    expect(region).toHaveAttribute("tabIndex", "0");
    await user.tab();
    expect(region).toHaveFocus();
  });
});
