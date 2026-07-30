import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

/**
 * F8-02-R1 — regresión E2E dedicada de D-5 (hallazgo de revisión manual
 * F8-02, `docs/release-wcag-v2.0.0-rc1.md` §5): insertar una cita de
 * evidencia o un aporte manual al final del documento y luego escribir con
 * TECLADO REAL justo después reemplazaba por completo el nodo insertado —
 * pérdida de contenido real. La causa era `trailingNode: false` en
 * `lib/document/schema.js` (corregido en F8-02). Esta prueba cierra el
 * círculo hasta la persistencia real: recarga la página y confirma que
 * TANTO el nodo atómico COMO el texto escrito después sobreviven, no solo
 * en memoria sino en `localStorage`.
 *
 * Complementa (no sustituye) las pruebas unitarias conductuales de
 * `tests/unit/document/DocumentEditor.test.jsx` ("D-5: ..."), que ejercen
 * el mismo mecanismo sin backend ni persistencia real.
 */

const APP_URL = "/app";
const DOC_KEY = "cdd.doc.v1";
const REAL_STREAM = readFileSync(
  path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt"),
  "utf8",
);
const TOKEN = "cdt_rt_d5_regresion_no_debe_aparecer";
const SECTION_TEXT = "Diagnostico D-5: desercion escolar en Antioquia entre 2018 y 2022.";
const QUESTION = "¿Cual fue el promedio de desercion escolar en el departamento de Antioquia entre 2018 y 2022?";
const TEXT_AFTER_CITATION = "Texto escrito con teclado real justo despues de insertar la cita (D-5).";
const TEXT_AFTER_MANUAL = "Texto escrito con teclado real justo despues del aporte manual (D-5).";

function answerFromStream(stream) {
  const block = stream.split(/\r?\n\r?\n/).find((candidate) => candidate.includes("event: answer"));
  const dataLine = block?.split(/\r?\n/).find((line) => line.startsWith("data: "));
  if (!dataLine) throw new Error("El fixture real no contiene evento answer");
  return JSON.parse(dataLine.slice(6));
}

const REAL_ANSWER = answerFromStream(REAL_STREAM);

async function mockBackend(page) {
  await page.route("**/v2/agent/query", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: REAL_ANSWER.run_id,
        run_access_token: TOKEN,
        token_expires_at: "2026-08-30T23:59:59Z",
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
}

async function waitForDocumentPersisted(page) {
  await page.waitForFunction((key) => window.localStorage.getItem(key) !== null, DOC_KEY, { timeout: 10_000 });
}

test.describe("/app — D-5, regresión de pérdida de contenido (F8-02-R1)", () => {
  test("cita de evidencia al final + texto escrito con teclado real después: ambos sobreviven en memoria y tras recargar", async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

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
    await page
      .getByLabel("Investigación en curso")
      .getByText("La investigación terminó con evidencia verificada.")
      .waitFor({ timeout: 15_000 });

    // Insertar la cita AL FINAL de la sección (después del texto ya
    // escrito) — el propio comando deja el editor enfocado al final
    // (`DocumentEditor.jsx:insertEvidenceCitation` → `focus("end")`), que
    // es exactamente la condición que disparaba D-5.
    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    const confirmDialog = page.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
    const requiresConfirmation = await confirmDialog
      .waitFor({ state: "visible", timeout: 1_500 })
      .then(() => true)
      .catch(() => false);
    if (requiresConfirmation) {
      await confirmDialog.getByRole("button", { name: "Insertar con advertencia" }).click();
    }
    const citation = editor.getByRole("group", { name: /Cita de evidencia:/ });
    await expect(citation).toBeVisible();

    // Escribir con TECLADO REAL justo después de insertar — sin clic
    // adicional, confiando en el mismo foco que dejó la app (reproduce la
    // interacción real de un usuario que sigue escribiendo).
    await page.keyboard.type(TEXT_AFTER_CITATION);

    // En memoria: la cita sigue existiendo Y el texto quedó después de ella.
    await expect(citation).toBeVisible();
    await expect(editor).toContainText(TEXT_AFTER_CITATION);
    const citationBox = await citation.boundingBox();
    const textLocator = editor.getByText(TEXT_AFTER_CITATION);
    const textBox = await textLocator.boundingBox();
    expect(textBox.y).toBeGreaterThan(citationBox.y); // el texto quedó DEBAJO de la cita, no la reemplazó

    // Persistencia real: esperar autoguardado y recargar.
    await waitForDocumentPersisted(page);
    await page.reload();

    const reloadedEditor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await expect(reloadedEditor.getByRole("group", { name: /Cita de evidencia:/ })).toBeVisible();
    await expect(reloadedEditor).toContainText(SECTION_TEXT);
    await expect(reloadedEditor).toContainText(TEXT_AFTER_CITATION);

    // Confirmación adicional directamente contra el documento serializado
    // en `localStorage` (no solo el DOM): el nodo atómico y el párrafo de
    // texto posterior existen los dos, en ese orden.
    const stored = JSON.parse(await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY));
    const sectionContent = stored.document.sections[0].content.content;
    const citationIndex = sectionContent.findIndex((node) => node.type === "evidenceCitation");
    expect(citationIndex).toBeGreaterThanOrEqual(0);
    const nodesAfterCitation = sectionContent.slice(citationIndex + 1);
    const textSurvived = nodesAfterCitation.some(
      (node) =>
        node.type === "paragraph" &&
        (node.content ?? []).some((inline) => inline.text?.includes(TEXT_AFTER_CITATION)),
    );
    expect(textSurvived).toBe(true);
  });

  test("aporte manual al final + texto escrito con teclado real después: ambos sobreviven en memoria y tras recargar", async ({
    page,
  }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await page.getByRole("button", { name: "Agregar dato manual" }).click();
    await page.getByLabel("Valor (opcional)").fill("17,50 unidades sintéticas D-5");
    await page.locator("#manual-entry-source").fill("Fuente sintética D-5");
    await page.getByRole("button", { name: "Guardar aporte manual" }).click();

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    const manualNode = editor.getByRole("group", { name: /Aporte manual — no verificado por el agente/ });
    await expect(manualNode).toBeVisible();

    // Igual que con la cita: el comando de inserción ya deja el editor
    // enfocado al final; se escribe de inmediato con teclado real.
    await page.keyboard.type(TEXT_AFTER_MANUAL);

    await expect(manualNode).toBeVisible();
    await expect(editor).toContainText(TEXT_AFTER_MANUAL);
    const manualBox = await manualNode.boundingBox();
    const textBox = await editor.getByText(TEXT_AFTER_MANUAL).boundingBox();
    expect(textBox.y).toBeGreaterThan(manualBox.y);

    await waitForDocumentPersisted(page);
    await page.reload();

    const reloadedEditor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await expect(
      reloadedEditor.getByRole("group", { name: /Aporte manual — no verificado por el agente/ }),
    ).toBeVisible();
    await expect(reloadedEditor).toContainText(TEXT_AFTER_MANUAL);

    const stored = JSON.parse(await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY));
    const sectionContent = stored.document.sections[0].content.content;
    const manualIndex = sectionContent.findIndex((node) => node.type === "manualEntry");
    expect(manualIndex).toBeGreaterThanOrEqual(0);
    const nodesAfterManual = sectionContent.slice(manualIndex + 1);
    const textSurvived = nodesAfterManual.some(
      (node) =>
        node.type === "paragraph" &&
        (node.content ?? []).some((inline) => inline.text?.includes(TEXT_AFTER_MANUAL)),
    );
    expect(textSurvived).toBe(true);
  });
});
