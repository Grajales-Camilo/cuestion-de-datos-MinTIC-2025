import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  createFreeDocumentViaPicker,
  createFreeDocumentViaPickerWithKeyboard,
} from "./helpers/templatePickerFlow.js";

const APP_URL = "/app";
const REAL_STREAM = readFileSync(
  path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt"),
  "utf8",
);
const TOKEN = "cdt_rt_f5_03_e2e_no_debe_aparecer";
const SECTION_TEXT = "Diagnostico de cobertura educativa en el municipio durante 2022.";

function answerFromStream(stream) {
  const block = stream.split(/\r?\n\r?\n/).find((candidate) => candidate.includes("event: answer"));
  const dataLine = block?.split(/\r?\n/).find((line) => line.startsWith("data: "));
  if (!dataLine) throw new Error("El fixture real no contiene evento answer");
  return JSON.parse(dataLine.slice(6));
}

const REAL_ANSWER = answerFromStream(REAL_STREAM);

/**
 * Igual que en `app-f5-02.spec.js`, pero además captura el cuerpo exacto de
 * cada `POST /v2/agent/query` — necesario para probar que `context_hint`
 * llega intacto (RF-104, F5-03A) y que "Cancelar" nunca produce un `POST`.
 */
async function mockBackend(page, { token = TOKEN } = {}) {
  const queryRequestBodies = [];

  await page.route("**/v2/agent/query", async (route) => {
    queryRequestBodies.push(route.request().postDataJSON());
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: REAL_ANSWER.run_id,
        run_access_token: token,
        token_expires_at: "2026-07-28T23:59:59Z",
        stream_url: `/v2/agent/stream/${REAL_ANSWER.run_id}`,
      }),
    });
  });
  await page.route(`**/v2/agent/stream/${REAL_ANSWER.run_id}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: REAL_STREAM });
  });
  await page.route(`**/v2/agent/runs/${REAL_ANSWER.run_id}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: REAL_ANSWER.run_id, status: "completed", answer: REAL_ANSWER }),
    });
  });

  return { queryRequestBodies };
}

async function typeIntoSection(page, text) {
  const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
  await editor.click();
  await page.keyboard.type(text);
  return editor;
}

function activeElementSnapshot() {
  const element = document.activeElement;
  return {
    label: element?.getAttribute?.("aria-label") ?? "",
    role: element?.getAttribute?.("role") ?? element?.tagName?.toLowerCase() ?? "",
    text: element?.textContent?.trim() ?? "",
  };
}

/** Recorrido real hacia adelante: nunca `.focus()`, nunca clic. */
async function tabUntil(page, predicate, description, limit = 80) {
  for (let index = 0; index < limit; index += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(activeElementSnapshot);
    if (predicate(active)) return active;
  }
  throw new Error(`No se encontró mediante Tab: ${description}`);
}

/** Recorrido real hacia atrás (Mayús+Tab). */
async function shiftTabUntil(page, predicate, description, limit = 80) {
  for (let index = 0; index < limit; index += 1) {
    await page.keyboard.press("Shift+Tab");
    const active = await page.evaluate(activeElementSnapshot);
    if (predicate(active)) return active;
  }
  throw new Error(`No se encontró mediante Mayús+Tab: ${description}`);
}

async function focusIsInsideDialog(page) {
  return page.evaluate(() => document.activeElement?.closest('[role="dialog"]') !== null);
}

test.describe("/app — F5-03A secciones e investigación contextual (RF-104)", () => {
  test("cancelar la vista previa no produce ningún POST", async ({ page }) => {
    const { queryRequestBodies } = await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await typeIntoSection(page, SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();

    const dialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
    await expect(dialog).toBeVisible();
    const preview = dialog.getByRole("region", { name: "Contexto que se enviará (texto literal de la sección)" });
    await expect(preview).toHaveText(SECTION_TEXT);

    await dialog.getByRole("button", { name: "Cancelar" }).click();
    await expect(dialog).not.toBeVisible();
    expect(queryRequestBodies).toHaveLength(0);
  });

  test("una sección vacía no abre la vista previa ni permite investigar", async ({ page }) => {
    const { queryRequestBodies } = await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    await expect(page.getByText("no tiene contenido suficiente para investigar")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(queryRequestBodies).toHaveLength(0);
  });

  test("confirmar envía exactamente un POST con el context_hint literal y la evidencia se inserta en la sección de origen", async ({
    page,
  }) => {
    const { queryRequestBodies } = await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await typeIntoSection(page, SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    const dialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
    await dialog
      .getByLabel("Pregunta para investigar")
      .fill("¿Cuál fue la cobertura educativa reportada en el municipio?");
    await dialog.getByRole("button", { name: "Investigar con este contexto" }).click();

    await page
      .getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })
      .getByRole("button", { name: "Aceptar e investigar" })
      .click();

    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
      timeout: 15_000,
    });

    expect(queryRequestBodies).toHaveLength(1);
    expect(queryRequestBodies[0]).toMatchObject({
      question: "¿Cuál fue la cobertura educativa reportada en el municipio?",
      context_hint: SECTION_TEXT,
    });

    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    const citation = page.getByRole("group", { name: /Cita de evidencia:/ });
    await expect(citation).toBeVisible();

    // La cita debe estar DENTRO del editor de "Sección 1" (sección de
    // origen), no en un editor distinto.
    const sectionEditor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await expect(sectionEditor.getByRole("group", { name: /Cita de evidencia:/ })).toHaveCount(1);
  });

  test("la pregunta libre sigue funcionando sin context_hint forzado, como flujo independiente", async ({ page }) => {
    const { queryRequestBodies } = await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    // Sin tocar ninguna sección ni el botón "Investigar esta sección".
    await page
      .getByLabel("Pregunta para investigar", { exact: true })
      .fill("¿Cuál fue el promedio de deserción escolar en Antioquia entre 2018 y 2022?");
    await page.getByRole("button", { name: "Investigar", exact: true }).click();
    await page
      .getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })
      .getByRole("button", { name: "Aceptar e investigar" })
      .click();

    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
      timeout: 15_000,
    });

    expect(queryRequestBodies).toHaveLength(1);
    expect(queryRequestBodies[0].question).toBe(
      "¿Cuál fue el promedio de deserción escolar en Antioquia entre 2018 y 2022?",
    );
    expect(queryRequestBodies[0].context_hint ?? null).toBeNull();
  });

  test("navegación real por teclado: alcanza, abre, recorre y confirma sin focus()/clics; el foco no escapa del modal", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    // Foco neutro: recién cargada la página, sin ningún clic previo.
    // RF-101-02-R1: storage vacío → el selector de plantilla es la PRIMERA
    // pantalla real; se recorre y confirma también exclusivamente por
    // teclado (`createFreeDocumentViaPickerWithKeyboard`), para no romper
    // la garantía "sin ningún clic previo" que esta prueba afirma.
    await createFreeDocumentViaPickerWithKeyboard(page);

    // 1. Alcanza el editor de la sección con Tab real (nunca `.click()`
    // ni `.focus()`) y escribe el diagnóstico — precondición de contenido,
    // no una afirmación de recorrido en sí misma.
    await tabUntil(
      page,
      (active) => active.role === "textbox" && active.label === "Documento de trabajo: Sección 1",
      "editor de la sección"
    );
    await page.keyboard.type(SECTION_TEXT);

    // 2. Retrocede con Mayús+Tab hasta "Investigar esta sección" (queda
    // antes del editor en el orden del documento) y lo abre con Enter.
    const investigateButton = page.getByRole("button", { name: "Investigar esta sección" });
    await shiftTabUntil(page, (active) => active.text === "Investigar esta sección", "botón Investigar esta sección");
    await expect(investigateButton).toBeFocused();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
    await expect(dialog).toBeVisible();
    // Foco inicial predecible del propio Modal: su botón "Cerrar".
    await expect(dialog.getByRole("button", { name: "Cerrar" })).toBeFocused();

    // 3. Recorre el modal con Tab hasta el textarea de la pregunta.
    const questionField = dialog.getByLabel("Pregunta para investigar");
    await tabUntil(page, (active) => active.role === "textarea", "campo de pregunta del modal");
    await expect(questionField).toBeFocused();

    // 4. `fill()`/escritura SOLO después de demostrar foco real por teclado.
    await page.keyboard.type("¿Qué reporta esta sección sobre cobertura?");
    expect(await focusIsInsideDialog(page)).toBe(true);

    // 5. Alcanza y activa "Investigar con este contexto" con Tab + Enter.
    const confirmButton = dialog.getByRole("button", { name: "Investigar con este contexto" });
    await tabUntil(
      page,
      (active) => active.text === "Investigar con este contexto",
      "botón Investigar con este contexto"
    );
    await expect(confirmButton).toBeFocused();
    expect(await focusIsInsideDialog(page)).toBe(true); // nunca escapó del modal
    await page.keyboard.press("Enter");

    // 6. Recorre y acepta el consentimiento también con teclado.
    const consentDialog = page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" });
    await expect(consentDialog).toBeVisible();
    const acceptButton = consentDialog.getByRole("button", { name: "Aceptar e investigar" });
    await tabUntil(page, (active) => active.text === "Aceptar e investigar", "botón Aceptar e investigar");
    await expect(acceptButton).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("cancelar la vista previa con teclado restaura el foco a 'Investigar esta sección', sin escapar del modal", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    // RF-101-02-R1: mismo motivo que la prueba anterior — cero clics, ni
    // siquiera para crear el documento inicial.
    await createFreeDocumentViaPickerWithKeyboard(page);

    await tabUntil(
      page,
      (active) => active.role === "textbox" && active.label === "Documento de trabajo: Sección 1",
      "editor de la sección"
    );
    await page.keyboard.type(SECTION_TEXT);

    const investigateButton = page.getByRole("button", { name: "Investigar esta sección" });
    await shiftTabUntil(page, (active) => active.text === "Investigar esta sección", "botón Investigar esta sección");
    await expect(investigateButton).toBeFocused();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
    await expect(dialog).toBeVisible();

    const cancelButton = dialog.getByRole("button", { name: "Cancelar" });
    await tabUntil(page, (active) => active.text === "Cancelar", "botón Cancelar del modal");
    await expect(cancelButton).toBeFocused();
    expect(await focusIsInsideDialog(page)).toBe(true);

    await page.keyboard.press("Enter");

    await expect(dialog).not.toBeVisible();
    await expect(investigateButton).toBeFocused();
  });

  test("axe WCAG 2.2 AA con la vista previa de sección abierta", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
    await typeIntoSection(page, SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    await expect(page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" })).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("320 px refluye sin overflow con la vista previa de sección abierta", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
    await typeIntoSection(page, SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    await expect(page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" })).toBeVisible();

    const overflow = await page.evaluate(() => ({
      body: document.body.scrollWidth > document.body.clientWidth,
      html: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    expect(overflow).toEqual({ body: false, html: false });
  });

  test("capturas finales representativas", async ({ page }) => {
    await mockBackend(page);

    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
    await typeIntoSection(page, SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    await expect(page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" })).toBeVisible();
    await page.screenshot({
      path: "../docs/frontend-v2/design/f5-03a/screenshots/investigar-seccion-desktop-1440.png",
      fullPage: true,
    });

    await page.setViewportSize({ width: 320, height: 800 });
    await page.reload();
    await page.evaluate(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });
    // RF-101-02-R1: tras limpiar el storage, `/app` (ya cargada tras el
    // reload) puede seguir mostrando el selector o el documento previo según
    // si el autoguardado alcanzó a persistir antes del reload; se pasa por
    // el selector explícitamente para dejar el estado determinista antes de
    // continuar (mismo criterio: no se altera ninguna aserción de contenido,
    // esta prueba no tiene ninguna sobre la sección más allá del texto que
    // ella misma escribe a continuación).
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);
    await typeIntoSection(page, SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    await expect(page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" })).toBeVisible();
    await page.screenshot({
      path: "../docs/frontend-v2/design/f5-03a/screenshots/investigar-seccion-mobile-320.png",
      fullPage: true,
    });
  });
});
