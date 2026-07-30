import { StepItem } from "./StepItem";
import { RUN_STATUS } from "../../lib/agent/runStates";

/**
 * `ol` semántico de la ruta central. Acepta cualquier cantidad de pasos y
 * repeticiones legítimas (reintentos de plan, etc.) — nunca asume un
 * número fijo de nodos ni los de una sola corrida particular. La
 * deduplicación ya ocurrió en `runReducer`/`streamRun`; este componente
 * solo renderiza lo que `state.steps` ya trae, sin filtrar de nuevo.
 */
export function RunTimeline({ steps, status }) {
  if (!steps || steps.length === 0) return null;

  const activeSeq = status === RUN_STATUS.STREAMING ? steps[steps.length - 1]?.seq : null;

  return (
    <ol className="flex flex-col" aria-label="Pasos de la investigación">
      {steps.map((step) => (
        <StepItem key={step.seq} step={step} active={step.seq === activeSeq} />
      ))}
    </ol>
  );
}
