import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { IconButton } from "../ui/IconButton";
import { Modal } from "../ui/Modal";

const DESKTOP_QUERY = "(min-width: 1024px)";

/**
 * El estado inicial es SIEMPRE `true` (escritorio), sin leer `window` en el
 * primer render: en SSR real (`pages/app.js`) el servidor no tiene
 * `window.matchMedia`, así que su HTML siempre asume escritorio. Si el
 * cliente leyera el valor real ya en su primer render (antes de montar),
 * un visitante en un viewport angosto produciría un primer render
 * distinto del HTML del servidor — error de hidratación real ("Did not
 * expect server HTML to contain a `<aside>` in `<main>`"), no solo
 * teórico: así fue como se detectó este defecto en un test E2E a 320px.
 * El valor real solo se aplica DESPUÉS de montar (mismo patrón que
 * `Modal.jsx`), con el costo aceptado de un parpadeo breve hacia el
 * layout de escritorio en dispositivos móviles antes de corregirse.
 */
function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(true);
  useEffect(() => {
    const mql = window.matchMedia(DESKTOP_QUERY);
    setIsDesktop(mql.matches);
    function handleChange(event) {
      setIsDesktop(event.matches);
    }
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, []);
  return isDesktop;
}

/**
 * `≥1024px`: panel lateral fijo, colapsable, sin trampa de foco (vive en
 * flujo normal de la página, como un `aside`). `<1024px`: drawer a
 * pantalla completa reutilizando la primitiva `Modal` de F1 — foco
 * atrapado y restaurado, cierre con Escape, ya probado ahí. En ambos casos
 * el botón de cierre tiene nombre accesible; el reflujo a 320px no
 * introduce scroll horizontal (contenido en columna única, sin anchos
 * fijos en px para texto).
 */
export function CopilotPanel({ open, onClose, title = "Copiloto", children }) {
  const isDesktop = useIsDesktop();
  const previouslyFocusedRef = useRef(null);

  // Modo panel (≥1024px): no es modal, así que no atrapa foco, pero SÍ lo
  // restaura al cerrarse — mismo principio que Modal.jsx, aplicado aquí
  // porque un `<aside>` en flujo normal no lo hace por sí solo.
  useEffect(() => {
    if (!isDesktop) return;
    if (open) {
      previouslyFocusedRef.current = document.activeElement;
    } else if (previouslyFocusedRef.current) {
      previouslyFocusedRef.current.focus?.();
      previouslyFocusedRef.current = null;
    }
  }, [open, isDesktop]);

  if (!isDesktop) {
    return (
      <Modal open={open} onClose={onClose} title={title} className="h-full max-w-none w-full rounded-none">
        {children}
      </Modal>
    );
  }

  if (!open) return null;

  return (
    <aside
      aria-label={title}
      className="flex w-full max-w-md shrink-0 flex-col gap-cdt-4 border-l border-cdt-blue-100 bg-cdt-white p-cdt-4"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-cdt-lg font-cdt-bold text-cdt-blue-900">{title}</h2>
        <IconButton label="Cerrar copiloto" variant="quiet" onClick={onClose}>
          <X className="h-5 w-5" />
        </IconButton>
      </div>
      {children}
    </aside>
  );
}
