import { expect, test } from "@playwright/test";
import { createFreeDocumentViaPicker } from "./helpers/templatePickerFlow.js";

/**
 * Menú Archivo/Editar/Formato estilo Google Docs (RF-105). Verifica que las
 * opciones ejecutan comandos reales sobre el editor Tiptap con el foco más
 * reciente (`DocumentMenuBar.jsx`/`DocumentSections.jsx`), no un maquetado
 * visual: negrita/alinear/estilo de párrafo mutan el DOM del editor,
 * deshacer/rehacer revierten cambios reales, y "Nuevo" pide confirmación
 * antes de reemplazar un documento con contenido.
 */
const APP_URL = "/app";

test.describe("Menú del documento (RF-105)", () => {
  test("Formato: negrita, alinear y estilo de párrafo mutan el editor real", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Texto de prueba");
    await page.keyboard.press("Control+A");

    await page.getByRole("menuitem", { name: "Formato" }).click();
    await page.getByRole("menuitemcheckbox", { name: "Negrita" }).click();
    await expect(editor.locator("strong")).toContainText("Texto de prueba");

    await page.getByRole("menuitem", { name: "Formato" }).click();
    await page.getByRole("menuitemradio", { name: "Centro" }).click();
    await expect(editor.locator("p")).toHaveCSS("text-align", "center");

    await page.getByRole("menuitem", { name: "Formato" }).click();
    await page.getByRole("menuitemradio", { name: "Título", exact: true }).click();
    await expect(editor.locator("h2")).toContainText("Texto de prueba");
  });

  test("Editar: deshacer y rehacer operan sobre el editor con foco", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Hola mundo");
    await expect(editor).toContainText("Hola mundo");

    await page.getByRole("menuitem", { name: "Editar" }).click();
    await page.getByRole("menuitem", { name: "Deshacer" }).click();
    await expect(editor).not.toContainText("Hola mundo");

    await page.getByRole("menuitem", { name: "Editar" }).click();
    await page.getByRole("menuitem", { name: "Rehacer" }).click();
    await expect(editor).toContainText("Hola mundo");
  });

  test("Escape cierra el menú y devuelve el foco a su disparador", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const archivoTrigger = page.getByRole("menuitem", { name: "Archivo" });
    await archivoTrigger.click();
    await expect(page.getByRole("menu", { name: "Archivo" })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu", { name: "Archivo" })).toBeHidden();
    await expect(archivoTrigger).toBeFocused();
  });

  test("flechas izquierda/derecha mueven el foco entre menús de nivel superior", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    await page.getByRole("menuitem", { name: "Archivo" }).click();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("menuitem", { name: "Editar" })).toBeFocused();
    await expect(page.getByRole("menu", { name: "Editar" })).toBeVisible();
  });

  test("Archivo > Nuevo pide confirmación antes de reemplazar un documento con contenido", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("Contenido importante");

    await page.getByRole("menuitem", { name: "Archivo" }).click();
    await page.getByRole("menuitem", { name: "MGA" }).click();
    await expect(page.getByRole("dialog", { name: "¿Reemplazar el documento actual?" })).toBeVisible();

    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(editor).toContainText("Contenido importante");

    await page.getByRole("menuitem", { name: "Archivo" }).click();
    await page.getByRole("menuitem", { name: "MGA" }).click();
    await page.getByRole("button", { name: "Reemplazar de todas formas" }).click();
    await expect(page.getByRole("textbox", { name: "Documento de trabajo: Problemática" })).toBeVisible();
  });

  test("Editar > Insertar dato manual abre el mismo formulario que el botón de la sección", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    await page.getByRole("menuitem", { name: "Editar" }).click();
    await page.getByRole("menuitem", { name: "Insertar dato manual" }).click();
    await expect(page.getByRole("dialog", { name: "Agregar dato manual" })).toBeVisible();
  });

  test("Formato > Superíndice alterna la marca real del editor", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const editor = page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" });
    await editor.click();
    await page.keyboard.type("x2");
    await page.keyboard.press("Control+A");

    await page.getByRole("menuitem", { name: "Formato" }).click();
    await page.getByRole("menuitemcheckbox", { name: "Superíndice" }).click();
    await expect(editor.locator("sup")).toContainText("x2");
  });

  test("Archivo > Descargar (.docx) dispara la misma descarga real que el botón Exportar", async ({ page }) => {
    await page.goto(APP_URL);
    await createFreeDocumentViaPicker(page);

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("menuitem", { name: "Archivo" }).click();
    await page.getByRole("menuitem", { name: "Descargar (.docx)" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.docx$/);
  });
});
