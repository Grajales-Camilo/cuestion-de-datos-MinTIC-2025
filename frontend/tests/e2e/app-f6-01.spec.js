import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const APP_URL = "/app";
const DOC_KEY = "cdd.doc.v1";
const REAL_STREAM = readFileSync(
  path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt"),
  "utf8",
);
const TOKEN = "cdt_rt_f6_01_e2e_no_debe_aparecer";
const SECTION_TEXT = "Diagnostico de desercion escolar en Antioquia entre 2018 y 2022.";
const QUESTION = "¿Cual fue el promedio de desercion escolar en el departamento de Antioquia entre 2018 y 2022?";

function answerFromStream(stream) {
  const block = stream.split(/\r?\n\r?\n/).find((candidate) => candidate.includes("event: answer"));
  const dataLine = block?.split(/\r?\n/).find((line) => line.startsWith("data: "));
  if (!dataLine) throw new Error("El fixture real no contiene evento answer");
  return JSON.parse(dataLine.slice(6));
}

const REAL_ANSWER = answerFromStream(REAL_STREAM);

/**
 * Variante del stream REAL con un único campo sobrescrito
 * (`evidence[0].quality.classification`) para ejercer la rama documentada
 * `no_recomendada` → `warningRequired: true`. Todo lo demás (run_id,
 * dataset, consulta, claims) sale intacto de la corrida capturada — no es un
 * fixture escrito a mano desde el contrato (`implementation-plan.md` §12.3),
 * es el mismo patrón ya usado en `tests/unit/document/citationNode.test.js`
 * (mutar un campo del fixture real para cubrir un caso límite documentado).
 */
function buildWarningVariantStream(rawStream) {
  const blocks = rawStream.split(/\r?\n\r?\n/);
  const transformed = blocks.map((block) => {
    if (!block.includes("event: answer")) return block;
    const lines = block.split(/\r?\n/);
    const dataLineIndex = lines.findIndex((line) => line.startsWith("data: "));
    const parsed = JSON.parse(lines[dataLineIndex].slice(6));
    parsed.evidence[0].quality = { ...parsed.evidence[0].quality, classification: "no_recomendada" };
    lines[dataLineIndex] = `data: ${JSON.stringify(parsed)}`;
    return lines.join("\n");
  });
  return transformed.join("\n\n");
}
const WARNING_STREAM = buildWarningVariantStream(REAL_STREAM);

async function mockBackend(page, { stream = REAL_STREAM, token = TOKEN } = {}) {
  await page.route("**/v2/agent/query", async (route) => {
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
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: stream });
  });
  await page.route(`**/v2/agent/runs/${REAL_ANSWER.run_id}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: REAL_ANSWER.run_id, status: "completed", answer: REAL_ANSWER }),
    });
  });
}

/** Escribe en la Sección 1, investiga desde ahí (context_hint = texto de la
 * sección) e inserta la cita resultante en esa misma sección — igual que
 * `app-f5-03.spec.js`, reutilizado aquí para dejar texto + cita real en el
 * documento antes de probar persistencia. */
async function typeAndInsertCitation(page) {
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

  // RF-404: una evidencia `no_recomendada` (variante de warningRequired) abre
  // una confirmación adicional antes de insertar de verdad.
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

async function waitForDocumentPersisted(page) {
  await page.waitForFunction((key) => window.localStorage.getItem(key) !== null, DOC_KEY, { timeout: 8_000 });
}

test.describe("/app — F6-01 persistencia documental (RF-102/RF-103, ESC-08)", () => {
  test("escribir texto + insertar una cita real, recargar: ambos sobreviven", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);

    await typeAndInsertCitation(page);
    await waitForDocumentPersisted(page);

    await page.reload();

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await expect(editor).toContainText(SECTION_TEXT);
    await expect(page.getByRole("group", { name: /Cita de evidencia:/ })).toBeVisible();
    await expect(page.getByText(REAL_ANSWER.evidence[0].dataset_name)).toBeVisible();
  });

  test("warningRequired sigue visible después de recargar (fixture real con classification sobrescrita)", async ({
    page,
  }) => {
    await mockBackend(page, { stream: WARNING_STREAM });
    await page.goto(APP_URL);

    await typeAndInsertCitation(page);
    await expect(page.getByText("Evidencia no recomendada: úsala con cautela.")).toBeVisible();
    await waitForDocumentPersisted(page);

    await page.reload();

    await expect(page.getByText("Evidencia no recomendada: úsala con cautela.")).toBeVisible();
  });

  test("cdd.doc.v1 nunca contiene cdt_rt_, Authorization ni token", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);

    await typeAndInsertCitation(page);
    await waitForDocumentPersisted(page);

    const raw = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(raw).not.toContain(TOKEN);
    expect(raw).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
    expect(raw.toLowerCase()).not.toContain('"token"');
    expect(raw.toLowerCase()).not.toContain('"authorization"');
  });

  test("versión futura sembrada: aviso visible, documento no sobrescrito ni con el debounce vencido, descarga disponible", async ({
    page,
  }) => {
    const futureEnvelope = {
      schemaVersion: 999,
      createdAt: "2026-01-01T00:00:00.000Z",
      updatedAt: "2026-01-01T00:00:00.000Z",
      document: { version: 1, templateId: "libre", title: "Documento futuro", sections: [] },
    };
    await page.addInitScript(
      ([key, envelope]) => window.localStorage.setItem(key, JSON.stringify(envelope)),
      [DOC_KEY, futureEnvelope],
    );
    await page.goto(APP_URL);

    await expect(page.getByText(/versión más nueva/)).toBeVisible();

    // Se puede seguir escribiendo en un documento nuevo en memoria (no se
    // bloquea la edición), pero la clave autoritativa NUNCA se sobrescribe
    // mientras la versión futura siga ahí — ni siquiera tras esperar más que
    // el debounce de 5 s.
    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Este cambio nunca debe sobrescribir la versión futura.");
    await page.waitForTimeout(6_000);

    const storedAfterEdit = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(JSON.parse(storedAfterEdit)).toEqual(futureEnvelope);

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Descargar archivo intacto" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });

  test("JSON corrupto se recupera de forma segura: se aísla, se abre un documento nuevo y editable", async ({
    page,
  }) => {
    await page.addInitScript(
      (key) => window.localStorage.setItem(key, "{esto no es json valido"),
      DOC_KEY,
    );
    await page.goto(APP_URL);

    await expect(page.getByText(/estaba dañado/)).toBeVisible();

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Documento nuevo tras corrupción");
    await expect(editor).toContainText("Documento nuevo tras corrupción");

    const corruptKeys = await page.evaluate(
      (key) => Object.keys(window.localStorage).filter((k) => k.startsWith(`${key}.corrupt.`)),
      DOC_KEY,
    );
    expect(corruptKeys.length).toBeGreaterThan(0);

    const diagnosticRaw = await page.evaluate(
      ([key, diagKey]) => window.localStorage.getItem(diagKey),
      [DOC_KEY, corruptKeys[0]],
    );
    expect(diagnosticRaw).toBe("{esto no es json valido");
  });

  test("teclado, axe WCAG 2.2 AA y reflujo a 320 px para el aviso de recuperación", async ({ page }) => {
    await page.addInitScript(
      (key) => window.localStorage.setItem(key, "{esto no es json valido"),
      DOC_KEY,
    );
    await page.goto(APP_URL);
    await expect(page.getByText(/estaba dañado/)).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);

    const dismissButton = page.getByRole("button", { name: "Entendido" });
    let reached = false;
    for (let index = 0; index < 40 && !reached; index += 1) {
      await page.keyboard.press("Tab");
      reached = await dismissButton.evaluate((node) => node === document.activeElement).catch(() => false);
    }
    expect(reached).toBe(true);
    await page.keyboard.press("Enter");
    await expect(page.getByText(/estaba dañado/)).toHaveCount(0);

    await page.setViewportSize({ width: 320, height: 800 });
    const overflow = await page.evaluate(() => ({
      body: document.body.scrollWidth > document.body.clientWidth,
      html: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    expect(overflow).toEqual({ body: false, html: false });
  });
});
