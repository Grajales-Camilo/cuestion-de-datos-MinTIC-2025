import { cx } from "./cx";

/**
 * Marcador de posición de carga. Decorativo por defecto (`aria-hidden`):
 * un lector de pantalla no debe anunciar cada bloque individual — quien
 * necesite anunciar "cargando" usa `LiveRegion` aparte, una sola vez.
 * Pulso suave y moderado (no shimmer en movimiento, sin degradado);
 * respeta `prefers-reduced-motion` a través de la regla ya declarada en
 * `.cdt-v2` (globals.css), que fuerza `animation-duration: 0.01ms`.
 */
export function Skeleton({ as: Component = "div", className, ...rest }) {
  return (
    <Component
      aria-hidden="true"
      className={cx("animate-pulse rounded-cdt-sm bg-cdt-blue-100", className)}
      {...rest}
    />
  );
}
