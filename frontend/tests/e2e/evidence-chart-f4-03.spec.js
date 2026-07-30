import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

/**
 * F4-03 — RF-503, escenario de gráfica. El único fixture real disponible
 * (`completed-with-claims.json`) tiene 8 dimensiones y 0 métricas, así que
 * NUNCA activa `EvidenceChart` (confirmado en `chartSpec.test.js` y
 * `components.test.jsx`). Este spec usa un doble sintético construido
 * INLINE — nunca guardado en `tests/fixtures/`, nunca presentado como
 * captura real — con exactamente 1 dimensión + 1 métrica + 3 filas
 * (fallback D-4), solo para probar el reflujo a 320px y accesibilidad con
 * la gráfica realmente visible.
 */

const APP_URL = "/app";
const RUN_ID = "run-e2e-chart-synthetic-0001";
const TOKEN = "cdt_rt_e2e_chart_token_no_debe_aparecer_nunca";
const QUESTION = "¿Cuál es la suma de valor por municipio en el conjunto sintético de prueba?";

const SYNTHETIC_CHARTABLE_ANSWER = {
  run_id: RUN_ID,
  status: "completed",
  intention: { topic: QUESTION },
  summary: "Suma de valor por municipio (doble sintético de prueba, F4-03).",
  narrative: null,
  evidence: [
    {
      evidence_id: "ev-synthetic-chart-0001",
      dataset_id: "synthetic-0001",
      dataset_name: "Dataset sintético de prueba (F4-03)",
      publisher: "Publicador sintético",
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1 GROUP BY municipio",
      executed_at: "2026-07-28T12:00:00Z",
      source_url: "https://www.datos.gov.co/resource/synthetic0001.json",
      data_updated_at: "2026-07-01T00:00:00Z",
      data_cutoff_at: "2026-07-01T00:00:00Z",
      data_cutoff_basis: "data_cutoff_at",
      columns: ["dim_1", "metric_sum_1"],
      rows: [
        { dim_1: "Sonsón", metric_sum_1: 12.5 },
        { dim_1: "Rionegro", metric_sum_1: 30 },
        { dim_1: "Marinilla", metric_sum_1: 7 },
      ],
      row_count: 3,
      narrative: null,
      chart_suggestion: null,
      quality: {
        eligibility_status: "eligible",
        eligibility_reasons: [],
        score_total: 80,
        classification: "alta",
        warnings_user: [],
        dimensions: {},
      },
    },
  ],
  claims: [],
  no_evidence_report: null,
  textual_facts: [],
  partial_textual_facts: [],
  presentation_warnings: [],
  usage: { steps_used: 1 },
};

function sseBody() {
  const stepEvent = [
    "id: 0",
    "event: step",
    `data: ${JSON.stringify({ step_number: 1, node: "execute_query", display_message: "Consultando datos.gov.co…", detail: null })}`,
    "",
    "",
  ].join("\n");
  const answerEvent = ["id: 1", "event: answer", `data: ${JSON.stringify(SYNTHETIC_CHARTABLE_ANSWER)}`, "", ""].join(
    "\n"
  );
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
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: RUN_ID, status: "completed", answer: SYNTHETIC_CHARTABLE_ANSWER }),
    });
  });
}

function main(page) {
  return page.locator("#contenido");
}

async function submitAndWaitForChart(page) {
  await mockBackend(page);
  await page.goto(APP_URL);
  await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
  await main(page).getByLabel("Pregunta para investigar").fill(QUESTION);
  await main(page).getByRole("button", { name: "Investigar", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
  await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });
  const chart = page.getByRole("img", { name: /Suma de Valor/ });
  await expect(chart).toBeVisible();
  return chart;
}

test.describe("/app — EvidenceChart con doble sintético (F4-03, RF-503)", () => {
  test("la gráfica aparece con nombre accesible y la tabla sigue disponible como alternativa textual", async ({
    page,
  }) => {
    const chart = await submitAndWaitForChart(page);
    await expect(chart).toHaveAccessibleName(/Dataset sintético de prueba/);
    await expect(page.getByRole("columnheader", { name: "Municipio" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Sonsón" })).toBeVisible();
  });

  test("320px: sin overflow horizontal de página con la gráfica visible", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await submitAndWaitForChart(page);

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });

  test("axe sin violaciones críticas con la gráfica visible", async ({ page }) => {
    await submitAndWaitForChart(page);

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});
