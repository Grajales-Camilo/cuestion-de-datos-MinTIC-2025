import { Card, CardHeader, CardBody, CardFooter } from "../ui/Card";
import { QualityBadge } from "./QualityBadge";
import { EvidenceNarrative } from "./EvidenceNarrative";
import { ClaimList } from "./ClaimList";
import { PresentationWarnings } from "./PresentationWarnings";
import { EvidenceTable } from "./EvidenceTable";
import { EvidenceChart } from "./EvidenceChart";
import { QualityDetails } from "./QualityDetails";
import { CitationBlock } from "./CitationBlock";
import { DownloadCsvButton } from "./DownloadCsvButton";
import { CopyCitationButton } from "./CopyCitationButton";
import { InsertEvidenceButton } from "./InsertEvidenceButton";
import { buildQualityViewModel, isEligibleEvidence } from "../../lib/evidence";

function claimsForEvidence(claims, evidenceId) {
  if (!Array.isArray(claims) || !evidenceId) return [];
  return claims.filter((claim) => claim?.evidence_id === evidenceId);
}

function warningsForClaims(warnings, claimIds) {
  if (!Array.isArray(warnings)) return [];
  return warnings.filter((warning) => claimIds.has(warning?.claim_id));
}

/**
 * Tarjeta de evidencia (`implementation-plan.md` §8.2). Orden estable: 1)
 * dataset/publicador/QualityBadge, 2) narrativa, 3) claims, 4) advertencias
 * de presentación, 5) tabla, 5b) gráfica (RF-503, solo si aplica), 6)
 * detalle de calidad, 7) cita, 8) acciones. Recibe la evidencia completa y
 * SOLO los claims/advertencias que le corresponden por
 * `evidence_id`/`claim_id` — nunca la lista completa de la corrida. Sin
 * evidencia válida O sin elegibilidad confirmada (`isEligibleEvidence`,
 * fail-closed, F4-02-R1), no renderiza nada (nunca una tarjeta vacía, nunca
 * dataset/filas/claims/cita bloqueados en el DOM).
 */
export function EvidenceCard({ evidence, claims, presentationWarnings, onInsertEvidence }) {
  if (!evidence || typeof evidence !== "object") return null;
  if (!isEligibleEvidence(evidence)) return null;

  const ownClaims = claimsForEvidence(claims, evidence.evidence_id);
  const ownClaimIds = new Set(ownClaims.map((claim) => claim?.claim_id).filter(Boolean));
  const ownWarnings = warningsForClaims(presentationWarnings, ownClaimIds);
  const viewModel = buildQualityViewModel(evidence);

  return (
    <Card
      as="section"
      aria-label={`Evidencia: ${evidence.dataset_name ?? "dataset sin nombre"}`}
      className="flex flex-col"
    >
      <CardHeader className="flex flex-wrap items-center justify-between gap-cdt-2">
        <div className="flex flex-col">
          <span className="text-cdt-base font-cdt-bold text-cdt-slate-900">
            {evidence.dataset_name ?? "Dataset sin nombre"}
          </span>
          <span className="text-cdt-xs text-cdt-slate-600">{evidence.publisher ?? "Publicador no disponible"}</span>
        </div>
        <QualityBadge classification={viewModel.classification} />
      </CardHeader>
      <CardBody className="flex flex-col gap-cdt-4">
        <EvidenceNarrative narrative={evidence.narrative} claims={ownClaims} />
        <ClaimList claims={ownClaims} />
        <PresentationWarnings warnings={ownWarnings} />
        <EvidenceTable evidence={evidence} claims={ownClaims} />
        <EvidenceChart evidence={evidence} claims={ownClaims} />
        <QualityDetails evidence={evidence} />
        <CitationBlock evidence={evidence} />
      </CardBody>
      <CardFooter className="flex flex-wrap gap-cdt-2">
        <InsertEvidenceButton
          evidence={evidence}
          claims={claims}
          onInsertEvidence={onInsertEvidence}
        />
        <DownloadCsvButton evidence={evidence} claims={ownClaims} />
        <CopyCitationButton evidence={evidence} />
      </CardFooter>
    </Card>
  );
}
