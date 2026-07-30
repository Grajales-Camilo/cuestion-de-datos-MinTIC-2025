import { readFileSync } from "node:fs";
import path from "node:path";
import { Editor } from "@tiptap/core";
import JSZip from "jszip";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../lib/api/redact.js", async () => {
  const actual = await vi.importActual("../../../lib/api/redact.js");
  return { ...actual, redact: vi.fn(actual.redact) };
});

import { redact } from "../../../lib/api/redact.js";
import {
  MANUAL_ENTRY_ERROR_CODES,
  buildManualEntryAttrs,
  validateManualEntryAttrs,
} from "../../../lib/document/manualEntry.js";
import { validateDocumentEditorJson } from "../../../lib/document/documentSchema.js";
import {
  DOCUMENT_MODEL_VERSION,
  FREE_TEMPLATE_ID,
  validateDocumentModel,
} from "../../../lib/document/documentModel.js";
import { createDocumentEditorExtensions } from "../../../lib/document/schema.js";
import { exportDocumentToDocx } from "../../../lib/document/exportDocx.js";

const editors = [];

// Todos los aportes manuales de este archivo son DOBLES SINTÉTICOS INLINE,
// escritos por el usuario para probar el núcleo; no representan backend ni se
// guardan en tests/fixtures/.
const BASE_ENTRY = Object.freeze({
  manualEntryId: "manual-sintetico-001",
  value: "  17,5  ",
  text: null,
  source: "Fuente escrita por el usuario, sintética",
  url: "https://ejemplo.invalid/fuente-sintetica",
  date: "2026-07-29",
  createdAt: "2026-07-29T12:00:00.000Z",
});

function createEditor(content = { type: "doc", content: [{ type: "paragraph" }] }) {
  const editor = new Editor({ extensions: createDocumentEditorExtensions(), content });
  editors.push(editor);
  return editor;
}

function manualNodes(json) {
  return (json.content ?? []).filter((node) => node.type === "manualEntry");
}

function modelWithContent(content) {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: "Documento sintético de prueba",
    sections: [{ sectionId: "sintetica-1", title: "Sección sintética", content }],
  };
}

function blobToArrayBuffer(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

afterEach(() => {
  vi.clearAllMocks();
  while (editors.length > 0) editors.pop().destroy();
});

describe("manualEntry — builder y validación (F7-01, T-506, RF-102/RF-103)", () => {
  it("construye atributos canónicos de forma determinista y conserva el contenido", () => {
    const first = buildManualEntryAttrs(BASE_ENTRY);
    const second = buildManualEntryAttrs(BASE_ENTRY);

    expect(first).toEqual({ ok: true, attrs: BASE_ENTRY });
    expect(second).toEqual(first);
  });

  it.each([
    ["ausente", undefined],
    ["null", null],
    ["vacío", ""],
    ["whitespace", "  \t  "],
  ])("rechaza source %s", (_label, source) => {
    const result = buildManualEntryAttrs({ ...BASE_ENTRY, source });
    expect(result).toEqual({ ok: false, code: MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE });
  });

  it("rechaza value y text ausentes, pero acepta cada uno por separado", () => {
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, value: null, text: null }).code).toBe(
      MANUAL_ENTRY_ERROR_CODES.MISSING_VALUE_OR_TEXT,
    );
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, value: "dato", text: null }).ok).toBe(true);
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, value: null, text: "texto literal" }).ok).toBe(true);
  });

  it("mantiene opcionales ausentes como null", () => {
    const result = buildManualEntryAttrs({
      manualEntryId: BASE_ENTRY.manualEntryId,
      value: 0,
      source: BASE_ENTRY.source,
      createdAt: BASE_ENTRY.createdAt,
    });

    expect(result).toEqual({
      ok: true,
      attrs: {
        manualEntryId: BASE_ENTRY.manualEntryId,
        value: 0,
        text: null,
        source: BASE_ENTRY.source,
        url: null,
        date: null,
        createdAt: BASE_ENTRY.createdAt,
      },
    });
  });

  it("conserva una URL HTTPS absoluta segura y rechaza URL insegura, relativa, protocol-relative o con credenciales", () => {
    expect(buildManualEntryAttrs(BASE_ENTRY)).toMatchObject({ ok: true, attrs: { url: BASE_ENTRY.url } });
    for (const url of [
      "http://ejemplo.invalid/fuente",
      "/fuente",
      "//ejemplo.invalid/fuente",
      "https://usuario:clave@ejemplo.invalid/fuente",
      "javascript:alert(1)",
    ]) {
      expect(buildManualEntryAttrs({ ...BASE_ENTRY, url })).toEqual({
        ok: false,
        code: MANUAL_ENTRY_ERROR_CODES.UNSAFE_URL,
      });
    }
  });

  it("rechaza fecha inválida y nunca la reescribe", () => {
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, date: "2026-02-31" }).code).toBe(
      MANUAL_ENTRY_ERROR_CODES.INVALID_DATE,
    );
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, date: "2026-07-29" }).attrs.date).toBe("2026-07-29");
  });

  it.each([
    "01/02/2026",
    "July 29, 2026",
    "2026-07-29T12:00:00Z",
    "2026-02-29",
  ])("R1 rojo: rechaza date no canónica o imposible: %s", (date) => {
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, date }).code).toBe(
      MANUAL_ENTRY_ERROR_CODES.INVALID_DATE,
    );
  });

  it("R1 rojo: acepta y conserva el día bisiesto canónico 2028-02-29", () => {
    const result = buildManualEntryAttrs({ ...BASE_ENTRY, date: "2028-02-29" });
    expect(result).toMatchObject({ ok: true, attrs: { date: "2028-02-29" } });
  });

  it.each([
    "July 29, 2026 12:00:00",
    "2026-07-29T12:00:00",
    "2026-07-29T07:00:00-05:00",
  ])("R1 rojo: rechaza createdAt no canónico: %s", (createdAt) => {
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, createdAt }).code).toBe(
      MANUAL_ENTRY_ERROR_CODES.INVALID_CREATED_AT,
    );
  });

  it("R1 rojo: acepta createdAt ISO canónico y la salida directa de toISOString", () => {
    const canonical = "2026-07-29T12:00:00.000Z";
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, createdAt: canonical }).ok).toBe(true);
    const generated = new Date().toISOString();
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, createdAt: generated }).ok).toBe(true);
  });

  it("rechaza secretos con código fijo sin filtrar el token ni [REDACTADO]", () => {
    const token = "cdt_rt_SINTETICO_NO_EXPORTAR";
    const result = buildManualEntryAttrs({ ...BASE_ENTRY, text: token, value: null });

    expect(result).toEqual({ ok: false, code: MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED });
    expect(JSON.stringify(result)).not.toContain(token);
    expect(JSON.stringify(result)).not.toContain("[REDACTADO]");
  });

  it("si redact falla inesperadamente también rechaza fail-closed con el mismo código seguro", () => {
    vi.mocked(redact).mockImplementationOnce(() => {
      throw new Error("secreto sintético que no debe salir");
    });

    const result = buildManualEntryAttrs(BASE_ENTRY);
    expect(result).toEqual({ ok: false, code: MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED });
    expect(JSON.stringify(result)).not.toContain("secreto sintético");
  });

  it.each([
    ["authorization", "Bearer secreto"],
    ["token", "secreto"],
    ["campo adicional", "cdt_rt_SINTETICO_EXTRA"],
  ])("R1 rojo: inspecciona un campo adicional sensible (%s) antes de proyectar", (key, value) => {
    const result = buildManualEntryAttrs({ ...BASE_ENTRY, [key]: value });
    expect(result).toEqual({ ok: false, code: MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED });
    expect(JSON.stringify(result)).not.toContain(value);
    expect(JSON.stringify(result)).not.toContain("[REDACTADO]");
  });

  it("R1 rojo: un campo adicional benigno se rechaza como clave desconocida", () => {
    expect(buildManualEntryAttrs({ ...BASE_ENTRY, metadata: "texto" })).toEqual({
      ok: false,
      code: MANUAL_ENTRY_ERROR_CODES.INVALID_ATTRIBUTE_KEYS,
    });
  });

  it("R1 rojo: exactamente las siete claves permitidas sigue siendo válido", () => {
    expect(Object.keys(BASE_ENTRY)).toHaveLength(7);
    expect(buildManualEntryAttrs(BASE_ENTRY)).toMatchObject({ ok: true });
  });
});

describe("manualEntry — nodo, restauración y guarda transaccional", () => {
  it("inserta el nodo especializado, atómico y de bloque; el JSON conserva atributos", () => {
    const editor = createEditor();
    expect(editor.commands.insertManualEntry(BASE_ENTRY)).toBe(true);

    const [node] = manualNodes(editor.getJSON());
    expect(node).toEqual({ type: "manualEntry", attrs: BASE_ENTRY });
    expect(editor.schema.nodes.manualEntry.spec.group).toBe("block");
    expect(editor.schema.nodes.manualEntry.spec.atom).toBe(true);
  });

  it("R1 rojo: la inserción especializada genera manualEntryId y createdAt canónicos", () => {
    const editor = createEditor();
    expect(editor.commands.insertManualEntry({
      value: "dato generado",
      text: null,
      source: "Fuente sintética",
      url: null,
      date: null,
    })).toBe(true);
    const [node] = manualNodes(editor.getJSON());
    expect(node.attrs.manualEntryId).toEqual(expect.any(String));
    expect(node.attrs.manualEntryId).not.toBe("");
    expect(node.attrs.createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  });

  it("insertContent genérico no evade atributos inválidos ni IDs duplicados", () => {
    const editor = createEditor();
    expect(editor.commands.insertManualEntry(BASE_ENTRY)).toBe(true);
    const before = editor.getJSON();

    editor.commands.insertContent({
      type: "manualEntry",
      attrs: { ...BASE_ENTRY, source: "   " },
    });
    expect(editor.getJSON()).toEqual(before);

    editor.commands.insertContent({ type: "manualEntry", attrs: BASE_ENTRY });
    expect(editor.getJSON()).toEqual(before);
  });

  it("HTML pegado no fabrica manualEntry", () => {
    const editor = createEditor();
    editor.commands.insertContent(
      '<div data-manual-entry="true" data-source="fuente sintética">dato pegado</div>',
    );
    expect(manualNodes(editor.getJSON())).toEqual([]);
  });

  it("rechaza manualEntry inválido y duplicado al validar el documento completo", () => {
    const invalid = {
      type: "doc",
      content: [{ type: "manualEntry", attrs: { ...BASE_ENTRY, source: "" } }],
    };
    expect(validateDocumentEditorJson(invalid)).toEqual({
      ok: false,
      code: MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE,
    });

    const duplicate = {
      type: "doc",
      content: [
        { type: "manualEntry", attrs: structuredClone(BASE_ENTRY) },
        { type: "manualEntry", attrs: structuredClone(BASE_ENTRY) },
      ],
    };
    expect(validateDocumentEditorJson(duplicate)).toEqual({
      ok: false,
      code: MANUAL_ENTRY_ERROR_CODES.DUPLICATE_MANUAL_ENTRY_ID,
    });
  });

  it("manualEntry y evidenceCitation pueden coexistir sin convertir ni mezclar sus tipos", () => {
    const content = {
      type: "doc",
      content: [
        { type: "manualEntry", attrs: structuredClone(BASE_ENTRY) },
        {
          type: "evidenceCitation",
          attrs: {
            citationId: "citation-sintetica-001",
            runId: "run-sintetico-001",
            evidenceId: "evidence-sintetica-001",
            datasetId: "dataset-sintetico-001",
            datasetName: "Dataset sintético de prueba",
            publisher: "Publicador sintético",
            soqlQuery: "SELECT valor FROM dataset_sintetico",
            executedAt: "2026-07-29T12:00:00.000Z",
            sourceUrl: "https://ejemplo.invalid/evidence",
            dataUpdatedAt: null,
            dataCutoffAt: null,
            dataCutoffBasis: null,
            qualityScore: 90,
            qualityClassification: "alta",
            eligibilityStatus: "eligible",
            warningRequired: false,
            claims: [],
            insertedAt: "2026-07-29T12:00:00.000Z",
          },
        },
      ],
    };

    expect(validateDocumentEditorJson(content)).toEqual({ ok: true });
    expect(content.content.map((node) => node.type)).toEqual(["manualEntry", "evidenceCitation"]);
  });

  it("el modelo completo rechaza una sección que contiene manualEntry inválido", () => {
    const result = validateDocumentModel(modelWithContent({
      type: "doc",
      content: [{ type: "manualEntry", attrs: { ...BASE_ENTRY, url: "/relativa" } }],
    }));
    expect(result.ok).toBe(false);
    expect(result.code).toBe("INVALID_SECTION_CONTENT");
  });

  it("rechaza IDs manualEntry duplicados incluso entre secciones distintas", () => {
    const content = {
      type: "doc",
      content: [{ type: "manualEntry", attrs: structuredClone(BASE_ENTRY) }],
    };
    const result = validateDocumentModel({
      ...modelWithContent(content),
      sections: [
        { sectionId: "sintetica-1", title: "Una", content: structuredClone(content) },
        { sectionId: "sintetica-2", title: "Dos", content: structuredClone(content) },
      ],
    });
    expect(result.ok).toBe(false);
    expect(result.code).toBe("INVALID_SECTION_CONTENT");
    expect(result.sectionId).toBe("sintetica-2");
  });

  it("el núcleo no importa ni ejecuta APIs de red", () => {
    const sources = [
      "lib/document/manualEntry.js",
      "lib/document/manualEntryNode.js",
      "lib/document/documentSchema.js",
      "lib/document/documentModel.js",
      "lib/document/exportDocxTree.js",
    ].map((file) => readFileSync(path.resolve(process.cwd(), file), "utf8"));
    const source = sources.join("\n").replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(source).not.toMatch(/\b(fetch|XMLHttpRequest|WebSocket)\b/);
    expect(source).not.toMatch(/lib\/(sse|agent)\//);
    expect(source).not.toMatch(/(agentClient|runReducer|EventSource)/);
  });
});

describe("manualEntry — exportación DOCX y OOXML", () => {
  it("genera un DOCX real con prefijo literal y nota al pie de fuente, URL y fecha", async () => {
    const result = await exportDocumentToDocx(modelWithContent({
      type: "doc",
      content: [{ type: "manualEntry", attrs: structuredClone(BASE_ENTRY) }],
    }));
    expect(result.ok).toBe(true);

    const zip = await JSZip.loadAsync(await blobToArrayBuffer(result.blob));
    const documentXml = await zip.file("word/document.xml").async("string");
    const footnotesXml = await zip.file("word/footnotes.xml").async("string");
    const unescaped = (value) => value
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&apos;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, "&");

    expect(unescaped(documentXml)).toContain("Aporte manual — no verificado por el agente");
    expect(unescaped(documentXml)).toContain(BASE_ENTRY.value);
    expect(unescaped(footnotesXml)).toContain(BASE_ENTRY.source);
    expect(unescaped(footnotesXml)).toContain(BASE_ENTRY.url);
    expect(unescaped(footnotesXml)).toContain(BASE_ENTRY.date);
    expect(unescaped(documentXml + footnotesXml)).not.toContain("evidencia verificada");
    expect(unescaped(documentXml + footnotesXml)).not.toContain("SoQL");
  });

  it("rechaza la exportación completa ante secreto o atributo inválido, sin Blob", async () => {
    const secret = await exportDocumentToDocx(modelWithContent({
      type: "doc",
      content: [{ type: "manualEntry", attrs: { ...BASE_ENTRY, text: "cdt_rt_EXPORT_NO" } }],
    }));
    expect(secret.ok).toBe(false);
    expect(secret.blob).toBeUndefined();

    const invalid = await exportDocumentToDocx(modelWithContent({
      type: "doc",
      content: [{ type: "manualEntry", attrs: { ...BASE_ENTRY, url: "/no-es-url" } }],
    }));
    expect(invalid.ok).toBe(false);
    expect(invalid.blob).toBeUndefined();
  });
});
