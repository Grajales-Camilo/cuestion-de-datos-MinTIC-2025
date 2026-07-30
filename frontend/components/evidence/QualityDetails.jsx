import { Disclosure } from "../ui/Disclosure";
import { buildQualityViewModel } from "../../lib/evidence";

/**
 * Vista completa del objeto `quality` de una evidencia
 * (`contracts/validacion-calidad.md` §4). Superficie primaria: puntaje,
 * clasificación, las 4 dimensiones (solo puntaje), elegibilidad y
 * advertencias — todo en español claro, sin enums crudos. Nombres de check
 * y demás detalle técnico viven exclusivamente en el `<Disclosure>` final.
 */

const DIMENSION_LABELS = {
  schema: "Esquema",
  completeness: "Completitud",
  timeliness: "Temporalidad",
  traceability: "Trazabilidad",
};
const DIMENSION_ORDER = ["schema", "completeness", "timeliness", "traceability"];

const ELIGIBILITY_STATUS_LABELS = {
  eligible: "Elegible para sustentar la respuesta",
  diagnostic_only: "Solo diagnóstico — no sustenta esta cifra",
  blocked: "Bloqueada — no se presenta como hallazgo",
};
const GENERIC_ELIGIBILITY_STATUS = "Estado de elegibilidad no reconocido";

const ELIGIBILITY_REASON_LABELS = {
  api_inactive: "La fuente del dato está inactiva en el portal.",
  publisher_unknown: "No fue posible verificar el publicador oficial de este dato.",
  publisher_private: "El publicador no es una entidad estatal reconocida.",
  pii_unknown: "No fue posible determinar el riesgo de datos personales de esta columna.",
  pii_high: "Esta columna contiene datos personales de alto riesgo.",
  pii_medium_requires_aggregation:
    "Esta columna requiere una consulta agregada por el riesgo de datos personales que contiene.",
  pii_aggregation_insufficient:
    "La consulta no agregó suficientes registros para proteger los datos personales involucrados.",
};
const GENERIC_ELIGIBILITY_REASON = "Restricción de elegibilidad no reconocida.";

function translateEligibilityStatus(status) {
  if (typeof status === "string" && Object.prototype.hasOwnProperty.call(ELIGIBILITY_STATUS_LABELS, status)) {
    return ELIGIBILITY_STATUS_LABELS[status];
  }
  return GENERIC_ELIGIBILITY_STATUS;
}

function translateEligibilityReason(reason) {
  if (typeof reason === "string" && Object.prototype.hasOwnProperty.call(ELIGIBILITY_REASON_LABELS, reason)) {
    return ELIGIBILITY_REASON_LABELS[reason];
  }
  return GENERIC_ELIGIBILITY_REASON;
}

function dimensionScoreLabel(dimension) {
  return dimension && typeof dimension.score === "number" ? `${dimension.score}/100` : "No disponible";
}

export function QualityDetails({ evidence }) {
  const quality = evidence?.quality && typeof evidence.quality === "object" ? evidence.quality : {};
  const dimensions = quality.dimensions && typeof quality.dimensions === "object" ? quality.dimensions : {};
  const viewModel = buildQualityViewModel(evidence);
  const scoreTotal = typeof quality.score_total === "number" ? quality.score_total : null;

  const dimensionsWithChecks = DIMENSION_ORDER.filter(
    (key) => Array.isArray(dimensions[key]?.checks) && dimensions[key].checks.length > 0
  );

  return (
    <div className="flex flex-col gap-cdt-3">
      <div className="flex flex-wrap items-baseline justify-between gap-cdt-2">
        <span className="text-cdt-sm font-cdt-bold text-cdt-slate-900">{viewModel.label}</span>
        <span className="text-cdt-sm text-cdt-slate-600">
          Puntaje: {scoreTotal === null ? "No disponible" : `${scoreTotal}/100`}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-cdt-2 sm:grid-cols-2">
        {DIMENSION_ORDER.map((key) => (
          <div
            key={key}
            className="flex items-center justify-between gap-cdt-2 rounded-cdt-md border border-cdt-blue-100 px-cdt-3 py-cdt-2"
          >
            <span className="text-cdt-sm font-cdt-bold text-cdt-slate-900">{DIMENSION_LABELS[key]}</span>
            <span className="text-cdt-sm text-cdt-slate-600">{dimensionScoreLabel(dimensions[key])}</span>
          </div>
        ))}
      </div>

      <p className="text-cdt-sm text-cdt-slate-900">
        <span className="font-cdt-bold">Elegibilidad: </span>
        {translateEligibilityStatus(viewModel.eligibilityStatus)}
      </p>

      {viewModel.eligibilityReasons.length > 0 ? (
        <ul className="flex flex-col gap-cdt-1 text-cdt-sm text-cdt-slate-900">
          {viewModel.eligibilityReasons.map((reason, index) => (
            <li key={`${reason}-${index}`}>{translateEligibilityReason(reason)}</li>
          ))}
        </ul>
      ) : null}

      {viewModel.warnings.length > 0 ? (
        <div className="flex flex-col gap-cdt-1 rounded-cdt-md bg-cdt-blue-50 p-cdt-3">
          <span className="text-cdt-xs font-cdt-bold text-cdt-slate-600">Advertencias de calidad</span>
          <ul className="flex flex-col gap-cdt-1 text-cdt-sm text-cdt-slate-900">
            {viewModel.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-cdt-sm text-cdt-slate-600">{viewModel.cutoffText}</p>

      <Disclosure summary="Ver detalle técnico de la validación">
        <div className="flex flex-col gap-cdt-3 pt-cdt-2">
          <p className="text-cdt-xs text-cdt-slate-600">
            validator_version:{" "}
            {typeof quality.validator_version === "string" ? quality.validator_version : "No disponible"}
          </p>
          {viewModel.eligibilityReasons.length > 0 ? (
            <p className="text-cdt-xs text-cdt-slate-600">
              Códigos crudos de elegibilidad: {viewModel.eligibilityReasons.join(", ")}
            </p>
          ) : null}
          {dimensionsWithChecks.map((key) => (
            <div key={key} className="flex flex-col gap-cdt-1">
              <p className="text-cdt-xs font-cdt-bold text-cdt-slate-600">{DIMENSION_LABELS[key]}</p>
              <ul className="flex flex-col gap-cdt-1 pl-cdt-3 text-cdt-xs text-cdt-slate-600">
                {dimensions[key].checks.map((check, index) => (
                  <li key={check?.check ?? index}>
                    <code>{typeof check?.check === "string" ? check.check : "check"}</code>
                    {": "}
                    {check?.passed ? "cumplido" : "no cumplido"}
                    {typeof check?.detail === "string" && check.detail ? ` — ${check.detail}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Disclosure>
    </div>
  );
}
