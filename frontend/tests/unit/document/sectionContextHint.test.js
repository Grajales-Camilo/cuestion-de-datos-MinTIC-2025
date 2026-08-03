import { describe, expect, it } from "vitest";
import {
  SECTION_CONTEXT_HINT_MAX_LENGTH,
  deriveContextHintFromText,
  deriveSectionContextHint,
  extractSectionText,
} from "../../../lib/document/sectionContextHint";

// Todos los documentos ProseMirror de este archivo son dobles sintéticos
// INLINE (estructura mínima para ejercer la extracción de texto), no
// capturas de una corrida real ni fixtures compartidos.
function paragraph(text) {
  return { type: "paragraph", content: [{ type: "text", text }] };
}

describe("extractSectionText — F5-03A, RF-104", () => {
  it("extrae texto de párrafos simples", () => {
    const doc = { type: "doc", content: [paragraph("La cobertura educativa subió en 2022.")] };
    expect(extractSectionText(doc)).toBe("La cobertura educativa subió en 2022.");
  });

  it("extrae texto de encabezados", () => {
    const doc = {
      type: "doc",
      content: [
        { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "Diagnóstico" }] },
        paragraph("Texto del cuerpo."),
      ],
    };
    expect(extractSectionText(doc)).toBe("Diagnóstico Texto del cuerpo.");
  });

  it("extrae texto de listas (bulletList/orderedList/listItem)", () => {
    const doc = {
      type: "doc",
      content: [
        {
          type: "bulletList",
          content: [
            { type: "listItem", content: [paragraph("Primer punto")] },
            { type: "listItem", content: [paragraph("Segundo punto")] },
          ],
        },
      ],
    };
    expect(extractSectionText(doc)).toBe("Primer punto Segundo punto");
  });

  it("extrae texto de blockquote", () => {
    const doc = {
      type: "doc",
      content: [{ type: "blockquote", content: [paragraph("Cita textual del diagnóstico.")] }],
    };
    expect(extractSectionText(doc)).toBe("Cita textual del diagnóstico.");
  });

  it("normaliza espacios y saltos entre bloques a un solo espacio", () => {
    const doc = {
      type: "doc",
      content: [paragraph("Primer párrafo."), paragraph("  Segundo   párrafo.  ")],
    };
    expect(extractSectionText(doc)).toBe("Primer párrafo. Segundo párrafo.");
  });

  it("un párrafo vacío o solo con espacio produce texto vacío", () => {
    expect(extractSectionText({ type: "doc", content: [{ type: "paragraph" }] })).toBe("");
    expect(extractSectionText(paragraph("   "))).toBe("");
  });

  it("los atributos de evidenceCitation nunca se filtran al texto extraído", () => {
    const doc = {
      type: "doc",
      content: [
        paragraph("Texto visible antes de la cita."),
        {
          type: "evidenceCitation",
          attrs: {
            citationId: "cid-secreto-001",
            datasetId: "dataset-secreto-002",
            soqlQuery: "SELECT secreto_columna FROM tabla_secreta",
            sourceUrl: "https://ejemplo.test/secreto",
          },
        },
        paragraph("Texto visible después de la cita."),
      ],
    };
    const extracted = extractSectionText(doc);
    expect(extracted).toBe("Texto visible antes de la cita. Texto visible después de la cita.");
    expect(extracted).not.toContain("cid-secreto-001");
    expect(extracted).not.toContain("dataset-secreto-002");
    expect(extracted).not.toContain("SELECT");
    expect(extracted).not.toContain("secreto");
  });
});

describe("deriveSectionContextHint — F5-03A, RF-104", () => {
  it("isEmpty es true cuando la sección no tiene texto visible", () => {
    const empty = deriveSectionContextHint({ type: "doc", content: [{ type: "paragraph" }] });
    expect(empty).toEqual({ value: "", truncated: false, isEmpty: true });
  });

  it("isEmpty es false y devuelve el texto tal cual cuando cabe dentro del límite", () => {
    const doc = { type: "doc", content: [paragraph("Diagnóstico corto de la sección.")] };
    const result = deriveSectionContextHint(doc);
    expect(result).toEqual({ value: "Diagnóstico corto de la sección.", truncated: false, isEmpty: false });
  });

  it("trunca a <=2000 caracteres respetando límite de palabra, sin cortar a mitad", () => {
    const longWord = "palabra ".repeat(300); // > 2000 caracteres, con espacios frecuentes
    const doc = { type: "doc", content: [paragraph(longWord)] };
    const result = deriveSectionContextHint(doc, { maxLength: SECTION_CONTEXT_HINT_MAX_LENGTH });
    expect(result.value.length).toBeLessThanOrEqual(SECTION_CONTEXT_HINT_MAX_LENGTH);
    expect(result.truncated).toBe(true);
    expect(result.value.endsWith("palabra")).toBe(true); // no corta a mitad de palabra
    expect(result.isEmpty).toBe(false);
  });
});

describe("deriveContextHintFromText — selección real de texto (F5-03A, RF-104)", () => {
  it("normaliza espacios de una selección igual que deriveSectionContextHint", () => {
    const result = deriveContextHintFromText("  cobertura   educativa  ");
    expect(result).toEqual({ value: "cobertura educativa", truncated: false, isEmpty: false });
  });

  it("isEmpty es true cuando la selección es solo espacio", () => {
    expect(deriveContextHintFromText("   ")).toEqual({ value: "", truncated: false, isEmpty: true });
  });

  it("trunca al mismo límite y con la misma regla de corte por palabra", () => {
    const longSelection = "palabra ".repeat(300);
    const result = deriveContextHintFromText(longSelection, { maxLength: SECTION_CONTEXT_HINT_MAX_LENGTH });
    expect(result.value.length).toBeLessThanOrEqual(SECTION_CONTEXT_HINT_MAX_LENGTH);
    expect(result.truncated).toBe(true);
    expect(result.value.endsWith("palabra")).toBe(true);
  });
});
