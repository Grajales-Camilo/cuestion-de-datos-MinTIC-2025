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
  "--cdt-blue-900": "#001c40",
  "--cdt-blue-700": "#002451",
  "--cdt-blue-500": "#0975ff",
  "--cdt-blue-100": "#6b91c0",
  "--cdt-blue-50": "#dee5ed",
  "--cdt-white": "#ffffff",
  "--cdt-slate-900": "#0f172a",
  "--cdt-slate-600": "#475569",
  "--cdt-slate-400": "#94a3b8",
  "--cdt-slate-100": "#f1f3f5",
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

  it("PALETTE-02: define un radio cero exclusivo para botones (rounded-cdt-none)", () => {
    expect(readVar("--cdt-radius-none")).toBe("0px");
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

  it("PALETTE-02: cdt-none mapea a var(--cdt-radius-none)", () => {
    expect(tailwindConfig).toMatch(/"cdt-none":\s*"var\(--cdt-radius-none\)"/);
  });
});

describe("PALETTE-02 — botones con esquinas rectas, otras primitivas conservan su radio", () => {
  const componentsDir = path.resolve(process.cwd(), "components/ui");
  const buttonJsx = readFileSync(path.join(componentsDir, "Button.jsx"), "utf-8");
  const iconButtonJsx = readFileSync(path.join(componentsDir, "IconButton.jsx"), "utf-8");
  const menuJsx = readFileSync(path.join(componentsDir, "Menu.jsx"), "utf-8");
  const cardJsx = readFileSync(path.join(componentsDir, "Card.jsx"), "utf-8");
  const modalJsx = readFileSync(path.join(componentsDir, "Modal.jsx"), "utf-8");
  const badgeJsx = readFileSync(path.join(componentsDir, "Badge.jsx"), "utf-8");

  it("Button e IconButton usan rounded-cdt-none", () => {
    expect(buttonJsx).toMatch(/rounded-cdt-none/);
    expect(iconButtonJsx).toMatch(/rounded-cdt-none/);
  });

  it("los botones del menú (disparador y opciones) usan rounded-cdt-none", () => {
    // El panel desplegable (contenedor, no botón) debe CONSERVAR su radio.
    expect(menuJsx).toMatch(/rounded-cdt-none/);
    expect(menuJsx).toMatch(/rounded-cdt-lg border border-cdt-blue-100 bg-cdt-white/);
  });

  it("Card, Modal y Badge conservan su radio (no son botones)", () => {
    expect(cardJsx).toMatch(/rounded-cdt-lg/);
    expect(cardJsx).not.toMatch(/rounded-cdt-none/);
    expect(modalJsx).toMatch(/rounded-cdt-lg/);
    expect(modalJsx).not.toMatch(/rounded-cdt-none/);
    expect(badgeJsx).toMatch(/rounded-cdt-full/);
    expect(badgeJsx).not.toMatch(/rounded-cdt-none/);
  });
});
