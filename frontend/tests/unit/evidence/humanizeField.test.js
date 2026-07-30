import { describe, expect, it } from "vitest";
import { humanizeField } from "../../../lib/evidence/humanizeField.js";

describe("humanizeField", () => {
  it("cambia guiones bajos por espacios y capitaliza solo la primera letra", () => {
    expect(humanizeField("nombre_empresa")).toBe("Nombre empresa");
    expect(humanizeField("fecha_de_certificaci_n")).toBe("Fecha de certificaci n");
  });

  it("un campo de una sola palabra se capitaliza igual", () => {
    expect(humanizeField("nueca")).toBe("Nueca");
  });

  it("nunca lanza con entradas vacías o no-string", () => {
    expect(humanizeField("")).toBe("");
    expect(humanizeField(null)).toBe("");
    expect(humanizeField(undefined)).toBe("");
  });

  it("no inventa significado: no expande siglas ni traduce nada más allá de espacios/capitalización", () => {
    expect(humanizeField("nueca")).not.toBe("Número Único de Empresa de Certificación Ambiental");
  });
});
