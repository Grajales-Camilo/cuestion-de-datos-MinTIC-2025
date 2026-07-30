import { NodeViewWrapper } from "@tiptap/react";
import { CalendarDays, ExternalLink, PenLine } from "lucide-react";
import { getSafeExternalUrl } from "../../../lib/evidence/safeExternalUrl";

function displayValue(value) {
  if (value === null || value === undefined) return null;
  return String(value);
}

function MetadataRow({ label, children }) {
  return (
    <div className="grid min-w-0 gap-cdt-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-cdt-3">
      <dt className="text-cdt-xs font-cdt-bold text-cdt-slate-600">{label}</dt>
      <dd className="min-w-0 break-words text-cdt-sm text-cdt-slate-900">{children}</dd>
    </div>
  );
}

/**
 * Representación visual del nodo atómico manualEntry. Es deliberadamente
 * distinta de EvidenceCitationNodeView: no presenta calidad, claims,
 * consulta ni estado de verificación (T-506, RF-102, RNF-007/RNF-012).
 */
export function ManualDataEntryNodeView({ node, selected = false }) {
  const attrs = node.attrs ?? {};
  const safeUrl = getSafeExternalUrl(attrs.url);
  const value = displayValue(attrs.value);
  const text = displayValue(attrs.text);

  return (
    <NodeViewWrapper
      as="aside"
      role="group"
      aria-label="Aporte manual — no verificado por el agente"
      data-manual-entry="true"
      contentEditable={false}
      className={[
        "my-cdt-5 min-w-0 max-w-full rounded-cdt-md border border-dashed bg-cdt-white p-cdt-4",
        selected ? "border-cdt-blue-500 ring-1 ring-cdt-blue-500 ring-offset-2" : "border-cdt-blue-700",
      ].join(" ")}
    >
      <div className="flex min-w-0 flex-col gap-cdt-4">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-cdt-3">
          <p className="flex min-w-0 items-start gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-blue-900">
            <PenLine className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" focusable="false" />
            <span className="break-words">Aporte manual — no verificado por el agente</span>
          </p>
          <span className="shrink-0 rounded-cdt-full bg-cdt-blue-900 px-cdt-3 py-cdt-1 text-cdt-xs font-cdt-bold text-cdt-white">
            Escrito por el usuario
          </span>
        </div>

        {value !== null ? (
          <div className="min-w-0 rounded-cdt-md bg-cdt-blue-50 p-cdt-3">
            <p className="text-cdt-xs font-cdt-bold text-cdt-slate-600">Valor</p>
            <p className="mt-cdt-1 min-w-0 break-words whitespace-pre-wrap text-cdt-base text-cdt-slate-900">{value}</p>
          </div>
        ) : null}

        {text !== null ? (
          <div className="min-w-0">
            <p className="text-cdt-xs font-cdt-bold text-cdt-slate-600">Texto o descripción</p>
            <p className="mt-cdt-1 min-w-0 break-words whitespace-pre-wrap text-cdt-sm text-cdt-slate-900">{text}</p>
          </div>
        ) : null}

        <dl className="flex min-w-0 flex-col gap-cdt-3">
          <MetadataRow label="Fuente">{attrs.source}</MetadataRow>
          {attrs.date ? (
            <MetadataRow label="Fecha de la fuente">
              <span className="inline-flex items-center gap-cdt-2">
                <CalendarDays className="h-4 w-4 shrink-0 text-cdt-blue-700" aria-hidden="true" focusable="false" />
                {attrs.date}
              </span>
            </MetadataRow>
          ) : null}
        </dl>

        {safeUrl ? (
          <a
            href={safeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-cdt-tap w-fit max-w-full items-center gap-cdt-2 break-words text-cdt-sm font-cdt-bold text-cdt-blue-700 underline underline-offset-4"
          >
            Abrir fuente declarada
            <ExternalLink className="h-4 w-4 shrink-0" aria-hidden="true" focusable="false" />
          </a>
        ) : null}
      </div>
    </NodeViewWrapper>
  );
}

export default ManualDataEntryNodeView;
