import { readFileSync } from "node:fs";
import JSZip from "jszip";
import { expect, test } from "@playwright/test";
import { createRichSyntheticDocx } from "../fixtures/docxSynthetic.js";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

const APP_URL = "/app";
const DOC_KEY = "cdd.doc.v1";
const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

async function chooseDocxFromFileMenu(
  page,
  buffer,
  name = "informe-sintetico.docx",
  { beforeSelection } = {},
) {
  const chooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("menuitem", { name: "Archivo" }).click();
  await page.getByRole("menuitem", { name: "Importar documento (.docx)" }).click();
  const chooser = await chooserPromise;
  // El Worker es un chunk estático same-origin preparado por el clic, antes
  // de que existan bytes del archivo. Dejar que esa carga termine permite
  // medir de forma estricta la conversión que comienza con `setFiles`.
  await page.waitForTimeout(300);
  beforeSelection?.();
  await chooser.setFiles({ name, mimeType: DOCX_MIME, buffer });
}

test.describe("/app — DOCX-IMPORT-01 local y controlado", () => {
  test("importar → confirmar → editar → autosave → recargar → exportar conserva el documento libre", async ({
    page,
  }, testInfo) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const currentEditor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await currentEditor.click();
    await page.keyboard.type("Documento anterior que no debe reemplazarse sin confirmar");

    const requests = [];
    const sockets = [];
    page.on("request", (request) => requests.push({
      method: request.method(),
      type: request.resourceType(),
      url: request.url(),
    }));
    page.on("websocket", (socket) => sockets.push(socket.url()));

    const fixture = await createRichSyntheticDocx();
    await chooseDocxFromFileMenu(page, fixture, "informe-sintetico.docx", {
      // Solo interesan solicitudes iniciadas DESPUÉS de seleccionar el DOCX.
      // El chunk local del Worker se solicitó antes, sin acceso al archivo.
      beforeSelection: () => { requests.length = 0; },
    });

    const summary = page.getByRole("dialog", { name: "Resumen de importación" });
    await expect(summary).toBeVisible({ timeout: 20_000 });
    await expect(summary.getByText("informe-sintetico.docx")).toBeVisible();
    await expect(summary.getByText(/encabezados/)).toBeVisible();
    await expect(summary.getByText(/párrafos/)).toBeVisible();
    await expect(summary.getByText(/enlaces seguros/)).toBeVisible();
    await expect(summary.getByText("No se detectaron elementos que deban descartarse o simplificarse.")).toBeVisible();
    await expect(summary.getByText(/no se convertirá en evidencia verificada/i)).toBeVisible();

    // Cancelar desde el resumen no toca el editor actual y devuelve el foco
    // al disparador Archivo del menú que inició el flujo.
    await summary.getByRole("button", { name: "Cancelar" }).click();
    await expect(currentEditor).toContainText("Documento anterior");
    await expect(page.getByRole("menuitem", { name: "Archivo" })).toBeFocused();

    await chooseDocxFromFileMenu(page, fixture, "informe-sintetico.docx", {
      beforeSelection: () => { requests.length = 0; },
    });
    await expect(summary).toBeVisible({ timeout: 20_000 });
    await summary.getByRole("button", { name: "Abrir como documento nuevo" }).click();

    const replace = page.getByRole("dialog", { name: "¿Reemplazar el documento actual?" });
    await expect(replace).toBeVisible();
    await replace.getByRole("button", { name: "Volver al resumen" }).click();
    await expect(summary).toBeVisible();
    await summary.getByRole("button", { name: "Abrir como documento nuevo" }).click();
    await replace.getByRole("button", { name: "Sí, reemplazar" }).click();

    const importedEditor = page.getByRole("textbox", { name: "Documento de trabajo: Contenido importado" });
    await expect(importedEditor).toBeVisible();
    await expect(importedEditor).toContainText("Título sintético");
    await expect(importedEditor.locator("strong")).toContainText("negrita");
    await expect(importedEditor.locator("em")).toContainText("cursiva");
    await expect(importedEditor.locator("ul")).toContainText("Elemento con viñeta");
    await expect(importedEditor.locator("ol")).toContainText("Elemento numerado");
    await expect(importedEditor.locator('a[href="https://example.test/recurso"]')).toContainText("enlace");
    await expect(page.getByText("Documento anterior que no debe reemplazarse sin confirmar")).toHaveCount(0);
    await expect(page.getByRole("group", { name: /Cita de evidencia:/ })).toHaveCount(0);

    const appendedText = " Texto editado después de importar.";
    await importedEditor.click();
    await page.keyboard.press("Control+End");
    await page.keyboard.type(appendedText);

    await page.waitForFunction(
      ([key, text]) => window.localStorage.getItem(key)?.includes(text),
      [DOC_KEY, appendedText.trim()],
      { timeout: 8_000 },
    );
    const stored = await page.evaluate((key) => JSON.parse(window.localStorage.getItem(key)), DOC_KEY);
    expect(stored.document.templateId).toBe("libre");
    expect(stored.document.title).toBe("informe-sintetico");
    expect(stored.document.sections[0].sectionId).toBe("contenido-importado");

    await page.reload();
    const restoredEditor = page.getByRole("textbox", { name: "Documento de trabajo: Contenido importado" });
    await expect(restoredEditor).toContainText(appendedText.trim());
    await expect(restoredEditor.locator('a[href="https://example.test/recurso"]')).toContainText("enlace");

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("menuitem", { name: "Archivo" }).click();
    await page.getByRole("menuitem", { name: "Descargar (.docx)" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("informe-sintetico.docx");
    const outputPath = testInfo.outputPath(download.suggestedFilename());
    await download.saveAs(outputPath);

    const zip = await JSZip.loadAsync(readFileSync(outputPath));
    const documentXml = await zip.file("word/document.xml").async("string");
    const relationshipsXml = await zip.file("word/_rels/document.xml.rels").async("string");
    expect(documentXml).toContain("Texto editado después de importar.");
    expect(documentXml).toMatch(/<w:b\/?/u);
    expect(documentXml).toMatch(/<w:i\/?/u);
    expect(relationshipsXml).toContain("https://example.test/recurso");

    // El contenido no genera fetch/XHR, POST, WebSocket ni contacto con
    // backend o dominio externo. La recarga posterior sí puede pedir activos
    // internos de Next; quedan fuera del intervalo de importación.
    expect(requests.filter((request) => ["fetch", "xhr"].includes(request.type) && !request.url.includes("/_next/"))).toEqual([]);
    expect(requests.filter((request) => request.method !== "GET")).toEqual([]);
    expect(requests.filter((request) => request.url.includes("/v2/") || request.url.includes("example.test"))).toEqual([]);
    expect(sockets.filter((url) => !url.includes("/_next/webpack-hmr"))).toEqual([]);
  });

  test("archivo corrupto se anuncia, conserva el documento y Escape restaura el foco", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);
    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Contenido que debe permanecer");

    await chooseDocxFromFileMenu(page, Buffer.from([0x50, 0x4b, 0x03, 0x04, 1, 2, 3, 4]), "corrupto.docx");
    const errorDialog = page.getByRole("dialog", { name: "No se pudo importar el documento" });
    await expect(errorDialog).toBeVisible({ timeout: 20_000 });
    await expect(errorDialog.getByRole("alert")).toContainText(/corrupto|incompleto/i);
    await expect(page.getByText(/Error de importación/)).toBeAttached();

    await page.keyboard.press("Escape");
    await expect(errorDialog).toBeHidden();
    await expect(page.getByRole("menuitem", { name: "Archivo" })).toBeFocused();
    await expect(editor).toContainText("Contenido que debe permanecer");
  });
});
