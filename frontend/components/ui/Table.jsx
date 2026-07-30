import { useId } from "react";
import { cx } from "./cx";

/**
 * Tabla de datos accesible. Exige `caption` o, en su defecto, un
 * `aria-label`/`aria-labelledby` propio en `...rest` — lanza si no hay
 * ninguno; nunca se renderiza una tabla sin nombre accesible. Encabezados
 * semánticos (`<th scope="col">`), sin simularlos con `<div>`.
 *
 * El contenedor con scroll horizontal es además `role="region"` +
 * `tabIndex={0}`: así un usuario de teclado puede enfocarlo y desplazarlo
 * con las flechas cuando la tabla es más ancha que su columna (sin esto,
 * el contenido desplazable sería inalcanzable por teclado). Su nombre
 * accesible reutiliza el `id` del `<caption>` visible vía
 * `aria-labelledby` — no repite el texto como un `aria-label` aparte, para
 * que un lector de pantalla no anuncie la misma descripción dos veces.
 */
export function Table({
  caption,
  columns,
  rows,
  getRowKey,
  className,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
  ...rest
}) {
  const captionId = useId();
  const hasCaption = Boolean(caption);
  const hasExternalName = Boolean(ariaLabel || ariaLabelledBy);

  if (!hasCaption && !hasExternalName) {
    throw new Error(
      "Table requiere `caption` o, en su defecto, `aria-label`/`aria-labelledby` — una tabla nunca se renderiza sin nombre accesible."
    );
  }

  // El nombre accesible vive en el contenedor desplazable (`role="region"`)
  // — la tabla anidada no repite el mismo `aria-label`/`aria-labelledby`,
  // para que un lector de pantalla no anuncie la misma descripción dos
  // veces al entrar a la región y luego a la tabla.
  const regionNameProps = hasCaption ? { "aria-labelledby": captionId } : { "aria-label": ariaLabel, "aria-labelledby": ariaLabelledBy };

  return (
    <div
      role="region"
      tabIndex={0}
      {...regionNameProps}
      className={cx("overflow-x-auto rounded-cdt-md border border-cdt-blue-100", className)}
    >
      <table className="w-full min-w-max border-collapse font-cdt-sans text-cdt-sm" {...rest}>
        {hasCaption ? (
          <caption id={captionId} className="px-cdt-3 py-cdt-2 text-left text-cdt-xs text-cdt-slate-600">
            {caption}
          </caption>
        ) : null}
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className="bg-cdt-blue-50 px-cdt-3 py-cdt-2 text-left font-cdt-bold text-cdt-slate-600"
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={getRowKey ? getRowKey(row, index) : index}>
              {columns.map((col) => (
                <td key={col.key} className="border-t border-cdt-blue-50 px-cdt-3 py-cdt-2 text-cdt-slate-900">
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
