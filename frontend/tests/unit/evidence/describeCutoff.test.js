import { describe, expect, it } from "vitest";
import { describeCutoff, formatSpanishDate } from "../../../lib/evidence/describeCutoff.js";

describe("formatSpanishDate", () => {
  it("formatea una fecha ISO en UTC, sin depender de la zona horaria del entorno", () => {
    expect(formatSpanishDate("2025-03-15T00:00:00Z")).toBe("15 de marzo de 2025");
  });

  it("fecha inválida o ausente: null, nunca lanza", () => {
    expect(formatSpanishDate("no es una fecha")).toBeNull();
    expect(formatSpanishDate(null)).toBeNull();
    expect(formatSpanishDate(undefined)).toBeNull();
  });
});

describe("describeCutoff — lee la forma anidada del contrato (quality.data_cutoff)", () => {
  it("usa evidence.quality.data_cutoff cuando existe, con prioridad sobre los campos planos", () => {
    const evidence = {
      quality: { data_cutoff: { basis: "data_cutoff_at", data_cutoff_at: "2025-06-01T00:00:00Z" } },
      data_cutoff_basis: "data_updated_at_fallback", // no debe usarse: la forma anidada gana
      data_cutoff_at: null,
      data_updated_at: "2020-01-01T00:00:00Z",
    };
    expect(describeCutoff(evidence)).toBe("Corte estadístico: 1 de junio de 2025.");
  });
});

describe("describeCutoff — sin ningún dato de corte disponible", () => {
  it("ni basis, ni data_cutoff_at, ni data_updated_at: honesto, nunca inventa una fecha", () => {
    expect(describeCutoff({})).toBe("Corte estadístico desconocido.");
  });
});
