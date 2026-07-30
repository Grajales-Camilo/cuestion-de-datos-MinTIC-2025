import { expect } from "@playwright/test";

/**
 * RF-101-02-R1: helper compartido para escenarios E2E que arrancan desde
 * storage VACÍO (sin `addInitScript` sembrando `cdd.doc.v1`) y necesitan un
 * documento real antes de continuar con su propio flujo. Desde RF-101-02,
 * `/app` ya no crea "libre" automáticamente: el usuario elige y confirma una
 * plantilla en `TemplatePicker` (ver `components/document/TemplatePicker.jsx`,
 * `pages/app.js`).
 *
 * NO usar este helper en escenarios que siembran un documento persistido
 * (`addInitScript` con una clave `cdd.doc.v1` ya válida, corrupta, de
 * versión futura o de migración fallida): esos deben seguir ejerciendo la
 * restauración/el bloqueo real de `useDocumentAutosave`, nunca ocultar el
 * selector fabricando un documento de más.
 *
 * Elige siempre "Libre" — es la plantilla que todos los escenarios
 * preexistentes de este archivo asumían implícitamente antes de RF-101-01/02
 * (una sola sección, "Sección 1"); no cambia ninguna expectativa de
 * contenido de esos escenarios.
 */
export async function createFreeDocumentViaPicker(page) {
  await expect(page.getByRole("radio", { name: /Libre/ })).toBeVisible();
  await page.getByRole("radio", { name: /Libre/ }).click();
  await page.getByRole("button", { name: "Crear documento" }).click();
  await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toBeVisible();
}

/**
 * Variante EXCLUSIVAMENTE por teclado (nunca `.click()`/`.focus()`) para los
 * escenarios que afirman "recorrido real por teclado, sin ningún clic
 * previo" desde la carga de la página (p. ej. `app-f5-03.spec.js`). No
 * asume que el radio "Libre" sea el primer elemento tabulable de la página
 * (el skip-link "Saltar al contenido" lo antecede) — recorre con Tab hasta
 * alcanzarlo, igual que los `tabUntil` locales de esos archivos. Espacio lo
 * marca; un Tab más alcanza "Crear documento"; Enter confirma. No usa
 * `.check()` ni ninguna API de Playwright que no pase por eventos de
 * teclado reales.
 */
export async function createFreeDocumentViaPickerWithKeyboard(page, { tabLimit = 30 } = {}) {
  const freeRadio = page.getByRole("radio", { name: /Libre/ });
  await expect(freeRadio).toBeVisible();

  let reached = false;
  for (let index = 0; index < tabLimit && !reached; index += 1) {
    await page.keyboard.press("Tab");
    reached = await freeRadio.evaluate((node) => node === document.activeElement).catch(() => false);
  }
  if (!reached) throw new Error("createFreeDocumentViaPickerWithKeyboard: no se alcanzó el radio 'Libre' con Tab");

  await page.keyboard.press("Space");
  await expect(freeRadio).toBeChecked();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Crear documento" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("textbox", { name: "Documento de trabajo: Sección 1" })).toBeVisible();
}
