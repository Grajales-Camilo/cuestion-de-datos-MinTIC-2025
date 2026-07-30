import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import JSZip from "jszip";
import { expect, test } from "@playwright/test";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

/**
 * F6-02B — descarga real de `.docx` desde `/app` (RF-102/RF-103, ESC-08).
 *
 * El fixture real usado para la evidencia es `completed-with-claims.json`
 * (única captura `completed` con `claims[]`/`label_status="verified"` del
 * repositorio, ver `tests/fixtures/README.md`: Método 2, caso
 * `pilot-041-eca`). Es un `.json`, no un `.sse.txt`: el cuerpo SSE se arma
 * a mano solo como envoltorio de transporte (`event: step` + `event:
 * answer`) — el mismo patrón ya establecido en
 * `tests/e2e/evidence-f4-02.spec.js`. El `answer` que viaja dentro de
 * `event: answer` es exactamente el capturado, sin alterar ningún campo
 * salvo en la variante `no_recomendada` (mutación de un único campo,
 * declarada explícitamente, igual que `app-f6-01.spec.js`).
 */

const APP_URL = "/app";
const TOKEN = "cdt_rt_f6_02b_e2e_no_debe_aparecer";
const SECTION_TEXT = "Diagnostico de codigos NUECA para la empresa 78 en Antioquia.";

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);
const RUN_ID = fixture.run_id;
const CITATION = fixture.answer.evidence[0].citation;
const QUESTION = fixture.answer.intention.topic;

function sseBody(answer) {
  const stepEvent = [
    "id: 0",
    "event: step",
    `data: ${JSON.stringify({ step_number: 1, node: "execute_query", display_message: "Consultando datos.gov.co…", detail: null })}`,
    "",
    "",
  ].join("\n");
  const answerEvent = ["id: 1", "event: answer", `data: ${JSON.stringify(answer)}`, "", ""].join("\n");
  return stepEvent + answerEvent;
}

function warningVariantAnswer() {
  // DOBLE SINTÉTICO ya autorizado (mismo patrón que
  // `app-f6-01.spec.js:buildWarningVariantStream`): un único campo mutado
  // sobre el fixture real, para ejercer `no_recomendada` → `warningRequired: true`.
  const answer = structuredClone(fixture.answer);
  answer.evidence[0].quality = { ...answer.evidence[0].quality, classification: "no_recomendada" };
  return answer;
}

async function mockBackend(page, { answer = fixture.answer, token = TOKEN } = {}) {
  await page.route("**/v2/agent/query", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        run_access_token: token,
        token_expires_at: "2026-07-30T23:59:59Z",
        stream_url: `/v2/agent/stream/${RUN_ID}`,
      }),
    });
  });
  await page.route(`**/v2/agent/stream/${RUN_ID}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: sseBody(answer) });
  });
  await page.route(`**/v2/agent/runs/${RUN_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: RUN_ID, status: "completed", answer }),
    });
  });
}

/** Igual que `typeAndInsertCitation` de `app-f6-01.spec.js`: escribe en la
 * Sección 1, investiga desde ahí y deja la cita real insertada. */
async function typeInvestigateAndInsert(page) {
  const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
  await editor.click();
  await page.keyboard.type(SECTION_TEXT);

  await page.getByRole("button", { name: "Investigar esta sección" }).click();
  const dialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
  await dialog.getByLabel("Pregunta para investigar").fill(QUESTION);
  await dialog.getByRole("button", { name: "Investigar con este contexto" }).click();

  await page
    .getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })
    .getByRole("button", { name: "Aceptar e investigar" })
    .click();

  await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole("button", { name: "Insertar en el documento" }).click();

  const confirmDialog = page.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
  const requiresConfirmation = await confirmDialog
    .waitFor({ state: "visible", timeout: 1_500 })
    .then(() => true)
    .catch(() => false);
  if (requiresConfirmation) {
    await confirmDialog.getByRole("button", { name: "Insertar con advertencia" }).click();
  }

  await expect(page.getByRole("group", { name: /Cita de evidencia:/ })).toBeVisible();
}

async function unzip(filePath) {
  const buffer = readFileSync(filePath);
  return JSZip.loadAsync(buffer);
}

function activeElementSnapshot() {
  const element = document.activeElement;
  return {
    label: element?.getAttribute?.("aria-label") ?? "",
    text: element?.textContent?.trim() ?? "",
  };
}

/** Recorrido real hacia adelante: nunca `.focus()`, nunca clic sobre el
 * destino. Mismo patrón que `app-f5-03.spec.js:tabUntil` — `page.evaluate`
 * aquí solo LEE `document.activeElement` tras cada `Tab` real, nunca lo
 * mueve. */
async function tabUntil(page, predicate, description, limit = 60) {
  for (let index = 0; index < limit; index += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(activeElementSnapshot);
    if (predicate(active)) return active;
  }
  throw new Error(`No se encontró mediante Tab: ${description}`);
}

test.describe("/app — F6-02B exportación DOCX real (RF-102/RF-103, ESC-08)", () => {
  test("escribir + investigar + insertar evidencia real, exportar CON TECLADO → descarga real con OOXML correcto (RF-103 completo)", async ({
    page,
  }, testInfo) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await typeInvestigateAndInsert(page);

    const exportButton = page.getByRole("button", { name: "Exportar en Word (.docx)" });
    await expect(exportButton).toBeVisible();

    const seenRequests = [];
    page.on("request", (request) => seenRequests.push(request.url()));

    // Foco neutro real (clic en un elemento no interactivo: el `<h1>` de
    // cabecera nunca es un destino de tabulación, así que esto solo quita
    // el foco de lo último clicado por `typeInvestigateAndInsert`, sin
    // moverlo programáticamente a ningún control concreto).
    await page.getByRole("heading", { name: "Cuestión de Datos", exact: true }).click();

    // Navegación real por TECLADO: solo `Tab`, en un bucle acotado, hasta
    // que el propio orden de tabulación de la página alcance el botón —
    // nunca `.focus()`, nunca `page.evaluate()` para mover el foco.
    await tabUntil(page, (el) => el.text.includes("Exportar en Word"), "botón Exportar en Word (.docx)");
    await expect(exportButton).toBeFocused();

    const downloadPromise = page.waitForEvent("download");
    await page.keyboard.press("Enter");
    const download = await downloadPromise;

    // 3) nombre sugerido seguro y terminado en .docx.
    const suggestedFilename = download.suggestedFilename();
    expect(suggestedFilename).toMatch(/\.docx$/);
    expect(suggestedFilename).not.toContain("/");
    expect(suggestedFilename).not.toContain("\\");
    expect(suggestedFilename).not.toContain("..");

    const outputPath = testInfo.outputPath(suggestedFilename);
    await download.saveAs(outputPath);

    // 4) tamaño mayor que cero.
    const { statSync } = await import("node:fs");
    expect(statSync(outputPath).size).toBeGreaterThan(0);

    // 5) contenido OOXML real.
    const zip = await unzip(outputPath);
    expect(zip.file("word/document.xml")).not.toBeNull();
    expect(zip.file("word/footnotes.xml")).not.toBeNull();

    const documentXml = await zip.file("word/document.xml").async("string");
    const footnotesXml = await zip.file("word/footnotes.xml").async("string");

    // Texto escrito inmediatamente antes del clic (SIN forzar guardado previo).
    expect(documentXml).toContain(SECTION_TEXT);

    // Campos RF-103 del fixture real, y referencia+nota asociadas.
    expect(footnotesXml).toContain(CITATION.dataset_id);
    expect(footnotesXml).toContain(CITATION.dataset_name);
    expect(footnotesXml).toContain(CITATION.publisher);
    expect(footnotesXml).toContain(CITATION.executed_at);
    const footnoteRefIds = [...documentXml.matchAll(/<w:footnoteReference[^>]*w:id="(-?\d+)"/g)]
      .map((m) => m[1])
      .filter((id) => Number(id) > 0);
    const footnoteIds = [...footnotesXml.matchAll(/<w:footnote[^>]*w:id="(-?\d+)"/g)].map((m) => m[1]);
    expect(footnoteRefIds.length).toBeGreaterThan(0);
    for (const id of footnoteRefIds) expect(footnoteIds).toContain(id);

    // 8) sin POST/fetch de documento ni URL con token durante la exportación.
    const backendRequests = seenRequests.filter((url) => url.includes("/v2/agent"));
    expect(backendRequests).toEqual([]);
    for (const url of seenRequests) expect(url).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
    expect(download.url()).toMatch(/^blob:/);

    // 10) la interfaz vuelve a quedar utilizable tras el éxito.
    await expect(page.getByRole("button", { name: "Exportar en Word (.docx)" })).toBeEnabled();
  });

  test("warningRequired:true sigue visible en el DOCX exportado (variante no_recomendada, doble sintético autorizado)", async ({
    page,
  }, testInfo) => {
    await mockBackend(page, { answer: warningVariantAnswer() });
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await typeInvestigateAndInsert(page);
    await expect(page.getByText("Evidencia no recomendada: úsala con cautela.")).toBeVisible();

    const exportButton = page.getByRole("button", { name: "Exportar en Word (.docx)" });
    const downloadPromise = page.waitForEvent("download");
    await exportButton.click();
    const download = await downloadPromise;

    const outputPath = testInfo.outputPath(download.suggestedFilename());
    await download.saveAs(outputPath);
    const zip = await unzip(outputPath);
    const documentXml = await zip.file("word/document.xml").async("string");
    const footnotesXml = await zip.file("word/footnotes.xml").async("string");

    expect(documentXml).toContain("Advertencia");
    expect(footnotesXml.toLowerCase()).toContain("no es recomendada");
  });

  test("teclado completo, foco visible, axe WCAG 2.2 AA y superficie real en 1440 px y 320 px", async ({ page }) => {
    await mockBackend(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    const exportButton = page.getByRole("button", { name: "Exportar en Word (.docx)" });
    const persistenceStatus = page.getByText("Guardado");
    await expect(exportButton).toBeVisible();
    // "Guardado" solo aparece tras el primer autoguardado con debounce
    // (5000 ms, `useDocumentAutosave`'s `DEFAULT_DEBOUNCE_MS`) del documento
    // libre recién sembrado: se da margen explícito por encima de esos 5 s
    // (el timeout por defecto de Playwright, también 5000 ms, empataría con
    // el debounce y sería una carrera bajo carga paralela).
    await expect(persistenceStatus).toBeVisible({ timeout: 8_000 });

    // 1440 px: comparte fila flexible con el estado de persistencia (misma
    // banda horizontal, no apilado como a 320 px).
    const [buttonBox, statusBox] = await Promise.all([exportButton.boundingBox(), persistenceStatus.boundingBox()]);
    expect(Math.abs(buttonBox.y - statusBox.y)).toBeLessThan(24);
    await page.screenshot({ path: test.info().outputPath("export-button-1440.png") });

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);

    // Foco neutro real, luego navegación real por TECLADO (solo `Tab`, bucle
    // acotado) — nunca `.focus()`, nunca `page.evaluate()` para mover el foco.
    await page.getByRole("heading", { name: "Cuestión de Datos", exact: true }).click();
    await tabUntil(page, (el) => el.text.includes("Exportar en Word"), "botón Exportar en Word (.docx)");
    await expect(exportButton).toBeFocused();

    await page.setViewportSize({ width: 320, height: 800 });
    await expect(exportButton).toBeVisible();
    const overflow = await page.evaluate(() => ({
      body: document.body.scrollWidth > document.body.clientWidth,
      html: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    expect(overflow).toEqual({ body: false, html: false });
    await page.screenshot({ path: test.info().outputPath("export-button-320.png") });
  });

  test("un documento con un token en el texto rechaza la exportación con un mensaje seguro, y la interfaz queda utilizable tras el error", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Nota interna cdt_rt_no_debe_exportarse_jamas fin de la nota.");

    const exportButton = page.getByRole("button", { name: "Exportar en Word (.docx)" });
    await exportButton.click();

    // Mensaje fijo y completo (`toHaveText`, no `toContainText`): por
    // construcción no puede llevar el token, sin necesidad de negar su
    // presencia por separado (el editor SÍ sigue mostrando el texto que
    // escribió el usuario — es su documento, nunca se borra por esto).
    // `getByRole("alert")` también resuelve el `__next-route-announcer__`
    // (siempre presente y vacío) — se filtra por el texto propio.
    await expect(
      page.getByRole("alert").filter({ hasText: "No pudimos exportar" }),
    ).toHaveText(
      "No pudimos exportar porque el documento contiene información sensible. Revísalo antes de intentarlo de nuevo.",
    );
    await expect(page.getByRole("button", { name: "Exportar en Word (.docx)" })).toBeEnabled();
    await expect(editor).toBeEditable();
  });
});
