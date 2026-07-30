import { redact } from "../api/redact.js";
import { getSafeExternalUrl } from "../evidence/safeExternalUrl.js";

const REQUIRED_SOURCE_FIELDS = Object.freeze([
  ["datasetId", "dataset_id"],
  ["datasetName", "dataset_name"],
  ["publisher", "publisher"],
  ["soqlQuery", "soql_query"],
  ["executedAt", "executed_at"],
  ["sourceUrl", "source_url"],
]);

const OPTIONAL_SOURCE_FIELDS = Object.freeze([
  ["dataUpdatedAt", "data_updated_at"],
  ["dataCutoffAt", "data_cutoff_at"],
  ["dataCutoffBasis", "data_cutoff_basis"],
]);

const ALLOWED_ATTRIBUTE_KEYS = new Set([
  "citationId",
  "runId",
  "evidenceId",
  ...REQUIRED_SOURCE_FIELDS.map(([attr]) => attr),
  ...OPTIONAL_SOURCE_FIELDS.map(([attr]) => attr),
  "qualityScore",
  "qualityClassification",
  "eligibilityStatus",
  "warningRequired",
  "claims",
  "insertedAt",
]);

const CLAIM_KEYS = Object.freeze([
  "claimId",
  "label",
  "displayValue",
  "unit",
  "sourceHash",
]);

export const EVIDENCE_CITATION_ERROR_CODES = Object.freeze({
  INVALID_PAYLOAD: "INVALID_PAYLOAD",
  INVALID_ATTRIBUTES: "INVALID_ATTRIBUTES",
  EVIDENCE_NOT_ELIGIBLE: "EVIDENCE_NOT_ELIGIBLE",
  MISSING_SOURCE_FIELDS: "MISSING_SOURCE_FIELDS",
  UNSAFE_SOURCE_URL: "UNSAFE_SOURCE_URL",
  MISSING_TRACEABILITY_FIELDS: "MISSING_TRACEABILITY_FIELDS",
  MISSING_INSERTION_METADATA: "MISSING_INSERTION_METADATA",
  INVALID_OPTIONAL_FIELDS: "INVALID_OPTIONAL_FIELDS",
  INVALID_CLAIMS: "INVALID_CLAIMS",
  WARNING_REQUIRED_MISMATCH: "WARNING_REQUIRED_MISMATCH",
  SENSITIVE_DATA_DETECTED: "SENSITIVE_DATA_DETECTED",
  INVALID_DOCUMENT_JSON: "INVALID_DOCUMENT_JSON",
  DUPLICATE_CITATION_ID: "DUPLICATE_CITATION_ID",
});

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

function readEvidenceField(evidence, field) {
  const citation = evidence?.citation;
  if (citation && typeof citation === "object" && hasOwn(citation, field)) {
    return citation[field];
  }
  return evidence?.[field];
}

function readOptionalEvidenceField(evidence, field) {
  const value = readEvidenceField(evidence, field);
  return value === undefined ? null : value;
}

function mapClaims(claims, evidenceId) {
  if (!Array.isArray(claims)) return [];

  return claims
    .filter((claim) => claim?.evidence_id === evidenceId)
    .map((claim) => ({
      claimId: claim.claim_id ?? null,
      label: claim.label ?? null,
      displayValue: claim.display_value ?? null,
      unit: claim.unit ?? null,
      sourceHash: claim.source_hash ?? null,
    }));
}

function serializableValuesEqual(left, right) {
  if (Object.is(left, right)) return true;
  if (typeof left !== typeof right || left === null || right === null) return false;

  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => serializableValuesEqual(item, right[index]))
    );
  }

  if (typeof left !== "object") return false;
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key) => hasOwn(right, key) && serializableValuesEqual(left[key], right[key]),
    )
  );
}

function containsSensitiveData(value) {
  try {
    return !serializableValuesEqual(value, redact(value));
  } catch {
    return true;
  }
}

function validOptionalString(value) {
  return value === undefined || value === null || isNonEmptyString(value);
}

function validClaims(claims) {
  if (!Array.isArray(claims)) return false;

  return claims.every((claim) => {
    if (!isPlainObject(claim)) return false;
    const keys = Object.keys(claim);
    if (
      keys.length !== CLAIM_KEYS.length ||
      keys.some((key) => !CLAIM_KEYS.includes(key)) ||
      CLAIM_KEYS.some((key) => !hasOwn(claim, key))
    ) {
      return false;
    }

    return (
      isNonEmptyString(claim.claimId) &&
      (claim.label === null || isNonEmptyString(claim.label)) &&
      isNonEmptyString(claim.displayValue) &&
      (claim.unit === null || isNonEmptyString(claim.unit)) &&
      isNonEmptyString(claim.sourceHash)
    );
  });
}

/**
 * Fuente única de invariantes de una cita persistida (T-504, RF-103).
 * Nunca devuelve datos rechazados ni incorpora valores sensibles al error.
 *
 * @param {unknown} attrs
 * @returns {{ok: true}|{ok: false, code: string}}
 */
export function validateEvidenceCitationAttrs(attrs) {
  if (!isPlainObject(attrs)) {
    return { ok: false, code: EVIDENCE_CITATION_ERROR_CODES.INVALID_ATTRIBUTES };
  }

  if (containsSensitiveData(attrs)) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.SENSITIVE_DATA_DETECTED,
    };
  }

  if (Object.keys(attrs).some((key) => !ALLOWED_ATTRIBUTE_KEYS.has(key))) {
    return { ok: false, code: EVIDENCE_CITATION_ERROR_CODES.INVALID_ATTRIBUTES };
  }

  if (
    REQUIRED_SOURCE_FIELDS.some(([attr]) => !isNonEmptyString(attrs[attr]))
  ) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.MISSING_SOURCE_FIELDS,
    };
  }

  if (!isNonEmptyString(attrs.runId) || !isNonEmptyString(attrs.evidenceId)) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.MISSING_TRACEABILITY_FIELDS,
    };
  }

  if (!isNonEmptyString(attrs.citationId) || !isNonEmptyString(attrs.insertedAt)) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.MISSING_INSERTION_METADATA,
    };
  }

  if (attrs.eligibilityStatus !== "eligible") {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.EVIDENCE_NOT_ELIGIBLE,
    };
  }

  if (getSafeExternalUrl(attrs.sourceUrl) === null) {
    return { ok: false, code: EVIDENCE_CITATION_ERROR_CODES.UNSAFE_SOURCE_URL };
  }

  if (
    !OPTIONAL_SOURCE_FIELDS.every(([attr]) => validOptionalString(attrs[attr])) ||
    !(
      attrs.qualityScore === undefined ||
      attrs.qualityScore === null ||
      (typeof attrs.qualityScore === "number" && Number.isFinite(attrs.qualityScore))
    ) ||
    !validOptionalString(attrs.qualityClassification) ||
    typeof attrs.warningRequired !== "boolean"
  ) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.INVALID_OPTIONAL_FIELDS,
    };
  }

  if (!validClaims(attrs.claims)) {
    return { ok: false, code: EVIDENCE_CITATION_ERROR_CODES.INVALID_CLAIMS };
  }

  const warningRequired = attrs.qualityClassification === "no_recomendada";
  if (attrs.warningRequired !== warningRequired) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.WARNING_REQUIRED_MISMATCH,
    };
  }

  return { ok: true };
}

function validateDocumentNode(node, citationIds) {
  if (!isPlainObject(node) || !isNonEmptyString(node.type)) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.INVALID_DOCUMENT_JSON,
    };
  }

  if (node.type === "evidenceCitation") {
    const result = validateEvidenceCitationAttrs(node.attrs);
    if (!result.ok) return result;

    if (citationIds.has(node.attrs.citationId)) {
      return {
        ok: false,
        code: EVIDENCE_CITATION_ERROR_CODES.DUPLICATE_CITATION_ID,
      };
    }
    citationIds.add(node.attrs.citationId);

    if (node.content !== undefined) {
      return {
        ok: false,
        code: EVIDENCE_CITATION_ERROR_CODES.INVALID_DOCUMENT_JSON,
      };
    }
  }

  if (node.content !== undefined) {
    if (!Array.isArray(node.content)) {
      return {
        ok: false,
        code: EVIDENCE_CITATION_ERROR_CODES.INVALID_DOCUMENT_JSON,
      };
    }
    for (const child of node.content) {
      const result = validateDocumentNode(child, citationIds);
      if (!result.ok) return result;
    }
  }

  return { ok: true };
}

/**
 * Valida citas y unicidad antes de restaurar JSON de ProseMirror. No corrige,
 * completa ni normaliza documentos inválidos.
 *
 * @param {unknown} json
 * @returns {{ok: true}|{ok: false, code: string}}
 */
export function validateEvidenceCitationDocumentJson(json) {
  if (!isPlainObject(json) || json.type !== "doc" || !Array.isArray(json.content)) {
    return {
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.INVALID_DOCUMENT_JSON,
    };
  }

  return validateDocumentNode(json, new Set());
}

/**
 * Construye los atributos persistibles de una cita de evidencia (T-504,
 * RF-103). Es una frontera de lista blanca: nunca copia el payload completo.
 *
 * @param {object} payload
 * @returns {{ok: true, attrs: object}|{ok: false, code: string}}
 */
export function buildEvidenceCitationAttrs(payload) {
  try {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { ok: false, code: EVIDENCE_CITATION_ERROR_CODES.INVALID_PAYLOAD };
    }

    const { runId, evidence, claims, citationId, insertedAt } = payload;
    const evidenceId = evidence?.evidence_id;
    const source = Object.fromEntries(
      REQUIRED_SOURCE_FIELDS.map(([attr, field]) => [
        attr,
        readEvidenceField(evidence, field),
      ]),
    );
    const optionalSource = Object.fromEntries(
      OPTIONAL_SOURCE_FIELDS.map(([attr, field]) => [
        attr,
        readOptionalEvidenceField(evidence, field),
      ]),
    );
    const qualityClassification = evidence?.quality?.classification ?? null;
    const attrs = {
      citationId,
      runId,
      evidenceId,
      ...source,
      ...optionalSource,
      qualityScore: evidence?.quality?.score_total ?? null,
      qualityClassification,
      eligibilityStatus: evidence?.quality?.eligibility_status ?? null,
      warningRequired: qualityClassification === "no_recomendada",
      claims: mapClaims(claims, evidenceId),
      insertedAt,
    };
    const validation = validateEvidenceCitationAttrs(attrs);
    return validation.ok ? { ok: true, attrs } : validation;
  } catch {
    return { ok: false, code: EVIDENCE_CITATION_ERROR_CODES.INVALID_PAYLOAD };
  }
}
