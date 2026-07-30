import { describe, expect, it } from "vitest";
import { normalizeSectionId } from "../../../lib/agent/sectionId";

describe("normalizeSectionId — F5-03A-R2", () => {
  it("un sectionId válido sobrevive exactamente", () => {
    expect(normalizeSectionId("seccion-1")).toBe("seccion-1");
    expect(normalizeSectionId("s1")).toBe("s1");
    // Espacios internos (no solo al inicio/fin) se conservan tal cual: la
    // regla es "sin información sensible", no "con formato canónico".
    expect(normalizeSectionId("sección con espacios")).toBe("sección con espacios");
  });

  it("null y undefined permanecen sin asociación (null)", () => {
    expect(normalizeSectionId(null)).toBeNull();
    expect(normalizeSectionId(undefined)).toBeNull();
  });

  it("vacío, whitespace, objeto, array y número terminan en null", () => {
    expect(normalizeSectionId("")).toBeNull();
    expect(normalizeSectionId("   ")).toBeNull();
    expect(normalizeSectionId("\t\n")).toBeNull();
    expect(normalizeSectionId({})).toBeNull();
    expect(normalizeSectionId({ sectionId: "s1" })).toBeNull();
    expect(normalizeSectionId([])).toBeNull();
    expect(normalizeSectionId(["s1"])).toBeNull();
    expect(normalizeSectionId(42)).toBeNull();
    expect(normalizeSectionId(0)).toBeNull();
    expect(normalizeSectionId(true)).toBeNull();
    expect(normalizeSectionId(false)).toBeNull();
  });

  it('"seccion-cdt_rt_secreto" termina en null, nunca en "[REDACTADO]"', () => {
    const result = normalizeSectionId("seccion-cdt_rt_secreto");
    expect(result).toBeNull();
    expect(result).not.toBe("[REDACTADO]");
  });

  it("cualquier variante que contenga el patrón cdt_rt_* en cualquier posición termina en null", () => {
    expect(normalizeSectionId("cdt_rt_al_inicio")).toBeNull();
    expect(normalizeSectionId("al-final-cdt_rt_x")).toBeNull();
    expect(normalizeSectionId("en-medio-cdt_rt_y-de-la-cadena")).toBeNull();
  });

  it("nunca lanza, incluso ante entradas patológicas", () => {
    expect(() => normalizeSectionId(Symbol("x"))).not.toThrow();
    expect(normalizeSectionId(Symbol("x"))).toBeNull();
    expect(() => normalizeSectionId(() => {})).not.toThrow();
    expect(normalizeSectionId(() => {})).toBeNull();
    expect(() => normalizeSectionId(new Date())).not.toThrow();
  });
});
