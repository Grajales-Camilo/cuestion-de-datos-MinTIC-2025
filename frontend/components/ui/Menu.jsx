import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { Check } from "lucide-react";
import { cx } from "./cx";

/**
 * Barra de menús accesible estilo "Archivo/Editar/Formato" (WAI-ARIA APG,
 * patrón Menubar). Un solo menú desplegable abierto a la vez; flechas
 * izquierda/derecha mueven el foco entre los menús de nivel superior
 * (tabindex progresivo, mismo patrón que `Tabs.jsx`) y, si ya había uno
 * abierto, abren el vecino de inmediato. Dentro de un menú desplegable,
 * flechas arriba/abajo mueven el foco entre sus opciones, Home/End saltan
 * a la primera/última, Escape cierra y devuelve el foco al disparador, y
 * un clic fuera cierra sin mover el foco.
 */
const MenuBarContext = createContext(null);
const MenuContext = createContext(null);

export function MenuBar({ ariaLabel, className, children }) {
  const [openId, setOpenId] = useState(null);
  const orderRef = useRef([]);

  function register(id) {
    if (!orderRef.current.includes(id)) orderRef.current.push(id);
    return () => {
      orderRef.current = orderRef.current.filter((existing) => existing !== id);
    };
  }

  function moveTo(fromId, direction) {
    const order = orderRef.current;
    const index = order.indexOf(fromId);
    if (index === -1) return null;
    const nextIndex = (index + direction + order.length) % order.length;
    return order[nextIndex] ?? null;
  }

  return (
    <MenuBarContext.Provider value={{ openId, setOpenId, register, moveTo }}>
      <div role="menubar" aria-label={ariaLabel} className={cx("flex items-center gap-cdt-1", className)}>
        {children}
      </div>
    </MenuBarContext.Provider>
  );
}

/** Un menú de nivel superior (p. ej. "Archivo"). `children` son `MenuItem`,
 * `MenuCheckboxItem`, `MenuRadioItem`, `MenuGroup` o `MenuDivider`. */
export function Menu({ label, children, triggerRef: externalTriggerRef }) {
  const id = useId();
  const bar = useContext(MenuBarContext);
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  const isOpen = bar.openId === id;

  useEffect(() => bar.register(id), [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isOpen) return undefined;

    function handlePointerDown(event) {
      if (triggerRef.current?.contains(event.target)) return;
      if (panelRef.current?.contains(event.target)) return;
      bar.setOpenId(null);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [isOpen, bar]);

  useEffect(() => {
    if (!isOpen) return;
    const firstItem = panelRef.current?.querySelector('[role^="menuitem"]');
    firstItem?.focus();
  }, [isOpen]);

  function focusNeighborItem(direction) {
    const items = Array.from(panelRef.current?.querySelectorAll('[role^="menuitem"]') ?? []);
    if (items.length === 0) return;
    const current = items.indexOf(document.activeElement);
    let nextIndex;
    if (direction === "first") nextIndex = 0;
    else if (direction === "last") nextIndex = items.length - 1;
    else nextIndex = (current + direction + items.length) % items.length;
    items[nextIndex]?.focus();
  }

  // Compartida por el disparador Y por el panel abierto: con un submenú
  // abierto y el foco dentro de él (caso normal tras abrir, ver el efecto de
  // foco inicial más abajo), flecha izquierda/derecha también debe cerrar
  // este menú y abrir+enfocar el vecino (WAI-ARIA APG, patrón Menubar).
  function moveToNeighborMenu(direction) {
    const neighborId = bar.moveTo(id, direction);
    if (neighborId === null) return;
    bar.setOpenId(neighborId);
    // El foco pasa al disparador vecino en el próximo tick (montado tras el
    // cambio de `openId`); `document.getElementById` evita mantener un mapa
    // de refs adicional solo para esta transición puntual.
    window.requestAnimationFrame(() => document.getElementById(`menu-trigger-${neighborId}`)?.focus());
  }

  function handleTriggerKeyDown(event) {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      bar.setOpenId(id);
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      moveToNeighborMenu(event.key === "ArrowRight" ? 1 : -1);
      return;
    }
    if (event.key === "Escape") {
      bar.setOpenId(null);
    }
  }

  function handlePanelKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusNeighborItem(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusNeighborItem(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusNeighborItem("first");
    } else if (event.key === "End") {
      event.preventDefault();
      focusNeighborItem("last");
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      moveToNeighborMenu(event.key === "ArrowRight" ? 1 : -1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      bar.setOpenId(null);
      triggerRef.current?.focus();
    }
  }

  return (
    <div className="relative">
      <button
        ref={(node) => {
          triggerRef.current = node;
          if (externalTriggerRef) externalTriggerRef.current = node;
        }}
        id={`menu-trigger-${id}`}
        type="button"
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        tabIndex={0}
        onClick={() => bar.setOpenId(isOpen ? null : id)}
        onKeyDown={handleTriggerKeyDown}
        className={cx(
          "min-h-cdt-tap rounded-cdt-md px-cdt-3 font-cdt-sans text-cdt-sm font-cdt-bold text-cdt-blue-900",
          "transition-colors duration-cdt-base ease-cdt-standard hover:bg-cdt-blue-100",
          isOpen && "bg-cdt-blue-100"
        )}
      >
        {label}
      </button>
      {isOpen ? (
        <MenuContext.Provider value={{ close: () => bar.setOpenId(null), refocusTrigger: () => triggerRef.current?.focus() }}>
          <div
            ref={panelRef}
            role="menu"
            aria-label={label}
            onKeyDown={handlePanelKeyDown}
            className="absolute left-0 top-[calc(100%+4px)] z-40 min-w-[14rem] rounded-cdt-lg border border-cdt-blue-100 bg-cdt-white p-cdt-2 shadow-none"
          >
            {children}
          </div>
        </MenuContext.Provider>
      ) : null}
    </div>
  );
}

function baseItemClasses(disabled) {
  return cx(
    "flex w-full min-h-cdt-tap items-center gap-cdt-2 rounded-cdt-md px-cdt-3 text-left font-cdt-sans text-cdt-sm text-cdt-slate-900",
    "transition-colors duration-cdt-base ease-cdt-standard",
    disabled ? "cursor-not-allowed opacity-50" : "hover:bg-cdt-blue-50"
  );
}

/** Opción simple de acción (no alterna estado). Cierra el menú tras ejecutar. */
export function MenuItem({ onSelect, disabled = false, icon: Icon, children }) {
  const menu = useContext(MenuContext);
  return (
    <button
      type="button"
      role="menuitem"
      tabIndex={-1}
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        onSelect?.();
        menu.close();
      }}
      className={baseItemClasses(disabled)}
    >
      {Icon ? <Icon className="h-4 w-4 shrink-0" aria-hidden="true" focusable="false" /> : null}
      <span className="flex-1">{children}</span>
    </button>
  );
}

/** Opción de alternar (Negrita/Cursiva/Superíndice): `aria-checked` refleja
 * el estado activo real del editor, nunca un estado local propio. */
export function MenuCheckboxItem({ checked, onSelect, disabled = false, children }) {
  const menu = useContext(MenuContext);
  return (
    <button
      type="button"
      role="menuitemcheckbox"
      aria-checked={checked}
      tabIndex={-1}
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        onSelect?.();
        menu.close();
      }}
      className={baseItemClasses(disabled)}
    >
      <Check
        className={cx("h-4 w-4 shrink-0", checked ? "opacity-100" : "opacity-0")}
        aria-hidden="true"
        focusable="false"
      />
      <span className="flex-1">{children}</span>
    </button>
  );
}

/** Opción mutuamente excluyente dentro de un `MenuGroup` (estilos de
 * párrafo, alineación). */
export function MenuRadioItem({ checked, onSelect, disabled = false, children }) {
  const menu = useContext(MenuContext);
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      tabIndex={-1}
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        onSelect?.();
        menu.close();
      }}
      className={baseItemClasses(disabled)}
    >
      <Check
        className={cx("h-4 w-4 shrink-0", checked ? "opacity-100" : "opacity-0")}
        aria-hidden="true"
        focusable="false"
      />
      <span className="flex-1">{children}</span>
    </button>
  );
}

/** Agrupa opciones relacionadas dentro de un menú (p. ej. "Alinear") con un
 * rótulo visible y `role="group"` para lectores de pantalla. */
export function MenuGroup({ label, children }) {
  return (
    <div role="group" aria-label={label} className="py-cdt-1">
      <p className="px-cdt-3 py-cdt-1 text-cdt-xs font-cdt-bold uppercase tracking-wide text-cdt-slate-400">
        {label}
      </p>
      {children}
    </div>
  );
}

export function MenuDivider() {
  return <div role="separator" className="my-cdt-1 h-px bg-cdt-blue-100" />;
}
