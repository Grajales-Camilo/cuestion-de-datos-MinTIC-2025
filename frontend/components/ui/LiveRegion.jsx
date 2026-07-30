import { VisuallyHidden } from "./VisuallyHidden";

/**
 * Región viva `aria-live="polite"` agrupada (constitution.md Art. V.4,
 * frontend/AGENTS.md: "no se anuncia cada paso de forma agresiva"). Recibe
 * un único `message` actual — no una lista que crece — para que el
 * lector de pantalla anuncie un solo mensaje sustituido, nunca una
 * acumulación ruidosa de pasos históricos. `aria-atomic="true"` asegura
 * que el mensaje completo se lea de una vez, no solo el fragmento que
 * cambió.
 *
 * Este componente NO conoce al agente ni al backend: no emite eventos,
 * no simula progreso, solo anuncia el texto que se le pasa (eso llega en
 * F2/F3 desde `runReducer` real).
 */
export function LiveRegion({ message, visuallyHidden = true }) {
  if (visuallyHidden) {
    return (
      <VisuallyHidden as="div" role="status" aria-live="polite" aria-atomic="true">
        {message}
      </VisuallyHidden>
    );
  }
  return (
    <div role="status" aria-live="polite" aria-atomic="true">
      {message}
    </div>
  );
}
