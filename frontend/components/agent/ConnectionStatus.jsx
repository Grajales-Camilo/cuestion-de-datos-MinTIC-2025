import { Wifi, WifiOff, RotateCw, LogOut } from "lucide-react";
import { Button } from "../ui/Button";
import { RUN_STATUS } from "../../lib/agent/runStates";

const MAX_RETRIES = 6;

/**
 * Cuatro estados visibles con texto + icono, nunca solo color
 * (`implementation-plan.md` §8.1): En vivo · Reconectando (intento N de 6)
 * · Sin conexión — Reintentar · Dejaste de seguirla.
 */
export function ConnectionStatus({ status, reconnectAttempt, onRetry }) {
  if (status === RUN_STATUS.STREAMING) {
    return (
      <p className="flex items-center gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-success">
        <Wifi className="h-4 w-4" aria-hidden="true" focusable="false" />
        En vivo
      </p>
    );
  }

  if (status === RUN_STATUS.RECONNECTING) {
    return (
      <p className="flex items-center gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-warning">
        <RotateCw className="h-4 w-4 animate-spin" aria-hidden="true" focusable="false" />
        Reconectando — intento {reconnectAttempt ?? 1} de {MAX_RETRIES}
      </p>
    );
  }

  if (status === RUN_STATUS.DISCONNECTED) {
    return (
      <div className="flex items-center gap-cdt-3">
        <p className="flex items-center gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-error">
          <WifiOff className="h-4 w-4" aria-hidden="true" focusable="false" />
          Sin conexión
        </p>
        {onRetry ? (
          <Button variant="secondary" onClick={onRetry}>
            Reintentar
          </Button>
        ) : null}
      </div>
    );
  }

  if (status === RUN_STATUS.DETACHED) {
    return (
      <p className="flex items-center gap-cdt-2 text-cdt-xs font-cdt-bold text-cdt-slate-600">
        <LogOut className="h-4 w-4" aria-hidden="true" focusable="false" />
        Dejaste de seguirla
      </p>
    );
  }

  return null;
}
