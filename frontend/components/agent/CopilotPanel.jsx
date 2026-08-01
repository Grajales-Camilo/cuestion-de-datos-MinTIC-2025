import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { IconButton } from "../ui/IconButton";
import { Modal } from "../ui/Modal";

const DESKTOP_QUERY = "(min-width: 1024px)";

const MIN_COPILOT_WIDTH_PX = 320;
const MAX_COPILOT_WIDTH_PX = 640;
const DEFAULT_COPILOT_WIDTH_PX = 420;
const KEYBOARD_RESIZE_STEP_PX = 24;

function clampCopilotWidth(value) {
  return Math.min(MAX_COPILOT_WIDTH_PX, Math.max(MIN_COPILOT_WIDTH_PX, value));
}

/**
 * Ancho del panel del copiloto (RF-105-02): arrastrable con el puntero y
 * operable por teclado, nunca solo uno de los dos. El separador vive en el
 * borde IZQUIERDO del panel — `aria-valuenow` es el ancho actual en px;
 * flecha izquierda AGRANDA el copiloto (el borde se corre hacia la
 * izquierda, le quita espacio al lienzo central), flecha derecha lo
 * ACHICA; Home/End saltan a los extremos. El estado no persiste entre
 * sesiones a propósito — cada carga de página arranca en
 * `DEFAULT_COPILOT_WIDTH_PX`, no es una preferencia declarada por el
 * usuario.
 */
function useResizableCopilotWidth() {
  const [widthPx, setWidthPx] = useState(DEFAULT_COPILOT_WIDTH_PX);
  const dragStateRef = useRef(null);

  function handlePointerMove(event) {
    const dragState = dragStateRef.current;
    if (!dragState) return;
    const deltaX = event.clientX - dragState.startX;
    setWidthPx(clampCopilotWidth(dragState.startWidth - deltaX));
  }

  function handlePointerUp() {
    dragStateRef.current = null;
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", handlePointerUp);
  }

  function handlePointerDown(event) {
    event.preventDefault();
    dragStateRef.current = { startX: event.clientX, startWidth: widthPx };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
  }

  function handleKeyDown(event) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setWidthPx((current) => clampCopilotWidth(current + KEYBOARD_RESIZE_STEP_PX));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setWidthPx((current) => clampCopilotWidth(current - KEYBOARD_RESIZE_STEP_PX));
    } else if (event.key === "Home") {
      event.preventDefault();
      setWidthPx(MAX_COPILOT_WIDTH_PX);
    } else if (event.key === "End") {
      event.preventDefault();
      setWidthPx(MIN_COPILOT_WIDTH_PX);
    }
  }

  return { widthPx, handlePointerDown, handleKeyDown };
}

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
  const { widthPx, handlePointerDown, handleKeyDown } = useResizableCopilotWidth();

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
    <div className="flex shrink-0">
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Cambiar ancho del panel del copiloto"
        aria-valuenow={Math.round(widthPx)}
        aria-valuemin={MIN_COPILOT_WIDTH_PX}
        aria-valuemax={MAX_COPILOT_WIDTH_PX}
        tabIndex={0}
        onPointerDown={handlePointerDown}
        onKeyDown={handleKeyDown}
        className="w-cdt-2 shrink-0 cursor-col-resize touch-none bg-cdt-blue-50 hover:bg-cdt-blue-100 focus-visible:bg-cdt-blue-100"
      />
      <aside
        aria-label={title}
        style={{ width: widthPx }}
        className="flex shrink-0 flex-col gap-cdt-4 bg-cdt-white p-cdt-4"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-cdt-lg font-cdt-bold text-cdt-blue-900">{title}</h2>
          <IconButton label="Cerrar copiloto" variant="quiet" onClick={onClose}>
            <X className="h-5 w-5" />
          </IconButton>
        </div>
        {children}
      </aside>
    </div>
  );
}
