import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const GALLERY_URL = "/_dev/ui";
// Tope de seguridad para el bucle de Tab real desde el documento: bastante
// por encima del número real de controles enfocables antes del botón
// objetivo, para que un cambio futuro en la galería no vuelva la prueba
// flaky por un límite demasiado ajustado.
const MAX_TAB_PRESSES = 60;

test.describe("Galería de componentes F1-01 — /_dev/ui", () => {
  test("cero violaciones de axe (WCAG 2.2 AA)", async ({ page }) => {
    await page.goto(GALLERY_URL);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
      .analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("cero errores de consola al cargar", async ({ page }) => {
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(String(err)));
    await page.goto(GALLERY_URL);
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
  });

  test("navegación completa solo con teclado: Tab real desde el documento llega al botón que abre el Modal", async ({
    page,
  }) => {
    await page.goto(GALLERY_URL);
    // Ningún .focus() de JS: se parte del body (sin nada enfocado) y se
    // avanza con Tab real, un control a la vez, tal como lo haría una
    // persona usando solo teclado.
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("Tab"); // primer Tab real desde el documento

    const openModalButton = page.getByRole("button", { name: "Abrir modal de ejemplo" });
    let reached = false;
    for (let i = 0; i < MAX_TAB_PRESSES; i += 1) {
      if (await openModalButton.evaluate((el) => el === document.activeElement)) {
        reached = true;
        break;
      }
      await page.keyboard.press("Tab");
    }
    expect(reached, `no se alcanzó el botón tras ${MAX_TAB_PRESSES} pulsaciones de Tab`).toBe(true);
    await expect(openModalButton).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "Confirmar inserción" })).toBeVisible();
  });

  test("Modal: foco inicial, trampa de Tab/Mayús+Tab (el foco nunca escapa) y cierre con Escape", async ({
    page,
  }) => {
    await page.goto(GALLERY_URL);
    const openButton = page.getByRole("button", { name: "Abrir modal de ejemplo" });
    await openButton.click();

    const dialog = page.getByRole("dialog", { name: "Confirmar inserción" });
    await expect(dialog).toBeVisible();
    // Nombre accesible no vacío (RF de F1-R1 punto 3).
    expect((await dialog.getAttribute("aria-labelledby")) || (await dialog.getAttribute("aria-label"))).toBeTruthy();

    // Acotados al diálogo: la galería también tiene un botón "Cancelar" en
    // el ejemplo de Card, fuera del modal — un locator sin acotar sería
    // ambiguo.
    const closeButton = dialog.getByRole("button", { name: "Cerrar" });
    const cancelButton = dialog.getByRole("button", { name: "Cancelar" });
    const confirmButton = dialog.getByRole("button", { name: "Confirmar" });

    // Foco inicial predecible: el primer control enfocable del diálogo.
    await expect(closeButton).toBeFocused();

    // Recorrido real hacia adelante con Tab: Cerrar → Cancelar → Confirmar
    // → (envuelve) Cerrar. El foco nunca debe salir del diálogo.
    await page.keyboard.press("Tab");
    await expect(cancelButton).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(confirmButton).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(closeButton).toBeFocused(); // trampa: vuelve al primero, no escapa al documento

    // Recorrido real hacia atrás con Mayús+Tab: Cerrar → Confirmar (envuelve).
    await page.keyboard.press("Shift+Tab");
    await expect(confirmButton).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(cancelButton).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(openButton).toBeFocused(); // restauración de foco
  });

  test("Disclosure: se expande y contrae con el teclado", async ({ page }) => {
    await page.goto(GALLERY_URL);
    const trigger = page.getByRole("button", { name: "Ver detalle técnico de la consulta" });
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText(/Dataset: ji8i-4anb/)).toBeVisible();
  });

  test("Tabs: flechas de teclado cambian la pestaña seleccionada", async ({ page }) => {
    await page.goto(GALLERY_URL);
    const first = page.getByRole("tab", { name: "Resumen" });
    const second = page.getByRole("tab", { name: "Detalle técnico" });
    await first.focus();
    await page.keyboard.press("ArrowRight");
    await expect(second).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Panel de detalle técnico.")).toBeVisible();
  });

  test("Table: el contenedor desplazable es una región con nombre accesible y foco real de teclado", async ({
    page,
  }) => {
    // La prueba del contrato inválido (sin caption/aria-label, que lanza)
    // vive en Vitest (tests/unit/ui/Table.test.jsx) — es una aserción
    // sobre una excepción de construcción de React, no sobre
    // comportamiento del navegador. Aquí se confirma en Chromium real que
    // la tabla válida de la galería expone su contenedor desplazable como
    // región enfocable.
    await page.goto(GALLERY_URL);
    const scrollRegion = page.getByRole("region", { name: /1 fila devuelta por datos\.gov\.co/ });
    await expect(scrollRegion).toBeVisible();
    await scrollRegion.focus();
    await expect(scrollRegion).toBeFocused();
  });

  test("1440px: sin overflow horizontal de página", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(GALLERY_URL);
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });

  test("320px: sin overflow horizontal de página (incluida la ruta central)", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await page.goto(GALLERY_URL);
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
    // El valor largo real de la corrida debe verse partido, no recortado.
    await expect(page.getByText("3,9660000000000000")).toBeVisible();
  });

  // NOTA (F1-R1): Playwright no expone una API pública equivalente al
  // "Acercar/zoom" real del navegador (Ctrl+/Ctrl-, WCAG 1.4.4). El
  // `document.documentElement.style.zoom` usado en F1-01 NO es zoom de
  // navegador — es una propiedad de layout no estándar de Chromium que no
  // reproduce el comportamiento real que un usuario obtiene con Ctrl+. Se
  // retira esa prueba en vez de conservar una que mide algo distinto de lo
  // que afirma medir. El criterio de "contenido legible sin scroll
  // horizontal cuando el espacio inline disponible se reduce" queda
  // cubierto de forma automatizada y reproducible por la prueba de 320px
  // de arriba (una reducción de espacio disponible comparable a un 200%
  // de zoom sobre un viewport de escritorio de ~1280px).
  //
  // VERIFICACIÓN MANUAL requerida antes de considerar F1 cerrado a nivel de
  // producto (no bloquea este gate de F1-R1, que es sobre las primitivas):
  //   1. Abrir http://localhost:3101/_dev/ui en Chrome de escritorio.
  //   2. Ctrl+ hasta 200% (o Ctrl+0 luego 5×Ctrl+).
  //   3. Confirmar visualmente que no hay scroll horizontal y que todo el
  //      texto y los controles siguen siendo legibles/operables.

  test("prefers-reduced-motion: el Skeleton no anima", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(GALLERY_URL);
    const skeleton = page.locator("[aria-hidden='true'].animate-pulse").first();
    await expect(skeleton).toBeVisible();
    const durationMs = await skeleton.evaluate((el) => {
      const raw = getComputedStyle(el).animationDuration; // p.ej. "0.01ms" o "1e-05s" según el navegador
      const value = parseFloat(raw);
      return raw.trim().endsWith("ms") ? value : value * 1000;
    });
    // 0.01ms es el valor forzado por la regla prefers-reduced-motion de
    // .cdt-v2 (globals.css); una tolerancia amplia evita comparar strings
    // que representan el mismo número en notaciones distintas (ms vs s).
    expect(durationMs).toBeLessThan(1);
  });
});
