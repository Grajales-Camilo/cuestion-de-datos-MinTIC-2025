import { CheckCircle2, Loader2 } from "lucide-react";
import { Disclosure } from "../ui/Disclosure";

/**
 * Un punto de la ruta central (Variante A, DESIGN-01). El paso activo se
 * distingue por icono Y color a la vez (spinner azul vs. check verde) —
 * nunca solo por color. El detalle técnico (`node`, `detail` crudo) vive
 * dentro de un `<Disclosure>`; nunca se muestra `message_dev` aquí (los
 * pasos no lo traen — solo `state.error`, que StepItem no toca).
 */
export function StepItem({ step, active }) {
  const hasDetail = Boolean(step.node || (step.detail && Object.keys(step.detail).length > 0));

  return (
    <li className="relative flex flex-col gap-cdt-1 border-l-2 border-cdt-blue-100 py-cdt-1 pb-cdt-4 pl-cdt-4 last:pb-0">
      <span
        className={`absolute -left-[7px] top-1 h-3 w-3 rounded-cdt-full ${
          active ? "bg-cdt-blue-500" : "bg-cdt-success"
        }`}
        aria-hidden="true"
      />
      <div className="flex items-center gap-cdt-2">
        {active ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-cdt-blue-500" aria-hidden="true" focusable="false" />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-cdt-success" aria-hidden="true" focusable="false" />
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
}
