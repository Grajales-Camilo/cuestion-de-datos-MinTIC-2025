import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cx } from "./cx";

/**
 * Revela/oculta contenido secundario tras un `<button>` real con
 * `aria-expanded`/`aria-controls` — completamente operable por teclado
 * (Enter/Espacio nativos del elemento `button`, sin JS adicional).
 *
 * Regla de uso (no se impone en código, se documenta): la información
 * crítica para responder la pregunta del usuario nunca debe vivir
 * exclusivamente dentro de un Disclosure cerrado por defecto — solo
 * detalle técnico ampliable (ver EvidenceCard en el plan, §8).
 */
export function Disclosure({
  summary,
  children,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  className,
}) {
  const generatedId = useId();
  const panelId = `disclosure-panel-${generatedId}`;
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;

  function toggle() {
    const next = !open;
    if (!isControlled) setUncontrolledOpen(next);
    onOpenChange?.(next);
  }

  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={toggle}
        className={cx(
          "inline-flex min-h-cdt-tap items-center gap-cdt-1 rounded-cdt-md",
          "font-cdt-sans text-cdt-sm font-cdt-bold text-cdt-blue-700",
          "transition-colors duration-cdt-base ease-cdt-standard hover:text-cdt-blue-900"
        )}
      >
        <ChevronDown
          className={cx("h-4 w-4 transition-transform duration-cdt-base ease-cdt-standard", open && "rotate-180")}
          aria-hidden="true"
          focusable="false"
        />
        {summary}
      </button>
      <div id={panelId} hidden={!open}>
        {children}
      </div>
    </div>
  );
}
