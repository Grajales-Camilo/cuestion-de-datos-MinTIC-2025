import { describe, expect, it } from "vitest";
import { buildQualityViewModel } from "../../../lib/evidence/quality.js";
import fixture from "../../fixtures/completed-with-claims.json";

/** Dobles sintéticos: objetos `quality`/`evidence` mínimos construidos a
 * mano para ejercitar clasificaciones y ramas de corte que no aparecen en
 * el único fixture real disponible (que es `alta` con fallback). No se
 * guardan en `tests/fixtures/` ni se presentan como evidencia real. */
function syntheticEvidence(overrides = {}) {
  return {
    quality: {
      classification: "alta",
      eligibility_status: "eligible",
      eligibility_reasons: [],
      warnings_user: [],
      score_total: 90,
    },
    data_cutoff_basis: "data_cutoff_at",
    data_cutoff_at: "2025-03-15T00:00:00Z",
    data_updated_at: "2025-03-20T00:00:00Z",
    ...overrides,
  };
}

describe("buildQualityViewModel — fixture real (completed-with-claims.json)", () => {
  it("clasificación alta con fallback de actualización, sin recalcular nada del backend", () => {
    const [evidence] = fixture.answer.evidence;
    const model = buildQualityViewModel(evidence);

    expect(model.classification).toBe(evidence.quality.classification);
    expect(model.eligibilityStatus).toBe(evidence.quality.eligibility_status);
    expect(model.eligibilityReasons).toEqual(evidence.quality.eligibility_reasons);
    expect(model.warnings).toEqual(evidence.quality.warnings_user);
    expect(model.requiresInsertionConfirmation).toBe(false);
    expect(model.cutoffText).toBe("Fecha de actualización del portal: 17 de octubre de 2024. Corte estadístico desconocido.");
    expect(model.cutoffText).not.toMatch(/\bcorte\b.*2024/i); // nunca llama "corte" a esa fecha
  });
});

describe("buildQualityViewModel — las 4 clasificaciones del contrato", () => {
  it.each(["alta", "media", "baja", "no_recomendada"])("clasificación '%s' se preserva tal cual", (classification) => {
    const evidence = syntheticEvidence({ quality: { classification, eligibility_status: "eligible", eligibility_reasons: [], warnings_user: [] } });
    const model = buildQualityViewModel(evidence);
    expect(model.classification).toBe(classification);
  });

  it("no_recomendada exige confirmación de inserción", () => {
    const evidence = syntheticEvidence({
      quality: { classification: "no_recomendada", eligibility_status: "eligible", eligibility_reasons: [], warnings_user: [] },
    });
    expect(buildQualityViewModel(evidence).requiresInsertionConfirmation).toBe(true);
  });

  it("alta/media/baja no exigen confirmación", () => {
    for (const classification of ["alta", "media", "baja"]) {
      const evidence = syntheticEvidence({
        quality: { classification, eligibility_status: "eligible", eligibility_reasons: [], warnings_user: [] },
      });
      expect(buildQualityViewModel(evidence).requiresInsertionConfirmation).toBe(false);
    }
  });
});

describe("buildQualityViewModel — corte estadístico real vs. fallback", () => {
  it("data_cutoff_at real se presenta explícitamente como corte", () => {
    const evidence = syntheticEvidence({ data_cutoff_basis: "data_cutoff_at", data_cutoff_at: "2025-03-15T00:00:00Z" });
    const model = buildQualityViewModel(evidence);
    expect(model.cutoffText).toBe("Corte estadístico: 15 de marzo de 2025.");
  });

  it("data_updated_at_fallback nunca llama 'corte' a la fecha de actualización del portal", () => {
    const evidence = syntheticEvidence({
      data_cutoff_basis: "data_updated_at_fallback",
      data_cutoff_at: null,
      data_updated_at: "2024-10-17T19:36:28Z",
    });
    const model = buildQualityViewModel(evidence);
    expect(model.cutoffText).toBe("Fecha de actualización del portal: 17 de octubre de 2024. Corte estadístico desconocido.");
    expect(model.cutoffText).not.toContain("corte 17 de octubre"); // nunca la trata como el corte real
  });
});

describe("buildQualityViewModel — clasificación o elegibilidad desconocida", () => {
  it("classification ausente o no reconocida: fallback seguro, exige confirmación", () => {
    const evidence = syntheticEvidence({ quality: { classification: "algo_nuevo_no_documentado", eligibility_status: "eligible", eligibility_reasons: [], warnings_user: [] } });
    const model = buildQualityViewModel(evidence);
    expect(model.classification).toBe("desconocida");
    expect(model.label).toBe("Calidad no clasificada");
    expect(model.requiresInsertionConfirmation).toBe(true);
  });

  it("evidence.quality ausente por completo no lanza y devuelve un modelo seguro", () => {
    expect(() => buildQualityViewModel({})).not.toThrow();
    const model = buildQualityViewModel({});
    expect(model.classification).toBe("desconocida");
    expect(model.eligibilityStatus).toBeNull();
    expect(model.eligibilityReasons).toEqual([]);
    expect(model.warnings).toEqual([]);
    expect(model.requiresInsertionConfirmation).toBe(true);
  });
});

describe("buildQualityViewModel — warnings_user separado de presentation_warnings", () => {
  it("solo lee quality.warnings_user; nunca mezcla presentation_warnings aunque estén en el mismo objeto evidencia", () => {
    const evidence = syntheticEvidence({
      quality: {
        classification: "alta",
        eligibility_status: "eligible",
        eligibility_reasons: [],
        warnings_user: ["advertencia de calidad real"],
      },
    });
    evidence.presentation_warnings = [{ code: "AMBIGUOUS_LABEL", message_user: "otra cosa distinta" }];
    const model = buildQualityViewModel(evidence);
    expect(model.warnings).toEqual(["advertencia de calidad real"]);
    expect(model.warnings).not.toContain("otra cosa distinta");
  });
});
