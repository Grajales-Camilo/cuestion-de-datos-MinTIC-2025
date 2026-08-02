import { forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "./cx";

/**
 * Botón accesible del sistema visual v2. Cuatro variantes exactas —
 * primaria, secundaria, silenciosa y destructiva — sin variantes
 * adicionales (DESIGN.md: jerarquía de acciones por color/peso, no por
 * cantidad de estilos). El consumidor debe renderizar este componente
 * dentro de un contenedor `.cdt-v2` para heredar tipografía y foco.
 * PALETTE-02: esquinas rectas (`rounded-cdt-none`) a propósito — es la
 * única primitiva de "control con apariencia de botón"; tarjetas, modales
 * y campos de texto conservan su radio.
 */
const VARIANT_CLASSES = {
  primary: "bg-cdt-blue-700 text-cdt-white hover:bg-cdt-blue-900 active:bg-cdt-blue-900",
  secondary:
    "bg-cdt-blue-50 text-cdt-blue-700 border border-cdt-blue-100 hover:bg-cdt-blue-100 active:bg-cdt-blue-100",
  quiet: "bg-transparent text-cdt-blue-700 hover:bg-cdt-blue-50 active:bg-cdt-blue-100",
  destructive: "bg-cdt-error text-cdt-white hover:brightness-90 active:brightness-95",
};

export const Button = forwardRef(function Button(
  {
    as: Component = "button",
    variant = "primary",
    loading = false,
    disabled = false,
    type = "button",
    className,
    children,
    ...rest
  },
  ref
) {
  const isDisabled = disabled || loading;
  const isButtonElement = Component === "button";
  return (
    <Component
      ref={ref}
      type={isButtonElement ? type : undefined}
      disabled={isButtonElement ? isDisabled : undefined}
      aria-disabled={!isButtonElement && isDisabled ? true : undefined}
      aria-busy={loading || undefined}
      className={cx(
        "inline-flex items-center justify-center gap-cdt-2 rounded-cdt-none px-cdt-4",
        "min-h-cdt-tap font-cdt-sans text-cdt-sm font-cdt-bold",
        "transition-colors duration-cdt-base ease-cdt-standard",
        "disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none",
        VARIANT_CLASSES[variant],
        className
      )}
      {...rest}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" focusable="false" />
      ) : null}
      {children}
    </Component>
  );
});

Button.displayName = "Button";
