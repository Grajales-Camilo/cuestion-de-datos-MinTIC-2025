import { expect, test } from "@playwright/test";

/**
 * Bajo un build real de producción (`next build && next start`, ver
 * playwright.prod.config.js): la galería de solo-desarrollo debe responder
 * 404, la raíz legacy debe seguir respondiendo 200 (D-7: `/` intacta y
 * aislada de `/app`), y `/app` (F3-7B) debe responder 200. Sustituye el
 * `test.skip` permanente de F1-01.
 */
test("producción real: /_dev/ui → 404, / → 200", async ({ request }) => {
  const galleryResponse = await request.get("/_dev/ui");
  expect(galleryResponse.status()).toBe(404);

  const rootResponse = await request.get("/");
  expect(rootResponse.status()).toBe(200);
});

test("producción real: /app → 200, lang=\"es\" y sin secretos en el HTML", async ({ request }) => {
  const response = await request.get("/app");
  expect(response.status()).toBe(200);

  const html = await response.text();
  expect(html).toMatch(/<html[^>]*\blang="es"/);

  // Ningún nombre de variable de proveedor ni forma de clave conocida debe
  // aparecer en el HTML servido — el frontend nunca debe llevar claves de
  // proveedor (LLM, Socrata, base de datos), solo NEXT_PUBLIC_BACKEND_URL.
  expect(html).not.toContain("GOOGLE_API_KEY");
  expect(html).not.toContain("SOCRATA_APP_TOKEN");
  expect(html).not.toMatch(/AIzaSy[0-9A-Za-z_-]{33}/); // formato de clave de Google API
});
