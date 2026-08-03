import { describe, expect, it } from "vitest";

/**
 * Verificación programática de contraste WCAG 2.2 AA (≥4.5:1 para texto
 * normal) para cada pareja texto/fondo realmente usada por las
 * primitivas de F1-01. No es una herramienta genérica: solo cubre las
 * parejas que el código de `frontend/components/ui/` produce.
 */
const TOKENS = {
  "blue-900": "#001c40",
  "blue-700": "#002451",
  "blue-500": "#0975ff",
  "blue-100": "#6b91c0",
  "blue-50": "#dee5ed",
  white: "#ffffff",
  "slate-900": "#0f172a",
  "slate-600": "#475569",
  "slate-400": "#94a3b8",
  "slate-100": "#f1f3f5",
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
  ["blue-700", "blue-50"], // Button secundaria en reposo (fondo propio, F1-05-R1)
  ["blue-700", "blue-100"], // Button secundaria/quiet en hover
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
  ["slate-900", "slate-100"], // Encabezados de /app sobre el fondo de página (pages/app.js)
  ["slate-600", "slate-100"], // Etiqueta "Recordar mis investigaciones..." sobre el fondo de página
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

const AA_NON_TEXT = 3;

// blue-500 nunca es texto (ver arriba), pero SÍ es el color del anillo de
// foco (`--cdt-focus-ring-color`) y del icono de paso activo — ambos son
// componentes de interfaz, no texto: el umbral WCAG 1.4.11 aplicable es
// 3:1. Solo contra white/blue-50 — NUNCA contra blue-100 — porque
// `outline-offset` deja ver lo que hay DETRÁS del elemento enfocado (la
// página/zona: blanco o un contenedor blue-50), no el propio relleno del
// elemento; blue-100 en este código solo aparece como borde de 1px o como
// relleno de un chip/badge, jamás como el fondo que rodea a un control
// enfocable (PALETTE-02, confirmado por inspección de
// `components/agent/CopilotPanel.jsx`, `components/ui/Menu.jsx`).
const FOCUS_RING_BACKGROUNDS = ["white", "blue-50"];

describe("contraste WCAG 1.4.11 (no textual) — anillo de foco / icono activo sobre cualquier fondo real", () => {
  it.each(FOCUS_RING_BACKGROUNDS)("blue-500 sobre %s cumple ≥3:1", (bgName) => {
    const ratio = contrastRatio(TOKENS["blue-500"], TOKENS[bgName]);
    expect(ratio).toBeGreaterThanOrEqual(AA_NON_TEXT);
  });
});

// PALETTE-02: blue-100 es ahora también `--cdt-border-color` (bordes
// estructurales, divisores, borde del lienzo) en TODA la interfaz — a
// diferencia de la revisión anterior, debe ser visible por sí solo sobre
// blanco como elemento de interfaz (WCAG 1.4.11, ≥3:1), no solo servir de
// tinte de fondo.
describe("contraste WCAG 1.4.11 (no textual) — blue-100 como borde estructural sobre blanco", () => {
  it("blue-100 sobre white cumple ≥3:1 (borde/divisor/borde del lienzo visibles)", () => {
    const ratio = contrastRatio(TOKENS["blue-100"], TOKENS.white);
    expect(ratio).toBeGreaterThanOrEqual(AA_NON_TEXT);
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
