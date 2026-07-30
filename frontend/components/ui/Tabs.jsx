import { useId, useRef, useState } from "react";
import { cx } from "./cx";

/**
 * Pestañas accesibles (`tablist`/`tab`/`tabpanel`, WAI-ARIA APG).
 *
 * Estrategia de foco (documentada, no implícita): tabindex progresivo
 * ("roving tabindex") — solo la pestaña activa tiene `tabIndex=0`, el
 * resto `-1`. Las flechas izquierda/derecha y Home/End mueven el foco Y
 * activan el panel correspondiente de inmediato ("activación automática"),
 * el patrón estándar para conjuntos de pestañas de contenido relacionado
 * y de bajo costo de cambio (no hay carga de red por pestaña en este
 * incremento).
 */
export function Tabs({ items, defaultActiveId, activeId: controlledActiveId, onChange, className }) {
  const generatedId = useId();
  const [uncontrolledActiveId, setUncontrolledActiveId] = useState(defaultActiveId ?? items[0]?.id);
  const isControlled = controlledActiveId !== undefined;
  const activeId = isControlled ? controlledActiveId : uncontrolledActiveId;
  const tabRefs = useRef({});

  function activate(id) {
    if (!isControlled) setUncontrolledActiveId(id);
    onChange?.(id);
  }

  function handleKeyDown(event, index) {
    let nextIndex = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % items.length;
    else if (event.key === "ArrowLeft") nextIndex = (index - 1 + items.length) % items.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = items.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextItem = items[nextIndex];
    activate(nextItem.id);
    tabRefs.current[nextItem.id]?.focus();
  }

  return (
    <div className={className}>
      <div role="tablist" className="flex gap-cdt-2 border-b border-cdt-blue-100">
        {items.map((item, index) => {
          const selected = item.id === activeId;
          const tabId = `tab-${generatedId}-${item.id}`;
          const panelId = `tabpanel-${generatedId}-${item.id}`;
          return (
            <button
              key={item.id}
              ref={(el) => {
                tabRefs.current[item.id] = el;
              }}
              type="button"
              role="tab"
              id={tabId}
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              onClick={() => activate(item.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={cx(
                "-mb-px min-h-cdt-tap border-b-2 px-cdt-4 font-cdt-sans text-cdt-sm font-cdt-bold",
                "transition-colors duration-cdt-base ease-cdt-standard",
                selected
                  ? "border-cdt-blue-700 text-cdt-blue-900"
                  : "border-transparent text-cdt-slate-600 hover:text-cdt-blue-700"
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) => {
        const selected = item.id === activeId;
        const tabId = `tab-${generatedId}-${item.id}`;
        const panelId = `tabpanel-${generatedId}-${item.id}`;
        return (
          <div
            key={item.id}
            role="tabpanel"
            id={panelId}
            aria-labelledby={tabId}
            hidden={!selected}
            tabIndex={0}
            className="py-cdt-4"
          >
            {item.content}
          </div>
        );
      })}
    </div>
  );
}
