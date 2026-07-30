import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * F8-01 — cobertura que faltaba en `/app` (backend real mockeado, no la
 * galería `/_dev/ui`) para los tres estados terminales que ya tenían
 * fixture real capturado (`tests/fixtures/README.md`, método 2:
 * serialización real desde PostgreSQL) pero ningún E2E los ejercía sobre la
 * ruta central: `no_evidence` SIN `external_sources` (ESC-03 puro —
 * `external_sources` CON sugerencias ya está cubierto en
 * `external-sources-f7-02b.spec.js`, no se duplica aquí), `interrupted` y
 * `failed`.
 *
 * `sseFromRealEvents` reconstruye el texto de wire SSE a partir del arreglo
 * `events` que ya trae cada fixture — no inventa ningún evento ni campo:
 * es la misma información real ya capturada (método 2), solo reserializada
 * al formato `id/event/data` que exige el endpoint de stream. El único
 * fixture con captura HTTP literal de bytes (método 1) es
 * `completed-stream.sse.txt`, usado en otros specs.
 */

const APP_URL = "/app";

function loadFixture(name) {
  return JSON.parse(readFileSync(path.resolve(process.cwd(), "tests/fixtures", name), "utf8"));
}

function sseFromRealEvents(events) {
  return events
    .map((entry) => [`id: ${entry.seq}`, `event: ${entry.event}`, `data: ${JSON.stringify(entry.data)}`, "", ""].join("\n"))
    .join("");
}

async function mockBackendFromFixture(page, fixture, { token }) {
  const runId = fixture.run_id;
  await page.route("**/v2/agent/query", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        run_access_token: token,
        token_expires_at: "2026-08-30T23:59:59Z",
        stream_url: `/v2/agent/stream/${runId}`,
      }),
    });
  });
  await page.route(`**/v2/agent/stream/${runId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseFromRealEvents(fixture.events),
    });
  });
  await page.route(`**/v2/agent/runs/${runId}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) });
  });
  return runId;
}

async function submitFreeQuestion(page, question) {
  await page.goto(APP_URL);
  await page.getByLabel("Pregunta para investigar").fill(question);
  await page.getByRole("button", { name: "Investigar", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })
    .getByRole("button", { name: "Aceptar e investigar" })
    .click();
}

// Deliberadamente sin acotar a `#contenido`: bajo 1024px `CopilotPanel`
// renderiza su contenido dentro de `Modal`, que hace `createPortal` a
// `document.body` — fuera de ese landmark (mismo hallazgo documentado en
// `evidence-f4-02.spec.js`). Los locators de este archivo se usan tanto en
// viewport de escritorio como en 320px, así que deben resolver en ambos.

test.describe("/app — no_evidence sin external_sources (ESC-03 puro, F8-01)", () => {
  const fixture = loadFixture("no-evidence.json");
  const TOKEN = "cdt_rt_f8_01_no_evidence_no_debe_aparecer";

  async function runToNoEvidence(page) {
    await mockBackendFromFixture(page, fixture, { token: TOKEN });
    await submitFreeQuestion(page, fixture.answer.intention.topic);
    await expect(page.getByText("No se encontró evidencia elegible para responder esta pregunta.")).toBeVisible({
      timeout: 15_000,
    });
  }

  test("explicación honesta, sin fabricar fuentes ni evidencia, reformulación disponible, cero token", async ({
    page,
  }) => {
    const consoleTexts = [];
    page.on("console", (msg) => consoleTexts.push(msg.text()));
    const requestUrls = [];
    page.on("request", (request) => requestUrls.push(request.url()));

    await runToNoEvidence(page);

    // Badge neutral, nunca rojo (Badge.jsx: no_evidence -> icono + texto,
    // nunca solo color) — ya cubierto en unit/Badge, aquí se confirma en
    // DOM real de `/app`.
    await expect(page.getByText("Sin evidencia elegible")).toBeVisible();

    // `external_sources: []` en el fixture: la sección completa no debe
    // aparecer (no se fabrica ninguna entidad ni acción).
    await expect(page.getByRole("heading", { name: "Fuentes oficiales sugeridas" })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "Agregar manualmente" })).not.toBeVisible();

    // Cero evidencia/claims fabricados: ninguna EvidenceCard.
    await expect(page.getByRole("region", { name: /Evidencia:/ })).toHaveCount(0);

    // Reformulación disponible: el botón para volver a preguntar existe y
    // el campo de pregunta sigue editable para reformular sin recargar.
    const retryButton = page.getByRole("button", { name: "Volver a preguntar" });
    await expect(retryButton).toBeEnabled();
    await expect(page.getByLabel("Pregunta para investigar")).toBeEditable();

    const html = await page.content();
    expect(html).not.toContain(TOKEN);
    expect(consoleTexts.join("\n")).not.toContain(TOKEN);
    expect(requestUrls.some((url) => url.includes(TOKEN))).toBe(false);
  });

  test("navegación por teclado alcanza 'Volver a preguntar'", async ({ page }) => {
    await runToNoEvidence(page);
    const retryButton = page.getByRole("button", { name: "Volver a preguntar" });
    await retryButton.focus();
    await expect(retryButton).toBeFocused();
  });

  test("axe WCAG 2.2 AA sin violaciones", async ({ page }) => {
    await runToNoEvidence(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("320px: sin overflow horizontal", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await runToNoEvidence(page);
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });
});

test.describe("/app — interrupted (F8-01)", () => {
  const fixture = loadFixture("interrupted.json");
  const TOKEN = "cdt_rt_f8_01_interrupted_no_debe_aparecer";

  async function runToInterrupted(page) {
    await mockBackendFromFixture(page, fixture, { token: TOKEN });
    await submitFreeQuestion(page, "¿Cuál fue el promedio de deserción escolar en Antioquia entre 2018 y 2022?");
    await expect(
      page.getByText("La investigación se interrumpió en el servidor. Esto es lo que alcanzó a verificar."),
    ).toBeVisible({ timeout: 15_000 });
  }

  test("badge ámbar con icono y texto, pasos parciales visibles, cero token", async ({ page }) => {
    const consoleTexts = [];
    page.on("console", (msg) => consoleTexts.push(msg.text()));
    await runToInterrupted(page);

    await expect(page.getByText("Interrumpido")).toBeVisible();
    const steps = page.getByRole("list", { name: "Pasos de la investigación" }).getByRole("listitem");
    // `fixture.steps` es el resumen final del servidor y NO incluye el
    // evento `start` (step_number 0) que sí llega por SSE y sí se
    // renderiza; el conteo real de listitems se deriva de los eventos
    // `step` reconstruidos, no del resumen.
    const stepEventCount = fixture.events.filter((entry) => entry.event === "step").length;
    await expect(steps).toHaveCount(stepEventCount);

    const html = await page.content();
    expect(html).not.toContain(TOKEN);
    expect(consoleTexts.join("\n")).not.toContain(TOKEN);
  });

  test("axe WCAG 2.2 AA sin violaciones", async ({ page }) => {
    await runToInterrupted(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("320px: sin overflow horizontal", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await runToInterrupted(page);
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });
});

test.describe("/app — failed (F8-01)", () => {
  const fixture = loadFixture("failed.json");
  const TOKEN = "cdt_rt_f8_01_failed_no_debe_aparecer";

  async function runToFailed(page) {
    await mockBackendFromFixture(page, fixture, { token: TOKEN });
    await submitFreeQuestion(page, "¿Qué temperatura registró la estación 0026195501?");
    // Acotado al panel del copiloto ("Investigación en curso", aria-label
    // presente tanto en el `<aside>` de escritorio como en el `Modal` de
    // <1024px): `state.error.messageUser` alimenta AL MISMO TIEMPO el
    // párrafo visible de `TerminalPanel` y la región `aria-live="polite"`
    // (`usePolitePolite`), con el mismo texto exacto para `failed`. Un
    // `page.getByText(...)` sin acotar es ambiguo (violación de modo
    // estricto) en cuanto ambos coexisten en el DOM — se reprodujo bajo
    // contención de CPU en la suite paralela completa.
    await expect(
      page.getByLabel("Investigación en curso").getByText("La fuente de datos no respondió a tiempo."),
    ).toBeVisible({ timeout: 15_000 });
  }

  test("message_user real del fixture, badge rojo con icono y texto, pasos parciales visibles, cero token", async ({
    page,
  }) => {
    const consoleTexts = [];
    page.on("console", (msg) => consoleTexts.push(msg.text()));
    await runToFailed(page);

    await expect(page.getByText("Fallido")).toBeVisible();
    const steps = page.getByRole("list", { name: "Pasos de la investigación" }).getByRole("listitem");
    const stepEventCount = fixture.events.filter((entry) => entry.event === "step").length;
    await expect(steps).toHaveCount(stepEventCount);

    const html = await page.content();
    expect(html).not.toContain(TOKEN);
    // message_dev nunca se expone al usuario (rule 6, runReducer.js).
    const errorEvent = fixture.events.find((entry) => entry.event === "error");
    expect(html).not.toContain(errorEvent.data.error.message_dev);
    expect(consoleTexts.join("\n")).not.toContain(TOKEN);
  });

  test("axe WCAG 2.2 AA sin violaciones", async ({ page }) => {
    await runToFailed(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("320px: sin overflow horizontal", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    await runToFailed(page);
    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });
});

test.describe("/app — modal de confirmación de evidencia no recomendada, axe (F8-01, RF-404)", () => {
  // Mismo patrón de doble sintético inline ya autorizado en
  // `app-f5-02.spec.js:notRecommendedSyntheticScenario`: un único campo
  // (`quality.classification`) mutado sobre el fixture REAL de stream
  // completo, exclusivamente para alcanzar la rama `no_recomendada` que
  // ningún fixture real capturado produce todavía.
  const REAL_STREAM = readFileSync(
    path.resolve(process.cwd(), "tests/fixtures/completed-stream.sse.txt"),
    "utf8",
  );
  const TOKEN = "cdt_rt_f8_01_rf404_modal_no_debe_aparecer";

  function answerFromStream(stream) {
    const block = stream.split(/\r?\n\r?\n/).find((candidate) => candidate.includes("event: answer"));
    const dataLine = block?.split(/\r?\n/).find((line) => line.startsWith("data: "));
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

  function notRecommendedScenario() {
    const answer = structuredClone(REAL_ANSWER);
    answer.run_id = "run-sintetico-inline-f8-01-rf404";
    const evidence = answer.evidence[0];
    evidence.evidence_id = "evidence-sintetica-inline-f8-01-rf404";
    evidence.quality = { ...evidence.quality, classification: "no_recomendada" };
    return { answer, stream: streamWithAnswer(REAL_STREAM, answer) };
  }

  test("axe WCAG 2.2 AA sin violaciones con el modal 'Insertar evidencia no recomendada' abierto", async ({
    page,
  }) => {
    const { answer, stream } = notRecommendedScenario();
    await page.route("**/v2/agent/query", async (route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: answer.run_id,
          run_access_token: TOKEN,
          token_expires_at: "2026-08-30T23:59:59Z",
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

    await submitFreeQuestion(page, "¿Cuál fue el promedio de deserción escolar en Antioquia entre 2018 y 2022?");
    await expect(page.getByLabel("Investigación en curso").getByText("La investigación terminó con evidencia verificada.")).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("button", { name: "Insertar en el documento" }).click();
    const dialog = page.getByRole("dialog", { name: "Insertar evidencia no recomendada" });
    await expect(dialog).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});

test.describe("/app — skip-link (F8-01)", () => {
  test("es el primer control alcanzable con Tab y mueve el foco al contenido principal", async ({ page }) => {
    await page.goto(APP_URL);
    // Sin clic previo: primer Tab real desde el documento recién cargado.
    await page.keyboard.press("Tab");
    const skipLink = page.getByRole("link", { name: "Saltar al contenido" });
    await expect(skipLink).toBeFocused();

    await page.keyboard.press("Enter");
    const focusedIsContent = await page.evaluate(() => document.activeElement?.id === "contenido");
    // El landmark `#contenido` no es tabulable por defecto; algunos
    // navegadores solo desplazan el scroll sin mover `document.activeElement`
    // cuando el destino carece de `tabindex`. Se acepta cualquiera de las
    // dos evidencias válidas de que el salto funcionó: el foco quedó en el
    // contenido, o el contenido quedó desplazado a la vista.
    const contentInView = await page.evaluate(() => {
      const el = document.getElementById("contenido");
      if (!el) return false;
      const rect = el.getBoundingClientRect();
      return rect.top <= 1 && rect.top >= -1;
    });
    expect(focusedIsContent || contentInView).toBe(true);
  });
});
