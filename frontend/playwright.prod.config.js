import { defineConfig } from "@playwright/test";

/**
 * Config separada para la única prueba que necesita un build de
 * producción real (no `next dev`): que `/_dev/ui` responda 404 y `/`
 * responda 200 bajo `next start`. Vive aparte de `playwright.config.js`
 * para no obligar a reconstruir el proyecto en cada corrida normal de
 * `npm run test:e2e` — se ejecuta con `npm run test:e2e:prod`.
 *
 * `webServer.command` encadena `next build && next start` a propósito:
 * Playwright arranca este comando, espera a que `url` responda, corre las
 * pruebas y SIEMPRE cierra el proceso al terminar (incluida la señal de
 * cierre al build/start hijo) — así no queda un `next start` de
 * producción huérfano en el puerto 3101.
 */
export default defineConfig({
  testDir: "./tests/e2e-prod",
  fullyParallel: false,
  reporter: "list",
  webServer: {
    command: "npm run build && npm run start -- -p 3101",
    url: "http://localhost:3101",
    reuseExistingServer: false,
    timeout: 180_000,
  },
  use: {
    baseURL: "http://localhost:3101",
    trace: "retain-on-failure",
    // Ver el mismo comentario en playwright.config.js: CI usa Chromium
    // embebido normal, no el canal "chrome" (workaround solo para Windows).
    channel: process.env.CI ? undefined : "chrome",
  },
});
