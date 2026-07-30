import { NodeViewWrapper } from "@tiptap/react";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Database,
  ExternalLink,
  FileQuestion,
  Landmark,
  ShieldCheck,
} from "lucide-react";
import { getSafeExternalUrl } from "../../../lib/evidence/safeExternalUrl";

const QUALITY_LABELS = Object.freeze({
  alta: "Calidad alta",
  media: "Calidad media",
  baja: "Calidad baja",
  no_recomendada: "Evidencia no recomendada",
});

const QUALITY_PRESENTATION = Object.freeze({
  alta: {
    className: "bg-cdt-success text-cdt-white",
    icon: ShieldCheck,
  },
  media: {
    className: "bg-cdt-warning text-cdt-white",
    icon: AlertTriangle,
  },
  baja: {
    className: "bg-cdt-warning text-cdt-white",
    icon: AlertTriangle,
  },
  no_recomendada: {
    className: "bg-cdt-warning text-cdt-white",
    icon: AlertTriangle,
  },
});

function formatDateTime(value) {
  if (typeof value !== "string" || value.trim() === "") return "No disponible";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No disponible";
  return new Intl.DateTimeFormat("es-CO", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function cutoffLabel(attrs) {
  if (attrs.dataCutoffBasis === "data_updated_at_fallback") {
    return {
      label: "Actualización del portal",
      value: formatDateTime(attrs.dataUpdatedAt ?? attrs.dataCutoffAt),
    };
  }
  if (attrs.dataCutoffAt) {
    return { label: "Corte disponible", value: formatDateTime(attrs.dataCutoffAt) };
  }
  return { label: "Actualización disponible", value: formatDateTime(attrs.dataUpdatedAt) };
}

function MetadataRow({ icon: Icon, label, children }) {
  return (
    <div className="grid min-w-0 gap-cdt-1 sm:grid-cols-[10rem_minmax(0,1fr)] sm:gap-cdt-3">
      <dt className="flex items-start gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-slate-600">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" focusable="false" />
        {label}
      </dt>
      <dd className="min-w-0 break-words text-cdt-sm text-cdt-slate-900">{children}</dd>
    </div>
  );
}

/**
 * Vista React del nodo atómico `evidenceCitation` (T-504, RF-103/RF-404).
 * Renderiza solo la lista blanca persistida por F5-01. Nunca refleja el
 * objeto de atributos como JSON ni como atributos `data-*`.
 */
export function EvidenceCitationNodeView({ node, selected }) {
  const attrs = node.attrs ?? {};
  const safeSourceUrl = getSafeExternalUrl(attrs.sourceUrl);
  const claims = Array.isArray(attrs.claims) ? attrs.claims : [];
  const cutoff = cutoffLabel(attrs);
  // La clasificación persistida basta para mostrar la advertencia. El
  // validador contractual exige además `warningRequired: true`, pero la vista
  // falla hacia el lado seguro incluso si recibe un nodo aislado mal formado.
  const isNotRecommended = attrs.qualityClassification === "no_recomendada";
  const qualityPresentation = QUALITY_PRESENTATION[attrs.qualityClassification] ?? {
    className: "bg-cdt-blue-900 text-cdt-white",
    icon: FileQuestion,
  };
  const QualityIcon = qualityPresentation.icon;
  const qualityLabel =
    QUALITY_LABELS[attrs.qualityClassification] ?? "Calidad no clasificada";

  return (
    <NodeViewWrapper
      as="aside"
      role="group"
      aria-label={`Cita de evidencia: ${attrs.datasetName ?? "dataset sin nombre"}`}
      data-evidence-citation="true"
      contentEditable={false}
      className={[
        "my-cdt-5 min-w-0 max-w-full rounded-cdt-lg border bg-cdt-blue-50 p-cdt-4",
        selected ? "border-cdt-blue-500" : "border-cdt-blue-100",
      ].join(" ")}
    >
      <div className="flex min-w-0 flex-col gap-cdt-4">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-cdt-3">
          <div className="min-w-0">
            <p className="flex items-center gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-blue-900">
              <Database className="h-4 w-4 shrink-0" aria-hidden="true" focusable="false" />
              Cita de evidencia
            </p>
            <p className="mt-cdt-1 break-words text-cdt-base font-cdt-bold text-cdt-slate-900">
              {attrs.datasetName ?? "Dataset sin nombre"}
            </p>
          </div>
          <span
            className={[
              "inline-flex items-center gap-cdt-2 rounded-cdt-full px-cdt-3 py-cdt-1 text-cdt-xs font-cdt-bold",
              qualityPresentation.className,
            ].join(" ")}
          >
            <QualityIcon className="h-4 w-4" aria-hidden="true" focusable="false" />
            {qualityLabel}
          </span>
        </div>

        {isNotRecommended ? (
          <p className="flex items-start gap-cdt-2 rounded-cdt-md bg-cdt-white p-cdt-3 text-cdt-sm font-cdt-bold text-cdt-warning">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" focusable="false" />
            Evidencia no recomendada: úsala con cautela.
          </p>
        ) : null}

        <dl className="flex min-w-0 flex-col gap-cdt-3">
          <MetadataRow icon={Landmark} label="Entidad publicadora">
            {attrs.publisher ?? "No disponible"}
          </MetadataRow>
          <MetadataRow icon={FileQuestion} label="Consulta de origen">
            <span className="whitespace-pre-wrap break-all">{attrs.soqlQuery ?? "No disponible"}</span>
          </MetadataRow>
          <MetadataRow icon={CalendarClock} label="Fecha de consulta">
            {formatDateTime(attrs.executedAt)}
          </MetadataRow>
          <MetadataRow icon={CalendarClock} label={cutoff.label}>
            {cutoff.value}
          </MetadataRow>
        </dl>

        <div className="min-w-0">
          <h3 className="flex items-center gap-cdt-2 text-cdt-sm font-cdt-bold text-cdt-blue-900">
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" focusable="false" />
            Claims asociados
          </h3>
          {claims.length > 0 ? (
            <ul className="mt-cdt-2 flex min-w-0 flex-col gap-cdt-2">
              {claims.map((claim) => (
                <li
                  key={claim.claimId}
                  className="min-w-0 break-words rounded-cdt-md bg-cdt-white p-cdt-3 text-cdt-sm text-cdt-slate-900"
                >
                  <span className="font-cdt-bold">{claim.label ?? "Etiqueta no confirmada"}:</span>{" "}
                  {claim.displayValue}
                  {claim.unit ? ` ${claim.unit}` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-cdt-2 text-cdt-sm text-cdt-slate-600">No hay claims asociados.</p>
          )}
        </div>

        {safeSourceUrl ? (
          <a
            href={safeSourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-cdt-tap w-fit max-w-full items-center gap-cdt-2 break-words text-cdt-sm font-cdt-bold text-cdt-blue-700 underline underline-offset-4"
          >
            Abrir fuente original
            <ExternalLink className="h-4 w-4 shrink-0" aria-hidden="true" focusable="false" />
          </a>
        ) : null}
      </div>
    </NodeViewWrapper>
  );
}

export default EvidenceCitationNodeView;
