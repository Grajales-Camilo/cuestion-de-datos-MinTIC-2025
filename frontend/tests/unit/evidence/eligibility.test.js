import { describe, expect, it } from "vitest";
import { isEligibleEvidence } from "../../../lib/evidence/eligibility.js";

describe("isEligibleEvidence — fail-closed (contracts/validacion-calidad.md §3.1)", () => {
  it("eligible → true", () => {
    expect(isEligibleEvidence({ quality: { eligibility_status: "eligible" } })).toBe(true);
  });

  it.each([
    ["blocked", { quality: { eligibility_status: "blocked" } }],
    ["diagnostic_only", { quality: { eligibility_status: "diagnostic_only" } }],
    ["quality ausente", {}],
    ["eligibility_status ausente", { quality: {} }],
    ["valor desconocido", { quality: { eligibility_status: "algo-no-reconocido" } }],
    ["evidence null", null],
    ["evidence undefined", undefined],
  ])("%s → false (falla cerrado, nunca se asume elegible)", (_label, evidence) => {
    expect(isEligibleEvidence(evidence)).toBe(false);
  });
});
