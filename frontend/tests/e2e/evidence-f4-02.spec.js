import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

/**
 * F4-02 — presentación funcional de evidencia en `/app`, con el ÚNICO
 * fixture real de `completed` con `claims[]`/`label_status="verified"`
 * disponible (`tests/fixtures/completed-with-claims.json`, ver su README:
 * captura real desde PostgreSQL, caso `pilot-041-eca`). Nunca se fabrica
 * `presentation_warnings` para estas capturas — ese campo es siempre `[]`
 * en este fixture, como en toda corrida real hasta que T-617C se
 * implemente en el runtime.
 */

const fixture = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../fixtures/completed-with-claims.json"), "utf8")
);

const APP_URL = "/app";
const RUN_ID = fixture.run_id;
const TOKEN = "cdt_rt_e2e_evidence_token_no_debe_aparecer_nunca";
const QUESTION = fixture.answer.intention.topic;

function sseBody() {
  const stepEvent = [
    "id: 0",
    "event: step",
    `data: ${JSON.stringify({
      step_number: 1,
      node: "execute_query",
      display_message: "Consultando datos.gov.co…",
      detail: null,
    })}`,
    "",
    "",
  ].join("\n");
  const answerEvent = ["id: 1", "event: answer", `data: ${JSON.stringify(fixture.answer)}`, "", ""].join("\n");
  return stepEvent + answerEvent;
}

async function mockBackend(page) {
  await page.route("**/v2/agent/query", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        run_access_token: TOKEN,
        token_expires_at: new Date(Date.now() + 3600_000).toISOString(),
        stream_url: `/v2/agent/stream/${RUN_ID}`,
      }),
    });
  });

  await page.route(`**/v2/agent/stream/${RUN_ID}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: sseBody() });
  });

  await page.route(`**/v2/agent/runs/${RUN_ID}`, async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) });
  });
}

function main(page) {
  return page.locator("#contenido");
}

async function submitAndWaitForEvidence(page) {
  await mockBackend(page);
  await page.goto(APP_URL);
  await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
  await main(page).getByLabel("Pregunta para investigar").fill(QUESTION);
  await main(page).getByRole("button", { name: "Investigar", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
  await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });
  // Buscado sobre `page`, no acotado a `#contenido`: bajo 1024px
  // `CopilotPanel` renderiza el contenido dentro de `Modal`, que hace
  // `createPortal` a `document.body` — fuera del landmark `#contenido`.
  const card = page.getByRole("region", { name: /Evidencia:/ });
  await expect(card).toBeVisible();
  return card;
}

test.describe("/app — EvidenceCard con fixture real (F4-02)", () => {
  test("investigación completed muestra su EvidenceCard con encabezados resueltos, sin dim_N/metric_N, y el valor crudo sin reformatear", async ({
    page,
  }) => {
    const card = await submitAndWaitForEvidence(page);

    const headers = await card.getByRole("columnheader").allTextContents();
    expect(headers.length).toBeGreaterThan(0);
    for (const header of headers) {
      expect(header).not.toMatch(/^\s*dim_\d+/);
      expect(header).not.toMatch(/^\s*metric_\d+/);
    }

    // Valor crudo de fila (`dim_4` en el fixture): se conserva EXACTO, sin
    // separadores de miles ni ningún otro reformateo del cliente.
    await expect(card.getByRole("cell", { name: "2368705607", exact: true })).toBeVisible();
  });

  test("descarga CSV con BOM UTF-8, filas y bloque de cita", async ({ page }) => {
    const card = await submitAndWaitForEvidence(page);

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      card.getByRole("button", { name: "Descargar CSV" }).click(),
    ]);
    const csvPath = await download.path();
    const buffer = fs.readFileSync(csvPath);
    // BOM UTF-8: EF BB BF.
    expect(buffer.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf]))).toBe(true);

    const text = buffer.toString("utf8");
    expect(text).toContain("2368705607");
    expect(text).toContain("Consulta SoQL");
    expect(text).toContain(fixture.answer.evidence[0].dataset_name);
  });

  test("copiar cita informa éxito en español", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const card = await submitAndWaitForEvidence(page);

    await card.getByRole("button", { name: "Copiar cita" }).click();
    await expect(card.getByText("Cita copiada.")).toBeVisible();
  });

  test("navegación por teclado alcanza las acciones de la tarjeta de evidencia", async ({ page }) => {
    const card = await submitAndWaitForEvidence(page);

    const downloadButton = card.getByRole("button", { name: "Descargar CSV" });
    await downloadButton.focus();
    await expect(downloadButton).toBeFocused();

    await page.keyboard.press("Tab");
    await expect(card.getByRole("button", { name: "Copiar cita" })).toBeFocused();
  });

  test("axe sin violaciones críticas con la EvidenceCard visible", async ({ page }) => {
    await submitAndWaitForEvidence(page);

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("320px: sin overflow horizontal de página con la EvidenceCard visible", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await submitAndWaitForEvidence(page);

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });
});
