import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cx } from "./cx";
import { IconButton } from "./IconButton";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function shouldRestoreFocus(restoreFocusRef) {
  return restoreFocusRef?.current !== false;
}

/**
 * Diálogo modal accesible: `role="dialog"` + `aria-modal="true"`, nombre
 * accesible obligatorio (`title`), foco inicial predecible, trampa de
 * foco (Tab / Mayús+Tab), cierre con Escape, restauración del foco al
 * elemento que lo abrió, bloqueo de scroll del body y limpieza completa
 * de listeners al desmontar — nada queda huérfano.
 *
 * Se monta en un portal a `document.body` solo mientras `open` es true;
 * SSR-seguro (no toca `document` hasta que el componente ya está montado
 * en el cliente).
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  initialFocusRef,
  className,
  restoreFocusRef,
  returnFocusRef,
}) {
  const titleId = useId();
  const dialogRef = useRef(null);
  const previouslyFocusedRef = useRef(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    // `mounted` y `title` son dependencias deliberadas, no solo `open`:
    // cuando
    // `open` ya es `true` en el primer render (montaje con el modal ya
    // abierto), este efecto se dispara junto con el de `setMounted` en el
    // mismo commit, pero el portal todavía no existe (`dialogRef.current`
    // es `null` porque el componente devolvió `null` mientras
    // `mounted === false`). Sin `mounted` en las dependencias, el efecto
    // corre una sola vez, antes de que el diálogo exista, y el foco
    // inicial nunca se aplica. Con `mounted` aquí, el efecto se repite en
    // cuanto el portal ya está montado. Si un flujo cambia de etapa dentro
    // del mismo modal (y con ello cambia `title`), el control anterior puede
    // desmontarse; repetir este efecto mantiene el foco dentro del diálogo.
    if (!open || !mounted) return undefined;

    previouslyFocusedRef.current = document.activeElement;
    const explicitReturnFocus = returnFocusRef?.current;
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const toFocus =
      initialFocusRef?.current ?? dialogRef.current?.querySelector(FOCUSABLE_SELECTOR) ?? dialogRef.current;
    toFocus?.focus();

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose?.();
        return;
      }
      if (event.key !== "Tab") return;

      const node = dialogRef.current;
      if (!node) return;
      const focusable = Array.from(node.querySelectorAll(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
      if (shouldRestoreFocus(restoreFocusRef)) {
        (explicitReturnFocus ?? previouslyFocusedRef.current)?.focus?.();
      }
    };
  }, [open, mounted, title, onClose, initialFocusRef, restoreFocusRef, returnFocusRef]);

  if (!mounted || !open) return null;

  if (!title) {
    throw new Error("Modal requiere la prop `title` como nombre accesible (no puede estar vacía).");
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-cdt-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cx(
          "max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded-cdt-lg border border-cdt-blue-100 bg-cdt-white p-cdt-6",
          "font-cdt-sans",
          className
        )}
      >
        <div className="mb-cdt-4 flex items-start justify-between gap-cdt-4">
          <h2 id={titleId} className="text-cdt-lg font-cdt-bold text-cdt-slate-900">
            {title}
          </h2>
          <IconButton label="Cerrar" variant="quiet" onClick={onClose}>
            <X className="h-5 w-5" aria-hidden="true" focusable="false" />
          </IconButton>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}
