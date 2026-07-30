import { AlertTriangle } from "lucide-react";

/**
 * Bloque propio para `presentation_warnings` (`contracts/api-rest.md`
 * §4c) — NUNCA fusionado con `quality.warnings_user` (eso vive en
 * `QualityDetails`). Muestra el `message_user` textual; `code` nunca es el
 * mensaje principal. Sin advertencias, no renderiza nada.
 */
export function PresentationWarnings({ warnings }) {
  const list = Array.isArray(warnings)
    ? warnings.filter((warning) => typeof warning?.message_user === "string" && warning.message_user.trim() !== "")
    : [];
  if (list.length === 0) return null;

  return (
    <div className="flex flex-col gap-cdt-1 rounded-cdt-md bg-cdt-blue-50 p-cdt-3">
      <div className="flex items-center gap-cdt-1">
        <AlertTriangle className="h-4 w-4 text-cdt-warning" aria-hidden="true" focusable="false" />
        <span className="text-cdt-xs font-cdt-bold text-cdt-slate-900">Advertencia sobre esta cifra</span>
      </div>
      <ul className="flex flex-col gap-cdt-1 text-cdt-sm text-cdt-slate-900">
        {list.map((warning, index) => (
          <li key={warning.claim_id ?? index}>{warning.message_user}</li>
        ))}
      </ul>
    </div>
  );
}
