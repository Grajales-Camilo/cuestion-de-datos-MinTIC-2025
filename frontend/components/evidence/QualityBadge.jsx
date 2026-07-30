import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from "lucide-react";
import { cx } from "../ui/cx";

/**
 * Insignia de clasificación de calidad de una evidencia
 * (`contracts/validacion-calidad.md` §3.1). Icono + texto siempre visibles,
 * nunca solo color. Deliberadamente NO reutiliza el enum cerrado de
 * `components/ui/Badge.jsx` (ese es de estado de corrida, no de
 * clasificación de evidencia — ver `lib/evidence/quality.js`).
 */
const CONFIG = {
  alta: { icon: CheckCircle2, label: "Calidad alta", classes: "bg-cdt-blue-700 text-cdt-white" },
  media: { icon: AlertTriangle, label: "Calidad media", classes: "bg-cdt-blue-100 text-cdt-blue-900" },
  baja: { icon: AlertTriangle, label: "Calidad baja", classes: "bg-cdt-warning text-cdt-white" },
  no_recomendada: { icon: XCircle, label: "No recomendada", classes: "bg-cdt-error text-cdt-white" },
  desconocida: { icon: HelpCircle, label: "Calidad no clasificada", classes: "bg-cdt-slate-600 text-cdt-white" },
};

export function QualityBadge({ classification, className }) {
  const config = CONFIG[classification] ?? CONFIG.desconocida;
  const Icon = config.icon;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-cdt-1 rounded-cdt-full px-cdt-3 py-cdt-1",
        "font-cdt-sans text-cdt-xs font-cdt-bold",
        config.classes,
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" focusable="false" />
      {config.label}
    </span>
  );
}
