import { cx } from "./cx";

/**
 * Oculta visualmente el contenido sin ocultarlo de lectores de pantalla.
 * Usa la utilidad `sr-only` incorporada en el núcleo de Tailwind (no un
 * valor arbitrario propio): posición absoluta, 1×1px, `clip` y
 * `overflow: hidden` — el patrón estándar documentado en design-principles
 * cap. 1 §"Jerarquía visual y semántica".
 */
export function VisuallyHidden({ as: Component = "span", className, children, ...rest }) {
  return (
    <Component className={cx("sr-only", className)} {...rest}>
      {children}
    </Component>
  );
}
