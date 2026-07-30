/**
 * Vista de presentación pura del objeto `quality` de una evidencia
 * (`contracts/validacion-calidad.md` §4). No recalcula `score_total`,
 * clasificación ni dimensiones — solo traduce lo que el backend ya
 * decidió a una forma lista para presentar. `quality.warnings_user` se
 * conserva como lista propia; `presentation_warnings` (§4c de
 * `api-rest.md`) vive fuera de este módulo y nunca se fusiona aquí.
 */
import { describeCutoff } from "./describeCutoff.js";

const CLASSIFICATION_LABELS = {
  alta: "Calidad alta",
  media: "Calidad media",
  baja: "Calidad baja",
  no_recomendada: "No recomendada",
};

const KNOWN_CLASSIFICATIONS = new Set(Object.keys(CLASSIFICATION_LABELS));

/**
 * @param {object} evidence - objeto Evidencia con su `quality` anidado.
 * @returns {{
 *   classification: string,
 *   label: string,
 *   badgeStatus: string,
 *   eligibilityStatus: string|null,
 *   eligibilityReasons: string[],
 *   warnings: string[],
 *   cutoffText: string,
 *   requiresInsertionConfirmation: boolean
 * }}
 */
export function buildQualityViewModel(evidence) {
  const quality = evidence?.quality && typeof evidence.quality === "object" ? evidence.quality : {};
  const rawClassification = typeof quality.classification === "string" ? quality.classification : null;
  const known = rawClassification !== null && KNOWN_CLASSIFICATIONS.has(rawClassification);
  const classification = known ? rawClassification : "desconocida";

  return {
    classification,
    label: known ? CLASSIFICATION_LABELS[classification] : "Calidad no clasificada",
    // Deliberadamente NO son los `status` cerrados de
    // `components/ui/Badge.jsx` (ese conjunto es de estado de corrida,
    // no de clasificación de evidencia — mezclarlos haría que Badge
    // lance para "alta"/"media"/"baja"/"no_recomendada"). F4-02 define
    // su propio mapeo visual en `QualityBadge` a partir de este valor.
    badgeStatus: classification,
    eligibilityStatus: typeof quality.eligibility_status === "string" ? quality.eligibility_status : null,
    eligibilityReasons: Array.isArray(quality.eligibility_reasons) ? quality.eligibility_reasons : [],
    warnings: Array.isArray(quality.warnings_user) ? quality.warnings_user : [],
    cutoffText: describeCutoff(evidence),
    // Fail-safe: una clasificación desconocida exige confirmación igual
    // que `no_recomendada` — nunca se trata un estado no reconocido como
    // seguro para insertar automáticamente.
    requiresInsertionConfirmation: classification === "no_recomendada" || classification === "desconocida",
  };
}
