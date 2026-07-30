import { expect, test } from "@playwright/test";

test("Playwright arranca un navegador Chromium real y navega una página en blanco", async ({
  page,
  browser,
}) => {
  await page.goto("about:blank");
  expect(await page.title()).toBe("");

  const userAgent = await page.evaluate(() => navigator.userAgent);
  console.log("[F0-R1 evidencia navegador] userAgent:", userAgent);
  console.log("[F0-R1 evidencia navegador] browser.version():", browser.version());
  expect(userAgent).toContain("Chrome");
  expect(browser.version()).toMatch(/^\d+\./);
});
