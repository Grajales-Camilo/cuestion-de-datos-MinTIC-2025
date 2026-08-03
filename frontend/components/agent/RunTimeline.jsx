import { useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "../ui/Button";
import { RUN_STATUS } from "../../lib/agent/runStates";
import { StepDetailModal } from "./StepDetailModal";

/**
 * Estado condensado de la investigación en curso (RF-105-02 — revisión de
 * dirección sobre DESIGN-01, aprobada explícitamente por el usuario). La
 * ruta vertical continua (un `<li>` por paso, apilados con línea
 * conectora) se retira: con investigaciones largas obligaba a desplazarse
 * hasta el final para ver a dónde iba la corrida. Ahora una sola tarjeta
 * muestra el ÚLTIMO paso recibido; el historial completo no desaparece,
 * sigue disponible con su detalle técnico en `StepDetailModal` ("Ver
 * detalle técnico"). La deduplicación ya ocurrió en runReducer/streamRun:
 * este componente solo lee el último elemento de `state.steps`.
 */
export function RunTimeline({ steps, status }) {
  const [detailOpen, setDetailOpen] = useState(false);
  if (!steps || steps.length === 0) return null;

  const lastStep = steps[steps.length - 1];
  const isActive = status === RUN_STATUS.STREAMING;

  return (
    <div className="flex items-center gap-cdt-2 rounded-cdt-lg border border-cdt-blue-100 p-cdt-3">
      {isActive ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-cdt-blue-500" aria-hidden="true" focusable="false" />
      ) : (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-cdt-success" aria-hidden="true" focusable="false" />
      )}
      <p className="min-w-0 flex-1 text-cdt-sm text-cdt-slate-900">{lastStep.displayMessage}</p>
      <Button variant="quiet" onClick={() => setDetailOpen(true)}>
        Ver detalle técnico
      </Button>
      <StepDetailModal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        steps={steps}
        activeSeq={isActive ? lastStep.seq : null}
      />
    </div>
  );
}
