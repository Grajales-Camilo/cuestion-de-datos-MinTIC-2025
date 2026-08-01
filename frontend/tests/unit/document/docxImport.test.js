import { describe, expect, it, vi } from "vitest";
import { validateDocumentEditorJson } from "../../../lib/document/documentSchema.js";
import { validateDocumentModel } from "../../../lib/document/documentModel.js";
import {
  DOCX_IMPORT_ERROR_CODES,
  DOCX_IMPORT_MAX_BYTES,
  DOCX_IMPORT_WARNING_CODES,
} from "../../../lib/document/docxImportPolicy.js";
import { convertDocxArrayBuffer } from "../../../lib/document/docxImportCore.js";
import {
  convertMammothHtmlToDocument,
  sanitizeImportedFilename,
} from "../../../lib/document/docxImportHtml.js";
import {
  addExternalRelationship,
  addUnsupportedSyntheticParts,
  bufferToArrayBuffer,
  createRichSyntheticDocx,
} from "../../fixtures/docxSynthetic.js";

function metadata(buffer, overrides = {}) {
  return {
    name: "informe-sintetico.docx",
    size: buffer.byteLength,
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ...overrides,
  };
}

async function convertBuffer(buffer, overrides) {
  return convertDocxArrayBuffer(bufferToArrayBuffer(buffer), metadata(buffer, overrides));
}

function allNodes(node) {
  return [node, ...(node.content ?? []).flatMap(allNodes)];
}

describe("DOCX-IMPORT-01 — parser/conversor local", () => {
  it("convierte títulos, párrafos, negrita, cursiva, listas y enlace HTTPS a un documento libre válido", async () => {
    const buffer = await createRichSyntheticDocx();
    const converted = await convertBuffer(buffer);
    const result = convertMammothHtmlToDocument(converted.html, {
      filename: "informe-sintetico.docx",
      warnings: converted.warnings,
    });
    const nodes = allNodes(result.model.sections[0].content);

    expect(validateDocumentEditorJson(result.model.sections[0].content)).toEqual({ ok: true });
    expect(validateDocumentModel(result.model)).toEqual({ ok: true });
    expect(result.model).toMatchObject({
      templateId: "libre",
      title: "informe-sintetico",
      sections: [{ sectionId: "contenido-importado", title: "Contenido importado" }],
    });
    expect(nodes.some((node) => node.type === "heading")).toBe(true);
    expect(nodes.some((node) => node.type === "paragraph")).toBe(true);
    expect(nodes.some((node) => node.type === "bulletList")).toBe(true);
    expect(nodes.some((node) => node.type === "orderedList")).toBe(true);
    expect(nodes.flatMap((node) => node.marks ?? []).some((mark) => mark.type === "bold")).toBe(true);
    expect(nodes.flatMap((node) => node.marks ?? []).some((mark) => mark.type === "italic")).toBe(true);
    expect(nodes.flatMap((node) => node.marks ?? []).some((mark) => mark.type === "link")).toBe(true);
    expect(JSON.stringify(result.model)).not.toContain("evidenceCitation");
    expect(JSON.stringify(result.model)).not.toContain("manualEntry");
    expect(JSON.stringify(result.model)).not.toContain("datasetId");
    expect(result.warnings).toEqual([]);
  });

  it("admite enlace HTTP/HTTPS y descarta protocolos inseguros conservando el texto", async () => {
    const http = await createRichSyntheticDocx({ link: "http://example.test/recurso" });
    const httpConverted = await convertBuffer(http);
    const httpResult = convertMammothHtmlToDocument(httpConverted.html, {
      filename: "enlace-http.docx",
      warnings: httpConverted.warnings,
    });
    expect(JSON.stringify(httpResult.model)).toContain("http://example.test/recurso");

    const unsafe = await createRichSyntheticDocx({ link: "javascript:alert(1)" });
    const converted = await convertBuffer(unsafe);
    const result = convertMammothHtmlToDocument(converted.html, {
      filename: "enlace.docx",
      warnings: converted.warnings,
    });

    expect(JSON.stringify(result.model)).toContain("enlace");
    expect(JSON.stringify(result.model)).not.toContain("javascript:");
    expect(result.warnings.some((item) => item.code === DOCX_IMPORT_WARNING_CODES.UNSAFE_LINKS_DISCARDED)).toBe(true);
  });

  it.each([
    ["extensión incorrecta", { name: "archivo.doc" }, DOCX_IMPORT_ERROR_CODES.INVALID_EXTENSION],
    ["MIME incompatible", { type: "application/pdf" }, DOCX_IMPORT_ERROR_CODES.INVALID_MIME_TYPE],
    ["más de 10 MiB", { size: DOCX_IMPORT_MAX_BYTES + 1 }, DOCX_IMPORT_ERROR_CODES.FILE_TOO_LARGE],
  ])("rechaza %s antes de convertir", async (_label, overrides, code) => {
    const buffer = await createRichSyntheticDocx();
    await expect(
      convertDocxArrayBuffer(bufferToArrayBuffer(buffer), metadata(buffer, overrides)),
    ).rejects.toMatchObject({ code });
  });

  it("rechaza archivo corrupto y paquete cifrado/no procesable", async () => {
    const corrupt = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 1, 2, 3, 4]).buffer;
    await expect(
      convertDocxArrayBuffer(corrupt, { name: "corrupto.docx", size: corrupt.byteLength, type: "" }),
    ).rejects.toMatchObject({ code: DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT });

    const encrypted = new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]).buffer;
    await expect(
      convertDocxArrayBuffer(encrypted, { name: "cifrado.docx", size: encrypted.byteLength, type: "" }),
    ).rejects.toMatchObject({ code: DOCX_IMPORT_ERROR_CODES.ENCRYPTED_DOCUMENT });
  });

  it("rechaza una relación externa no permitida", async () => {
    const buffer = await addExternalRelationship(await createRichSyntheticDocx());
    await expect(convertBuffer(buffer)).rejects.toMatchObject({
      code: DOCX_IMPORT_ERROR_CODES.EXTERNAL_RELATIONSHIP,
    });
  });

  it("detecta tablas, imágenes, encabezados/pies, comentarios, cambios, notas, ecuaciones, campos y objetos", async () => {
    const base = await createRichSyntheticDocx({ includeTable: true, includeImage: true });
    const buffer = await addUnsupportedSyntheticParts(base);
    const converted = await convertBuffer(buffer);
    const codes = new Set(converted.warnings.map((item) => item.code));

    for (const code of [
      DOCX_IMPORT_WARNING_CODES.TABLES_SIMPLIFIED,
      DOCX_IMPORT_WARNING_CODES.IMAGES_DISCARDED,
      DOCX_IMPORT_WARNING_CODES.HEADERS_FOOTERS_DISCARDED,
      DOCX_IMPORT_WARNING_CODES.COMMENTS_DISCARDED,
      DOCX_IMPORT_WARNING_CODES.TRACK_CHANGES_SIMPLIFIED,
      DOCX_IMPORT_WARNING_CODES.NOTES_SIMPLIFIED,
      DOCX_IMPORT_WARNING_CODES.EQUATIONS_DISCARDED,
      DOCX_IMPORT_WARNING_CODES.FIELDS_SIMPLIFIED,
      DOCX_IMPORT_WARNING_CODES.EMBEDDED_OBJECTS_DISCARDED,
    ]) expect(codes.has(code)).toBe(true);
  });

  it("sanitiza nombre y contenido sin ejecutar ni montar HTML", () => {
    const result = convertMammothHtmlToDocument(
      '<h1>Título</h1><p>Texto\u202E oculto <u>subrayado</u><script>fetch("https://example.test")</script><a href="data:text/html,x">vínculo</a></p>',
      { filename: '  informe<>:"/\\|?*.docx' },
    );
    expect(result.model.title).toBe("informe");
    expect(JSON.stringify(result.model)).not.toContain('"type":"script"');
    expect(JSON.stringify(result.model)).not.toContain("fetch");
    expect(JSON.stringify(result.model)).not.toContain("data:text");
    expect(JSON.stringify(result.model)).not.toContain("\u202E");
    expect(result.warnings).toContainEqual(expect.objectContaining({
      code: DOCX_IMPORT_WARNING_CODES.UNSUPPORTED_STYLES_SIMPLIFIED,
    }));
    expect(sanitizeImportedFilename("...docx")).toBe("Documento importado");
  });

  it("no realiza solicitudes de red durante preflight, Mammoth ni sanitización", async () => {
    const fetchSpy = vi.fn(() => { throw new Error("network forbidden"); });
    vi.stubGlobal("fetch", fetchSpy);
    const buffer = await createRichSyntheticDocx();
    const converted = await convertBuffer(buffer);
    convertMammothHtmlToDocument(converted.html, { filename: "local.docx", warnings: converted.warnings });
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
