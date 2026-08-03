import { CheckCircle2, Loader2 } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Disclosure } from "../ui/Disclosure";

/**
 * Selector de pasos con su detalle técnico (RF-105-02). Reemplaza el
 * disclosure que antes vivía en cada punto de la ruta vertical retirada
 * (`StepItem.jsx`, ya no existe): aquí el usuario elige QUÉ paso desplegar,
 * en vez de tenerlos todos siempre visibles uno tras otro. El contenido de
 * cada detalle (nodo + JSON crudo) es exactamente el mismo de antes.
 *
 * Recibe la misma referencia de `steps` que `RunTimeline`: si la
 * investigación sigue en curso mientras el modal está abierto, la lista se
 * actualiza sola en el siguiente render — no hay lógica de "tiempo real"
 * propia de este componente, ni una copia congelada al abrir.
 */
export function StepDetailModal({ open, onClose, steps, activeSeq }) {
  return (
    <Modal open={open} onClose={onClose} title="Detalle técnico de la investigación" className="max-w-lg">
      <ul className="flex flex-col divide-y divide-cdt-blue-100" aria-label="Pasos de la investigación">
        {steps.map((step) => {
          const hasDetail = Boolean(step.node || (step.detail && Object.keys(step.detail).length > 0));
          const isActive = step.seq === activeSeq;
          return (
            <li key={step.seq} className="flex flex-col gap-cdt-1 py-cdt-3 first:pt-0 last:pb-0">
              <div className="flex items-center gap-cdt-2">
                {isActive ? (
                  <Loader2
                    className="h-4 w-4 shrink-0 animate-spin text-cdt-blue-500"
                    aria-hidden="true"
                    focusable="false"
                  />
                ) : (
                  <CheckCircle2
                    className="h-4 w-4 shrink-0 text-cdt-success"
                    aria-hidden="true"
                    focusable="false"
                  />
                )}
                <p className="text-cdt-sm text-cdt-slate-900">{step.displayMessage}</p>
              </div>
              {hasDetail ? (
                <Disclosure summary="Ver detalle técnico">
                  <dl className="mt-cdt-1 rounded-cdt-md bg-cdt-blue-50 p-cdt-2 text-cdt-xs text-cdt-slate-600">
                    {step.node ? (
                      <>
                        <dt className="inline font-cdt-bold text-cdt-slate-900">Nodo: </dt>
                        <dd className="inline">{step.node}</dd>
                      </>
                    ) : null}
                    {step.detail && Object.keys(step.detail).length > 0 ? (
                      <pre className="mt-cdt-1 whitespace-pre-wrap break-words text-cdt-xs">
                        {JSON.stringify(step.detail, null, 2)}
                      </pre>
                    ) : null}
                  </dl>
                </Disclosure>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Modal>
  );
}
