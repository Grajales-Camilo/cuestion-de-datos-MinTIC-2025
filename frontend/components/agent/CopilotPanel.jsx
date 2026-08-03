import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { IconButton } from "../ui/IconButton";
import { Modal } from "../ui/Modal";

const DESKTOP_QUERY = "(min-width: 1024px)";

const MIN_COPILOT_WIDTH_PX = 320;
const MAX_COPILOT_WIDTH_PX = 640;
const FALLBACK_COPILOT_WIDTH_PX = 420;
const COPILOT_DEFAULT_RATIO = 0.3; // 30% copiloto / 70% lienzo central, por defecto
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
 * ACHICA; Home/End saltan a los extremos.
 *
 * Valor por defecto (RF-105-03): 70% lienzo central / 30% copiloto, medido
 * UNA sola vez contra el ancho real del padre de `wrapperRef` (el `<main>`
 * de 3 zonas) la primera vez que el panel se monta abierto en
 * escritorio — no un porcentaje vivo que se recalcule con cada resize de
 * ventana, ni un valor fijo en píxeles ajeno al viewport real. Después de
 * esa primera medición, el ancho queda enteramente bajo control del
 * usuario (arrastre/teclado) y sobrevive a cerrar/abrir el panel dentro de
 * la misma carga de página — solo una recarga real vuelve a medir 70/30.
 */
function useResizableCopilotWidth(wrapperRef, { active }) {
  const [widthPx, setWidthPx] = useState(FALLBACK_COPILOT_WIDTH_PX);
  const dragStateRef = useRef(null);
  const hasMeasuredDefaultRef = useRef(false);

  useEffect(() => {
    if (hasMeasuredDefaultRef.current || !active) return;
    // El ancho de referencia es el del PADRE (el `<main>` de 3 zonas), no
    // el del propio wrapper: este wrapper todavía no tiene un ancho fijado
    // en el primer render (medirse a sí mismo sería circular).
    const containerWidth = wrapperRef.current?.parentElement?.getBoundingClientRect().width;
    if (!containerWidth) return;
    hasMeasuredDefaultRef.current = true;
    setWidthPx(clampCopilotWidth(Math.round(containerWidth * COPILOT_DEFAULT_RATIO)));
  }, [active, wrapperRef]);

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
  // Padre real (el `<main>` de 3 zonas) contra el que se mide el 70/30
  // inicial: este wrapper es su hijo directo tanto en `app.js` como en la
  // galería F3-7A de `_dev/ui.js`.
  const outerRef = useRef(null);
  const { widthPx, handlePointerDown, handleKeyDown } = useResizableCopilotWidth(outerRef, {
    active: open && isDesktop,
  });

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
    <div ref={outerRef} className="flex shrink-0">
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
