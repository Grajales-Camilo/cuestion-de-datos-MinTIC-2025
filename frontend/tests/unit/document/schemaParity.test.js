import { readFileSync } from "node:fs";
import path from "node:path";
import { Editor, getSchema } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";
import { createDocumentEditorExtensions } from "../../../lib/document/schema.js";
import { createVisualDocumentEditorExtensions } from "../../../components/canvas/editor/visualExtensions.js";

/**
 * Paridad entre el esquema headless puro (`lib/document/schema.js`,
 * `EvidenceCitationNodeBase`) y el esquema visual de React
 * (`components/canvas/editor/visualExtensions.js`, `EvidenceCitationNode`
 * extendido solo con `addNodeView`). F5-03A-R1: nunca deben divergir dos
 * definiciones manuales del mismo nodo.
 */

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

const editors = [];

function realFixturePayload() {
  return {
    runId: fixture.run_id,
    evidence: structuredClone(fixture.answer.evidence[0]),
    claims: structuredClone(fixture.answer.claims),
    citationId: "citation-parity-001",
    insertedAt: "2026-07-28T13:00:00.000Z",
  };
}

function createEditor(extensions, content = { type: "doc", content: [{ type: "paragraph" }] }) {
  const editor = new Editor({ extensions, content });
  editors.push(editor);
  return editor;
}

function citationNodes(json) {
  return (json.content ?? []).filter((node) => node.type === "evidenceCitation");
}

function manualNodes(json) {
  return (json.content ?? []).filter((node) => node.type === "manualEntry");
}

afterEach(() => {
  while (editors.length > 0) editors.pop().destroy();
});

describe("Paridad de esquema: base pura vs. visual (F5-03A-R1)", () => {
  it("el nodo evidenceCitation expone exactamente los mismos atributos en ambas variantes", () => {
    const pureSchema = getSchema(createDocumentEditorExtensions());
    const visualSchema = getSchema(createVisualDocumentEditorExtensions());

    const pureAttrs = Object.keys(pureSchema.nodes.evidenceCitation.spec.attrs).sort();
    const visualAttrs = Object.keys(visualSchema.nodes.evidenceCitation.spec.attrs).sort();
    expect(visualAttrs).toEqual(pureAttrs);
  });

  it("el nodo manualEntry reutiliza exactamente los mismos atributos en ambas variantes", () => {
    const pureSchema = getSchema(createDocumentEditorExtensions());
    const visualSchema = getSchema(createVisualDocumentEditorExtensions());

    expect(Object.keys(visualSchema.nodes.manualEntry.spec.attrs).sort()).toEqual(
      Object.keys(pureSchema.nodes.manualEntry.spec.attrs).sort(),
    );
  });

  it("insertar el mismo aporte manual sintético conserva atributos y guarda en ambas variantes", () => {
    const pureEditor = createEditor(createDocumentEditorExtensions());
    const visualEditor = createEditor(createVisualDocumentEditorExtensions());
    const payload = {
      value: "17,50 unidades sintéticas",
      text: "Descripción sintética",
      source: "Fuente sintética",
      url: "https://example.gov.co/fuente-sintetica",
      date: "2026-07-29",
    };

    expect(pureEditor.commands.insertManualEntry(payload)).toBe(true);
    expect(visualEditor.commands.insertManualEntry(payload)).toBe(true);
    const pureAttrs = manualNodes(pureEditor.getJSON())[0].attrs;
    const visualAttrs = manualNodes(visualEditor.getJSON())[0].attrs;
    expect(Object.keys(visualAttrs).sort()).toEqual(Object.keys(pureAttrs).sort());
    expect(visualAttrs).toMatchObject(payload);
    expect(pureAttrs).toMatchObject(payload);
  });

  it("insertar la misma cita real produce atributos idénticos en ambas variantes", () => {
    const pureEditor = createEditor(createDocumentEditorExtensions());
    const visualEditor = createEditor(createVisualDocumentEditorExtensions());

    expect(pureEditor.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);
    expect(visualEditor.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);

    const [pureCitation] = citationNodes(pureEditor.getJSON());
    const [visualCitation] = citationNodes(visualEditor.getJSON());
    expect(visualCitation).toEqual(pureCitation);
  });

  it("rechaza el mismo payload inválido (falta un campo obligatorio) en ambas variantes", () => {
    const pureEditor = createEditor(createDocumentEditorExtensions());
    const visualEditor = createEditor(createVisualDocumentEditorExtensions());

    const invalidPayload = realFixturePayload();
    delete invalidPayload.evidence.source_url;
    delete invalidPayload.evidence.citation.source_url;

    expect(pureEditor.commands.insertEvidenceCitation(invalidPayload)).toBe(false);
    expect(visualEditor.commands.insertEvidenceCitation(invalidPayload)).toBe(false);
    expect(citationNodes(pureEditor.getJSON())).toHaveLength(0);
    expect(citationNodes(visualEditor.getJSON())).toHaveLength(0);
  });

  it("validateDocumentEditorJson acepta/rechaza igual un documento con la cita real insertada", async () => {
    const { validateDocumentEditorJson } = await import("../../../lib/document/documentSchema.js");
    const pureEditor = createEditor(createDocumentEditorExtensions());
    pureEditor.commands.insertEvidenceCitation(realFixturePayload());
    const documentWithCitation = pureEditor.getJSON();

    expect(validateDocumentEditorJson(documentWithCitation)).toEqual({ ok: true });

    const tampered = structuredClone(documentWithCitation);
    // `length - 2`, no `length - 1`: `trailingNode` (hallazgo de revisión
    // manual F8-02, `lib/document/schema.js`) añade un párrafo vacío tras
    // la cita — el nodo `evidenceCitation` real queda penúltimo.
    tampered.content[tampered.content.length - 2].attrs.citationId = "";
    expect(validateDocumentEditorJson(tampered).ok).toBe(false);
  });
});
