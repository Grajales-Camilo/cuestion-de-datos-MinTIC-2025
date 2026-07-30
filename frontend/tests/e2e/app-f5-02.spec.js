import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

const APP_URL = "/app";
const REAL_STREAM = readFileSync(
  path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt"),
  "utf8",
);
const TOKEN = "cdt_rt_f5_02_e2e_no_debe_aparecer";

function answerFromStream(stream) {
  const block = stream
    .split(/\r?\n\r?\n/)
    .find((candidate) => candidate.includes("event: answer"));
  const dataLine = block?.split(/\r?\n/).find((line) => line.startsWith("data: "));
  if (!dataLine) throw new Error("El fixture real no contiene evento answer");
  return JSON.parse(dataLine.slice(6));
}

function streamWithAnswer(stream, answer) {
  return stream
    .split(/(\r?\n\r?\n)/)
    .map((block) => {
      if (!block.includes("event: answer")) return block;
      return block
        .split(/\r?\n/)
        .map((line) => (line.startsWith("data: ") ? `data: ${JSON.stringify(answer)}` : line))
        .join("\n");
    })
    .join("");
}

const REAL_ANSWER = answerFromStream(REAL_STREAM);

// Doble sintético INLINE exclusivo de RF-404. No se guarda en fixtures y
// deriva del payload real únicamente para ejercer la clasificación que aún
// no tiene una corrida capturada adecuada.
function notRecommendedSyntheticScenario() {
  const answer = structuredClone(REAL_ANSWER);
  answer.run_id = "run-sintetico-inline-rf404";
  const evidence = answer.evidence[0];
  evidence.evidence_id = "evidence-sintetica-inline-rf404";
  evidence.dataset_name = "Doble sintético inline RF-404 — no es fixture real";
  evidence.citation.dataset_name = evidence.dataset_name;
  evidence.quality.classification = "no_recomendada";
  evidence.quality.score_total = 42;
  evidence.quality.warnings_user = [
    "La actualización disponible requiere cautela antes de citar esta evidencia.",
  ];
  answer.claims = answer.claims.map((claim) => ({
    ...claim,
    evidence_id: evidence.evidence_id,
  }));
  return { answer, stream: streamWithAnswer(REAL_STREAM, answer) };
}

async function mockBackend(page, { stream = REAL_STREAM, token = TOKEN } = {}) {
  const answer = answerFromStream(stream);
  const requestUrls = [];
  page.on("request", (request) => requestUrls.push(request.url()));

  await page.route("**/v2/agent/query", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: answer.run_id,
        run_access_token: token,
        token_expires_at: "2026-07-28T23:59:59Z",
        stream_url: `/v2/agent/stream/${answer.run_id}`,
      }),
    });
  });
  await page.route(`**/v2/agent/stream/${answer.run_id}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "text/event-stream", body: stream });
  });
  await page.route(`**/v2/agent/runs/${answer.run_id}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: answer.run_id, status: "completed", answer }),
    });
  });
  return { answer, requestUrls };
}

async function completeRun(page, { stream = REAL_STREAM } = {}) {
  const mocked = await mockBackend(page, { stream });
  await page.goto(APP_URL);
  await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript
  await page.getByLabel("Pregunta para investigar").fill(
    "¿Cuál fue el promedio de deserción escolar en Antioquia entre 2018 y 2022?",
  );
  await page.getByRole("button", { name: "Investigar", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })
    .getByRole("button", { name: "Aceptar e investigar" })
    .click();
  await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
    timeout: 15_000,
  });
  return mocked;
}

async function insertRealEvidence(page) {
  await page.getByRole("button", { name: "Insertar en el documento" }).click();
  return page.getByRole("group", { name: /Cita de evidencia:/ });
}

async function tabUntil(page, predicate, description, limit = 80) {
  for (let index = 0; index < limit; index += 1) {
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => {
      const element = document.activeElement;
      return {
        label: element?.getAttribute?.("aria-label") ?? "",
        role: element?.getAttribute?.("role") ?? element?.tagName?.toLowerCase() ?? "",
        text: element?.textContent?.trim() ?? "",
      };
    });
    if (predicate(active)) return active;
  }
  throw new Error(`No se encontró mediante Tab: ${description}`);
}

test.describe("/app — F5-02 editor, cita y RF-404", () => {
  test("fixture real: corrida → EvidenceCard → comando Tiptap → NodeView", async ({ page }) => {
    const { answer } = await completeRun(page);
    const citation = await insertRealEvidence(page);

    await expect(citation).toBeVisible();
    await expect(citation).toContainText(answer.evidence[0].dataset_name);
    await expect(citation).toContainText("Desercion: 3,9660000000000000");
    await expect(citation.getByRole("link", { name: /Abrir fuente/ })).toHaveAttribute(
      "href",
      answer.evidence[0].source_url,
    );
  });

  test("navegación principal exclusivamente por teclado devuelve foco al editor", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page); // RF-101-02-R1: storage vacío, sin addInitScript

    await tabUntil(
      page,
      (active) => active.role === "textarea",
      "campo de pregunta",
    );
    const questionInput = page.getByLabel("Pregunta para investigar");
    const keyboardQuestion = "Promedio de desercion escolar en Antioquia entre 2018 y 2022";
    // El contenido se establece después de alcanzar el campo con Tab; desde
    // ese punto, toda la navegación y activación se hace exclusivamente con
    // teclado. `fill` evita depender del mapa de teclado del SO del runner.
    await questionInput.fill(keyboardQuestion);
    await expect(questionInput).toHaveValue(keyboardQuestion);
    await expect(page.getByText(`${keyboardQuestion.length}/2000 caracteres (mínimo 10)`)).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Investigar", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" }),
    ).toBeVisible();
    await tabUntil(
      page,
      (active) => active.text === "Aceptar e investigar",
      "aceptar consentimiento",
    );
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
      timeout: 15_000,
    });
    await tabUntil(
      page,
      (active) => active.text.includes("Insertar en el documento"),
      "insertar evidencia",
    );
    await page.keyboard.press("Enter");

    await expect(page.getByRole("group", { name: /Cita de evidencia:/ })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toBeFocused();
  });

  test("axe WCAG 2.2 AA y ausencia de token tras insertar", async ({ page }) => {
    const consoleMessages = [];
    page.on("console", (message) => consoleMessages.push(message.text()));
    const { requestUrls } = await completeRun(page);
    await insertRealEvidence(page);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag22aa"])
      .analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);

    const html = await page.content();
    const documentJson = await page
      .getByRole("textbox", { name: "Documento de trabajo: Sección 1" })
      .evaluate((element) => element.pmViewDesc?.node?.toJSON?.() ?? null);
    expect(documentJson).not.toBeNull();
    expect(JSON.stringify(documentJson)).not.toContain(TOKEN);
    expect(html).not.toContain(TOKEN);
    expect(consoleMessages.join("\n")).not.toContain(TOKEN);
    expect(requestUrls.some((url) => url.includes(TOKEN))).toBe(false);
  });

  test("320 px refluye sin overflow y conserva la cita", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    await completeRun(page);
    await insertRealEvidence(page);
    const citation = page.getByRole("group", { name: /Cita de evidencia:/ });
    await expect(citation).toBeVisible();

    const overflow = await page.evaluate(() => ({
      body: document.body.scrollWidth > document.body.clientWidth,
      html: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    expect(overflow).toEqual({ body: false, html: false });
  });

  test("RF-404 sintético inline: cancelar no inserta y confirmar deja advertencia permanente", async ({ page }) => {
    const synthetic = notRecommendedSyntheticScenario();
    await completeRun(page, { stream: synthetic.stream });

    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    const dialog = page.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("group", { name: /Cita de evidencia:/ })).toHaveCount(0);

    await dialog.getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByRole("group", { name: /Cita de evidencia:/ })).toHaveCount(0);

    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    await page
      .getByRole("dialog", { name: "Insertar evidencia no recomendada" })
      .getByRole("button", { name: "Insertar con advertencia" })
      .click();
    const citation = page.getByRole("group", { name: /Cita de evidencia:/ });
    await expect(citation).toContainText("Evidencia no recomendada: úsala con cautela.");
  });

  test("capturas finales representativas con datos del fixture real", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await completeRun(page);
    await insertRealEvidence(page);
    await page.screenshot({ path: "test-results/f5-02-desktop-1440.png", fullPage: true });

    await page.setViewportSize({ width: 320, height: 800 });
    await page.reload();
    await page.evaluate(() => {
      window.localStorage.clear();
      window.sessionStorage.clear();
    });
    await completeRun(page);
    await insertRealEvidence(page);
    await page.screenshot({ path: "test-results/f5-02-mobile-320.png", fullPage: true });
  });
});
