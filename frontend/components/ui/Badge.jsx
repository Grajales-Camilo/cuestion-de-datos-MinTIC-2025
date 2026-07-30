import { CheckCircle2, AlertTriangle, Info, XCircle, PauseCircle } from "lucide-react";
import { cx } from "./cx";

/**
 * Insignia de estado. El significado nunca depende solo del color: cada
 * `status` trae su propio icono y su propio texto en español, visibles
 * siempre — no hay una variante "solo color". Conjunto cerrado de 5
 * estados reales del contrato del agente (nunca se inventan estados
 * nuevos aquí; ver `contracts/api-rest.md`).
 *
 * Corrección semántica normativa (no reabrir):
 * - `verified`/`completed` → verde. Evidencia verificada.
 * - `no_evidence` → NEUTRAL (azul profundo sobre fondo azul claro), nunca
 *   rojo: la ausencia de evidencia es un resultado honesto, no un error.
 * - `interrupted` → ámbar. Cobertura parcial.
 * - `warning` → ámbar. Advertencia de presentación.
 * - `failed` → rojo. Fallo real o dato rechazado.
 */
const STATUS_CONFIG = {
  verified: {
    icon: CheckCircle2,
    label: "Verificado",
    classes: "bg-cdt-success text-cdt-white",
  },
  warning: {
    icon: AlertTriangle,
    label: "Advertencia",
    classes: "bg-cdt-warning text-cdt-white",
  },
  no_evidence: {
    icon: Info,
    label: "Sin evidencia elegible",
    classes: "bg-cdt-blue-50 text-cdt-blue-900",
  },
  interrupted: {
    icon: PauseCircle,
    label: "Interrumpido",
    classes: "bg-cdt-warning text-cdt-white",
  },
  failed: {
    icon: XCircle,
    label: "Fallido",
    classes: "bg-cdt-error text-cdt-white",
  },
};

export function Badge({ status, children, className, ...rest }) {
  const config = STATUS_CONFIG[status];
  if (!config) {
    throw new Error(
      `Badge: status "${status}" no reconocido. Valores válidos: ${Object.keys(STATUS_CONFIG).join(", ")}.`
    );
  }
  const Icon = config.icon;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-cdt-1 rounded-cdt-full px-cdt-3 py-cdt-1",
        "font-cdt-sans text-cdt-xs font-cdt-bold",
        config.classes,
        className
      )}
      {...rest}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" focusable="false" />
      {children ?? config.label}
    </span>
  );
}
