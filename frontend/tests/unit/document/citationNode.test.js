import { readFileSync } from "node:fs";
import path from "node:path";
import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";
import {
  buildEvidenceCitationAttrs,
  EVIDENCE_CITATION_ERROR_CODES,
  validateEvidenceCitationDocumentJson,
} from "../../../lib/document/evidenceCitation.js";
import { createDocumentEditorExtensions } from "../../../lib/document/schema.js";

const fixture = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"),
    "utf8",
  ),
);
const editors = [];

function realFixturePayload() {
  return {
    runId: fixture.run_id,
    evidence: structuredClone(fixture.answer.evidence[0]),
    claims: structuredClone(fixture.answer.claims),
    citationId: "citation-node-001",
    insertedAt: "2026-07-28T13:00:00.000Z",
  };
}

function createEditor(content = { type: "doc", content: [{ type: "paragraph" }] }) {
  const editor = new Editor({
    extensions: createDocumentEditorExtensions(),
    content,
  });
  editors.push(editor);
  return editor;
}

function citationNodes(json) {
  return (json.content ?? []).filter((node) => node.type === "evidenceCitation");
}

function realFixtureAttrs(overrides = {}) {
  const result = buildEvidenceCitationAttrs(realFixturePayload());
  if (!result.ok) throw new Error(result.code);
  return { ...structuredClone(result.attrs), ...overrides };
}

afterEach(() => {
  while (editors.length > 0) editors.pop().destroy();
});

describe("EvidenceCitationNode (T-504, RF-103)", () => {
  it("inserta la cita completa como nodo atómico y preserva trazabilidad", () => {
    const editor = createEditor();

    expect(editor.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);

    const [citation] = citationNodes(editor.getJSON());
    expect(citation.type).toBe("evidenceCitation");
    expect(citation.attrs.runId).toBe(fixture.run_id);
    expect(citation.attrs.evidenceId).toBe(fixture.answer.evidence[0].evidence_id);
    expect(citation.attrs.eligibilityStatus).toBe("eligible");
    expect(citation.attrs.citationId).toBe("citation-node-001");
    expect(citation.attrs.insertedAt).toBe("2026-07-28T13:00:00.000Z");
  });

  it("R2: inserta y valida documentalmente un claim ambiguo con label=null", () => {
    const editor = createEditor();
    const payload = realFixturePayload();
    payload.claims[0].label = null;
    payload.claims[0].label_status = "ambiguous";

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    const json = editor.getJSON();
    expect(citationNodes(json)[0].attrs.claims[0].label).toBeNull();
    expect(validateEvidenceCitationDocumentJson(json)).toEqual({ ok: true });
  });

  it("R2: inserta un claim histórico sin label y lo conserva como null", () => {
    const editor = createEditor();
    const payload = realFixturePayload();
    delete payload.claims[0].label;
    payload.claims[0].claim = "Texto que no debe convertirse en etiqueta";
    payload.claims[0].columns = ["columna_no_autorizada"];

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    const json = editor.getJSON();
    expect(citationNodes(json)[0].attrs.claims[0].label).toBeNull();
    expect(JSON.stringify(json)).not.toContain(
      "Texto que no debe convertirse en etiqueta",
    );
    expect(JSON.stringify(json)).not.toContain("columna_no_autorizada");
    expect(validateEvidenceCitationDocumentJson(json)).toEqual({ ok: true });
  });

  it.each([
    ["datasetId", "dataset_id"],
    ["datasetName", "dataset_name"],
    ["publisher", "publisher"],
    ["soqlQuery", "soql_query"],
    ["executedAt", "executed_at"],
    ["sourceUrl", "source_url"],
  ])("omitir %s devuelve false y no modifica el JSON", (_attr, sourceField) => {
    const editor = createEditor();
    const before = editor.getJSON();
    const payload = realFixturePayload();
    delete payload.evidence.citation[sourceField];
    delete payload.evidence[sourceField];

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(false);
    expect(editor.getJSON()).toEqual(before);
  });

  it.each([
    "https://usuario:clave@www.datos.gov.co/resource/y97c-tfd9.json",
    "javascript:alert(1)",
  ])("sourceUrl insegura no se inserta: %s", (sourceUrl) => {
    const editor = createEditor();
    const before = editor.getJSON();
    const payload = realFixturePayload();
    payload.evidence.citation.source_url = sourceUrl;

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(false);
    expect(editor.getJSON()).toEqual(before);
  });

  it.each(["blocked", "diagnostic_only", undefined, "desconocida"])(
    "elegibilidad %s no se inserta",
    (eligibilityStatus) => {
      const editor = createEditor();
      const before = editor.getJSON();
      const payload = realFixturePayload();
      if (eligibilityStatus === undefined) {
        delete payload.evidence.quality.eligibility_status;
      } else {
        payload.evidence.quality.eligibility_status = eligibilityStatus;
      }

      expect(editor.commands.insertEvidenceCitation(payload)).toBe(false);
      expect(editor.getJSON()).toEqual(before);
    },
  );

  it("el JSON final no contiene secretos ni campos operativos prohibidos", () => {
    const editor = createEditor();
    const payload = realFixturePayload();
    payload.runAccessToken = "TOKEN_CORRIDA_PRIVADO";
    payload.Authorization = "Bearer AUTH_PRIVADA";
    payload.evidence.message_dev = "DETALLE_DEV_PRIVADO";
    payload.evidence.raw_payload = { secreto: "PAYLOAD_CRUDO_PRIVADO" };
    payload.evidence.error = new Error("ERROR_PRIVADO");
    payload.claims[0].Authorization = "Bearer AUTH_CLAIM_PRIVADA";

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    const serialized = JSON.stringify(editor.getJSON());
    for (const forbidden of [
      "TOKEN_CORRIDA_PRIVADO",
      "AUTH_PRIVADA",
      "DETALLE_DEV_PRIVADO",
      "PAYLOAD_CRUDO_PRIVADO",
      "ERROR_PRIVADO",
      "AUTH_CLAIM_PRIVADA",
      "Authorization",
      "message_dev",
      "raw_payload",
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
  });

  it("mantiene strings HTML/script como datos sin crear elementos arbitrarios", () => {
    const editor = createEditor();
    const payload = realFixturePayload();
    const hostile = '<script>globalThis.__citationXss = true</script><iframe src="x"></iframe>';
    payload.evidence.citation.dataset_name = hostile;
    payload.evidence.dataset_name = hostile;

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    expect(citationNodes(editor.getJSON())[0].attrs.datasetName).toBe(hostile);
    expect(editor.view.dom.querySelector("script, iframe, img")).toBeNull();
    expect(globalThis.__citationXss).toBeUndefined();
  });

  it("HTML pegado que imita data-evidence-citation no fabrica el nodo", () => {
    const editor = createEditor();

    expect(
      editor.commands.insertContent(
        '<div data-evidence-citation="true" data-dataset-id="falso">contenido pegado</div>',
      ),
    ).toBe(true);
    expect(citationNodes(editor.getJSON())).toEqual([]);
  });

  it("restaura el JSON ProseMirror sin perder atributos de la cita", () => {
    const original = createEditor();
    expect(original.commands.insertEvidenceCitation(realFixturePayload())).toBe(true);
    const json = original.getJSON();

    expect(validateEvidenceCitationDocumentJson(json)).toEqual({ ok: true });
    const restored = createEditor(json);
    expect(restored.getJSON()).toEqual(json);
  });

  it("citationId es único dentro del documento y un duplicado no lo modifica", () => {
    const editor = createEditor();
    const payload = realFixturePayload();
    expect(editor.commands.insertEvidenceCitation(payload)).toBe(true);
    const beforeDuplicate = editor.getJSON();

    expect(editor.commands.insertEvidenceCitation(payload)).toBe(false);
    expect(editor.getJSON()).toEqual(beforeDuplicate);
  });

  it("el esquema solo contiene los nodos y marcas autorizados y rechaza h1", () => {
    const editor = createEditor();

    expect(Object.keys(editor.schema.nodes).sort()).toEqual(
      [
        "blockquote",
        "bulletList",
        "doc",
        "evidenceCitation",
        "heading",
        "listItem",
        "manualEntry",
        "orderedList",
        "paragraph",
        "text",
      ].sort(),
    );
    expect(Object.keys(editor.schema.marks).sort()).toEqual(["bold", "italic"]);
    expect(editor.commands.setHeading({ level: 1 })).toBe(false);
    expect(editor.commands.setHeading({ level: 2 })).toBe(true);
  });

  it("los módulos nuevos no introducen persistencia HTML", () => {
    const sources = [
      "lib/document/evidenceCitation.js",
      "lib/document/schema.js",
      "components/canvas/editor/extensions/EvidenceCitationNode.js",
    ].map((file) => readFileSync(path.resolve(process.cwd(), file), "utf8"));

    expect(sources.join("\n")).not.toMatch(/getHTML\s*\(/);
    expect(sources.join("\n")).not.toMatch(/setContent\s*\(\s*[`'\"]/);
  });

  it("una acción desconocida o payload inválido falla sin excepción global", () => {
    const editor = createEditor();
    const before = editor.getJSON();
    let result;

    expect(() => {
      result = editor.commands.insertEvidenceCitation({ action: "desconocida" });
    }).not.toThrow();
    expect(result).toBe(false);
    expect(() => editor.commands.insertEvidenceCitation(null)).not.toThrow();
    expect(editor.commands.insertEvidenceCitation(null)).toBe(false);
    expect(editor.getJSON()).toEqual(before);
  });

  it("R1: insertContent genérico no puede omitir warningRequired", () => {
    const target = createEditor();
    const before = target.getJSON();
    target.commands.insertContent({
      type: "evidenceCitation",
      attrs: realFixtureAttrs({
        qualityClassification: "no_recomendada",
        warningRequired: false,
      }),
    });

    expect(target.getJSON()).toEqual(before);
  });

  it("R1: insertContent genérico acepta atributos válidos", () => {
    const editor = createEditor();

    editor.commands.insertContent({
      type: "evidenceCitation",
      attrs: realFixtureAttrs(),
    });

    expect(citationNodes(editor.getJSON())).toHaveLength(1);
  });

  it("R1: otra clasificación con warningRequired=true no modifica el documento", () => {
    const editor = createEditor();
    const before = editor.getJSON();

    editor.commands.insertContent({
      type: "evidenceCitation",
      attrs: realFixtureAttrs({ warningRequired: true }),
    });

    expect(editor.getJSON()).toEqual(before);
  });

  it("R1: insertContent genérico con citationId duplicado no modifica el documento", () => {
    const editor = createEditor();
    const attrs = realFixtureAttrs();
    editor.commands.insertContent({ type: "evidenceCitation", attrs });
    const beforeDuplicate = editor.getJSON();

    editor.commands.insertContent({ type: "evidenceCitation", attrs });

    expect(editor.getJSON()).toEqual(beforeDuplicate);
  });

  it.each(["blocked", "diagnostic_only", "desconocida", null])(
    "R1: insertContent genérico rechaza eligibilityStatus %s",
    (eligibilityStatus) => {
      const editor = createEditor();
      const before = editor.getJSON();

      editor.commands.insertContent({
        type: "evidenceCitation",
        attrs: realFixtureAttrs({ eligibilityStatus }),
      });

      expect(editor.getJSON()).toEqual(before);
    },
  );

  it("R1: la guarda transaccional rechaza material sensible", () => {
    const editor = createEditor();
    const before = editor.getJSON();

    editor.commands.insertContent({
      type: "evidenceCitation",
      attrs: realFixtureAttrs({ publisher: "Entidad cdt_rt_SECRETO_PLUGIN" }),
    });

    expect(editor.getJSON()).toEqual(before);
  });

  it("R1: JSON no_recomendada con warningRequired=false se rechaza sin corregir", () => {
    const attrs = realFixtureAttrs({
      qualityClassification: "no_recomendada",
      warningRequired: false,
    });
    const json = {
      type: "doc",
      content: [{ type: "evidenceCitation", attrs }],
    };

    expect(validateEvidenceCitationDocumentJson(json)).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.WARNING_REQUIRED_MISMATCH,
    });
    expect(json.content[0].attrs.warningRequired).toBe(false);
  });

  it("R1: JSON con citationId duplicados se rechaza", () => {
    const attrs = realFixtureAttrs();
    const json = {
      type: "doc",
      content: [
        { type: "evidenceCitation", attrs: structuredClone(attrs) },
        { type: "evidenceCitation", attrs: structuredClone(attrs) },
      ],
    };

    expect(validateEvidenceCitationDocumentJson(json)).toEqual({
      ok: false,
      code: EVIDENCE_CITATION_ERROR_CODES.DUPLICATE_CITATION_ID,
    });
  });
});
