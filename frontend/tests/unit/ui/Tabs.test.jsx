import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tabs } from "../../../components/ui/Tabs";

const ITEMS = [
  { id: "a", label: "Resumen", content: <p>Panel A</p> },
  { id: "b", label: "Detalle", content: <p>Panel B</p> },
  { id: "c", label: "Historial", content: <p>Panel C</p> },
];

describe("Tabs", () => {
  it("roles tablist/tab/tabpanel con aria-selected y aria-controls consistentes", () => {
    render(<Tabs items={ITEMS} />);
    const tablist = screen.getByRole("tablist");
    const tabs = screen.getAllByRole("tab");
    expect(tablist).toBeInTheDocument();
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", tabs[0].id);
    expect(tabs[0]).toHaveAttribute("aria-controls", panel.id);
  });

  it("clic selecciona la pestaña y revela su panel", async () => {
    const user = userEvent.setup();
    render(<Tabs items={ITEMS} />);
    await user.click(screen.getByRole("tab", { name: "Detalle" }));
    expect(screen.getByRole("tab", { name: "Detalle" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Panel B")).toBeVisible();
  });

  it("flecha derecha/izquierda mueve selección y foco (tabindex progresivo)", async () => {
    const user = userEvent.setup();
    render(<Tabs items={ITEMS} />);
    const first = screen.getByRole("tab", { name: "Resumen" });
    const second = screen.getByRole("tab", { name: "Detalle" });
    expect(first).toHaveAttribute("tabIndex", "0");
    expect(second).toHaveAttribute("tabIndex", "-1");

    first.focus();
    await user.keyboard("{ArrowRight}");
    expect(second).toHaveFocus();
    expect(second).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowLeft}");
    expect(first).toHaveFocus();
  });

  it("Home y End saltan al primer y último tab", async () => {
    const user = userEvent.setup();
    render(<Tabs items={ITEMS} />);
    const first = screen.getByRole("tab", { name: "Resumen" });
    const last = screen.getByRole("tab", { name: "Historial" });

    first.focus();
    await user.keyboard("{End}");
    expect(last).toHaveFocus();

    await user.keyboard("{Home}");
    expect(first).toHaveFocus();
  });

  it("los paneles no activos quedan ocultos (hidden), no desmontados sin más", () => {
    render(<Tabs items={ITEMS} />);
    expect(screen.getByText("Panel A")).toBeVisible();
    expect(screen.getByText("Panel B")).not.toBeVisible();
    expect(screen.getByText("Panel C")).not.toBeVisible();
  });
});
