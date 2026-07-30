import { readFileSync } from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

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
 * documento antes de probar persistencia. Asume storage vacío al entrar
 * (los tres llamadores de este archivo no siembran ningún documento
 * previo), así que primero pasa por el selector de plantilla (RF-101-02). */
async function typeAndInsertCitation(page) {
  await createFreeDocumentViaPicker(page);

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

  test("versión futura sembrada: aviso visible, TemplatePicker ofrece crear un documento en memoria, aviso persiste y nunca se sobrescribe ni con el debounce vencido, descarga disponible", async ({
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

    // RF-101-02: no se auto-abre "libre" — el usuario elige explícitamente.
    // No hay ningún control "Cambiar plantilla"/"Nuevo documento" aparte del
    // selector inicial.
    await expect(page.getByRole("button", { name: /Cambiar plantilla/i })).toHaveCount(0);
    await page.getByRole("radio", { name: /Libre/ }).click();
    await page.getByRole("button", { name: "Crear documento" }).click();

    // El aviso de "versión más nueva" sigue visible DESPUÉS de crear el
    // documento en memoria — nunca se reemplaza por el lienzo normal.
    await expect(page.getByText(/versión más nueva/)).toBeVisible();

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

  test("migración fallida sembrada (mecanismo real, sin mockear storage/notifyChange): aviso visible, descarga del original, y el raw en localStorage nunca cambia ni con el debounce vencido", async ({
    page,
  }) => {
    // RF-101-02-R1, requisito 5: `loadStoredDocument` (llamado por
    // `useDocumentAutosave` sin `migrations`, ver `hooks/useDocumentAutosave.js`)
    // usa el valor por defecto `migrations = {}` en producción. Un sobre con
    // `schemaVersion` por debajo de `DOCUMENT_STORAGE_SCHEMA_VERSION` (1) no
    // tiene ningún paso `migrations[0]` disponible, así que
    // `migrateStoredDocument` devuelve `{ ok: false, reason:
    // "no_migration_path" }` (documentStorage.js) y `loadStoredDocument`
    // clasifica el resultado como `MIGRATION_FAILED` — el MISMO camino real
    // que seguiría un sobre legítimo de una versión de esquema anterior que
    // esta build ya no sabe migrar. No se mockea `localStorage` ni
    // `notifyChange`: es el storage real del navegador y el hook real.
    const legacyEnvelope = {
      schemaVersion: 0,
      createdAt: "2020-01-01T00:00:00.000Z",
      updatedAt: "2020-01-01T00:00:00.000Z",
      document: { legacyShape: true, note: "Sobre de una version de esquema anterior sin ruta de migracion." },
    };
    const legacyRaw = JSON.stringify(legacyEnvelope);
    await page.addInitScript(
      ([key, raw]) => window.localStorage.setItem(key, raw),
      [DOC_KEY, legacyRaw],
    );
    await page.goto(APP_URL);

    // Aviso específico de `migration_failed` (BLOCKED_MESSAGES,
    // DocumentPersistenceStatus.jsx) — deliberadamente distinto del de
    // `future_version`: el original nunca se tocó, solo no se pudo
    // actualizar con seguridad.
    await expect(page.getByText(/No pudimos actualizar de forma segura el documento guardado/)).toBeVisible();

    // Se guarda el raw INICIAL una sola vez, leído directamente de
    // localStorage (no reconstruido con JSON.stringify): la comparación
    // final debe ser identidad de bytes, no igualdad estructural.
    const initialRaw = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(initialRaw).toBe(legacyRaw);

    // Descarga del original ANTES de crear ningún documento nuevo.
    const firstDownloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Descargar archivo intacto" }).click();
    const firstDownload = await firstDownloadPromise;
    expect(firstDownload.suggestedFilename()).toMatch(/\.json$/);

    // Elegir una plantilla y editar el documento en memoria: RF-101-02 no
    // auto-abre "libre" — el usuario elige explícitamente, conviviendo con
    // el aviso de migración fallida (nunca lo reemplaza).
    await page.getByRole("radio", { name: /Libre/ }).click();
    await page.getByRole("button", { name: "Crear documento" }).click();
    await expect(page.getByText(/No pudimos actualizar de forma segura el documento guardado/)).toBeVisible();

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Este cambio nunca debe sobrescribir el sobre con migración fallida.");

    // Más que el debounce (`DEFAULT_DEBOUNCE_MS` = 5000 ms en
    // `useDocumentAutosave.js`): `readyRef` nunca pasó a `true` en la rama
    // `MIGRATION_FAILED`, así que `notifyChange` sigue siendo un no-op
    // durante el resto de la sesión de página, sin excepción para el
    // documento nuevo creado en memoria.
    await page.waitForTimeout(6_000);

    const rawAfterEdit = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(rawAfterEdit).toBe(legacyRaw);

    // El aviso sigue visible y el original sigue siendo descargable después
    // de editar y esperar el debounce.
    await expect(page.getByText(/No pudimos actualizar de forma segura el documento guardado/)).toBeVisible();
    const secondDownloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Descargar archivo intacto" }).click();
    const secondDownload = await secondDownloadPromise;
    expect(secondDownload.suggestedFilename()).toMatch(/\.json$/);
  });

  test("JSON corrupto se recupera de forma segura: aviso + TemplatePicker conviven, backup se conserva, y solo tras elegir plantilla aparece un documento nuevo editable", async ({
    page,
  }) => {
    await page.addInitScript(
      (key) => window.localStorage.setItem(key, "{esto no es json valido"),
      DOC_KEY,
    );
    await page.goto(APP_URL);

    await expect(page.getByText(/estaba dañado/)).toBeVisible();

    // El selector aparece JUNTO al aviso — el respaldo (copia aislada) ya
    // existe antes de que el usuario elija nada.
    await expect(page.getByRole("radio", { name: /Libre/ })).toBeVisible();
    const corruptKeysBeforeChoice = await page.evaluate(
      (key) => Object.keys(window.localStorage).filter((k) => k.startsWith(`${key}.corrupt.`)),
      DOC_KEY,
    );
    expect(corruptKeysBeforeChoice.length).toBeGreaterThan(0);
    const diagnosticRawBeforeChoice = await page.evaluate(
      ([key, diagKey]) => window.localStorage.getItem(diagKey),
      [DOC_KEY, corruptKeysBeforeChoice[0]],
    );
    expect(diagnosticRawBeforeChoice).toBe("{esto no es json valido");

    // Antes de elegir, no hay editor todavía (no se auto-crea "libre").
    await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toHaveCount(0);

    await page.getByRole("radio", { name: /Libre/ }).click();
    await page.getByRole("button", { name: "Crear documento" }).click();

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Documento nuevo tras corrupción");
    await expect(editor).toContainText("Documento nuevo tras corrupción");

    // El respaldo aislado sigue intacto tras crear y escribir el documento
    // nuevo — nunca se pierde ni se sobrescribe.
    const corruptKeysAfter = await page.evaluate(
      (key) => Object.keys(window.localStorage).filter((k) => k.startsWith(`${key}.corrupt.`)),
      DOC_KEY,
    );
    expect(corruptKeysAfter).toEqual(corruptKeysBeforeChoice);
    const diagnosticRawAfter = await page.evaluate(
      ([key, diagKey]) => window.localStorage.getItem(diagKey),
      [DOC_KEY, corruptKeysAfter[0]],
    );
    expect(diagnosticRawAfter).toBe("{esto no es json valido");
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
