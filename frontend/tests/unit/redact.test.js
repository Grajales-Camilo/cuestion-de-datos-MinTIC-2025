import { describe, expect, it } from "vitest";
import { redact } from "../../lib/api/redact.js";

describe("redact", () => {
  it("sustituye el patrón cdt_rt_ dentro de una cadena", () => {
    const input = "el token fue cdt_rt_9f8aAB12_-xyz y siguió el texto";
    const out = redact(input);
    expect(out).not.toContain("cdt_rt_9f8aAB12_-xyz");
    expect(out).toContain("[REDACTADO]");
  });

  it("deja intacta una cadena sin el patrón", () => {
    expect(redact("texto normal sin secretos")).toBe("texto normal sin secretos");
  });

  it("redacta el valor completo de claves sensibles sin distinguir mayúsculas", () => {
    const input = {
      Authorization: "Bearer algo-que-no-es-cdt_rt",
      token: "valor-cualquiera",
      ACCESS_TOKEN: "otro-valor",
      run_access_token: "cdt_rt_abcdef123456",
      pregunta: "¿cuántos habitantes tiene Sonsón?",
    };
    const out = redact(input);
    expect(out.Authorization).toBe("[REDACTADO]");
    expect(out.token).toBe("[REDACTADO]");
    expect(out.ACCESS_TOKEN).toBe("[REDACTADO]");
    expect(out.run_access_token).toBe("[REDACTADO]");
    expect(out.pregunta).toBe("¿cuántos habitantes tiene Sonsón?");
  });

  it("redacta dentro de arrays y objetos anidados", () => {
    const input = {
      steps: [
        { detail: "sin secretos aquí" },
        { detail: "token filtrado: cdt_rt_zzz999" },
      ],
      headers: [{ Authorization: "Bearer x" }],
      meta: { nested: { deeper: "cdt_rt_deep000" } },
    };
    const out = redact(input);
    expect(out.steps[0].detail).toBe("sin secretos aquí");
    expect(out.steps[1].detail).not.toContain("cdt_rt_zzz999");
    expect(out.headers[0].Authorization).toBe("[REDACTADO]");
    expect(out.meta.nested.deeper).not.toContain("cdt_rt_deep000");
  });

  it("no modifica el objeto de entrada", () => {
    const input = { token: "secreto", other: { value: "cdt_rt_abc" } };
    const snapshot = JSON.parse(JSON.stringify(input));
    redact(input);
    expect(input).toEqual(snapshot);
  });

  it("maneja null, undefined y valores ordinarios sin lanzar", () => {
    expect(() => redact(null)).not.toThrow();
    expect(redact(null)).toBe(null);
    expect(() => redact(undefined)).not.toThrow();
    expect(redact(undefined)).toBe(undefined);
    expect(redact(42)).toBe(42);
    expect(redact(true)).toBe(true);
    expect(redact({ a: null, b: [null, 1, "x"] })).toEqual({
      a: null,
      b: [null, 1, "x"],
    });
  });
});
