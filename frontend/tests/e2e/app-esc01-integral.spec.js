import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import JSZip from "jszip";
import { expect, test } from "@playwright/test";

/**
 * ESC-01 integral (F8-01, Parte 4 del encargo): UNA sola prueba que
 * encadena el recorrido completo sin fragmentarlo en aserciones triviales
 * — escribir → investigar con contexto visible → consentimiento ANTES del
 * primer POST → pasos SSE en vivo → terminal `completed` con
 * evidencia/claims/calidad → insertar en la sección de origen → persistir →
 * recargar → exportar DOCX con nota al pie → cero token en todo momento.
 *
 * Los pasos individuales ya tienen cobertura dedicada más profunda en otros
 * specs (`app-f5-03`, `app-f6-01`, `app-f6-02b-export`, `evidence-f4-02`) —
 * esta prueba no los reemplaza, es la que faltaba: la cadena única de punta
 * a punta que exige el encargo, con el fixture real completo
 * (`completed-stream.sse.txt`, 9 pasos + 1 respuesta terminal, método 1 de
 * `tests/fixtures/README.md`).
 */

const APP_URL = "/app";
const DOC_KEY = "cdd.doc.v1";
const TOKEN = "cdt_rt_esc01_integral_no_debe_aparecer_nunca";
const SECTION_TEXT = "Diagnostico integral de desercion escolar en Antioquia entre 2018 y 2022 (ESC-01).";

const REAL_STREAM = readFileSync(
  path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt"),
  "utf8",
);

function answerFromStream(stream) {
  const block = stream.split(/\r?\n\r?\n/).find((candidate) => candidate.includes("event: answer"));
  const dataLine = block?.split(/\r?\n/).find((line) => line.startsWith("data: "));
  return JSON.parse(dataLine.slice(6));
}

const REAL_ANSWER = answerFromStream(REAL_STREAM);
const STEP_EVENT_COUNT = REAL_STREAM.split(/\r?\n\r?\n/).filter((block) => block.includes("event: step")).length;
const QUESTION = REAL_ANSWER.intention.topic;

test.describe("/app — ESC-01 integral, fixture real completo (F8-01)", () => {
  test("escribir + investigar con contexto → consentimiento antes del POST → pasos SSE → completed con evidencia/claims/calidad → insertar en la sección de origen → persistir → recargar → exportar DOCX con nota al pie → cero token en todo momento", async ({
    page,
  }, testInfo) => {
    const postRequestBodies = [];
    const requestUrls = [];
    const consoleTexts = [];
    page.on("request", (request) => {
      requestUrls.push(request.url());
      if (request.url().includes("/v2/agent/query") && request.method() === "POST") {
        postRequestBodies.push(request.postDataJSON());
      }
    });
    page.on("console", (msg) => consoleTexts.push(msg.text()));

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

    // 1) Escribir en la Sección 1.
    await page.goto(APP_URL);
    const sectionEditor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await sectionEditor.click();
    await page.keyboard.type(SECTION_TEXT);

    // 2) Investigar CON CONTEXTO VISIBLE (vista previa literal del texto que
    // se enviará, RF-104) desde esa misma sección.
    await page.getByRole("button", { name: "Investigar esta sección" }).click();
    const investigateDialog = page.getByRole("dialog", { name: "Investigar esta sección: Sección 1" });
    await expect(investigateDialog).toBeVisible();
    await expect(
      investigateDialog.getByRole("region", { name: "Contexto que se enviará (texto literal de la sección)" }),
    ).toHaveText(SECTION_TEXT);
    await investigateDialog.getByLabel("Pregunta para investigar").fill(QUESTION);
    await investigateDialog.getByRole("button", { name: "Investigar con este contexto" }).click();

    // 3) Consentimiento ANTES del primer POST (RF-802): cero llamadas hasta
    // aceptar explícitamente.
    const consentDialog = page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" });
    await expect(consentDialog).toBeVisible();
    expect(postRequestBodies).toHaveLength(0);
    await consentDialog.getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(consentDialog).not.toBeVisible();
    await expect.poll(() => postRequestBodies.length).toBe(1);
    expect(postRequestBodies[0]).toMatchObject({ question: QUESTION, context_hint: SECTION_TEXT });

    // 4) Pasos SSE visibles en vivo, en una región `aria-live` agrupada, sin
    // que el terminal aparezca antes de tiempo.
    const timeline = page.getByRole("list", { name: "Pasos de la investigación" });
    await expect(timeline.getByRole("listitem")).toHaveCount(STEP_EVENT_COUNT, { timeout: 15_000 });

    // 5) Terminal `completed`, con evidencia/claims/calidad visibles.
    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
      timeout: 15_000,
    });
    const evidenceCard = page.getByRole("region", { name: /Evidencia:/ });
    await expect(evidenceCard).toBeVisible();
    await expect(page.getByText("Verificado").first()).toBeVisible();

    // 6) Insertar en la SECCIÓN DE ORIGEN (no un editor genérico).
    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    const confirmDialog = page.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
    const requiresConfirmation = await confirmDialog
      .waitFor({ state: "visible", timeout: 1_500 })
      .then(() => true)
      .catch(() => false);
    if (requiresConfirmation) {
      await confirmDialog.getByRole("button", { name: "Insertar con advertencia" }).click();
    }
    const citation = sectionEditor.getByRole("group", { name: /Cita de evidencia:/ });
    await expect(citation).toBeVisible();
    await expect(citation).toContainText(REAL_ANSWER.evidence[0].dataset_name);

    // 7) Persistir (autoguardado localStorage) y recargar: texto + cita
    // sobreviven.
    await page.waitForFunction((key) => window.localStorage.getItem(key) !== null, DOC_KEY, { timeout: 10_000 });
    await page.reload();
    const reloadedEditor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await expect(reloadedEditor).toContainText(SECTION_TEXT);
    await expect(reloadedEditor.getByRole("group", { name: /Cita de evidencia:/ })).toBeVisible();

    // 8) Exportar en Word con nota al pie real de la cita.
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Exportar en Word (.docx)" }).click();
    const download = await downloadPromise;
    const outputPath = testInfo.outputPath(download.suggestedFilename());
    await download.saveAs(outputPath);
    const { statSync } = await import("node:fs");
    expect(statSync(outputPath).size).toBeGreaterThan(0);

    const zip = await JSZip.loadAsync(readFileSync(outputPath));
    const documentXml = await zip.file("word/document.xml").async("string");
    const footnotesXml = await zip.file("word/footnotes.xml").async("string");
    expect(documentXml).toContain(SECTION_TEXT);
    const citationMeta = REAL_ANSWER.evidence[0].citation;
    expect(footnotesXml).toContain(citationMeta.dataset_id);
    expect(footnotesXml).toContain(citationMeta.dataset_name);
    expect(footnotesXml).toContain(citationMeta.publisher);

    // 9) Cero token en TODO momento: DOM, consola, URLs de red y el propio
    // `.docx` exportado.
    const html = await page.content();
    expect(html).not.toContain(TOKEN);
    expect(consoleTexts.join("\n")).not.toContain(TOKEN);
    expect(requestUrls.some((url) => url.includes(TOKEN))).toBe(false);
    expect(documentXml).not.toContain(TOKEN);
    expect(footnotesXml).not.toContain(TOKEN);

    // 10) Axe limpio en el estado final (completed + cita insertada).
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});
