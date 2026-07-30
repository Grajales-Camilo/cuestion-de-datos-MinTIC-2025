import { defineConfig } from "@playwright/test";

/**
 * Config dedicada exclusivamente a la medición RNF-008 (feedback visual
 * <500 ms, primer paso visible <2 s). Vive aparte de `playwright.config.js`
 * porque el defecto observado en F7 (505 ms medidos una vez, contra un
 * límite contractual <500 ms) es del ARNÉS, no del producto: la medición
 * compartía CPU con hasta seis workers de la suite funcional paralela.
 * `workers: 1` + `fullyParallel: false` aíslan por completo la medición de
 * cualquier otra prueba que se ejecute al mismo tiempo. El umbral
 * contractual NO se toca aquí — la única corrección es dónde y cómo se mide.
 *
 * Mismo canal/puerto/`reuseExistingServer:false` que `playwright.config.js`;
 * ver el comentario allí sobre `channel: "chrome"` en Windows. Cuando
 * `scripts/run-e2e.mjs` ya administra el servidor (`CDT_E2E_SERVER_MANAGED`),
 * esta config tampoco arranca uno nuevo.
 */
export default defineConfig({
  testDir: "./tests/e2e-perf",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  webServer: process.env.CDT_E2E_SERVER_MANAGED ? undefined : {
    command: "node ./node_modules/next/dist/bin/next dev -p 3101",
    url: "http://localhost:3101",
    reuseExistingServer: false,
    timeout: 60_000,
  },
  use: {
    baseURL: "http://localhost:3101",
    trace: "retain-on-failure",
    // Ver el mismo comentario en playwright.config.js: CI usa Chromium
    // embebido normal, no el canal "chrome" (workaround solo para Windows).
    channel: process.env.CI ? undefined : "chrome",
  },
});
