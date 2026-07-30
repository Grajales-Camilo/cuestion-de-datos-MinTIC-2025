import { describe, expect, it } from "vitest";

/**
 * Verificación programática de contraste WCAG 2.2 AA (≥4.5:1 para texto
 * normal) para cada pareja texto/fondo realmente usada por las
 * primitivas de F1-01. No es una herramienta genérica: solo cubre las
 * parejas que el código de `frontend/components/ui/` produce.
 */
const TOKENS = {
  "blue-900": "#0c2d57",
  "blue-700": "#1d4e89",
  "blue-500": "#2e7cd6",
  "blue-100": "#dbeafe",
  "blue-50": "#eff6ff",
  white: "#ffffff",
  "slate-900": "#0f172a",
  "slate-600": "#475569",
  "slate-400": "#94a3b8",
  success: "#15803d",
  warning: "#b45309",
  error: "#b91c1c",
};

function hexToRgb(hex) {
  const value = hex.replace("#", "");
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  };
}

function channelToLinear(channel) {
  const c = channel / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex) {
  const { r, g, b } = hexToRgb(hex);
  return 0.2126 * channelToLinear(r) + 0.7152 * channelToLinear(g) + 0.0722 * channelToLinear(b);
}

function contrastRatio(hexA, hexB) {
  const lumA = relativeLuminance(hexA);
  const lumB = relativeLuminance(hexB);
  const lighter = Math.max(lumA, lumB);
  const darker = Math.min(lumA, lumB);
  return (lighter + 0.05) / (darker + 0.05);
}

const AA_NORMAL_TEXT = 4.5;

// Cada pareja [texto, fondo] realmente usada en components/ui/*.jsx.
const USED_PAIRS = [
  ["blue-700", "white"], // Button secundaria/quiet, enlaces
  ["blue-900", "white"], // Títulos, hover primaria
  ["slate-900", "white"], // Cuerpo de texto
  ["slate-600", "white"], // Texto secundario
  ["white", "blue-700"], // Button primaria
  ["white", "blue-900"], // Button primaria hover
  ["white", "success"], // Badge verificado
  ["white", "warning"], // Badge advertencia/interrumpido
  ["white", "error"], // Badge fallido, Button destructiva
  ["blue-900", "blue-50"], // Badge no_evidence (tratamiento neutral)
  ["slate-600", "blue-50"], // Texto secundario sobre fondo de sección
];

describe("contraste WCAG 2.2 AA — parejas texto/fondo reales", () => {
  it.each(USED_PAIRS)("%s sobre %s cumple ≥4.5:1", (textName, bgName) => {
    const ratio = contrastRatio(TOKENS[textName], TOKENS[bgName]);
    expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it("blue-500 sobre white NO cumple 4.5:1 para texto normal (por eso nunca es color de texto)", () => {
    const ratio = contrastRatio(TOKENS["blue-500"], TOKENS.white);
    expect(ratio).toBeLessThan(AA_NORMAL_TEXT);
  });
});

describe("prohibición: blue-500 nunca es color de texto normal", () => {
  it("ningún componente de components/ui usa text-cdt-blue-500", async () => {
    const { readFileSync, readdirSync } = await import("node:fs");
    const path = await import("node:path");
    const dir = path.resolve(process.cwd(), "components/ui");
    const files = readdirSync(dir).filter((f) => f.endsWith(".jsx"));
    expect(files.length).toBeGreaterThan(0);
    for (const file of files) {
      const content = readFileSync(path.join(dir, file), "utf-8");
      expect(content, `${file} no debe usar text-cdt-blue-500`).not.toMatch(/text-cdt-blue-500/);
    }
  });
});

describe("pesos tipográficos autorizados — solo font-cdt-normal / font-cdt-bold", () => {
  it("ningún componente de components/ui usa un peso fuera de los dos autorizados", async () => {
    const { readFileSync, readdirSync } = await import("node:fs");
    const path = await import("node:path");
    const dir = path.resolve(process.cwd(), "components/ui");
    const files = readdirSync(dir).filter((f) => f.endsWith(".jsx"));
    const forbidden = /font-(thin|extralight|light|medium|semibold|extrabold|black)\b/;
    for (const file of files) {
      const content = readFileSync(path.join(dir, file), "utf-8");
      expect(content, `${file} usa un peso no autorizado`).not.toMatch(forbidden);
    }
  });
});
