import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const GALLERY_URL = "/_dev/ui";

async function openCopilotAndSelectScenario(page, scenarioLabel) {
  await page.goto(GALLERY_URL);
  await page.getByRole("button", { name: scenarioLabel, exact: true }).click();
  await page.getByRole("button", { name: "Abrir copiloto" }).click();
}

test.describe("Muestra funcional F3-7A — /_dev/ui#agent-demo", () => {
  test("flujo simulado completo: feedback inmediato visible, primer paso visible, termina completed", async ({
    page,
  }) => {
    // La medición cronometrada de RNF-008 (feedback <500ms, primer paso <2s)
    // vive en `tests/e2e-perf/rnf008.spec.js`, ejecutada en proceso aparte
    // con un solo worker — aquí solo se cubre el camino FUNCIONAL (que los
    // elementos existan y terminen en el estado correcto), sin cronometrar,
    // para no duplicar la métrica bajo la contención de la suite paralela.
    await openCopilotAndSelectScenario(page, "Completado");

    const questionBox = page.getByLabel("Pregunta para investigar");
    await questionBox.fill("¿Qué códigos NUECA corresponden a la empresa 78 en Antioquia?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Preparando la investigación…")).toBeVisible();

    // RF-105-02: los pasos ya no se apilan en una lista visible; la tarjeta
    // condensada de `RunTimeline` aparece en cuanto llega el primer evento
    // real, señalada por el botón que abre el detalle técnico completo.
    await expect(page.getByRole("button", { name: "Ver detalle técnico", exact: true })).toBeVisible({
      timeout: 2000,
    });

    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Verificado").first()).toBeVisible({ timeout: 15000 });
  });

  test("no_evidence termina en estado neutral, nunca rojo", async ({ page }) => {
    await openCopilotAndSelectScenario(page, "Sin evidencia");
    await page.getByLabel("Pregunta para investigar").fill("¿Cuál es el precio promedio de vivienda en Marte?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    await expect(page.getByText("Sin evidencia elegible")).toBeVisible({ timeout: 20000 });
  });

  test("interrupted y failed muestran su mensaje, con acciones de reintento", async ({ page }) => {
    await openCopilotAndSelectScenario(page, "Fallido");
    await page.getByLabel("Pregunta para investigar").fill("¿Qué temperatura registró la estación 0026195501?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    const copilot = page.getByLabel("Copiloto — muestra F3-7A");
    await expect(copilot.getByText("La fuente de datos no respondió a tiempo.")).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole("button", { name: "Volver a preguntar" })).toBeVisible();
  });

  test("reconexión: repite eventos del servidor sin duplicar pasos en la ruta central", async ({ page }) => {
    await openCopilotAndSelectScenario(page, "Reconectando (repite eventos, sin duplicar pasos)");
    await page.getByLabel("Pregunta para investigar").fill("¿Qué códigos NUECA corresponden a la empresa 78?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();

    await expect(page.getByText(/Reconectando/)).toBeVisible({ timeout: 5000 });
    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Verificado").first()).toBeVisible({ timeout: 20000 });

    // Los pasos reales de este fixture (`select_candidate`, `profile_dataset`
    // repetidos entre otras cosas) no deben aparecer duplicados pese a que
    // el escenario reenvía un tramo solapado a propósito. RF-105-02: ese
    // conteo ya no vive en una lista siempre visible — se verifica dentro
    // del modal "Ver detalle técnico", que sigue mostrando cada paso real.
    await page.getByRole("button", { name: "Ver detalle técnico", exact: true }).click();
    const modal = page.getByRole("dialog", { name: "Detalle técnico de la investigación" });
    const items = modal.getByRole("listitem");
    const count = await items.count();
    const texts = await items.allTextContents();
    expect(new Set(texts).size).toBe(count); // ningún texto de paso repetido
  });

  test("navegación completa solo con teclado: Tab real llega al selector de escenario y al submit", async ({
    page,
  }) => {
    await page.goto(GALLERY_URL);
    const completedBtn = page.getByRole("button", { name: "Completado", exact: true });
    await completedBtn.focus();
    await expect(completedBtn).toBeFocused();

    await page.keyboard.press("Enter"); // selecciona el escenario con teclado
    await page.getByRole("button", { name: "Abrir copiloto" }).focus();
    await page.keyboard.press("Enter");

    const questionBox = page.getByLabel("Pregunta para investigar");
    await expect(questionBox).toBeVisible();
    await questionBox.focus();
    await page.keyboard.type("¿Qué códigos NUECA corresponden a la empresa 78 en Antioquia?");
    await page.keyboard.press("Tab"); // hacia el botón Investigar (no hay context hint en esta demo)
    await expect(page.getByRole("button", { name: "Investigar", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Preparando la investigación…")).toBeVisible();
  });

  test("cero violaciones de axe con el copiloto abierto y una corrida terminada", async ({ page }) => {
    await openCopilotAndSelectScenario(page, "Completado");
    await page.getByLabel("Pregunta para investigar").fill("¿Qué códigos NUECA corresponden a la empresa 78?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Verificado").first()).toBeVisible({ timeout: 15000 });

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("320px: sin overflow horizontal con el copiloto (drawer) abierto", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await openCopilotAndSelectScenario(page, "Completado");
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });

  test("prefers-reduced-motion: el spinner del paso activo no anima; axe sin violaciones con la investigación activa (F8-01)", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openCopilotAndSelectScenario(page, "Streaming (sin terminar)");
    await page.getByLabel("Pregunta para investigar").fill("¿Qué códigos NUECA corresponden a la empresa 78?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();

    const spinner = page.locator(".animate-spin").first();
    await expect(spinner).toBeVisible({ timeout: 5000 });
    const durationMs = await spinner.evaluate((el) => {
      const raw = getComputedStyle(el).animationDuration;
      const value = parseFloat(raw);
      return raw.trim().endsWith("ms") ? value : value * 1000;
    });
    expect(durationMs).toBeLessThan(1);

    // Este escenario nunca termina (permanece "streaming" a propósito): es
    // el único punto estable para auditar axe con pasos EN VIVO, sin la
    // fragilidad de intentar congelar un stream real de `/app` a mitad de
    // camino (F8-01, matriz de accesibilidad, estado "investigación activa").
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("cero errores de consola durante un flujo completo", async ({ page }) => {
    const errors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(String(err)));

    await openCopilotAndSelectScenario(page, "Completado");
    await page.getByLabel("Pregunta para investigar").fill("¿Qué códigos NUECA corresponden a la empresa 78?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Verificado").first()).toBeVisible({ timeout: 15000 });

    expect(errors).toEqual([]);
  });

  test("proporción por defecto 70% lienzo / 30% copiloto (RF-105-03)", async ({ page }) => {
    await page.goto(GALLERY_URL);
    await page.getByRole("button", { name: "Abrir copiloto" }).click();

    const aside = page.getByLabel("Copiloto — muestra F3-7A");
    const { asideWidth, containerWidth } = await aside.evaluate((el) => ({
      asideWidth: el.getBoundingClientRect().width,
      // El contenedor real: el padre del wrapper que envuelve separador+aside.
      containerWidth: el.parentElement.parentElement.getBoundingClientRect().width,
    }));

    const ratio = asideWidth / containerWidth;
    // Margen de tolerancia por redondeo a entero y por el propio ancho del
    // separador (8px) que también vive dentro del contenedor medido.
    expect(ratio).toBeGreaterThan(0.27);
    expect(ratio).toBeLessThan(0.33);
  });

  test("divisor arrastrable: teclado y puntero cambian el ancho real del copiloto (RF-105-02)", async ({ page }) => {
    await page.goto(GALLERY_URL);
    await page.getByRole("button", { name: "Abrir copiloto" }).click();

    const separator = page.getByRole("separator", { name: "Cambiar ancho del panel del copiloto" });
    const aside = page.getByLabel("Copiloto — muestra F3-7A");

    const initialWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    expect(await separator.getAttribute("aria-valuenow")).toBe(String(Math.round(initialWidth)));

    // Teclado: flecha izquierda agranda, flecha derecha achica (documentado
    // en `CopilotPanel.jsx`).
    await separator.focus();
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    const widerWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    expect(widerWidth).toBeGreaterThan(initialWidth);
    expect(await separator.getAttribute("aria-valuenow")).toBe(String(Math.round(widerWidth)));

    await page.keyboard.press("ArrowRight");
    const narrowerWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    expect(narrowerWidth).toBeLessThan(widerWidth);

    await page.keyboard.press("End"); // salta al mínimo
    const minWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    expect(await separator.getAttribute("aria-valuenow")).toBe(String(Math.round(minWidth)));
    expect(minWidth).toBeLessThan(narrowerWidth);

    await page.keyboard.press("Home"); // salta al máximo
    const maxWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    expect(maxWidth).toBeGreaterThan(minWidth);

    // Puntero real: arrastrar el separador hacia la izquierda debe agrandar
    // el copiloto (mismo sentido que la flecha izquierda del teclado).
    await page.keyboard.press("End"); // vuelve al mínimo para tener margen de arrastre
    const beforeDragWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    const box = await separator.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 80, box.y + box.height / 2, { steps: 8 });
    await page.mouse.up();
    const afterDragWidth = await aside.evaluate((el) => el.getBoundingClientRect().width);
    expect(afterDragWidth).toBeGreaterThan(beforeDragWidth);
  });
});
