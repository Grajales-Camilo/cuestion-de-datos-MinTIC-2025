import { describe, expect, it } from "vitest";
import { EMPTY_DOCUMENT_JSON } from "../../../lib/document/documentSchema";
import {
  APPROVED_TEMPLATE_IDS,
  DOCUMENT_MODEL_ERROR_CODES,
  DOCUMENT_MODEL_VERSION,
  FREE_TEMPLATE_ID,
  MGA_TEMPLATE_ID,
  PLAN_DE_DESARROLLO_TEMPLATE_ID,
  TEMPLATE_DOCUMENT_ERROR_CODES,
  createFreeTemplateDocument,
  createMgaTemplateDocument,
  createPlanDeDesarrolloTemplateDocument,
  createTemplateDocument,
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

  it("acepta explícitamente los tres IDs aprobados de RF-101-01: 'libre', 'mga', 'plan-de-desarrollo'", () => {
    for (const templateId of APPROVED_TEMPLATE_IDS) {
      const doc = validTwoSectionDocument();
      doc.templateId = templateId;
      expect(validateDocumentModel(doc)).toEqual({ ok: true });
    }
    expect(APPROVED_TEMPLATE_IDS).toEqual(["libre", "mga", "plan-de-desarrollo"]);
  });

  it("rechaza IDs desconocidos y variantes no canónicas (mayúsculas, espacios, sinónimos) sin repararlas", () => {
    const rejected = [
      "plantilla-desconocida",
      "conpes",
      "policy_brief",
      "LIBRE",
      " libre",
      "libre ",
      "Libre",
      "MGA",
      " mga",
      "mga ",
      "Mga",
      "PLAN-DE-DESARROLLO",
      "plan_de_desarrollo",
      "plan de desarrollo",
      "Plan-De-Desarrollo",
      " plan-de-desarrollo",
      "plan-de-desarrollo ",
    ];
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

describe("createMgaTemplateDocument / createPlanDeDesarrolloTemplateDocument / createTemplateDocument — RF-101-01", () => {
  // Reproduce literalmente la tabla "Decisión" de
  // docs/frontend-v2/adr/ADR-0005-plantilla-mga.md — no resume ni
  // reinterpreta; sirve para comparar por igualdad exacta contra la salida
  // real de la factoría.
  const MGA_EXPECTED_SECTIONS = [
    {
      sectionId: "problematica",
      title: "Problemática",
      description: "Describe el problema central, sus causas, efectos y la situación que se busca transformar.",
    },
    {
      sectionId: "participantes_poblacion_localizacion",
      title: "Participantes, población y localización",
      description:
        "Identifica los actores involucrados, la población afectada y objetivo, y la localización del proyecto.",
    },
    {
      sectionId: "objetivos",
      title: "Objetivos",
      description: "Define el objetivo general y los objetivos específicos relacionados con las causas del problema.",
    },
    {
      sectionId: "alternativas",
      title: "Alternativas de solución",
      description: "Formula y compara las alternativas consideradas para alcanzar los objetivos.",
    },
    {
      sectionId: "preparacion",
      title: "Preparación",
      description:
        "Desarrolla las necesidades, análisis técnico, localización, cadena de valor, costos, riesgos, ingresos y beneficios aplicables.",
    },
    {
      sectionId: "evaluacion_ex_ante",
      title: "Evaluación ex ante",
      description:
        "Presenta el flujo de caja, los indicadores de evaluación financiera, económica o social aplicables y la justificación de la alternativa seleccionada.",
    },
    {
      sectionId: "programacion",
      title: "Programación",
      description:
        "Define productos, indicadores de producto y gestión, metas, fuentes de verificación, supuestos y fuentes de financiación.",
    },
  ];

  // Reproduce literalmente la tabla "Decisión" de
  // docs/frontend-v2/adr/ADR-0004-plantilla-plan-de-desarrollo.md.
  const PLAN_DE_DESARROLLO_EXPECTED_SECTIONS = [
    {
      sectionId: "diagnostico",
      title: "Diagnóstico",
      description: "Describe la situación actual, las problemáticas, brechas y líneas base que sustentan el plan.",
    },
    {
      sectionId: "vision_articulacion",
      title: "Visión y articulación estratégica",
      description:
        "Define la visión de desarrollo, el objetivo general y su articulación con los instrumentos de planeación aplicables.",
    },
    {
      sectionId: "programas_metas",
      title: "Programas, indicadores y metas",
      description:
        "Formula las líneas estratégicas, programas, objetivos específicos, indicadores de resultado y producto, y sus metas.",
    },
    {
      sectionId: "ppi",
      title: "Plan plurianual de inversiones (PPI)",
      description: "Relaciona los programas con sus fuentes de financiación, recursos estimados y vigencias.",
    },
    {
      sectionId: "seguimiento_evaluacion",
      title: "Seguimiento y evaluación",
      description:
        "Define los indicadores, responsables, periodicidad y mecanismos para revisar el avance y los resultados.",
    },
  ];

  it("createMgaTemplateDocument produce exactamente las 7 secciones de ADR-0005, en orden, con content inicialmente vacío", () => {
    const doc = createMgaTemplateDocument();
    expect(validateDocumentModel(doc)).toEqual({ ok: true });
    expect(doc.version).toBe(DOCUMENT_MODEL_VERSION);
    expect(doc.templateId).toBe(MGA_TEMPLATE_ID);
    expect(doc.sections).toHaveLength(7);
    expect(
      doc.sections.map(({ sectionId, title, description }) => ({ sectionId, title, description })),
    ).toEqual(MGA_EXPECTED_SECTIONS);
    for (const section of doc.sections) {
      expect(section.content).toEqual(EMPTY_DOCUMENT_JSON);
    }
  });

  it("createPlanDeDesarrolloTemplateDocument produce exactamente las 5 secciones de ADR-0004, en orden, con content inicialmente vacío", () => {
    const doc = createPlanDeDesarrolloTemplateDocument();
    expect(validateDocumentModel(doc)).toEqual({ ok: true });
    expect(doc.version).toBe(DOCUMENT_MODEL_VERSION);
    expect(doc.templateId).toBe(PLAN_DE_DESARROLLO_TEMPLATE_ID);
    expect(doc.sections).toHaveLength(5);
    expect(
      doc.sections.map(({ sectionId, title, description }) => ({ sectionId, title, description })),
    ).toEqual(PLAN_DE_DESARROLLO_EXPECTED_SECTIONS);
    for (const section of doc.sections) {
      expect(section.content).toEqual(EMPTY_DOCUMENT_JSON);
    }
  });

  it("MGA: ninguna sección comparte referencia de content con otra, ni entre dos llamadas distintas", () => {
    const first = createMgaTemplateDocument();
    const second = createMgaTemplateDocument();

    const contentRefs = new Set(first.sections.map((section) => section.content));
    expect(contentRefs.size).toBe(first.sections.length);

    first.sections[0].content.content.push({ type: "paragraph" });
    expect(second.sections[0].content.content).toHaveLength(1);
  });

  it("Plan de desarrollo: ninguna sección comparte referencia de content con otra, ni entre dos llamadas distintas", () => {
    const first = createPlanDeDesarrolloTemplateDocument();
    const second = createPlanDeDesarrolloTemplateDocument();

    const contentRefs = new Set(first.sections.map((section) => section.content));
    expect(contentRefs.size).toBe(first.sections.length);

    first.sections[0].content.content.push({ type: "paragraph" });
    expect(second.sections[0].content.content).toHaveLength(1);
  });

  it("createTemplateDocument despacha los tres IDs aprobados a documentos válidos con el templateId correcto", () => {
    for (const templateId of APPROVED_TEMPLATE_IDS) {
      const doc = createTemplateDocument(templateId);
      expect(validateDocumentModel(doc)).toEqual({ ok: true });
      expect(doc.templateId).toBe(templateId);
    }
    expect(createTemplateDocument(FREE_TEMPLATE_ID).sections).toHaveLength(1);
    expect(createTemplateDocument(MGA_TEMPLATE_ID).sections).toHaveLength(7);
    expect(createTemplateDocument(PLAN_DE_DESARROLLO_TEMPLATE_ID).sections).toHaveLength(5);
  });

  it("createTemplateDocument falla determinísticamente ante un ID desconocido, sin caer en 'libre'", () => {
    for (const templateId of ["conpes", "policy_brief", "MGA", "Plan-De-Desarrollo", "", null, undefined, 42, {}]) {
      expect(() => createTemplateDocument(templateId)).toThrow(
        new RegExp(TEMPLATE_DOCUMENT_ERROR_CODES.UNKNOWN_TEMPLATE_ID),
      );
    }
  });
});
