import { cx } from "./cx";

/**
 * Contenedor base. Sin sombra dura ni degradado (constitution.md Art. V.2):
 * un borde de 1px y un radio pequeño bastan para separar del fondo.
 */
export function Card({ as: Component = "div", className, children, ...rest }) {
  return (
    <Component
      className={cx(
        "rounded-cdt-lg border border-cdt-blue-100 bg-cdt-white",
        className
      )}
      {...rest}
    >
      {children}
    </Component>
  );
}

export function CardHeader({ className, children, ...rest }) {
  return (
    <div
      className={cx("border-b border-cdt-blue-100 px-cdt-4 py-cdt-3", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardBody({ className, children, ...rest }) {
  return (
    <div className={cx("px-cdt-4 py-cdt-4", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardFooter({ className, children, ...rest }) {
  return (
    <div
      className={cx("flex gap-cdt-2 border-t border-cdt-blue-100 px-cdt-4 py-cdt-3", className)}
      {...rest}
    >
      {children}
    </div>
  );
}
