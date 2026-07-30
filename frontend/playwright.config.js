import { defineConfig } from "@playwright/test";

/**
 * Requisito de instalación (máquina limpia y CI): `npx playwright install
 * chrome` — instala/registra el canal `chrome` (navegador Chrome estable,
 * gestionado por Playwright igual que `chromium`, pero resuelto como una
 * instalación de sistema en vez del paquete "Chrome for Testing" embebido).
 *
 * Por qué `channel: "chrome"` y no `channel: "chromium"`:
 * el paquete "chromium" embebido de Playwright (`chromium-1234`, Chrome for
 * Testing) falló en esta máquina con `spawn UNKNOWN` / "Error al generar el
 * contexto de activación... No se encontró el ensamblado dependiente
 * 151.0.7922.34" (ver Visor de eventos > Aplicación, proveedor
 * SideBySide) — un fallo de resolución de manifiesto WinSxS específico de
 * ese binario descargado, reproducible incluso tras reinstalar con
 * `playwright install chromium --force`. El canal `chrome` (Chrome
 * instalado como aplicación de Windows, con sus dependencias SxS
 * correctamente registradas) arranca sin ese problema y es la alternativa
 * documentada por Playwright (`npx playwright install chrome`), compatible
 * con CI vía el mismo comando. No requiere instalar `chromium_headless_shell`,
 * que fue el binario ausente en la corrida original de F1-01.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  reporter: "list",
  // La galería de F1-01 (`/_dev/ui`) solo existe en modo desarrollo — sus
  // pruebas necesitan `next dev`, no `next build && next start`. Puerto
  // fijo 3101 (nunca 3000: en este entorno hay procesos ajenos al
  // proyecto que lo usan). `reuseExistingServer: false` siempre — nunca se
  // reutiliza una instancia vieja o ajena, ni siquiera fuera de CI.
  webServer: process.env.CDT_E2E_SERVER_MANAGED ? undefined : {
    // Invoca Next directamente para que Playwright sea padre del servidor.
    // En Windows, la capa adicional npm -> cmd puede cerrar el listener pero
    // conservar heredado el pipe de salida e impedir que la suite termine.
    command: "node ./node_modules/next/dist/bin/next dev -p 3101",
    url: "http://localhost:3101",
    reuseExistingServer: false,
    timeout: 60_000,
  },
  use: {
    baseURL: "http://localhost:3101",
    trace: "retain-on-failure",
    // CI (Ubuntu, `$CI` lo define `actions/checkout`/runners de GitHub) no
    // sufre el fallo de resolución WinSxS de Windows que motivó el canal
    // "chrome": ahí se usa el Chromium embebido normal, instalado en el job
    // con `npx playwright install --with-deps chromium` — ver ci.yml.
    channel: process.env.CI ? undefined : "chrome",
  },
});
