import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Vitest no expone `afterEach` como global en este proyecto (vitest.config.js
// no activa `test.globals`), así que la auto-limpieza interna de
// @testing-library/react nunca se registra por sí sola. Sin esto, cada
// `render()` (y sobre todo cada `createPortal` a `document.body`, como el
// de Modal.jsx) se acumula entre pruebas del mismo archivo.
afterEach(() => {
  cleanup();
});

// jsdom no implementa `window.matchMedia` (usado por CopilotPanel para
// distinguir panel de escritorio vs. drawer <1024px). Por defecto reporta
// "no coincide" (`matches: false`) — cada prueba que necesite simular
// escritorio debe sobrescribirlo explícitamente, no asumirlo aquí.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
