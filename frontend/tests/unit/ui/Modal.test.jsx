import { useRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Modal } from "../../../components/ui/Modal";

function Harness({ initialOpen = false }) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Abrir
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title="Confirmar">
        <button type="button">Primero</button>
        <button type="button">Segundo</button>
      </Modal>
    </div>
  );
}

function RestoreControlHarness() {
  const [open, setOpen] = useState(false);
  const restoreFocusRef = useRef(true);
  return (
    <div>
      <button type="button" onClick={() => {
        restoreFocusRef.current = true;
        setOpen(true);
      }}>
        Abrir controlado
      </button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Confirmar foco"
        restoreFocusRef={restoreFocusRef}
      >
        <button type="button" onClick={() => {
          restoreFocusRef.current = false;
          setOpen(false);
        }}>
          Cerrar sin restaurar
        </button>
      </Modal>
    </div>
  );
}

describe("Modal", () => {
  afterEach(() => {
    document.body.style.overflow = "";
  });

  it("role=dialog, aria-modal=true y nombre accesible obligatorio (title)", async () => {
    render(<Harness />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Abrir" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirmar" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("foco inicial predecible: cae en el primer elemento enfocable del diálogo", async () => {
    render(<Harness />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Abrir" }));
    await screen.findByRole("dialog");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cerrar" })).toHaveFocus();
    });
  });

  it("trampa de foco: Tab desde el último elemento vuelve al primero, y viceversa", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    await screen.findByRole("dialog");

    const closeBtn = screen.getByRole("button", { name: "Cerrar" });
    const first = screen.getByRole("button", { name: "Primero" });
    const second = screen.getByRole("button", { name: "Segundo" });

    await waitFor(() => expect(closeBtn).toHaveFocus());
    await user.tab();
    expect(first).toHaveFocus();
    await user.tab();
    expect(second).toHaveFocus();
    await user.tab(); // sale del último -> vuelve al primero (Cerrar)
    expect(closeBtn).toHaveFocus();

    await user.tab({ shift: true }); // Mayús+Tab desde el primero -> va al último
    expect(second).toHaveFocus();
  });

  it("Escape cierra el modal", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("restaura el foco al elemento que abrió el modal, al cerrarse", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const openBtn = screen.getByRole("button", { name: "Abrir" });
    await user.click(openBtn);
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(openBtn).toHaveFocus());
  });

  it("restoreFocusRef.current=false evita restaurar el disparador", async () => {
    const user = userEvent.setup();
    render(<RestoreControlHarness />);
    const trigger = screen.getByRole("button", { name: "Abrir controlado" });
    await user.click(trigger);
    await screen.findByRole("dialog", { name: "Confirmar foco" });
    await user.click(screen.getByRole("button", { name: "Cerrar sin restaurar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).not.toHaveFocus();
  });

  it("bloquea y restaura el scroll del body sin dejarlo huérfano", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(document.body.style.overflow).toBe("");
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    await screen.findByRole("dialog");
    expect(document.body.style.overflow).toBe("hidden");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(document.body.style.overflow).toBe(""));
  });

  it("closed (open=false): no se monta nada en el DOM (sin portal huérfano)", () => {
    render(<Modal open={false} onClose={() => {}} title="Nunca visible" />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("initialOpen=true: el foco inicial cae en el diálogo también cuando `open` ya es true en el primer render", async () => {
    // Regresión F1-R1: el efecto de foco corría antes de que el portal
    // existiera cuando `open` ya era `true` desde el montaje, y nunca se
    // repetía porque su dependencia `open` no cambiaba después. Esta
    // prueba habría fallado con el código anterior (el foco se habría
    // quedado en `document.body`, no en el botón "Cerrar").
    render(<Harness initialOpen />);
    await screen.findByRole("dialog");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cerrar" })).toHaveFocus();
    });
  });

  it("exige un título accesible no vacío: title='' lanza en vez de renderizar un diálogo sin nombre", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Modal open onClose={() => {}} title="">contenido</Modal>)).toThrow();
    spy.mockRestore();
  });

  it("limpia el listener de teclado global al desmontar mientras está abierto", async () => {
    const removeSpy = vi.spyOn(document, "removeEventListener");
    const user = userEvent.setup();
    const { unmount } = render(<Harness initialOpen />);
    await screen.findByRole("dialog");
    unmount();
    expect(removeSpy).toHaveBeenCalledWith("keydown", expect.any(Function));
    removeSpy.mockRestore();
    void user;
  });
});
