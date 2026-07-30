import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { scanBundle } from "../../../scripts/audit-client-bundle.mjs";

/**
 * RNF-011 — pruebas del escáner con bundles sintéticos temporales, nunca
 * contra un `.next/static/` real (que puede no existir en la máquina que
 * corre `vitest`). Cada archivo se crea en un directorio temporal aislado
 * y se borra al terminar.
 */

let tmpDir;

beforeEach(() => {
  tmpDir = mkdtempSync(path.join(os.tmpdir(), "cdt-bundle-audit-"));
});

afterEach(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

function writeChunk(relativePath, content) {
  const fullPath = path.join(tmpDir, relativePath);
  mkdirSync(path.dirname(fullPath), { recursive: true });
  writeFileSync(fullPath, content, "utf8");
}

describe("scanBundle (RNF-011)", () => {
  it("detecta una clave real de Google/Gemini incrustada", () => {
    writeChunk("chunks/app.js", `const cfg={key:"AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY"};`);
    const { findings } = scanBundle(tmpDir);
    expect(findings).toEqual([
      { file: "chunks/app.js", code: "GOOGLE_GEMINI_KEY_FORMAT", label: expect.any(String), count: 1 },
    ]);
  });

  it("detecta una clave real de Anthropic incrustada", () => {
    writeChunk("chunks/app.js", `var t="sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789";`);
    const { findings } = scanBundle(tmpDir);
    expect(findings.some((f) => f.code === "ANTHROPIC_KEY_FORMAT")).toBe(true);
  });

  it("detecta una clave real de OpenAI incrustada, sin confundirla con Anthropic", () => {
    writeChunk("chunks/app.js", `var t="sk-proj-abcdefghijklmnopqrstuvwxyz0123456789ABCDEF";`);
    const { findings } = scanBundle(tmpDir);
    expect(findings).toEqual([
      { file: "chunks/app.js", code: "OPENAI_KEY_FORMAT", label: expect.any(String), count: 1 },
    ]);
  });

  it("detecta una cadena de conexión de base de datos con credenciales embebidas", () => {
    writeChunk("chunks/app.js", `const url="postgresql://usuario:claveSecreta123@db.interno:5432/cuestion";`);
    const { findings } = scanBundle(tmpDir);
    expect(findings.some((f) => f.code === "DB_CONNECTION_CREDENTIALS")).toBe(true);
  });

  it("detecta un valor real asignado a SOCRATA_APP_TOKEN", () => {
    writeChunk("chunks/app.js", `env={SOCRATA_APP_TOKEN:"abcTokenRealDeSocrata123"};`);
    const { findings } = scanBundle(tmpDir);
    expect(findings.some((f) => f.code === "SOCRATA_APP_TOKEN_VALUE")).toBe(true);
  });

  it("detecta un token de corrida concreto incrustado (RF-801)", () => {
    writeChunk("chunks/app.js", `console.log("cdt_rt_9f8e7d6c5b4a3210filtradoAccidentalmente");`);
    const { findings } = scanBundle(tmpDir);
    expect(findings.some((f) => f.code === "RUNTIME_TOKEN_LEAK")).toBe(true);
  });

  it("el nombre de una variable de entorno SIN valor real no produce falso positivo", () => {
    writeChunk(
      "chunks/app.js",
      `throw new Error("Falta GOOGLE_API_KEY, SOCRATA_APP_TOKEN, ANTHROPIC_API_KEY o OPENAI_API_KEY en el entorno del servidor.");`,
    );
    const { findings } = scanBundle(tmpDir);
    expect(findings).toEqual([]);
  });

  it("el literal de detección cdt_rt_ usado por redact.js no produce falso positivo", () => {
    // Forma real en la que el bundle transpila la regex fuente de
    // lib/api/redact.js: el patrón de detección, no un token concreto.
    writeChunk("chunks/redact.js", String.raw`const TOKEN_PATTERN=/cdt_rt_[A-Za-z0-9_-]+/g;`);
    const { findings } = scanBundle(tmpDir);
    expect(findings).toEqual([]);
  });

  it("nunca imprime el secreto detectado, solo ruta/tipo/código/conteo", () => {
    const secret = "AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY";
    writeChunk("chunks/app.js", `const cfg={key:"${secret}"};`);
    const consoleSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const { findings } = scanBundle(tmpDir);
    // La función de escaneo no imprime nada por sí misma (main() sí
    // imprime el reporte formateado; aquí se confirma que el resultado
    // estructurado tampoco contiene el secreto en ningún campo).
    expect(JSON.stringify(findings)).not.toContain(secret);

    consoleSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it("un bundle limpio (sin patrones de secreto) pasa sin hallazgos", () => {
    writeChunk(
      "chunks/app.js",
      `import{a}from"react";export default function App(){return a("div",null,"Cuestión de Datos");}`,
    );
    writeChunk("chunks/styles.css", `.cdt-blue-900{color:#0b2e59}`);
    const { findings, filesScanned } = scanBundle(tmpDir);
    expect(findings).toEqual([]);
    expect(filesScanned).toBe(2);
  });

  it("ignora extensiones fuera del alcance del bundle cliente (imágenes, fuentes)", () => {
    writeChunk("media/logo.png", "no-es-texto-binario-simulado");
    writeChunk("media/font.woff2", "binario-simulado");
    const { findings, filesScanned } = scanBundle(tmpDir);
    expect(filesScanned).toBe(0);
    expect(findings).toEqual([]);
  });
});
