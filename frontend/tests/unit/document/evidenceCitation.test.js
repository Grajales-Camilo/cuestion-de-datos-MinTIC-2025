import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  buildEvidenceCitationAttrs,
  EVIDENCE_CITATION_ERROR_CODES,
  validateEvidenceCitationAttrs,
} from "../../../lib/document/evidenceCitation.js";

const fixture = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"),
    "utf8",
  ),
);

function realFixturePayload() {
  return {
    runId: fixture.run_id,
    evidence: structuredClone(fixture.answer.evidence[0]),
    claims: structuredClone(fixture.answer.claims),
    citationId: "citation-fixture-001",
    insertedAt: "2026-07-28T12:00:00.000Z",
  };
}

// Doble sintético focalizado: permite mutar elegibilidad/calidad sin alterar
// el fixture real capturado por F2/F4.
function syntheticPayload() {
  return {
    runId: "run-sintetico-001",
    evidence: {
      evidence_id: "evidence-sintetica-001",
      quality: {
        eligibility_status: "eligible",
        score_total: 54,
        classification: "baja",
      },
      citation: {
        dataset_id: "abcd-1234",
        dataset_name: "Dataset sintético de prueba",
        publisher: "Entidad pública de prueba",
        soql_query: "SELECT count(*) AS total",
        executed_at: "2026-07-28T10:00:00Z",
        source_url: "https://www.datos.gov.co/resource/abcd-1234.json",
        data_updated_at: "2026-07-20T00:00:00Z",
        data_cutoff_at: "2026-06-30T00:00:00Z",
        data_cutoff_basis: "data_cutoff_at",
      },
    },
    claims: [
      {
        claim_id: "claim-sintetico-001",
        evidence_id: "evidence-sintetica-001",
        label: "Total",
        display_value: "42",
        unit: "registros",
        source_hash: "sha256:permitido",
        raw_value: 42,
        formula: "count(*)",
      },
    ],
    citationId: "citation-sintetica-001",
    insertedAt: "2026-07-28T11:00:00Z",
  };
}

function syntheticAttrs() {
  const result = buildEvidenceCitationAttrs(syntheticPayload());
  if (!result.ok) throw new Error(result.code);
  return structuredClone(result.attrs);
}

describe("buildEvidenceCitationAttrs (T-504, RF-103)", () => {
  it("construye una cita completa desde completed-with-claims.json", () => {
    const result = buildEvidenceCitationAttrs(realFixturePayload());

    expect(result.ok).toBe(true);
    expect(result.attrs).toMatchObject({
      citationId: "citation-fixture-001",
      runId: fixture.run_id,
      evidenceId: fixture.answer.evidence[0].evidence_id,
      datasetId: "y97c-tfd9",
      publisher: "Superintendencia de Servicios Públicos Domiciliarios - AAA",
      dataUpdatedAt: "2024-10-17T19:36:28+00:00",
      dataCutoffAt: "2024-10-17T19:36:28+00:00",
      dataCutoffBasis: "data_updated_at_fallback",
      qualityScore: 91,
      qualityClassification: "alta",
      eligibilityStatus: "eligible",
      warningRequired: false,
      insertedAt: "2026-07-28T12:00:00.000Z",
    });
    expect(result.attrs.claims).toHaveLength(2);
  });

  it.each([
    ["datasetId", "dataset_id"],
    ["datasetName", "dataset_name"],
    ["publisher", "publisher"],
    ["soqlQuery", "soql_query"],
    ["executedAt", "executed_at"],
    ["sourceUrl", "source_url"],
  ])("rechaza el campo obligatorio ausente %s", (attr, sourceField) => {
    const payload = syntheticPayload();
    delete payload.evidence.citation[sourceField];

    expect(buildEvidenceCitationAttrs(payload)).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.MISSING_SOURCE_FIELDS,
    });
  });

  it("trata strings de solo espacios como campos ausentes sin inventar reemplazos", () => {
    const payload = syntheticPayload();
    payload.evidence.citation.publisher = "   ";

    expect(buildEvidenceCitationAttrs(payload)).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.MISSING_SOURCE_FIELDS,
    });
  });

  it.each([
    "http://www.datos.gov.co/resource/abcd-1234.json",
    "https://usuario:clave@www.datos.gov.co/resource/abcd-1234.json",
    "javascript:alert(1)",
  ])("rechaza sourceUrl insegura sin reflejar el valor: %s", (sourceUrl) => {
    const payload = syntheticPayload();
    payload.evidence.citation.source_url = sourceUrl;

    const result = buildEvidenceCitationAttrs(payload);
    expect(result).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.UNSAFE_SOURCE_URL,
    });
    expect(JSON.stringify(result)).not.toContain(sourceUrl);
  });

  it.each(["blocked", "diagnostic_only", undefined, "desconocida"])(
    "falla cerrado para elegibilidad %s",
    (eligibilityStatus) => {
      const payload = syntheticPayload();
      if (eligibilityStatus === undefined) {
        delete payload.evidence.quality.eligibility_status;
      } else {
        payload.evidence.quality.eligibility_status = eligibilityStatus;
      }

      expect(buildEvidenceCitationAttrs(payload)).toEqual({
        ok: false,
        code: EVIDENCE_CITATION_ERROR_CODES.EVIDENCE_NOT_ELIGIBLE,
      });
    },
  );

  it("filtra claims por evidence_id y conserva solo el subconjunto permitido", () => {
    const payload = syntheticPayload();
    payload.claims.push({
      claim_id: "claim-ajeno",
      evidence_id: "otra-evidencia",
      label: "No debe entrar",
      display_value: "999",
      unit: null,
      source_hash: "sha256:ajeno",
    });

    const result = buildEvidenceCitationAttrs(payload);
    expect(result.ok).toBe(true);
    expect(result.attrs.claims).toEqual([
      {
        claimId: "claim-sintetico-001",
        label: "Total",
        displayValue: "42",
        unit: "registros",
        sourceHash: "sha256:permitido",
      },
    ]);
    expect(Object.keys(result.attrs.claims[0])).toEqual([
      "claimId",
      "label",
      "displayValue",
      "unit",
      "sourceHash",
    ]);
  });

  it("R2: acepta label=null para un claim ambiguo sin inventar etiqueta", () => {
    const payload = syntheticPayload();
    payload.claims[0].label = null;
    payload.claims[0].label_status = "ambiguous";
    payload.claims[0].claim = "Texto que no debe usarse como etiqueta";
    payload.claims[0].columns = ["columna_que_no_debe_usarse"];

    const result = buildEvidenceCitationAttrs(payload);

    expect(result.ok).toBe(true);
    expect(result.attrs.claims[0]).toEqual({
      claimId: "claim-sintetico-001",
      label: null,
      displayValue: "42",
      unit: "registros",
      sourceHash: "sha256:permitido",
    });
    expect(validateEvidenceCitationAttrs(result.attrs)).toEqual({ ok: true });
  });

  it("R2: normaliza a null el label ausente de un claim histórico", () => {
    const payload = syntheticPayload();
    delete payload.claims[0].label;
    payload.claims[0].claim = "Texto histórico que no debe usarse";
    payload.claims[0].columns = ["columna_historica"];

    const result = buildEvidenceCitationAttrs(payload);

    expect(result.ok).toBe(true);
    expect(result.attrs.claims[0].label).toBeNull();
    expect(JSON.stringify(result.attrs)).not.toContain(
      "Texto histórico que no debe usarse",
    );
    expect(JSON.stringify(result.attrs)).not.toContain("columna_historica");
  });

  it.each(["", "   "])("R2: rechaza label no nulo vacío %j", (label) => {
    const payload = syntheticPayload();
    payload.claims[0].label = label;

    expect(buildEvidenceCitationAttrs(payload)).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.INVALID_CLAIMS,
    });
  });

  it("R2: preserva exactamente un label string válido", () => {
    const payload = syntheticPayload();
    payload.claims[0].label = "  Etiqueta contractual  ";

    const result = buildEvidenceCitationAttrs(payload);

    expect(result.ok).toBe(true);
    expect(result.attrs.claims[0].label).toBe("  Etiqueta contractual  ");
  });

  it("nunca copia token, Authorization, message_dev, payload crudo ni Error", () => {
    const payload = syntheticPayload();
    payload.token = "SECRETO_PAYLOAD";
    payload.Authorization = "Bearer SECRETO_AUTH";
    payload.evidence.message_dev = "SECRETO_DEV";
    payload.evidence.raw_payload = { secreto: "SECRETO_RAW" };
    payload.evidence.error = new Error("SECRETO_ERROR");
    payload.claims[0].Authorization = "Bearer SECRETO_CLAIM";

    const result = buildEvidenceCitationAttrs(payload);
    expect(result.ok).toBe(true);
    const serialized = JSON.stringify(result.attrs);
    for (const forbidden of [
      "SECRETO_PAYLOAD",
      "SECRETO_AUTH",
      "SECRETO_DEV",
      "SECRETO_RAW",
      "SECRETO_ERROR",
      "SECRETO_CLAIM",
      "Authorization",
      "message_dev",
      "raw_payload",
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("fuerza warningRequired para no_recomendada aunque el llamador envíe false", () => {
    const payload = syntheticPayload();
    payload.evidence.quality.classification = "no_recomendada";
    payload.warningRequired = false;

    const result = buildEvidenceCitationAttrs(payload);
    expect(result.ok).toBe(true);
    expect(result.attrs.qualityClassification).toBe("no_recomendada");
    expect(result.attrs.warningRequired).toBe(true);
  });

  it.each(["alta", "baja", null, "clasificacion-aditiva"])(
    "produce warningRequired=false para %s",
    (classification) => {
      const payload = syntheticPayload();
      payload.evidence.quality.classification = classification;

      const result = buildEvidenceCitationAttrs(payload);
      expect(result.ok).toBe(true);
      expect(result.attrs.qualityClassification).toBe(classification);
      expect(result.attrs.warningRequired).toBe(false);
    },
  );

  it("citationId e insertedAt inyectados hacen la salida determinista", () => {
    const payload = syntheticPayload();

    expect(buildEvidenceCitationAttrs(payload)).toEqual(
      buildEvidenceCitationAttrs(structuredClone(payload)),
    );
  });

  it("deriva eligibilityStatus de evidence y no del payload del llamador", () => {
    const payload = syntheticPayload();
    payload.eligibilityStatus = "blocked";

    const result = buildEvidenceCitationAttrs(payload);
    expect(result.ok).toBe(true);
    expect(result.attrs.eligibilityStatus).toBe("eligible");
    expect(validateEvidenceCitationAttrs(result.attrs)).toEqual({ ok: true });
  });

  it.each([
    [
      "tipo opcional inválido",
      (attrs) => (attrs.qualityScore = "54"),
      EVIDENCE_CITATION_ERROR_CODES.INVALID_OPTIONAL_FIELDS,
    ],
    [
      "claims inválidos",
      (attrs) => (attrs.claims = [{ label: "incompleto" }]),
      EVIDENCE_CITATION_ERROR_CODES.INVALID_CLAIMS,
    ],
    [
      "advertencia improcedente",
      (attrs) => (attrs.warningRequired = true),
      EVIDENCE_CITATION_ERROR_CODES.WARNING_REQUIRED_MISMATCH,
    ],
  ])("validateEvidenceCitationAttrs rechaza %s", (_label, mutate, code) => {
    const attrs = syntheticAttrs();
    mutate(attrs);

    expect(validateEvidenceCitationAttrs(attrs)).toEqual({ ok: false, code });
  });

  it.each([
    ["datasetName", (payload, token) => (payload.evidence.citation.dataset_name = token)],
    ["publisher", (payload, token) => (payload.evidence.citation.publisher = token)],
    ["soqlQuery", (payload, token) => (payload.evidence.citation.soql_query = token)],
    [
      "sourceUrl/query",
      (payload, token) =>
        (payload.evidence.citation.source_url =
          `https://www.datos.gov.co/resource/abcd-1234.json?access=${token}`),
    ],
    ["citationId", (payload, token) => (payload.citationId = token)],
    ["claim.label", (payload, token) => (payload.claims[0].label = token)],
    [
      "claim.displayValue",
      (payload, token) => (payload.claims[0].display_value = token),
    ],
    [
      "claim.sourceHash",
      (payload, token) => (payload.claims[0].source_hash = token),
    ],
  ])("R1: token incrustado en %s rechaza toda la cita", (_field, mutate) => {
    const payload = syntheticPayload();
    const token = "cdt_rt_SECRETO_R1";
    mutate(payload, token);

    const result = buildEvidenceCitationAttrs(payload);
    expect(result).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.SENSITIVE_DATA_DETECTED,
    });
    expect(JSON.stringify(result)).not.toContain(token);
    expect(JSON.stringify(result)).not.toContain("[REDACTADO]");
  });
});
