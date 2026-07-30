/**
 * Lista de claims de UNA evidencia (ya filtrados por el llamador). Por
 * claim: `label` verificado o "Etiqueta no confirmada", `display_value`
 * exacto (nunca recalculado), `unit` sin tocar el valor, columnas y filas
 * fuente. Nunca infiere una etiqueta desde la prosa, el valor numérico o el
 * alias — solo usa `label`/`label_status` tal como llegan del backend.
 */
export function ClaimList({ claims }) {
  const list = Array.isArray(claims) ? claims : [];
  if (list.length === 0) return null;

  return (
    <ul className="flex flex-col gap-cdt-2">
      {list.map((claim, index) => {
        const hasVerifiedLabel =
          claim?.label_status === "verified" && typeof claim?.label === "string" && claim.label.trim() !== "";
        const label = hasVerifiedLabel ? claim.label : "Etiqueta no confirmada";
        const columns = Array.isArray(claim?.columns) ? claim.columns : [];
        const rows = Array.isArray(claim?.source_row_indexes) ? claim.source_row_indexes : [];

        return (
          <li key={claim?.claim_id ?? index} className="rounded-cdt-md border border-cdt-blue-100 p-cdt-3">
            <div className="flex flex-wrap items-baseline gap-cdt-2">
              <span
                className={
                  hasVerifiedLabel
                    ? "text-cdt-sm font-cdt-bold text-cdt-slate-900"
                    : "text-cdt-sm italic text-cdt-slate-600"
                }
              >
                {label}
              </span>
              <span className="text-cdt-base font-cdt-bold text-cdt-blue-900">
                {claim?.display_value ?? ""}
                {claim?.unit ? (
                  <span className="ml-cdt-1 text-cdt-sm font-cdt-normal text-cdt-slate-600">{claim.unit}</span>
                ) : null}
              </span>
            </div>
            {columns.length > 0 ? (
              <p className="text-cdt-xs text-cdt-slate-600">Columnas fuente: {columns.join(", ")}</p>
            ) : null}
            {rows.length > 0 ? (
              <p className="text-cdt-xs text-cdt-slate-600">Filas fuente: {rows.join(", ")}</p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
