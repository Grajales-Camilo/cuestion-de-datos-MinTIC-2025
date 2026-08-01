import { expect, test } from "@playwright/test";

/**
 * RNF-008, medición reproducible y aislada (spec.md: feedback visual
 * <500 ms tras el clic; primer paso del agente visible <2 s). Se ejecuta en
 * `playwright.perf.config.js` (1 worker, sin paralelismo) para que la
 * medición no comparta CPU con la suite funcional — el defecto detectado en
 * F7 (una corrida midió 505 ms) era contención del arnés, no del producto.
 * El umbral contractual permanece sin tocar: <500 ms / <2000 ms.
 *
 * Usa la muestra funcional F3-7A (`/_dev/ui`, escenario "Completado"): un
 * doble en memoria del cliente real (mismo `CopilotPanel`/`useAgentRun` que
 * `/app`), sin red — mide el tiempo real de render de React desde el clic,
 * que es exactamente lo que RNF-008 exige medir ("mide solo el frontend",
 * plan.md §12.2), sin la variable adicional de latencia de red simulada.
 *
 * Tres repeticiones consecutivas en el MISMO proceso de 1 worker; cada una
 * registra sus tiempos por consola (no solo pass/fail) y se afirma contra el
 * umbral de forma independiente.
 */

const GALLERY_URL = "/_dev/ui";
const REPETITIONS = 3;

async function openCopilotAndSelectScenario(page, scenarioLabel) {
  await page.goto(GALLERY_URL);
  await page.getByRole("button", { name: scenarioLabel, exact: true }).click();
  await page.getByRole("button", { name: "Abrir copiloto" }).click();
}

for (let repetition = 1; repetition <= REPETITIONS; repetition += 1) {
  test(`RNF-008 repetición ${repetition}/${REPETITIONS}: feedback <500ms, primer paso <2s`, async ({ page }) => {
    await openCopilotAndSelectScenario(page, "Completado");

    const questionBox = page.getByLabel("Pregunta para investigar");
    await questionBox.fill("¿Qué códigos NUECA corresponden a la empresa 78 en Antioquia?");

    const t0 = Date.now();
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    await expect(page.getByLabel("Copiloto — muestra F3-7A").getByText("Preparando la investigación…")).toBeVisible();
    const feedbackMs = Date.now() - t0;

    // RF-105-02: el primer paso ya no aparece como un <li> en una lista
    // siempre visible, sino como el mensaje de la tarjeta condensada de
    // `RunTimeline` — señalada por el botón que abre su detalle técnico.
    await expect(page.getByRole("button", { name: "Ver detalle técnico", exact: true })).toBeVisible({
      timeout: 2000,
    });
    const firstStepMs = Date.now() - t0;

    // eslint-disable-next-line no-console
    console.log(`[RNF-008] repetición ${repetition}/${REPETITIONS}: feedbackMs=${feedbackMs} firstStepMs=${firstStepMs}`);

    expect(feedbackMs, `feedback visual (repetición ${repetition})`).toBeLessThan(500);
    expect(firstStepMs, `primer paso visible (repetición ${repetition})`).toBeLessThan(2000);
  });
}
