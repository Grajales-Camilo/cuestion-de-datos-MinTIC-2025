import { describe, expect, it } from "vitest";
import { resolveBackendUrl } from "../../lib/config/backendUrl.js";

describe("resolveBackendUrl", () => {
  it("acepta una URL http válida y la deja igual", () => {
    expect(
      resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "http://localhost:8000" })
    ).toBe("http://localhost:8000");
  });

  it("acepta https", () => {
    expect(
      resolveBackendUrl({
        NEXT_PUBLIC_BACKEND_URL: "https://api.cuestiondedatos.com",
      })
    ).toBe("https://api.cuestiondedatos.com");
  });

  it("normaliza la barra final", () => {
    expect(
      resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "http://localhost:8000/" })
    ).toBe("http://localhost:8000");
  });

  it("nunca hace fallback silencioso: lanza si falta la variable", () => {
    expect(() => resolveBackendUrl({})).toThrow(/NEXT_PUBLIC_BACKEND_URL/);
    expect(() => resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "" })).toThrow();
    expect(() => resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "   " })).toThrow();
  });

  it("el mensaje de error no incluye el objeto env completo ni otros secretos presentes en él", () => {
    let thrown;
    try {
      resolveBackendUrl({
        OTHER_SECRET_KEY: "sk-super-secreto-no-relacionado",
      });
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeDefined();
    expect(thrown.message).not.toContain("sk-super-secreto-no-relacionado");
    expect(thrown.message).not.toContain("OTHER_SECRET_KEY");
  });

  it("rechaza esquemas distintos de http/https", () => {
    expect(() =>
      resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "ftp://localhost:8000" })
    ).toThrow();
    expect(() =>
      resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "ws://localhost:8000" })
    ).toThrow();
  });

  it("rechaza credenciales embebidas sin filtrarlas en el mensaje", () => {
    let thrown;
    try {
      resolveBackendUrl({
        NEXT_PUBLIC_BACKEND_URL: "http://usuario:claveSecreta@localhost:8000",
      });
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeDefined();
    expect(thrown.message).not.toContain("claveSecreta");
    expect(thrown.message).not.toContain("usuario:claveSecreta");
  });

  it("rechaza query string", () => {
    expect(() =>
      resolveBackendUrl({
        NEXT_PUBLIC_BACKEND_URL: "http://localhost:8000?debug=1",
      })
    ).toThrow();
  });

  it("rechaza fragmento (#)", () => {
    expect(() =>
      resolveBackendUrl({
        NEXT_PUBLIC_BACKEND_URL: "http://localhost:8000#seccion",
      })
    ).toThrow();
  });

  it("rechaza cualquier ruta distinta de la raíz", () => {
    expect(() =>
      resolveBackendUrl({
        NEXT_PUBLIC_BACKEND_URL: "http://localhost:8000/v2",
      })
    ).toThrow();
  });

  it("rechaza texto que no es una URL en absoluto", () => {
    expect(() =>
      resolveBackendUrl({ NEXT_PUBLIC_BACKEND_URL: "esto no es una url" })
    ).toThrow();
  });
});
