import { describe, expect, it } from "vitest";
import { normalizeContextHint } from "../../lib/agent/contextHint.js";

describe("normalizeContextHint", () => {
  it("texto normal por debajo del límite: no se trunca", () => {
    const result = normalizeContextHint("Contexto breve de una sección del documento.");
    expect(result).toEqual({ value: "Contexto breve de una sección del documento.", truncated: false });
  });

  it("corte por palabra: no parte una palabra a la mitad", () => {
    const word = "palabra ";
    const text = word.repeat(300); // 2400 caracteres, muchos espacios
    const result = normalizeContextHint(text);

    expect(result.truncated).toBe(true);
    expect(result.value.length).toBeLessThanOrEqual(2000);
    expect(result.value.endsWith("palabra")).toBe(true);
    expect(text.startsWith(result.value)).toBe(true);
  });

  it("palabra única extensa sin límite razonable: corte duro seguro", () => {
    const text = "a".repeat(2500); // una sola "palabra", sin espacios
    const result = normalizeContextHint(text);

    expect(result.truncated).toBe(true);
    expect(result.value).toBe("a".repeat(2000));
    expect(result.value.length).toBe(2000);
  });

  it("entrada inicial excesiva (initialContextHint > 2000): se normaliza igual que el contexto editado", () => {
    const initialContextHint = "Sección ".repeat(300); // > 2000 caracteres
    const result = normalizeContextHint(initialContextHint);

    expect(result.truncated).toBe(true);
    expect(result.value.length).toBeLessThanOrEqual(2000);
  });

  it("nunca produce un valor que exceda maxLength (ausencia de 422 evitable)", () => {
    const text = "x".repeat(5000);
    const result = normalizeContextHint(text);
    expect(result.value.length).toBeLessThanOrEqual(2000);
  });

  it("un espacio temprano no produce un corte casi vacío", () => {
    const text = "a " + "b".repeat(3000);
    const result = normalizeContextHint(text);
    // El único espacio está en la posición 1: muy por debajo del 50% del
    // límite, así que se prefiere el corte duro sobre un fragmento de "a".
    expect(result.value.length).toBe(2000);
  });

  it("entrada vacía o no-string: no lanza, no se trunca", () => {
    expect(normalizeContextHint("")).toEqual({ value: "", truncated: false });
    expect(normalizeContextHint(undefined)).toEqual({ value: "", truncated: false });
    expect(normalizeContextHint(null)).toEqual({ value: "", truncated: false });
  });

  it("respeta un maxLength distinto del predeterminado", () => {
    const result = normalizeContextHint("uno dos tres cuatro", { maxLength: 8 });
    expect(result.truncated).toBe(true);
    expect(result.value.length).toBeLessThanOrEqual(8);
  });
});
