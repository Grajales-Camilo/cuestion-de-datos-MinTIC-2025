import { forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "./cx";

const VARIANT_CLASSES = {
  primary: "bg-cdt-blue-700 text-cdt-white hover:bg-cdt-blue-900 active:bg-cdt-blue-900",
  secondary:
    "bg-cdt-blue-50 text-cdt-blue-700 border border-cdt-blue-100 hover:bg-cdt-blue-100 active:bg-cdt-blue-100",
  quiet: "bg-transparent text-cdt-blue-700 hover:bg-cdt-blue-50 active:bg-cdt-blue-100",
  destructive: "bg-cdt-error text-cdt-white hover:brightness-90 active:brightness-95",
};

/**
 * Botón de solo icono. `label` es obligatorio: se convierte en el nombre
 * accesible (`aria-label`) porque no hay texto visible que lo provea. El
 * icono en sí (children) siempre queda fuera del árbol accesible
 * (`aria-hidden`) para que los lectores de pantalla no dupliquen el nombre.
 */
export const IconButton = forwardRef(function IconButton(
  { variant = "quiet", loading = false, disabled = false, type = "button", label, className, children, ...rest },
  ref
) {
  if (!label) {
    throw new Error("IconButton requiere la prop `label` como nombre accesible.");
  }
  const isDisabled = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-label={label}
      aria-busy={loading || undefined}
      className={cx(
        "inline-flex items-center justify-center rounded-cdt-none",
        "h-cdt-tap w-cdt-tap",
        "transition-colors duration-cdt-base ease-cdt-standard",
        "disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none",
        VARIANT_CLASSES[variant],
        className
      )}
      {...rest}
    >
      {loading ? (
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" focusable="false" />
      ) : (
        <span aria-hidden="true" className="inline-flex h-5 w-5 items-center justify-center">
          {children}
        </span>
      )}
    </button>
  );
});

IconButton.displayName = "IconButton";
