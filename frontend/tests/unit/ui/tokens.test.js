import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CDT_BLUE_700 } from "../../../lib/design/colorTokens.js";

// Los 12 tokens cromáticos exactos exigidos por el encargo F1-01
// (idénticos a constitution.md Art. V y plan.md §7). Se leen directamente
// del archivo CSS real (fuente única de verdad, no un mock ni una copia)
// para que un cambio accidental de hex en tokens.css rompa esta prueba.
const TOKENS_CSS_PATH = path.resolve(process.cwd(), "styles/tokens.css");
const tokensCss = readFileSync(TOKENS_CSS_PATH, "utf-8");

function readVar(name) {
  const match = tokensCss.match(new RegExp(`${name}:\\s*([^;]+);`));
  return match ? match[1].trim() : undefined;
}

const EXPECTED_TOKENS = {
  "--cdt-blue-900": "#004e8c",
  "--cdt-blue-700": "#0068a8",
  "--cdt-blue-500": "#1f7ee0",
  "--cdt-blue-100": "#cde8ff",
  "--cdt-blue-50": "#f3f9ff",
  "--cdt-white": "#ffffff",
  "--cdt-slate-900": "#0f172a",
  "--cdt-slate-600": "#475569",
  "--cdt-slate-400": "#94a3b8",
  "--cdt-success": "#15803d",
  "--cdt-warning": "#b45309",
  "--cdt-error": "#b91c1c",
};

describe("tokens.css — fuente única de verdad", () => {
  it("expone los 12 tokens cromáticos con su valor hexadecimal exacto", () => {
    for (const [name, expected] of Object.entries(EXPECTED_TOKENS)) {
      const actual = readVar(name)?.toLowerCase();
      expect(actual, `${name} debería ser ${expected}`).toBe(expected);
    }
  });

  it("lib/design/colorTokens.js (espejo JS para Chart.js) nunca se desincroniza de --cdt-blue-700", () => {
    expect(CDT_BLUE_700).toBe(readVar("--cdt-blue-700"));
  });

  it("expone exactamente dos pesos tipográficos: 400 y 700", () => {
    expect(readVar("--cdt-weight-normal")).toBe("400");
    expect(readVar("--cdt-weight-bold")).toBe("700");
  });

  it("define un tamaño táctil mínimo de 44px", () => {
    expect(readVar("--cdt-tap-min")).toBe("44px");
  });

  it("define un anillo de foco visible que nunca depende solo del color (ancho + offset)", () => {
    expect(readVar("--cdt-focus-ring-width")).toBe("2px");
    expect(readVar("--cdt-focus-ring-offset")).toBe("2px");
    expect(readVar("--cdt-focus-ring-color")).toBe("var(--cdt-blue-500)");
  });
});

describe("tailwind.config.js — utilidades cdt-* consumen las variables reales", () => {
  const tailwindConfigPath = path.resolve(process.cwd(), "tailwind.config.js");
  const tailwindConfig = readFileSync(tailwindConfigPath, "utf-8");

  it("no duplica los hexadecimales: cada color cdt-* referencia var(--cdt-*)", () => {
    for (const name of Object.keys(EXPECTED_TOKENS)) {
      const slug = name.replace("--cdt-", "cdt-");
      const re = new RegExp(`"${slug}":\\s*"var\\(${name}\\)"`);
      expect(tailwindConfig, `${slug} debería mapear a var(${name})`).toMatch(re);
    }
  });

  it("no introduce un tercer peso tipográfico", () => {
    const fontWeightBlockMatch = tailwindConfig.match(/fontWeight:\s*{([^}]*)}/);
    expect(fontWeightBlockMatch).toBeTruthy();
    const entries = fontWeightBlockMatch[1].match(/"cdt-[a-z]+"/g) ?? [];
    expect(entries.sort()).toEqual(['"cdt-bold"', '"cdt-normal"']);
  });
});
