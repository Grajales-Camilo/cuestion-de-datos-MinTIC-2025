import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * `/app` con transporte controlado (`page.route`): F3-7B no tiene todavía
 * un backend simulado embebido como `/_dev/ui` (F3-7A) — `/app` habla
 * directo con `NEXT_PUBLIC_BACKEND_URL` (D-7), así que estas pruebas
 * interceptan exactamente esas tres llamadas (`POST /v2/agent/query`,
 * `GET /v2/agent/stream/{run_id}`, `DELETE /v2/agent/runs/{run_id}`) sin
 * tocar ningún backend real. Todos los locators quedan acotados al
 * landmark `#contenido` de `/app` para que ninguna aserción pueda pasar
 * por una badge o texto estático de la galería (`/_dev/ui`).
 */

const APP_URL = "/app";
const RUN_ID = "run-e2e-0001";
const TOKEN = "cdt_rt_e2e_token_no_debe_aparecer_nunca";

function sseBody({ runId, stepMessage = "Consultando datos.gov.co…" }) {
  const stepEvent = [
    "id: 0",
    "event: step",
    `data: ${JSON.stringify({ step_number: 1, node: "execute_query", display_message: stepMessage, detail: null })}`,
    "",
    "",
  ].join("\n");
  const answerEvent = [
    "id: 1",
    "event: answer",
    `data: ${JSON.stringify({
      run_id: runId,
      status: "completed",
      intention: { topic: "prueba e2e" },
      evidence: [],
      claims: [],
      presentation_warnings: [],
      textual_facts: [],
      no_evidence_report: null,
      usage: { steps_used: 1 },
    })}`,
    "",
    "",
  ].join("\n");
  return stepEvent + answerEvent;
}

async function mockBackend(page, { runId = RUN_ID, token = TOKEN } = {}) {
  const postCalls = [];
  const deleteCalls = [];

  await page.route("**/v2/agent/query", async (route) => {
    postCalls.push(route.request().postDataJSON());
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: runId,
        run_access_token: token,
        token_expires_at: new Date(Date.now() + 3600_000).toISOString(),
        stream_url: `/v2/agent/stream/${runId}`,
      }),
    });
  });

  await page.route(`**/v2/agent/stream/${runId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody({ runId }),
    });
  });

  await page.route(`**/v2/agent/runs/${runId}`, async (route) => {
    if (route.request().method() === "DELETE") {
      deleteCalls.push(true);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: runId, status: "completed", answer: { evidence: [], claims: [] } }),
    });
  });

  return { postCalls, deleteCalls };
}

function main(page) {
  return page.locator("#contenido");
}

// Acotado a la lista del historial: la misma pregunta puede seguir visible
// en el `<textarea>` del composer (que no se limpia tras enviar), así que
// un locator sin acotar sería ambiguo (violación de "strict mode").
function historyList(page) {
  return main(page).getByRole("list", { name: "Historial de investigaciones" });
}

async function submitQuestion(page, question = "¿Cuál es la tasa de deserción escolar en Sonsón?") {
  await main(page).getByLabel("Pregunta para investigar").fill(question);
  await main(page).getByRole("button", { name: "Investigar", exact: true }).click();
}

test.describe("/app — consentimiento (D-9, RF-802)", () => {
  test("primera investigación → modal → aceptación → flujo, sin POST antes de aceptar", async ({ page }) => {
    const { postCalls } = await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page);

    const dialog = page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" });
    await expect(dialog).toBeVisible();
    expect(postCalls).toHaveLength(0); // cero POST antes de aceptar

    await dialog.getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(dialog).not.toBeVisible();

    await expect.poll(() => postCalls.length).toBe(1);
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });
  });

  test("segunda investigación no vuelve a mostrar el modal", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la primera pregunta de esta sesión?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });

    await submitQuestion(page, "¿Cuál es la segunda pregunta de esta sesión?");
    await expect(page.getByRole("dialog")).not.toBeVisible();
  });

  test("Cancelar no envía nada y permite reintentar después", async ({ page }) => {
    const { postCalls } = await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page);
    await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible();
    expect(postCalls).toHaveLength(0);
  });
});

test.describe("/app — historial (RF-502)", () => {
  test("la investigación aparece en el historial y sobrevive a una recarga", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la cobertura educativa en Antioquia?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });
    await expect(historyList(page).getByText("¿Cuál es la cobertura educativa en Antioquia?")).toBeVisible();

    await page.reload();
    await expect(historyList(page).getByText("¿Cuál es la cobertura educativa en Antioquia?")).toBeVisible();
    await expect(main(page).getByRole("button", { name: "Reejecutar" })).toBeVisible();
  });

  test("Reejecutar crea una corrida nueva (un segundo POST)", async ({ page }) => {
    const { postCalls } = await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la cobertura educativa en Antioquia?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });

    await main(page).getByRole("button", { name: "Reejecutar" }).click();
    await expect.poll(() => postCalls.length).toBe(2);
  });

  test("Refinar precarga la pregunta en el composer para editar antes de enviar", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la cobertura educativa en Antioquia?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });

    await main(page).getByRole("button", { name: "Refinar" }).click();
    await expect(main(page).getByLabel("Pregunta para investigar")).toHaveValue(
      "¿Cuál es la cobertura educativa en Antioquia?"
    );
  });
});

test.describe("/app — borrado (RF-803)", () => {
  test("borrado exitoso: confirmación explícita, luego desaparece del historial", async ({ page }) => {
    const { deleteCalls } = await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la cobertura educativa en Antioquia?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });

    await main(page).getByRole("button", { name: "Borrar esta investigación" }).click();
    const confirmDialog = page.getByRole("dialog", { name: "Borrar esta investigación" });
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog.getByText(/completa e irreversible/)).toBeVisible();
    expect(deleteCalls).toHaveLength(0); // no borra antes de confirmar

    await confirmDialog.getByRole("button", { name: "Borrar de forma irreversible" }).click();
    await expect(historyList(page).getByText("¿Cuál es la cobertura educativa en Antioquia?")).not.toBeVisible();
    expect(deleteCalls).toHaveLength(1);
    // Hallazgo de revisión manual F8-02 (NVDA): antes de este fix, quitar la
    // tarjeta del historial era la única señal — silenciosa para quien usa
    // lector de pantalla. El borrado exitoso ahora se anuncia por la misma
    // región `aria-live` que ya usa el aporte manual (`pages/app.js`).
    await expect(page.getByRole("status").filter({ hasText: "La investigación se borró de forma irreversible." })).toBeVisible();
  });

  test("borrado fallido: conserva el registro y muestra un mensaje seguro", async ({ page }) => {
    await mockBackend(page);
    await page.route(`**/v2/agent/runs/${RUN_ID}`, async (route) => {
      if (route.request().method() === "DELETE") {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "UNAUTHORIZED", status: null, message_user: "no autorizado", retryable: false } }),
        });
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la cobertura educativa en Antioquia?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });

    await main(page).getByRole("button", { name: "Borrar esta investigación" }).click();
    await page.getByRole("dialog", { name: "Borrar esta investigación" }).getByRole("button", { name: "Borrar de forma irreversible" }).click();

    await expect(historyList(page).getByText("¿Cuál es la cobertura educativa en Antioquia?")).toBeVisible();
    await expect(main(page).getByRole("alert")).toBeVisible();
  });
});

test.describe("/app — teclado, responsive y accesibilidad", () => {
  test("Escape cierra el modal de consentimiento sin aceptar", async ({ page }) => {
    const { postCalls } = await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page);
    await expect(page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).not.toBeVisible();
    expect(postCalls).toHaveLength(0);
  });

  test("320px: el modal de consentimiento no produce scroll horizontal", async ({ page }) => {
    await mockBackend(page);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(APP_URL);

    await submitQuestion(page);
    await expect(page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })).toBeVisible();

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasOverflow).toBe(false);
  });

  test("axe sin violaciones críticas con el modal de consentimiento abierto", async ({ page }) => {
    await mockBackend(page);
    await page.goto(APP_URL);
    await submitQuestion(page);
    await expect(page.getByRole("dialog", { name: "Antes de iniciar tu primera investigación" })).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});

test.describe("/app — seguridad del token (RNF-011)", () => {
  test("el token nunca aparece en la URL, el HTML ni la consola", async ({ page }) => {
    const consoleTexts = [];
    page.on("console", (msg) => consoleTexts.push(msg.text()));
    const requestUrls = [];
    page.on("request", (request) => requestUrls.push(request.url()));

    await mockBackend(page);
    await page.goto(APP_URL);

    await submitQuestion(page, "¿Cuál es la cobertura educativa en Antioquia?");
    await page.getByRole("dialog").getByRole("button", { name: "Aceptar e investigar" }).click();
    await expect(main(page).getByText("Completada")).toBeVisible({ timeout: 10000 });

    const html = await page.content();
    expect(html).not.toContain(TOKEN);
    expect(consoleTexts.join("\n")).not.toContain(TOKEN);
    expect(requestUrls.some((url) => url.includes(TOKEN))).toBe(false);
  });
});
