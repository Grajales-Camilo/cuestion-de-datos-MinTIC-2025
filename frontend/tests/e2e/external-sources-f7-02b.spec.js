import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import JSZip from "jszip";
import path from "node:path";
import { readFileSync } from "node:fs";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

const APP_URL = "http://localhost:3101/app";
const DOC_KEY = "cdd.doc.v1";
const RUN_ID = "f702b000-0000-4000-8000-000000000001";
const QUESTION = "¿Dónde puedo consultar un indicador territorial sintético?";
const SECTION_TEXT = "Contexto sintético inline de la sección de origen.";
const USER_VALUE = "17,50 unidades sintéticas confirmadas por el usuario";
const SENSITIVE = "cdt_rt_external_source_sintetico_no_visible";
const SUGGESTION = Object.freeze({
  entidad: "Entidad oficial sintética de prueba",
  url: "https://datos.example.gov.co/catalogo/indicador-sintetico",
  por_que: "Puede contener el indicador territorial solicitado por el usuario.",
});

function noEvidenceAnswer(externalSources) {
  return {
    status: "no_evidence",
    intention: { topic: "indicador territorial sintético" },
    evidence: [],
    claims: [],
    presentation_warnings: [],
    textual_facts: [],
    no_evidence_report: {
      reason: "No se encontró evidencia elegible en el catálogo consultado.",
      datasets_reviewed: [],
      external_sources: externalSources,
    },
    usage: null,
  };
}

function sseBody(answer) {
  const step = [
    "id: 1",
    "event: step",
    `data: ${JSON.stringify({ step_number: 1, node: "abstain", display_message: "Revisando cobertura del catálogo…", detail: null })}`,
    "",
    "",
  ].join("\n");
  const terminal = ["id: 2", "event: answer", `data: ${JSON.stringify(answer)}`, "", ""].join("\n");
  return step + terminal;
}

async function mockNoEvidenceBackend(page, externalSources) {
  await page.route("**/v2/agent/query", (route) =>
    route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        run_access_token: "transport-token-f7-02b",
        token_expires_at: "2026-07-30T23:59:59Z",
        stream_url: `/v2/agent/stream/${RUN_ID}`,
      }),
    }),
  );
  const answer = noEvidenceAnswer(externalSources);
  await page.route(`**/v2/agent/stream/${RUN_ID}`, (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: sseBody(answer) }),
  );
  await page.route(`**/v2/agent/runs/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: RUN_ID, status: "no_evidence", answer }),
    }),
  );
}

async function startSectionInvestigation(page) {
  const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
  await editor.click();
  await page.keyboard.type(SECTION_TEXT);
  await page.getByRole("button", { name: "Investigar esta sección" }).click();
  const investigateDialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
  await investigateDialog.getByLabel("Pregunta para investigar").fill(QUESTION);
  await investigateDialog.getByRole("button", { name: "Investigar con este contexto" }).click();
  const consent = page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" });
  await consent.getByRole("button", { name: "Aceptar e investigar" }).click();
  await expect(page.getByText("No se encontró evidencia elegible para responder esta pregunta.")).toBeVisible({ timeout: 15_000 });
}

async function tabUntil(page, predicate, description, limit = 100) {
  for (let index = 0; index < limit; index += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => ({
      text: document.activeElement?.textContent?.trim() ?? "",
      label: document.activeElement?.getAttribute("aria-label") ?? "",
    }));
    if (predicate(active)) return;
  }
  throw new Error(`No se encontró mediante Tab: ${description}`);
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

test.describe("F7-02B — external_sources a aporte manual", () => {
  test("prellenado seguro, teclado, sección de origen, persistencia, DOCX y cero red adicional", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockNoEvidenceBackend(page, [
      SUGGESTION,
      { ...SUGGESTION, entidad: "Fuente sensible omitida", metadata: SENSITIVE },
    ]);
    const agentRequests = [];
    const consoleMessages = [];
    page.on("request", (request) => {
      if (request.url().includes("/v2/agent")) agentRequests.push(`${request.method()} ${request.url()}`);
    });
    page.on("console", (message) => consoleMessages.push(message.text()));

    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
    await startSectionInvestigation(page);
    await expect(page.getByRole("heading", { name: "Fuentes oficiales sugeridas" })).toBeVisible();
    expect(await page.getByRole("button", { name: "Agregar manualmente" }).count()).toBe(1);
    await expect(page.getByText(SUGGESTION.entidad)).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Fuentes oficiales sugeridas" }).getByText(SUGGESTION.por_que),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: `Abrir ${SUGGESTION.entidad}` })).toHaveAttribute("href", SUGGESTION.url);
    await expect(page.getByText("Fuente sensible omitida")).not.toBeVisible();
    const requestsBeforeManualFlow = agentRequests.length;

    await tabUntil(page, (active) => active.text === "Agregar manualmente", "Agregar manualmente");
    const suggestionTrigger = page.getByRole("button", { name: "Agregar manualmente" });
    await page.keyboard.press("Enter");
    const manualDialog = page.getByRole("dialog", { name: "Agregar dato manual" });
    await expect(manualDialog).toBeVisible();
    await expect(page.getByLabel("Valor (opcional)")).toBeFocused();
    await expect(page.getByRole("textbox", { name: "Fuente", exact: true })).toHaveValue(SUGGESTION.entidad);
    await expect(page.getByLabel("URL de la fuente (opcional)")).toHaveValue(SUGGESTION.url);
    await expect(page.getByLabel("Texto o descripción (opcional)")).toHaveValue("");
    await expect(page.getByLabel("Fecha de la fuente (opcional)")).toHaveValue("");
    await expect(manualDialog.getByText(SUGGESTION.por_que)).toBeVisible();
    await page.screenshot({
      path: path.resolve(process.cwd(), "../docs/frontend-v2/design/f7-02b/screenshots/external-source-prefill-1440.png"),
      fullPage: true,
    });

    await page.keyboard.press("Escape");
    await expect(manualDialog).not.toBeVisible();
    await expect(suggestionTrigger).toBeFocused();

    await page.setViewportSize({ width: 320, height: 900 });
    await expect(page.getByRole("dialog", { name: "Investigación en curso" })).toBeVisible();
    await tabUntil(page, (active) => active.text === "Agregar manualmente", "Agregar manualmente móvil");
    await page.keyboard.press("Enter");
    await expect(manualDialog).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Investigación en curso" })).not.toBeVisible();
    await expect(page.getByRole("textbox", { name: "Fuente", exact: true })).toHaveValue(SUGGESTION.entidad);
    await expect(page.getByLabel("URL de la fuente (opcional)")).toHaveValue(SUGGESTION.url);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    const axeResults = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(axeResults.violations).toEqual([]);
    await page.screenshot({
      path: path.resolve(process.cwd(), "../docs/frontend-v2/design/f7-02b/screenshots/external-source-prefill-320.png"),
      fullPage: true,
    });

    await expect(page.getByLabel("Valor (opcional)")).toBeFocused();
    await page.keyboard.type(USER_VALUE);
    await tabUntil(page, (active) => active.text === "Guardar aporte manual", "Guardar aporte manual");
    await page.keyboard.press("Enter");
    await expect(manualDialog).not.toBeVisible();
    await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toBeFocused();
    const manualNode = page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ });
    await expect(manualNode).toContainText(USER_VALUE);
    await expect(manualNode).toContainText(SUGGESTION.entidad);
    await expect(manualNode).not.toContainText(SUGGESTION.por_que);

    await page.waitForFunction(
      ({ key, value }) => window.localStorage.getItem(key)?.includes(value),
      { key: DOC_KEY, value: USER_VALUE },
      { timeout: 10_000 },
    );
    const stored = JSON.parse(await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY));
    const attrs = stored.document.sections[0].content.content.find((node) => node.type === "manualEntry").attrs;
    expect(attrs.value).toBe(USER_VALUE);
    expect(attrs.text).toBeNull();
    expect(attrs.source).toBe(SUGGESTION.entidad);
    expect(attrs.url).toBe(SUGGESTION.url);
    expect(attrs.date).toBeNull();
    expect(JSON.stringify(stored)).not.toContain(SUGGESTION.por_que);
    expect(JSON.stringify(stored)).not.toContain("external_sources");
    expect(agentRequests).toHaveLength(requestsBeforeManualFlow);

    await page.reload();
    await expect(page.getByRole("group", { name: /Aporte manual — no verificado por el agente/ })).toContainText(USER_VALUE);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Exportar en Word (.docx)" }).click();
    const { documentXml, footnotesXml } = await readDocx(await downloadPromise, testInfo);
    expect(documentXml).toContain("Aporte manual — no verificado por el agente");
    expect(documentXml).toContain(USER_VALUE);
    expect(documentXml).not.toContain("Verificado");
    expect(footnotesXml).toContain(SUGGESTION.entidad);
    expect(footnotesXml).toContain(SUGGESTION.url);
    expect(footnotesXml).not.toContain(SUGGESTION.por_que);
    expect(agentRequests).toHaveLength(requestsBeforeManualFlow);

    const browserValues = await page.evaluate(() => ({
      local: Object.values(localStorage),
      session: Object.values(sessionStorage),
      body: document.body.textContent,
      url: location.href,
    }));
    expect(JSON.stringify(browserValues)).not.toContain(SENSITIVE);
    expect(consoleMessages.join("\n")).not.toContain(SENSITIVE);
    expect(documentXml).not.toContain(SENSITIVE);
    expect(footnotesXml).not.toContain(SENSITIVE);
  });

  test("external_sources vacío no muestra bloque ni acción", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockNoEvidenceBackend(page, []);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
    await startSectionInvestigation(page);
    await expect(page.getByRole("heading", { name: "Fuentes oficiales sugeridas" })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Agregar manualmente" })).not.toBeVisible();
  });
});
