import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import JSZip from "jszip";
import { expect, test } from "@playwright/test";

const APP_URL = "/app";
const DOC_KEY = "cdd.doc.v1";
const MANUAL = {
  value: "17,50 unidades sintéticas",
  text: "Descripción manual sintética",
  source: "Fuente manual sintética",
  url: "https://example.gov.co/fuente-manual",
  date: "2026-07-29",
};
const KEYBOARD_MANUAL = {
  value: "17,50 unidades sintéticas",
  text: "Descripción manual sintética",
  source: "Fuente manual sintética",
};
const TOKEN = "cdt_rt_manual_f7_02a_no_debe_persistir";
const SECTION_TEXT = "Diagnostico de codigos NUECA para la empresa 78 en Antioquia.";
const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);
const RUN_ID = fixture.run_id;
const CITATION = fixture.answer.evidence[0].citation;
const QUESTION = fixture.answer.intention.topic;

function sseBody(answer) {
  const step = [
    "id: 0",
    "event: step",
    `data: ${JSON.stringify({ step_number: 1, node: "execute_query", display_message: "Consultando datos.gov.co…", detail: null })}`,
    "",
    "",
  ].join("\n");
  const answerEvent = ["id: 1", "event: answer", `data: ${JSON.stringify(answer)}`, "", ""].join("\n");
  return step + answerEvent;
}

async function mockBackend(page) {
  await page.route("**/v2/agent/query", (route) =>
    route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        run_access_token: "cdt_rt_f7_02a_mock_transport",
        token_expires_at: "2026-07-30T23:59:59Z",
        stream_url: `/v2/agent/stream/${RUN_ID}`,
      }),
    }),
  );
  await page.route(`**/v2/agent/stream/${RUN_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: sseBody(fixture.answer) }),
  );
  await page.route(`**/v2/agent/runs/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: RUN_ID, status: "completed", answer: fixture.answer }),
    }),
  );
}

async function tabUntil(page, predicate, description, limit = 80) {
  for (let index = 0; index < limit; index += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => ({
      text: document.activeElement?.textContent?.trim() ?? "",
      label: document.activeElement?.getAttribute("aria-label") ?? "",
    }));
    if (predicate(active)) return active;
  }
  throw new Error(`No se encontró mediante Tab: ${description}`);
}

async function openManualWithKeyboard(page) {
  await tabUntil(page, (active) => active.text.includes("Agregar dato manual"), "Agregar dato manual");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Agregar dato manual" })).toBeVisible();
}

async function fillManualWithKeyboard(page) {
  await expect(page.getByLabel("Valor (opcional)")).toBeFocused();
  await page.keyboard.type(KEYBOARD_MANUAL.value);
  await page.keyboard.press("Tab");
  await page.keyboard.type(KEYBOARD_MANUAL.text);
  await page.keyboard.press("Tab");
  await page.keyboard.type(KEYBOARD_MANUAL.source);
  await page.keyboard.press("Tab");
  // URL opcional: se visita mediante Tab real y se deja vacía.
  await page.keyboard.press("Tab");
  // Fecha opcional: también se visita mediante Tab real y se deja vacía.
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
}

async function waitForDocumentPersisted(page) {
  await page.waitForFunction((key) => window.localStorage.getItem(key) !== null, DOC_KEY, { timeout: 10_000 });
}

async function readDocx(download, testInfo) {
  const outputPath = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(outputPath);
  const zip = await JSZip.loadAsync(readFileSync(outputPath));
  return {
    documentXml: await zip.file("word/document.xml").async("string"),
    footnotesXml: await zip.file("word/footnotes.xml").async("string"),
  };
}

test.describe("F7-02A — aporte manual visual, persistencia y DOCX", () => {
  test("inserción solo con teclado, persistencia, DOCX, foco, axe y 320 px", async ({ page }, testInfo) => {
    const requests = [];
    page.on("request", (request) => requests.push(request.url()));
    await page.goto(APP_URL);
    await expect(page.getByRole("button", { name: "Agregar dato manual" })).toBeVisible();

    await openManualWithKeyboard(page);
    await fillManualWithKeyboard(page);

    await expect(page.getByRole("dialog", { name: "Agregar dato manual" })).not.toBeVisible();
    await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toBeFocused();

    await expect(page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ })).toContainText(
      KEYBOARD_MANUAL.value,
    );
    await expect(page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ })).toContainText(
      KEYBOARD_MANUAL.text,
    );
    await expect(page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ })).toContainText(
      KEYBOARD_MANUAL.source,
    );
    await expect(page.getByRole("link", { name: "Abrir fuente declarada" })).not.toBeVisible();
    await expect(page.getByText("El aporte manual se agregó al documento.")).toBeVisible();
    await waitForDocumentPersisted(page);

    const stored = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(stored).toContain(KEYBOARD_MANUAL.value);
    expect(stored).toContain(KEYBOARD_MANUAL.text);
    expect(stored).not.toContain(TOKEN);
    const storedDocument = JSON.parse(stored);
    const manualNode = storedDocument.document.sections[0].content.content.find(
      (node) => node.type === "manualEntry",
    );
    expect(manualNode.attrs.date).toBeNull();
    expect(requests.filter((url) => url.includes("/v2/agent"))).toEqual([]);

    await page.reload();
    const manualGroup = page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ });
    await expect(manualGroup).toContainText(KEYBOARD_MANUAL.value);
    await expect(manualGroup).toContainText(KEYBOARD_MANUAL.text);
    await expect(manualGroup).toContainText(KEYBOARD_MANUAL.source);

    const axeResults = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(axeResults.violations).toEqual([]);

    await page.setViewportSize({ width: 320, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(
      true,
    );
    await page.screenshot({
      path: path.resolve(process.cwd(), "../docs/frontend-v2/design/f7-02a/screenshots/manual-entry-320.png"),
      fullPage: true,
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.screenshot({
      path: path.resolve(process.cwd(), "../docs/frontend-v2/design/f7-02a/screenshots/manual-entry-1440.png"),
      fullPage: true,
    });

    const exportButton = page.getByRole("button", { name: "Exportar en Word (.docx)" });
    const downloadPromise = page.waitForEvent("download");
    await exportButton.click();
    const { documentXml, footnotesXml } = await readDocx(await downloadPromise, testInfo);
    expect(documentXml).toContain("Aporte manual — no verificado por el agente");
    expect(footnotesXml).toContain(KEYBOARD_MANUAL.source);
    expect(footnotesXml).not.toContain("Fecha declarada");
    expect(footnotesXml).not.toContain("2026-");
    expect(documentXml).not.toContain("Verificado");
    expect(documentXml).not.toContain(TOKEN);
  });

  test("fecha real del aporte se conserva mediante el control date", async ({ page }) => {
    await page.goto(APP_URL);
    await page.getByRole("button", { name: "Agregar dato manual" }).click();
    await page.getByLabel("Valor (opcional)").fill(MANUAL.value);
    await page.locator("#manual-entry-source").fill(MANUAL.source);
    await page.locator("#manual-entry-date").fill(MANUAL.date);
    await page.getByRole("button", { name: "Guardar aporte manual" }).click();

    await expect(page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ })).toContainText(
      MANUAL.date,
    );
    await waitForDocumentPersisted(page);
    const stored = JSON.parse(await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY));
    const manualNode = stored.document.sections[0].content.content.find((node) => node.type === "manualEntry");
    expect(manualNode.attrs.date).toBe(MANUAL.date);
  });

  test("cancelar y Escape no cambian el documento y restauran el foco", async ({ page }) => {
    await page.goto(APP_URL);
    const trigger = page.getByRole("button", { name: "Agregar dato manual" });
    await trigger.click();
    await expect(page.getByRole("dialog", { name: "Agregar dato manual" })).toBeVisible();
    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByRole("dialog", { name: "Agregar dato manual" })).not.toBeVisible();
    await expect(trigger).toBeFocused();

    const before = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    await trigger.press("Enter");
    await page.getByLabel("Texto o descripción (opcional)").fill(TOKEN);
    await page.locator("#manual-entry-source").fill("Fuente sintética");
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    const after = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(after).toBe(before);
  });

  test("manualEntry y EvidenceCitation coexisten en una sección y no generan red manual", async ({ page }) => {
    await mockBackend(page);
    const agentRequests = [];
    page.on("request", (request) => {
      if (request.url().includes("/v2/agent")) agentRequests.push(request.url());
    });
    await page.goto(APP_URL);

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type(SECTION_TEXT);
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    const dialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
    await dialog.getByLabel("Pregunta para investigar").fill(QUESTION);
    await dialog.getByRole("button", { name: "Investigar con este contexto" }).click();
    await page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" }).getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    const confirmation = page.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
    if (await confirmation.isVisible().catch(() => false)) {
      await confirmation.getByRole("button", { name: "Insertar con advertencia" }).click();
    }
    await expect(page.locator('[data-evidence-citation="true"]')).toBeVisible();

    agentRequests.length = 0;
    await page.getByRole("button", { name: "Agregar dato manual" }).click();
    await page.getByLabel("Valor (opcional)").fill("Dato sintético junto a evidencia");
    await page.locator("#manual-entry-source").fill("Fuente humana sintética");
    await page.getByRole("button", { name: "Guardar aporte manual" }).click();
    const section = page.getByRole("region", { name: "Sección 1" });
    const evidenceNode = section.locator('[data-evidence-citation="true"]');
    const manualNode = section.getByRole("group", { name: /Aporte manual — no verificado por el agente/ });
    await expect(evidenceNode).toBeVisible();
    await expect(evidenceNode).toContainText("Cita de evidencia");
    await expect(evidenceNode).toContainText("Calidad alta");
    await expect(manualNode).toBeVisible();
    await expect(manualNode).toContainText("Aporte manual — no verificado por el agente");
    await expect(manualNode).not.toContainText(/Verificado|calidad|claims|SoQL/);
    await page.setViewportSize({ width: 1440, height: 900 });
    const closeCopilot = page.getByRole("button", { name: "Cerrar copiloto" });
    if (await closeCopilot.isVisible().catch(() => false)) await closeCopilot.click();
    await page.screenshot({
      path: path.resolve(process.cwd(), "../docs/frontend-v2/design/f7-02a/screenshots/manual-vs-evidence-1440.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 320, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(
      true,
    );
    await expect(page.getByRole("dialog", { name: "Investigación en curso" })).not.toBeVisible();
    await page.screenshot({
      path: path.resolve(process.cwd(), "../docs/frontend-v2/design/f7-02a/screenshots/manual-vs-evidence-320.png"),
      fullPage: true,
    });
    expect(agentRequests).toEqual([]);
    await waitForDocumentPersisted(page);
    const stored = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(stored).toContain(CITATION.dataset_id);
    expect(stored).toContain("Dato sintético junto a evidencia");
  });

  test("token visible solo durante la escritura y rechazado sin persistencia", async ({ page }) => {
    const requests = [];
    page.on("request", (request) => requests.push(request.url()));
    await page.goto(APP_URL);
    await page.getByRole("button", { name: "Agregar dato manual" }).click();
    await page.getByLabel("Texto o descripción (opcional)").fill(TOKEN);
    await page.locator("#manual-entry-source").fill("Fuente sintética");
    await page.getByRole("button", { name: "Guardar aporte manual" }).click();
    await expect(page.getByText("No pudimos guardar el aporte porque contiene información sensible.")).toBeVisible();
    await expect(page.getByLabel("Texto o descripción (opcional)")).toHaveValue(TOKEN);
    await expect(
      page.getByText("No pudimos guardar el aporte porque contiene información sensible.", { exact: true }),
    ).not.toContainText(TOKEN);
    const stored = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(stored ?? "").not.toContain(TOKEN);
    expect(requests.filter((url) => url.includes("/v2/agent"))).toEqual([]);
  });
});
