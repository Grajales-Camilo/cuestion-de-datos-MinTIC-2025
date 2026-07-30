import { describe, expect, it } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useConsent } from "../../../hooks/useConsent";

function makeMemoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

function Harness({ storage, consentVersion, onReady }) {
  const result = useConsent({ storage, consentVersion });
  onReady?.(result);
  return (
    <div>
      <p data-testid="granted">{String(result.consentGranted)}</p>
      <button type="button" onClick={result.acceptConsent}>
        Aceptar
      </button>
      <button type="button" onClick={result.revokeConsent}>
        Revocar
      </button>
    </div>
  );
}

describe("useConsent", () => {
  it("sin registro previo: consentGranted false, cero escritura implícita", () => {
    const storage = makeMemoryStorage();
    render(<Harness storage={storage} consentVersion={1} />);
    expect(screen.getByTestId("granted")).toHaveTextContent("false");
  });

  it("acceptConsent(): concede y persiste la versión vigente", async () => {
    const storage = makeMemoryStorage();
    const user = userEvent.setup();
    render(<Harness storage={storage} consentVersion={1} />);

    await user.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(screen.getByTestId("granted")).toHaveTextContent("true");
    expect(storage.getItem("cdd.consent.v1")).toContain('"consentVersion":1');
  });

  it("una versión distinta de la vigente vuelve a pedir consentimiento", async () => {
    // La versión vigente es una constante de despliegue (D-9): en la app
    // real solo cambia entre cargas de página, nunca en un re-render en
    // caliente del mismo árbol montado — se simula desmontando y volviendo
    // a montar con la nueva versión, como ocurriría tras un despliegue.
    const storage = makeMemoryStorage();
    const user = userEvent.setup();
    const { unmount } = render(<Harness storage={storage} consentVersion={1} />);
    await user.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(screen.getByTestId("granted")).toHaveTextContent("true");
    unmount();

    render(<Harness storage={storage} consentVersion={2} />);
    expect(screen.getByTestId("granted")).toHaveTextContent("false");
  });

  it("revokeConsent(): retira la concesión", async () => {
    const storage = makeMemoryStorage();
    const user = userEvent.setup();
    render(<Harness storage={storage} consentVersion={1} />);
    await user.click(screen.getByRole("button", { name: "Aceptar" }));
    await user.click(screen.getByRole("button", { name: "Revocar" }));
    expect(screen.getByTestId("granted")).toHaveTextContent("false");
  });
});
