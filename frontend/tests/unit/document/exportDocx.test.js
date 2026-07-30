import { readFileSync } from "node:fs";
import path from "node:path";
import { Editor } from "@tiptap/core";
import JSZip from "jszip";
import { afterEach, describe, expect, it } from "vitest";
import {
  EXPORT_DOCX_ERROR_CODES,
  exportDocumentToDocx,
  sanitizeExportFilename,
} from "../../../lib/document/exportDocx.js";
import {
  DOCUMENT_MODEL_VERSION,
  FREE_TEMPLATE_ID,
  createFreeTemplateDocument,
} from "../../../lib/document/documentModel.js";
import { createDocumentEditorExtensions } from "../../../lib/document/schema.js";

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

const editors = [];
function createEditor(content) {
  const editor = new Editor({ extensions: createDocumentEditorExtensions(), content });
  editors.push(editor);
  return editor;
}
afterEach(() => {
  while (editors.length > 0) editors.pop().destroy();
});

// Tras insertar un nodo atómico (`evidenceCitation`), Tiptap deja una
// `NodeSelection` sobre ese nodo: una segunda llamada a `insertContent` (lo
// que hace `insertEvidenceCitation` internamente) REEMPLAZARÍA ese nodo en
// vez de añadir uno nuevo a continuación. Se mueve la selección al final del
// documento antes de cada inserción para que las citas se acumulen.
function insertCitationAtDocEnd(editor, payload) {
  // Inserta un párrafo vacío al final (posición de texto válida) antes de
  // mover ahí la selección: evita dejar una `NodeSelection` sobre el átomo
  // recién insertado, que haría que la SIGUIENTE cita lo reemplazara en vez
  // de añadirse a continuación.
  editor.commands.insertContentAt(editor.state.doc.content.size, { type: "paragraph" });
  editor.commands.setTextSelection(editor.state.doc.content.size);
  return editor.commands.insertEvidenceCitation(payload);
}

function documentWithSections(sections, overrides = {}) {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: "Documento de prueba",
    sections,
    ...overrides,
  };
}

// Fixture REAL (completed-with-claims.json): payload mínimo para insertar la
// cita de evidencia verdadera vía `insertEvidenceCitation` (mismo criterio
// que `documentStorage.test.js`/`evidenceCitation.test.js`).
function realFixturePayload({ citationId = "citation-export-001" } = {}) {
  return {
    runId: fixture.run_id,
    evidence: structuredClone(fixture.answer.evidence[0]),
    claims: structuredClone(fixture.answer.claims),
    citationId,
    insertedAt: "2026-07-29T12:00:00.000Z",
  };
}

// DOBLE SINTÉTICO inline (declarado como tal): segunda cita con dataset
// distinguible del fixture real, solo para probar orden/asociación
// determinista entre dos citas (PARTE 2, prueba 12). Nunca se presenta como
// evidencia real.
function syntheticSecondPayload({ citationId = "citation-export-002" } = {}) {
  return {
    runId: "run-sintetico-export-002",
    evidence: {
      evidence_id: "evidence-sintetica-export-002",
      quality: { eligibility_status: "eligible", score_total: 88, classification: "alta" },
      citation: {
        dataset_id: "sint-9999",
        dataset_name: "Dataset sintético de exportación",
        publisher: "Entidad pública sintética",
        soql_query: "SELECT count(*) AS total_sintetico",
        executed_at: "2026-07-29T09:00:00Z",
        source_url: "https://www.datos.gov.co/resource/sint-9999.json",
        data_updated_at: "2026-07-20T00:00:00Z",
      },
    },
    claims: [
      {
        claim_id: "claim-sintetico-export-002",
        evidence_id: "evidence-sintetica-export-002",
        label: "Total sintético",
        display_value: "7",
        unit: null,
        source_hash: "sha256:sintetico",
      },
    ],
    citationId,
    insertedAt: "2026-07-29T09:05:00.000Z",
  };
}

// DOBLE SINTÉTICO inline (declarado como tal): claim con `label: null`
// legítimo (el fixture real no trae ninguno) para probar que F6-02A-R1
// nunca fabrica una etiqueta quando el backend no la afirmó (Art. I).
function syntheticNullLabelPayload({ citationId = "citation-null-label-001" } = {}) {
  return {
    runId: "run-sintetico-null-label",
    evidence: {
      evidence_id: "evidence-sintetica-null-label",
      quality: { eligibility_status: "eligible", score_total: 80, classification: "alta" },
      citation: {
        dataset_id: "null-label-1234",
        dataset_name: "Dataset sintético etiqueta ausente",
        publisher: "Entidad pública sintética",
        soql_query: "SELECT metric_sum_1 AS metric_sum_1",
        executed_at: "2026-07-30T00:00:00Z",
        source_url: "https://www.datos.gov.co/resource/null-label-1234.json",
      },
    },
    claims: [
      {
        claim_id: "claim-null-label-001",
        evidence_id: "evidence-sintetica-null-label",
        label: null,
        display_value: "3,2",
        unit: "%",
        source_hash: "sha256:nulllabel",
      },
    ],
    citationId,
    insertedAt: "2026-07-30T00:05:00.000Z",
  };
}

const RICH_CONTENT_DOC = Object.freeze({
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "Encabezado H2" }] },
    { type: "heading", attrs: { level: 3 }, content: [{ type: "text", text: "Encabezado H3" }] },
    { type: "heading", attrs: { level: 4 }, content: [{ type: "text", text: "Encabezado H4" }] },
    {
      type: "paragraph",
      content: [
        { type: "text", text: "Texto normal, " },
        { type: "text", text: "texto en negrita", marks: [{ type: "bold" }] },
        { type: "text", text: " y " },
        { type: "text", text: "texto en cursiva", marks: [{ type: "italic" }] },
        { type: "text", text: "." },
      ],
    },
    {
      type: "bulletList",
      content: [
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Item sin orden uno" }] }] },
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Item sin orden dos" }] }] },
      ],
    },
    {
      type: "orderedList",
      content: [
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Item ordenado uno" }] }] },
        { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Item ordenado dos" }] }] },
      ],
    },
    { type: "blockquote", content: [{ type: "paragraph", content: [{ type: "text", text: "Texto de la cita en bloque" }] }] },
  ],
});

// jsdom (entorno de estas pruebas) implementa `Blob` pero NO
// `Blob.prototype.arrayBuffer()` (limitación conocida de jsdom 26, no del
// navegador real: ahí `Packer.toBlob(...).arrayBuffer()` sí existe). Se usa
// `FileReader`, que jsdom sí implementa, como puente solo para inspeccionar
// el contenido en pruebas — la API pública de `exportDocx.js` sigue
// devolviendo un `Blob` real sin ningún ajuste para el entorno de pruebas.
function blobToArrayBuffer(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

async function unzipBlob(blob) {
  const buffer = await blobToArrayBuffer(blob);
  return JSZip.loadAsync(buffer);
}

async function xmlPart(zip, name) {
  const file = zip.file(name);
  expect(file, `falta ${name} en el paquete OOXML`).not.toBeNull();
  return file.async("string");
}

function footnoteReferenceIds(documentXml) {
  return [...documentXml.matchAll(/<w:footnoteReference[^>]*w:id="(-?\d+)"/g)].map((m) => m[1]);
}

function footnoteIds(footnotesXml) {
  return [...footnotesXml.matchAll(/<w:footnote[^>]*w:id="(-?\d+)"/g)].map((m) => m[1]);
}

// El paquete OOXML escapa entidades XML (`'` → `&apos;`, `&` → `&amp;`, …)
// dentro del texto de los `<w:t>`. Se desescapa SOLO para comparar en la
// prueba contra el valor almacenado tal cual — nunca para decidir qué se
// exporta.
function xmlUnescape(text) {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&");
}

describe("exportDocumentToDocx — contrato de validación (F6-02A, RF-102/RF-103)", () => {
  it("1) un DocumentModel libre válido genera un DOCX (Blob no vacío)", async () => {
    const doc = documentWithSections([{ sectionId: "s1", title: "Sección 1", content: RICH_CONTENT_DOC }]);

    const result = await exportDocumentToDocx(doc);

    expect(result.ok).toBe(true);
    expect(result.blob).toBeInstanceOf(Blob);
    expect(result.blob.size).toBeGreaterThan(0);
    expect(result.filename).toMatch(/\.docx$/);
  });

  it("2) un documento inválido rechaza la exportación COMPLETA, sin Blob parcial", async () => {
    const invalidDoc = { version: DOCUMENT_MODEL_VERSION, templateId: FREE_TEMPLATE_ID, title: "x", sections: [] };

    const result = await exportDocumentToDocx(invalidDoc);

    expect(result).toEqual({ ok: false, code: EXPORT_DOCX_ERROR_CODES.INVALID_DOCUMENT });
    expect(result.blob).toBeUndefined();
  });

  it("rechaza un templateId no aprobado incluso si tuviera forma válida", async () => {
    // No existe hoy ninguna plantilla distinta de "libre" (D-6 PENDIENTE):
    // se fuerza el campo para probar la segunda barrera, independiente del
    // validador de documentModel.js.
    const doc = createFreeTemplateDocument();
    doc.templateId = "plan-de-desarrollo";

    const result = await exportDocumentToDocx(doc);

    // documentModel.js YA rechaza cualquier templateId distinto de "libre",
    // así que esto llega como INVALID_DOCUMENT, no como UNSUPPORTED_TEMPLATE
    // — ambas rutas cumplen el mismo contrato: rechazo completo.
    expect(result.ok).toBe(false);
    expect(result.blob).toBeUndefined();
  });
});

describe("exportDocumentToDocx — mapeo mínimo de contenido (F6-02A, prueba 3)", () => {
  it("3) título, secciones, párrafos, encabezados h2-h4, listas, blockquote, negrita e cursiva aparecen en el OOXML", async () => {
    const doc = documentWithSections(
      [{ sectionId: "s1", title: "Título de sección", description: "Descripción de sección", content: RICH_CONTENT_DOC }],
      { title: "Título del documento de prueba" },
    );

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");

    expect(documentXml).toContain("Título del documento de prueba");
    expect(documentXml).toContain("Título de sección");
    expect(documentXml).toContain("Descripción de sección");
    expect(documentXml).toContain("Encabezado H2");
    expect(documentXml).toContain("Encabezado H3");
    expect(documentXml).toContain("Encabezado H4");
    expect(documentXml).toContain("Texto normal,");
    expect(documentXml).toContain("Item sin orden uno");
    expect(documentXml).toContain("Item ordenado uno");
    expect(documentXml).toContain("Texto de la cita en bloque");

    // Negrita/cursiva: deben existir como formato real (w:b / w:i), no como
    // texto plano indistinguible.
    expect(documentXml).toMatch(/<w:b\/?>[\s\S]{0,200}texto en negrita|texto en negrita[\s\S]{0,200}<w:b\/?>/);
    expect(documentXml).toContain("texto en negrita");
    expect(documentXml).toContain("texto en cursiva");
    expect(/<w:rPr>[^]*?<w:b\s*\/>[^]*?<\/w:rPr>\s*<w:t[^>]*>texto en negrita/.test(documentXml)).toBe(true);
    expect(/<w:rPr>[^]*?<w:i\s*\/>[^]*?<\/w:rPr>\s*<w:t[^>]*>texto en cursiva/.test(documentXml)).toBe(true);
  });
});

describe("exportDocumentToDocx — EvidenceCitation y notas al pie (F6-02A, pruebas 4-7 y 11-12, RF-103)", () => {
  it("4) una EvidenceCitation real del fixture produce una referencia en el cuerpo y una nota al pie asociada", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    editor.commands.insertContent("Hallazgo citado a continuación.");
    expect(editor.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");
    const footnotesXml = await xmlPart(zip, "word/footnotes.xml");

    const refIds = footnoteReferenceIds(documentXml).filter((id) => Number(id) > 0);
    expect(refIds).toHaveLength(1);
    expect(footnotesXml).toContain(fixture.answer.evidence[0].citation.dataset_name);
  });

  it("5) los seis campos obligatorios de RF-103 aparecen completos y SIN MODIFICACIÓN en la nota al pie", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    editor.commands.insertEvidenceCitation(realFixturePayload());
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const footnotesXml = xmlUnescape(await xmlPart(zip, "word/footnotes.xml"));
    const citation = fixture.answer.evidence[0].citation;

    expect(footnotesXml).toContain(citation.dataset_id);
    expect(footnotesXml).toContain(citation.dataset_name);
    expect(footnotesXml).toContain(citation.publisher);
    expect(footnotesXml).toContain(citation.soql_query);
    expect(footnotesXml).toContain(citation.executed_at);
    expect(footnotesXml).toContain(citation.source_url);
  });

  it("6) warningRequired:true permanece visible en el cuerpo y en la nota al pie", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    const payload = realFixturePayload({ citationId: "citation-warning-001" });
    payload.evidence = { ...payload.evidence, quality: { ...payload.evidence.quality, classification: "no_recomendada" } };
    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");
    const footnotesXml = await xmlPart(zip, "word/footnotes.xml");

    expect(documentXml).toContain("Advertencia");
    expect(footnotesXml).toContain("Advertencia");
    expect(footnotesXml.toLowerCase()).toContain("no es recomendada");
  });

  it("7) una fuente HTTPS segura genera una relación de hipervínculo válida", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    editor.commands.insertEvidenceCitation(realFixturePayload());
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const footnoteRels = await xmlPart(zip, "word/_rels/footnotes.xml.rels");
    expect(footnoteRels).toContain("hyperlink");
    expect(footnoteRels).toContain("https://www.datos.gov.co");
  });

  it("11) cada referencia de nota al pie del cuerpo apunta a una nota que EXISTE en footnotes.xml", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    insertCitationAtDocEnd(editor, realFixturePayload({ citationId: "citation-a" }));
    insertCitationAtDocEnd(editor, syntheticSecondPayload({ citationId: "citation-b" }));
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");
    const footnotesXml = await xmlPart(zip, "word/footnotes.xml");

    const referenced = new Set(footnoteReferenceIds(documentXml).filter((id) => Number(id) > 0));
    const existing = new Set(footnoteIds(footnotesXml));
    for (const id of referenced) {
      expect(existing.has(id), `la referencia a la nota ${id} no existe en footnotes.xml`).toBe(true);
    }
    expect(referenced.size).toBe(2);
  });

  it("12) dos citas distintas mantienen asociación y ORDEN deterministas (por recorrido del documento, no por objeto)", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    insertCitationAtDocEnd(editor, realFixturePayload({ citationId: "citation-a" }));
    insertCitationAtDocEnd(editor, syntheticSecondPayload({ citationId: "citation-b" }));
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const first = await exportDocumentToDocx(doc);
    const second = await exportDocumentToDocx(doc);
    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);

    for (const result of [first, second]) {
      const zip = await unzipBlob(result.blob);
      const footnotesXml = await xmlPart(zip, "word/footnotes.xml");
      const realDatasetIndex = footnotesXml.indexOf(fixture.answer.evidence[0].citation.dataset_name);
      const syntheticDatasetIndex = footnotesXml.indexOf("Dataset sintético de exportación");
      expect(realDatasetIndex).toBeGreaterThanOrEqual(0);
      expect(syntheticDatasetIndex).toBeGreaterThan(realDatasetIndex);
    }
  });
});

describe("exportDocumentToDocx — label ausente nunca se inventa (F6-02A-R1, Art. I)", () => {
  it("un claim con label:null NO produce 'Etiqueta no confirmada' ni ninguna otra etiqueta fabricada, y conserva displayValue/unit literales", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    expect(editor.commands.insertEvidenceCitation(syntheticNullLabelPayload())).toBe(true);
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");
    const footnotesXml = await xmlPart(zip, "word/footnotes.xml");

    for (const xml of [documentXml, footnotesXml]) {
      expect(xml).not.toContain("Etiqueta no confirmada");
      expect(xml.toLowerCase()).not.toContain("sin etiqueta");
      expect(xml.toLowerCase()).not.toContain("etiqueta desconocida");
    }
    // displayValue/unit literales conservados en el cuerpo, sin ningún
    // prefijo de etiqueta inventado.
    expect(documentXml).toContain("3,2");
    expect(documentXml).toContain("%");

    // Trazabilidad completa preservada en la nota al pie pese a la ausencia
    // de label: los 6 campos RF-103 siguen presentes.
    expect(footnotesXml).toContain("null-label-1234");
    expect(footnotesXml).toContain("Dataset sintético etiqueta ausente");
    expect(footnotesXml).toContain("Entidad pública sintética");
    expect(footnotesXml).toContain("SELECT metric_sum_1 AS metric_sum_1");
    expect(footnotesXml).toContain("2026-07-30T00:00:00Z");
  });

  it("una label VÁLIDA se conserva exactamente en el cuerpo (fixture real, label 'Nueca')", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    expect(editor.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");

    expect(documentXml).toContain("Nueca");
    expect(documentXml).toContain("2.368.705.607");
  });

  it("sin claims, la referencia usa la frase neutral 'Evidencia citada' (describe el nodo, no suplanta una etiqueta factual)", async () => {
    // DOBLE SINTÉTICO: cita válida cuyo `claims` queda vacío tras el filtro
    // por `evidence_id` (ningún claim del payload apunta a esta evidencia).
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    const payload = syntheticNullLabelPayload({ citationId: "citation-sin-claims-001" });
    payload.claims = []; // sin claims asociados a esta evidencia
    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const documentXml = await xmlPart(zip, "word/document.xml");
    expect(documentXml).toContain("Evidencia citada");
  });

  it("los 6 campos obligatorios de RF-103 siguen fallando cerrados: sin fallback aunque falte uno", async () => {
    const attrs = {
      citationId: "citation-missing-required-001",
      runId: "run-x",
      evidenceId: "evidence-x",
      datasetId: "abcd-1",
      datasetName: null, // obligatorio ausente: NO debe rellenarse con un valor inventado
      publisher: "Entidad X",
      soqlQuery: "SELECT 1",
      executedAt: "2026-07-29T00:00:00Z",
      sourceUrl: "https://www.datos.gov.co/resource/abcd-1.json",
      eligibilityStatus: "eligible",
      warningRequired: false,
      claims: [],
      insertedAt: "2026-07-29T00:00:00Z",
    };
    const content = { type: "doc", content: [{ type: "evidenceCitation", attrs }] };
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content }]);

    const result = await exportDocumentToDocx(doc);

    expect(result.ok).toBe(false);
    expect(result.blob).toBeUndefined();
  });
});

describe("exportDocumentToDocx — seguridad: URL insegura y datos sensibles (F6-02A, pruebas 8-10, RF-801)", () => {
  it("8) una EvidenceCitation con sourceUrl inseguro (http/credenciales) rechaza la exportación completa", async () => {
    // Hand-crafted: `insertEvidenceCitation` ya rechaza esto en la inserción
    // real (F5-01); se construye el JSON directamente para probar que
    // exportDocumentToDocx también falla cerrado si esa forma llegara por
    // otra vía (p. ej. un documento restaurado de un sobre manipulado).
    const attrs = {
      citationId: "citation-insecure-001",
      runId: "run-x",
      evidenceId: "evidence-x",
      datasetId: "abcd-1",
      datasetName: "Dataset X",
      publisher: "Entidad X",
      soqlQuery: "SELECT 1",
      executedAt: "2026-07-29T00:00:00Z",
      sourceUrl: "https://usuario:clave@www.datos.gov.co/resource/abcd-1.json",
      dataUpdatedAt: null,
      dataCutoffAt: null,
      dataCutoffBasis: null,
      qualityScore: 90,
      qualityClassification: "alta",
      eligibilityStatus: "eligible",
      warningRequired: false,
      claims: [],
      insertedAt: "2026-07-29T00:00:00Z",
    };
    const content = { type: "doc", content: [{ type: "evidenceCitation", attrs }] };
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content }]);

    const result = await exportDocumentToDocx(doc);

    expect(result.ok).toBe(false);
    expect(result.blob).toBeUndefined();
  });

  it.each([
    ["título", (doc) => ({ ...doc, title: "Reporte cdt_rt_secreto123 filtrado" })],
    [
      "texto de sección",
      (doc) => ({
        ...doc,
        sections: [
          {
            ...doc.sections[0],
            content: {
              type: "doc",
              content: [{ type: "paragraph", content: [{ type: "text", text: "cdt_rt_secreto123 en el cuerpo" }] }],
            },
          },
        ],
      }),
    ],
    [
      "descripción de sección",
      (doc) => ({
        ...doc,
        sections: [{ ...doc.sections[0], description: "cdt_rt_secreto123 en la descripción" }],
      }),
    ],
  ])("9) un token cdt_rt_* en %s produce SENSITIVE_DATA_DETECTED con un mensaje/código constante", async (_label, mutate) => {
    const base = documentWithSections([{ sectionId: "s1", title: "Sección", content: RICH_CONTENT_DOC }]);
    const tampered = mutate(base);

    const result = await exportDocumentToDocx(tampered);

    expect(result).toEqual({ ok: false, code: EXPORT_DOCX_ERROR_CODES.SENSITIVE_DATA_DETECTED });
  });

  it("un token en los atributos de una cita ya es rechazado por la fuente de verdad compartida (defensa en profundidad, no exportDocx en solitario)", async () => {
    // A diferencia del título/texto/descripción, un token en `attrs` de una
    // cita YA es detectado por `validateEvidenceCitationAttrs`
    // (`evidenceCitation.js`, F5-01) dentro de `validateDocumentModel` — que
    // exportDocumentToDocx llama PRIMERO. Por eso aquí el código público es
    // INVALID_DOCUMENT, no SENSITIVE_DATA_DETECTED: la exportación falla
    // cerrada de todos modos, solo que en una capa anterior.
    const attrs = {
      citationId: "citation-token-001",
      runId: "run-x",
      evidenceId: "evidence-x",
      datasetId: "abcd-1",
      datasetName: "Dataset cdt_rt_secreto123",
      publisher: "Entidad X",
      soqlQuery: "SELECT 1",
      executedAt: "2026-07-29T00:00:00Z",
      sourceUrl: "https://www.datos.gov.co/resource/abcd-1.json",
      dataUpdatedAt: null,
      dataCutoffAt: null,
      dataCutoffBasis: null,
      qualityScore: 90,
      qualityClassification: "alta",
      eligibilityStatus: "eligible",
      warningRequired: false,
      claims: [],
      insertedAt: "2026-07-29T00:00:00Z",
    };
    const content = { type: "doc", content: [{ type: "evidenceCitation", attrs }] };
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content }]);

    const result = await exportDocumentToDocx(doc);

    expect(result.ok).toBe(false);
    expect(result.blob).toBeUndefined();
  });

  it("10) ningún XML generado (de un documento legítimo) contiene 'token', 'Authorization' ni 'message_dev'", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    editor.commands.insertContent("Texto legítimo sin secretos.");
    editor.commands.insertEvidenceCitation(realFixturePayload());
    const doc = documentWithSections(
      [
        { sectionId: "s1", title: "Sección con contenido enriquecido", description: "Descripción sin secretos", content: RICH_CONTENT_DOC },
        { sectionId: "s2", title: "Sección con evidencia", content: editor.getJSON() },
      ],
      { title: "Documento legítimo" },
    );

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    const names = Object.keys(zip.files).filter((name) => name.endsWith(".xml"));
    for (const name of names) {
      const xml = await zip.file(name).async("string");
      expect(xml).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
      expect(xml.toLowerCase()).not.toContain("authorization");
      expect(xml.toLowerCase()).not.toContain("message_dev");
    }
  });
});

describe("exportDocumentToDocx — nombre de archivo saneado (F6-02A, prueba 14)", () => {
  it("14) sanitizeExportFilename elimina separadores de ruta y caracteres inválidos, y siempre termina en .docx", () => {
    expect(sanitizeExportFilename('Reporte/Política: "Educación" <2026>')).toMatch(/^[A-Za-z0-9._-]+\.docx$/);
    expect(sanitizeExportFilename("../../etc/passwd")).not.toContain("/");
    expect(sanitizeExportFilename("../../etc/passwd")).not.toContain("..");
    expect(sanitizeExportFilename("   ")).toBe("documento-cuestion-de-datos.docx");
    expect(sanitizeExportFilename("")).toBe("documento-cuestion-de-datos.docx");
    expect(sanitizeExportFilename(null)).toBe("documento-cuestion-de-datos.docx");
    expect(sanitizeExportFilename(undefined)).toBe("documento-cuestion-de-datos.docx");
    expect(sanitizeExportFilename(42)).toBe("documento-cuestion-de-datos.docx");
    for (const filename of ["a".repeat(500), "CON", "con"]) {
      expect(sanitizeExportFilename(filename)).toMatch(/\.docx$/);
    }
  });

  it("14) exportDocumentToDocx deriva el nombre real del título del documento", async () => {
    const doc = documentWithSections([{ sectionId: "s1", title: "Sección", content: RICH_CONTENT_DOC }], {
      title: "Diagnóstico / Cobertura: Educación",
    });

    const result = await exportDocumentToDocx(doc);

    expect(result.ok).toBe(true);
    expect(result.filename).toBe("Diagnostico-Cobertura-Educacion.docx");
  });

  it("F6-02A-R1: detecta nombres reservados de Windows incluso con extensión o sufijo", () => {
    for (const reserved of [
      "CON", "con", "CON.txt", "PRN.doc", "AUX.anything", "AUX.x",
      "NUL.x", "NUL",
      "COM1", "com5.bak", "COM9.old",
      "LPT1", "lpt9.old",
    ]) {
      expect(sanitizeExportFilename(reserved), `título "${reserved}" debía caer al fallback`).toBe(
        "documento-cuestion-de-datos.docx",
      );
    }
    // Nombres NO reservados que se parecen a uno: deben conservarse.
    expect(sanitizeExportFilename("CON1")).toBe("CON1.docx");
    expect(sanitizeExportFilename("CON-1")).toBe("CON-1.docx");
    expect(sanitizeExportFilename("CONFIDENCIAL")).toBe("CONFIDENCIAL.docx");
  });

  it("F6-02A-R1: longitud máxima documentada (255, incluida .docx); un título largo se trunca de forma determinista sin quedar vacío", () => {
    const longTitle = "a".repeat(400);
    const result = sanitizeExportFilename(longTitle);

    expect(result.length).toBeLessThanOrEqual(255);
    expect(result).toMatch(/\.docx$/);
    expect(result).not.toBe(".docx"); // nunca vacío antes de la extensión
    // Determinismo: el mismo título produce siempre el mismo recorte.
    expect(sanitizeExportFilename(longTitle)).toBe(result);
  });

  it("F6-02A-R1: nunca termina en punto ni espacio (ni tras truncar)", () => {
    expect(sanitizeExportFilename("Título con punto final.")).not.toMatch(/\.\.docx$/);
    expect(sanitizeExportFilename("Título con punto final.")).not.toMatch(/ \.docx$/);
    // Un título largo que trunca justo sobre un separador tampoco deja '-'/'.' colgando.
    const trunctationEdge = `${"a".repeat(249)}.`.repeat(2);
    const result = sanitizeExportFilename(trunctationEdge);
    expect(result.replace(/\.docx$/, "")).not.toMatch(/[-.]$/);
  });

  it("F6-02A-R1: conserva siempre la extensión .docx y no agrega hash/fecha inventados salvo el fallback existente", () => {
    expect(sanitizeExportFilename("Documento normal")).toBe("Documento-normal.docx");
    expect(sanitizeExportFilename("Documento normal")).not.toMatch(/\d{4}-\d{2}-\d{2}/); // sin fecha inventada
    expect(sanitizeExportFilename("Documento normal")).not.toMatch(/[0-9a-f]{8,}/i); // sin hash inventado
  });
});

describe("exportDocumentToDocx — validez del paquete OOXML (F6-02A, pruebas 13 y 15)", () => {
  it("13) un documento con una cita inválida entre contenido válido NO genera un archivo parcial", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    editor.commands.insertContent("Contenido válido antes de la cita rota.");
    const validSectionContent = editor.getJSON();

    // Sección 2 manipulada directamente (bypass del comando de inserción):
    // le falta `soqlQuery`, uno de los 6 campos obligatorios de RF-103.
    const brokenAttrs = {
      citationId: "citation-broken-001",
      runId: "run-x",
      evidenceId: "evidence-x",
      datasetId: "abcd-1",
      datasetName: "Dataset roto",
      publisher: "Entidad X",
      // soqlQuery ausente a propósito
      executedAt: "2026-07-29T00:00:00Z",
      sourceUrl: "https://www.datos.gov.co/resource/abcd-1.json",
      eligibilityStatus: "eligible",
      warningRequired: false,
      claims: [],
      insertedAt: "2026-07-29T00:00:00Z",
    };
    const brokenSectionContent = { type: "doc", content: [{ type: "evidenceCitation", attrs: brokenAttrs }] };

    const doc = documentWithSections([
      { sectionId: "s1", title: "Sección válida", content: validSectionContent },
      { sectionId: "s2", title: "Sección con cita rota", content: brokenSectionContent },
    ]);

    const result = await exportDocumentToDocx(doc);

    expect(result.ok).toBe(false);
    expect(result.blob).toBeUndefined();
  });

  it("15) la salida es un paquete OOXML válido con, como mínimo, word/document.xml y word/footnotes.xml", async () => {
    const editor = createEditor({ type: "doc", content: [{ type: "paragraph" }] });
    editor.commands.insertEvidenceCitation(realFixturePayload());
    const doc = documentWithSections([{ sectionId: "s1", title: "Evidencia", content: editor.getJSON() }]);

    const result = await exportDocumentToDocx(doc);
    expect(result.ok).toBe(true);

    const zip = await unzipBlob(result.blob);
    expect(zip.file("word/document.xml")).not.toBeNull();
    expect(zip.file("word/footnotes.xml")).not.toBeNull();
    expect(zip.file("[Content_Types].xml")).not.toBeNull();

    // Tamaño del artefacto de prueba (informativo, sin optimización
    // prematura — F6-02A, sección de rendimiento del prompt).
    // eslint-disable-next-line no-console
    console.info(`[exportDocx] tamaño del .docx de prueba: ${result.blob.size} bytes`);
  });
});
