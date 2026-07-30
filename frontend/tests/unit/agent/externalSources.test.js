import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../lib/api/redact.js", async () => {
  const actual = await vi.importActual("../../../lib/api/redact.js");
  return { ...actual, redact: vi.fn(actual.redact), actualRedactForTest: actual.redact };
});

import { actualRedactForTest, redact } from "../../../lib/api/redact.js";
import { normalizeExternalSources } from "../../../lib/agent/externalSources.js";

const VALID = Object.freeze({
  entidad: "Entidad pública sintética",
  url: "https://datos.example.gov.co/recurso?q=uno",
  por_que: "Puede contener el dato territorial solicitado.",
});

afterEach(() => {
  vi.mocked(redact).mockReset();
  vi.mocked(redact).mockImplementation(actualRedactForTest);
});

describe("normalizeExternalSources — F7-02B, T-506", () => {
  it("conserva literalmente los tres campos y el orden recibido", () => {
    const second = {
      entidad: "Segunda entidad sintética",
      url: "https://segunda.example.gov.co/fuente",
      por_que: "Otra razón sintética.",
    };
    expect(normalizeExternalSources([VALID, second])).toEqual([VALID, second]);
  });

  it.each([
    [{ ...VALID, entidad: " " }],
    [{ ...VALID, por_que: "" }],
    [{ ...VALID, url: "http://example.gov.co" }],
    [{ ...VALID, url: "javascript:alert(1)" }],
    [{ ...VALID, url: "/relativa" }],
    [{ ...VALID, url: "https://usuario:clave@example.gov.co" }],
    [null],
    [new Date()],
  ])("omite el elemento malformado %#", (item) => {
    expect(normalizeExternalSources([item])).toEqual([]);
  });

  it.each([
    [{ ...VALID, entidad: "cdt_rt_entidad_sintetica" }],
    [{ ...VALID, url: "https://example.gov.co/cdt_rt_url_sintetica" }],
    [{ ...VALID, por_que: "cdt_rt_razon_sintetica" }],
    [{ ...VALID, metadata: { authorization: "Bearer secreto sintético" } }],
    [{ ...VALID, entidad: "[REDACTADO]" }],
  ])("omite secretos incluso en campos aditivos %#", (item) => {
    const result = normalizeExternalSources([item]);
    expect(result).toEqual([]);
    expect(JSON.stringify(result)).not.toContain("[REDACTADO]");
  });

  it("falla cerrado si redact lanza", () => {
    vi.mocked(redact).mockImplementationOnce(() => {
      throw new Error("detalle nativo que no debe salir");
    });
    expect(normalizeExternalSources([VALID])).toEqual([]);
  });

  it("ignora campos aditivos benignos", () => {
    expect(normalizeExternalSources([{ ...VALID, metadata: "texto sintético" }])).toEqual([VALID]);
  });

  it.each([undefined, null, {}, "texto"])("entrada no-array devuelve []: %p", (input) => {
    expect(normalizeExternalSources(input)).toEqual([]);
  });
});
