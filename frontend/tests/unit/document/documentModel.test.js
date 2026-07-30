import { describe, expect, it } from "vitest";
import { EMPTY_DOCUMENT_JSON } from "../../../lib/document/documentSchema";
import {
  DOCUMENT_MODEL_ERROR_CODES,
  DOCUMENT_MODEL_VERSION,
  FREE_TEMPLATE_ID,
  createFreeTemplateDocument,
  validateDocumentModel,
} from "../../../lib/document/documentModel";

// Doble sintético INLINE: estructura mínima del modelo documental para
// ejercer la validación, no una captura de una corrida real.
function validTwoSectionDocument() {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: "Documento libre",
    sections: [
      { sectionId: "s1", title: "Sección 1", content: structuredClone(EMPTY_DOCUMENT_JSON) },
      { sectionId: "s2", title: "Sección 2", content: structuredClone(EMPTY_DOCUMENT_JSON) },
    ],
  };
}

describe("documentModel — F5-03A, RF-101/RF-104", () => {
  it("la plantilla libre produce un documento válido con sectionId estable", () => {
    const first = createFreeTemplateDocument();
    const second = createFreeTemplateDocument();
    expect(validateDocumentModel(first)).toEqual({ ok: true });
    expect(first.templateId).toBe(FREE_TEMPLATE_ID);
    expect(first.sections).toHaveLength(1);
    expect(first.sections[0].sectionId).toBe(second.sections[0].sectionId);
    expect(first.sections[0].sectionId).toBeTruthy();
  });

  it("createFreeTemplateDocument no comparte referencias entre llamadas (contenido independiente)", () => {
    const first = createFreeTemplateDocument();
    const second = createFreeTemplateDocument();
    first.sections[0].content.content.push({ type: "paragraph" });
    expect(second.sections[0].content.content).toHaveLength(1);
  });

  it("un documento válido de dos secciones pasa la validación", () => {
    expect(validateDocumentModel(validTwoSectionDocument())).toEqual({ ok: true });
  });

  it("rechaza sectionId duplicados en todo el documento", () => {
    const doc = validTwoSectionDocument();
    doc.sections[1].sectionId = doc.sections[0].sectionId;
    const result = validateDocumentModel(doc);
    expect(result).toMatchObject({
      ok: false,
      code: DOCUMENT_MODEL_ERROR_CODES.DUPLICATE_SECTION_ID,
      sectionId: doc.sections[0].sectionId,
    });
  });

  it("JSON inválido en cualquier sección invalida el documento COMPLETO, no solo esa sección", () => {
    const doc = validTwoSectionDocument();
    // La segunda sección (no la primera) tiene un nodo de tipo desconocido:
    // la primera sección sigue siendo válida por sí sola, pero el documento
    // entero debe rechazarse — no hay carga parcial.
    doc.sections[1].content = { type: "doc", content: [{ type: "nodo-inexistente" }] };
    const result = validateDocumentModel(doc);
    expect(result.ok).toBe(false);
    expect(result.code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTION_CONTENT);
    expect(result.sectionId).toBe(doc.sections[1].sectionId);
  });

  it("rechaza version distinta a la soportada", () => {
    const doc = validTwoSectionDocument();
    doc.version = 2;
    expect(validateDocumentModel(doc)).toMatchObject({
      ok: false,
      code: DOCUMENT_MODEL_ERROR_CODES.INVALID_VERSION,
    });
  });

  it("rechaza templateId y title vacíos", () => {
    const withoutTemplate = validTwoSectionDocument();
    withoutTemplate.templateId = "";
    expect(validateDocumentModel(withoutTemplate).code).toBe(
      DOCUMENT_MODEL_ERROR_CODES.INVALID_TEMPLATE_ID,
    );

    const withoutTitle = validTwoSectionDocument();
    withoutTitle.title = "   ";
    expect(validateDocumentModel(withoutTitle).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_TITLE);
  });

  it("rechaza sections vacío, no-array o con sectionId vacío", () => {
    const emptySections = validTwoSectionDocument();
    emptySections.sections = [];
    expect(validateDocumentModel(emptySections).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS);

    const notArray = validTwoSectionDocument();
    notArray.sections = "no-array";
    expect(validateDocumentModel(notArray).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS);

    const emptyId = validTwoSectionDocument();
    emptyId.sections[0].sectionId = "";
    expect(validateDocumentModel(emptyId).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTION_ID);
  });

  it("rechaza explícitamente 'plan-de-desarrollo' (D-6 sigue PENDIENTE, sin normalizar el valor)", () => {
    const doc = validTwoSectionDocument();
    doc.templateId = "plan-de-desarrollo";
    expect(validateDocumentModel(doc)).toEqual({
      ok: false,
      code: DOCUMENT_MODEL_ERROR_CODES.INVALID_TEMPLATE_ID,
    });
  });

  it("rechaza 'mga', cualquier valor desconocido, y variantes con mayúsculas/espacios sin repararlas", () => {
    const rejected = ["mga", "plantilla-desconocida", "LIBRE", " libre", "libre ", "Libre"];
    for (const templateId of rejected) {
      const doc = validTwoSectionDocument();
      doc.templateId = templateId;
      expect(validateDocumentModel(doc).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_TEMPLATE_ID);
    }
  });

  it("rechaza templateId vacío/no-string sin intentar repararlo", () => {
    const rejected = ["", "   ", null, undefined, 42, {}, []];
    for (const templateId of rejected) {
      const doc = validTwoSectionDocument();
      doc.templateId = templateId;
      expect(validateDocumentModel(doc).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_TEMPLATE_ID);
    }
  });

  it("rechaza un documento que no es un objeto plano", () => {
    expect(validateDocumentModel(null).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_DOCUMENT);
    expect(validateDocumentModel([]).code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_DOCUMENT);
    expect(validateDocumentModel("doc").code).toBe(DOCUMENT_MODEL_ERROR_CODES.INVALID_DOCUMENT);
  });
});
