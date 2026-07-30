import { expect, test } from "@playwright/test";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

const APP_URL = "/app";
const DOC_KEY = "cdd.doc.v1";

async function waitForDocumentPersisted(page) {
  await page.waitForFunction((key) => window.localStorage.getItem(key) !== null, DOC_KEY, { timeout: 8_000 });
}

test.describe("/app — RF-101-02 selector de plantilla (RF-101)", () => {
  test("storage vacío: aparece el selector y NO se crea 'libre' automáticamente", async ({ page }) => {
    await page.goto(APP_URL);

    await expect(page.getByRole("radio", { name: /Libre/ })).toBeVisible();
    await expect(page.getByRole("radio", { name: /^MGA/ })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Plan de desarrollo/ })).toBeVisible();
    for (const radio of await page.getByRole("radio").all()) {
      await expect(radio).not.toBeChecked();
    }
    await expect(page.getByRole("button", { name: "Crear documento" })).toBeDisabled();

    // Ningún editor todavía: no hay documento en memoria hasta que el
    // usuario confirme una elección.
    await expect(page.getByRole("textbox", { name: /^Documento de trabajo:/ })).toHaveCount(0);

    // Sin persistir nada todavía: no se crea la plantilla libre "por debajo".
    const stored = await page.evaluate((key) => window.localStorage.getItem(key), DOC_KEY);
    expect(stored).toBeNull();
  });

  test("elegir 'Libre': crea un documento de una sola sección, oculta el selector y muestra el lienzo", async ({
    page,
  }) => {
    await page.goto(APP_URL);

    await createFreeDocumentViaPicker(page);

    await expect(page.getByRole("radio")).toHaveCount(0); // el selector se desmontó
  });

  test("elegir 'MGA': crea el documento con las 7 secciones aprobadas (ADR-0005), en orden", async ({ page }) => {
    await page.goto(APP_URL);

    await page.getByRole("radio", { name: /^MGA/ }).click();
    await page.getByRole("button", { name: "Crear documento" }).click();

    await expect(page.getByRole("radio")).toHaveCount(0);
    const expectedTitles = [
      "Problemática",
      "Participantes, población y localización",
      "Objetivos",
      "Alternativas de solución",
      "Preparación",
      "Evaluación ex ante",
      "Programación",
    ];
    for (const title of expectedTitles) {
      await expect(page.getByRole("textbox", { name: `Documento de trabajo: ${title}` })).toBeVisible();
    }
  });

  test("elegir 'Plan de desarrollo': crea el documento con las 5 secciones aprobadas (ADR-0004), en orden", async ({
    page,
  }) => {
    await page.goto(APP_URL);

    await page.getByRole("radio", { name: /Plan de desarrollo/ }).click();
    await page.getByRole("button", { name: "Crear documento" }).click();

    await expect(page.getByRole("radio")).toHaveCount(0);
    const expectedTitles = [
      "Diagnóstico",
      "Visión y articulación estratégica",
      "Programas, indicadores y metas",
      "Plan plurianual de inversiones (PPI)",
      "Seguimiento y evaluación",
    ];
    for (const title of expectedTitles) {
      await expect(page.getByRole("textbox", { name: `Documento de trabajo: ${title}` })).toBeVisible();
    }
  });

  test("un documento restaurado ABRE DIRECTAMENTE ese documento y NUNCA muestra el selector", async ({ page }) => {
    const restoredEnvelope = {
      schemaVersion: 1,
      createdAt: "2026-07-01T00:00:00.000Z",
      updatedAt: "2026-07-01T00:00:00.000Z",
      document: {
        version: 1,
        templateId: "libre",
        title: "Documento libre",
        sections: [
          {
            sectionId: "seccion-1",
            title: "Sección 1",
            content: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "Texto ya restaurado." }] }] },
          },
        ],
      },
    };
    await page.addInitScript(
      ([key, envelope]) => window.localStorage.setItem(key, JSON.stringify(envelope)),
      [DOC_KEY, restoredEnvelope],
    );

    await page.goto(APP_URL);

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await expect(editor).toBeVisible();
    await expect(editor).toContainText("Texto ya restaurado.");

    // El selector nunca aparece cuando hay un documento restaurado.
    await expect(page.getByRole("radio")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Crear documento" })).toHaveCount(0);
  });

  test("ni en un documento restaurado ni en uno recién creado existe ningún control para cambiar de plantilla", async ({
    page,
  }) => {
    // Caso 1: documento recién creado.
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);
    await expect(page.getByRole("button", { name: /Cambiar plantilla/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Nuevo documento/i })).toHaveCount(0);

    // Caso 2: documento restaurado tras recargar — hay que esperar a que el
    // autoguardado (debounce ≤5 s) persista antes de recargar, si no
    // `cdd.doc.v1` seguiría vacío y el selector volvería a aparecer (eso
    // sería correcto para la app, pero no es lo que este caso quiere probar).
    await waitForDocumentPersisted(page);
    await page.reload();
    await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Cambiar plantilla/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Nuevo documento/i })).toHaveCount(0);
  });
});
