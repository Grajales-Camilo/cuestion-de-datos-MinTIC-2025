import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { devOnlyGetStaticProps } from "../../../lib/gallery/devOnlyGuard";

describe("galería /_dev/ui — disponibilidad (lib/gallery/devOnlyGuard.js real)", () => {
  it("en producción, devuelve notFound:true (404 real, no un simple null)", () => {
    expect(devOnlyGetStaticProps({ NODE_ENV: "production" })).toEqual({ notFound: true });
  });

  it("fuera de producción, devuelve props normales (galería disponible)", () => {
    expect(devOnlyGetStaticProps({ NODE_ENV: "development" })).toEqual({ props: {} });
    expect(devOnlyGetStaticProps({ NODE_ENV: "test" })).toEqual({ props: {} });
    expect(devOnlyGetStaticProps({})).toEqual({ props: {} });
  });
});

describe("galería /_dev/ui — límites de F1-01 (sin conectar el agente)", () => {
  const source = readFileSync(path.resolve(process.cwd(), "pages/_dev/ui.js"), "utf-8");

  it("usa el guard real de disponibilidad (lib/gallery/devOnlyGuard), no una copia", () => {
    expect(source).toMatch(/devOnlyGetStaticProps/);
  });

  // Se buscan sentencias `import ... from "...";` reales, no cualquier
  // mención textual — el propio JSDoc del archivo nombra estos módulos
  // a propósito para documentar que están deliberadamente fuera del
  // alcance de F1-01.
  const importLines = source.split("\n").filter((line) => line.trim().startsWith("import "));

  it("no importa el cliente HTTP del agente", () => {
    expect(importLines.some((line) => line.includes("agentClient"))).toBe(false);
  });

  it("no importa el transporte SSE", () => {
    expect(importLines.some((line) => line.includes("streamRun") || line.includes("parseSseChunk"))).toBe(false);
  });

  it("no importa el reducer de estado del agente", () => {
    expect(importLines.some((line) => line.includes("runReducer"))).toBe(false);
  });

  it("incluye el valor largo real de la corrida, sin redondear, para probar reflujo", () => {
    expect(source).toContain("3,9660000000000000");
  });
});
