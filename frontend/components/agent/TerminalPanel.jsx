import { useState } from "react";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EvidenceCard } from "../evidence";
import { isEligibleEvidence } from "../../lib/evidence";
import { RUN_STATUS } from "../../lib/agent/runStates";
import { normalizeExternalSources } from "../../lib/agent/externalSources";

const BADGE_STATUS_BY_RUN_STATUS = {
  [RUN_STATUS.COMPLETED]: "verified",
  [RUN_STATUS.NO_EVIDENCE]: "no_evidence",
  [RUN_STATUS.INTERRUPTED]: "interrupted",
  [RUN_STATUS.FAILED]: "failed",
};

function terminalMessage(state) {
  switch (state.status) {
    case RUN_STATUS.COMPLETED:
      return "La investigación terminó con evidencia verificada.";
    case RUN_STATUS.NO_EVIDENCE:
      return "No se encontró evidencia elegible para responder esta pregunta.";
    case RUN_STATUS.INTERRUPTED:
      return "La investigación se interrumpió en el servidor. Esto es lo que alcanzó a verificar.";
    case RUN_STATUS.FAILED:
      return state.error?.messageUser ?? "La investigación no pudo completarse.";
    default:
      return "";
  }
}

/**
 * Presenta el desenlace, las acciones generales y — desde F4-02 — una
 * `EvidenceCard` por cada elemento ELEGIBLE de `state.evidence`, con
 * evidencia completa (`completed`) o parcial conservada
 * (`interrupted`/`failed`). `no_evidence` no necesita tratamiento especial
 * aquí: su `state.evidence` ya es `[]` por contrato, así que no aparece
 * ninguna tarjeta.
 *
 * F4-02-R1: cuando alguna evidencia no es elegible (`blocked`,
 * `diagnostic_only`, o `eligibility_status` ausente/desconocido —
 * `EvidenceCard` ya la omite por completo, fail-closed), se muestra UNA
 * única notificación genérica, sin código ni motivo ni metadato del
 * contenido bloqueado — nunca una por cada elemento omitido.
 */
export function TerminalPanel({ state, onRestart, onInsertEvidence, onAddManualSource }) {
  const [manualGuidance, setManualGuidance] = useState("");
  const badgeStatus = BADGE_STATUS_BY_RUN_STATUS[state.status];
  if (!badgeStatus) return null;

  const evidenceList = Array.isArray(state.evidence) ? state.evidence : [];
  const hasEligibleEvidence = evidenceList.some(isEligibleEvidence);
  const hasIneligibleEvidence = evidenceList.some((evidence) => !isEligibleEvidence(evidence));
  const suggestedSources =
    state.status === RUN_STATUS.NO_EVIDENCE
      ? normalizeExternalSources(state.noEvidenceReport?.external_sources)
      : [];

  return (
    <div className="flex flex-col gap-cdt-3 rounded-cdt-lg border border-cdt-blue-100 p-cdt-4">
      <Badge status={badgeStatus} />
      <p className="text-cdt-sm text-cdt-slate-900">{terminalMessage(state)}</p>
      <div className="flex gap-cdt-2">
        <Button variant="secondary" onClick={onRestart}>
          Volver a preguntar
        </Button>
      </div>
      {suggestedSources.length > 0 ? (
        <section
          aria-labelledby="suggested-sources-heading"
          className="min-w-0 rounded-cdt-md bg-cdt-blue-50 p-cdt-4"
        >
          <h3 id="suggested-sources-heading" className="text-cdt-base font-cdt-bold text-cdt-blue-900">
            Fuentes oficiales sugeridas
          </h3>
          <p className="mt-cdt-2 text-cdt-sm text-cdt-slate-900">
            Estas fuentes no fueron consultadas por el agente. Revisa el dato antes de incorporarlo como aporte manual.
          </p>
          <ul className="mt-cdt-3 divide-y divide-cdt-blue-100">
            {suggestedSources.map((source) => (
              <li key={`${source.entidad}\u0000${source.url}`} className="min-w-0 py-cdt-3 first:pt-0 last:pb-0">
                <p className="break-words text-cdt-sm font-cdt-bold text-cdt-slate-900">{source.entidad}</p>
                <p className="mt-cdt-1 break-words text-cdt-sm text-cdt-slate-600">{source.por_que}</p>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Abrir ${source.entidad}`}
                  className="mt-cdt-2 inline-block max-w-full break-all text-cdt-sm font-cdt-bold text-cdt-blue-700 underline underline-offset-2"
                >
                  Consultar fuente oficial
                </a>
                <div className="mt-cdt-3">
                  <Button
                    variant="secondary"
                    onClick={() => {
                      const opened =
                        typeof onAddManualSource === "function" && onAddManualSource(source) === true;
                      setManualGuidance(
                        opened
                          ? ""
                          : "Usa “Agregar dato manual” en la sección donde quieres incorporar el aporte.",
                      );
                    }}
                  >
                    Agregar manualmente
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          {manualGuidance ? (
            <p role="status" className="mt-cdt-3 text-cdt-sm font-cdt-bold text-cdt-blue-900">
              {manualGuidance}
            </p>
          ) : null}
        </section>
      ) : null}
      {hasEligibleEvidence ? (
        <div className="flex flex-col gap-cdt-4">
          {evidenceList.map((evidence, index) => (
            <EvidenceCard
              key={evidence?.evidence_id ?? index}
              evidence={evidence}
              claims={state.claims}
              presentationWarnings={state.presentationWarnings}
              onInsertEvidence={
                typeof onInsertEvidence === "function"
                  ? ({ evidence: selectedEvidence, claims }) =>
                      onInsertEvidence({
                        runId: state.runId,
                        evidence: selectedEvidence,
                        claims,
                      })
                  : undefined
              }
            />
          ))}
        </div>
      ) : null}
      {hasIneligibleEvidence ? (
        <p role="status" className="text-cdt-sm text-cdt-slate-600">
          Parte de la evidencia no puede mostrarse porque no cumple las reglas de elegibilidad.
        </p>
      ) : null}
    </div>
  );
}
