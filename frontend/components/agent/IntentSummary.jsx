import { Button } from "../ui/Button";

/**
 * Presenta `state.intention` (forma real observada en corridas: `{topic,
 * entity, period, operation, territory}` — diverge del ejemplo de
 * `contracts/api-rest.md` §4, que muestra un string; se sigue la forma real
 * del runtime, ya consumida así por `runReducer`). Nunca renderiza `null`,
 * `undefined` ni un campo ausente: cada fragmento de la frase solo aparece
 * si el dato realmente llegó.
 */
export function IntentSummary({ intention, onReformulate }) {
  if (!intention || typeof intention !== "object") return null;

  const { topic, entity, territory, period, operation } = intention;
  const hasAny = Boolean(topic || entity || territory || period || operation);
  if (!hasAny) return null;

  return (
    <div className="rounded-cdt-md bg-cdt-blue-50 p-cdt-3">
      <p className="text-cdt-sm text-cdt-slate-900">
        Entendí:{" "}
        {topic ? <strong className="text-cdt-blue-900">{topic}</strong> : null}
        {entity ? (
          <>
            {" "}
            sobre <strong className="text-cdt-blue-900">{entity}</strong>
          </>
        ) : null}
        {territory ? (
          <>
            {" "}
            en <strong className="text-cdt-blue-900">{territory}</strong>
          </>
        ) : null}
        {period ? (
          <>
            , periodo <strong className="text-cdt-blue-900">{period}</strong>
          </>
        ) : null}
        {operation ? (
          <>
            , operación <strong className="text-cdt-blue-900">{operation}</strong>
          </>
        ) : null}
        .
      </p>
      {onReformulate ? (
        <Button variant="quiet" onClick={onReformulate} className="mt-cdt-2">
          No es lo que quería — reformular
        </Button>
      ) : null}
    </div>
  );
}
