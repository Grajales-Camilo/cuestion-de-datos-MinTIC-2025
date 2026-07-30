import { readFileSync } from "node:fs";
import path from "node:path";
import { createRef } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
  DocumentEditor,
  EMPTY_DOCUMENT_JSON,
  validateDocumentEditorJson,
} from "../../../components/canvas/editor";

// Fixture real (mismo método que schemaParity.test.js): nunca un payload
// de cita escrito a mano desde el contrato.
const citationFixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

function realCitationPayload(citationId) {
  return {
    runId: citationFixture.run_id,
    evidence: structuredClone(citationFixture.answer.evidence[0]),
    claims: structuredClone(citationFixture.answer.claims),
    citationId,
    insertedAt: "2026-07-30T13:00:00.000Z",
  };
}

// Busca por TIPO, nunca por índice fijo: F8-02-R1 exige que la prueba
// encuentre el nodo aunque su posición cambie (p. ej. por el párrafo
// final que añade `trailingNode`).
function nodesOfType(json, type) {
  return (json.content ?? []).filter((node) => node.type === type);
}

// ProseMirror mide la selección al desplazar el cursor. jsdom no implementa
// estas geometrías; el doble local evita convertir una deuda ambiental en
// un falso fallo de la lógica del editor.
if (typeof Range !== "undefined" && typeof Range.prototype.getClientRects !== "function") {
  Range.prototype.getClientRects = () => [];
}
if (typeof Range !== "undefined" && typeof Range.prototype.getBoundingClientRect !== "function") {
  Range.prototype.getBoundingClientRect = () => ({
    bottom: 0,
    height: 0,
    left: 0,
    right: 0,
    top: 0,
    width: 0,
  });
}
if (typeof document !== "undefined" && typeof document.elementFromPoint !== "function") {
  document.elementFromPoint = () =>
    document.querySelector('[role="textbox"]') ?? document.body;
}

function renderEditor(props = {}) {
  const ref = createRef();
  const result = render(<DocumentEditor ref={ref} {...props} />);
  return { ref, ...result };
}

describe("DocumentEditor — F5-02, RF-103/RNF-007", () => {
  it("carga un JSON documental válido y expone ProseMirror JSON como salida autoritativa", async () => {
    const initialContent = {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "Contenido válido" }] }],
    };
    const { ref, container } = renderEditor({ initialContent });

    await screen.findByRole("textbox", { name: "Documento de trabajo" });
    await waitFor(() => expect(ref.current).not.toBeNull());
    expect(ref.current.getJSON()).toEqual(initialContent);
    expect(container.textContent).toContain("Contenido válido");
    expect(container.querySelector("[data-document-json]")).toBeNull();
  });

  it("rechaza completamente un documento inicial inválido sin filtrar el payload", () => {
    const invalid = {
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "NO DEBE CARGARSE" }] },
        { type: "image", attrs: { src: "https://example.test/private.png" } },
      ],
    };
    renderEditor({ initialContent: invalid });

    expect(screen.queryByRole("textbox", { name: "Documento de trabajo" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No pudimos abrir el documento porque su contenido no es válido",
    );
    expect(screen.queryByText("NO DEBE CARGARSE")).not.toBeInTheDocument();
    expect(screen.queryByText(/private\.png/)).not.toBeInTheDocument();
  });

  it.each([
    ["Encabezado nivel 2", "heading", { level: 2 }],
    ["Lista con viñetas", "bulletList", null],
    ["Lista numerada", "orderedList", null],
    ["Cita en bloque", "blockquote", null],
  ])("la barra aplica %s dentro del esquema permitido", async (label, nodeType, attrs) => {
    const user = userEvent.setup();
    const { ref } = renderEditor();
    await screen.findByRole("textbox", { name: "Documento de trabajo" });

    await user.click(screen.getByRole("button", { name: label }));
    await waitFor(() => {
      const first = ref.current.getJSON().content[0];
      expect(first.type).toBe(nodeType);
      if (attrs) expect(first.attrs).toMatchObject(attrs);
    });
    expect(screen.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");
  });

  it.each([
    ["Negrita", "bold"],
    ["Cursiva", "italic"],
  ])("la barra aplica la marca %s", async (label, markType) => {
    const user = userEvent.setup();
    const { ref } = renderEditor();
    const textbox = await screen.findByRole("textbox", { name: "Documento de trabajo" });

    await user.click(textbox);
    await user.click(screen.getByRole("button", { name: label }));
    await user.type(textbox, "Texto marcado");

    await waitFor(() => {
      expect(ref.current.getJSON().content[0].content[0].marks).toContainEqual({ type: markType });
    });
  });

  it("tiene nombre, semántica de edición, toolbar accesible y estado de foco", async () => {
    renderEditor();
    const textbox = await screen.findByRole("textbox", { name: "Documento de trabajo" });

    expect(textbox).toHaveAttribute("aria-multiline", "true");
    expect(screen.getByRole("toolbar", { name: "Formato del documento" })).toBeInTheDocument();
    expect(textbox.parentElement.parentElement).toHaveClass("focus-within:ring-2");
  });

  it("valida el JSON con F5-01 antes del esquema cerrado", () => {
    expect(validateDocumentEditorJson(EMPTY_DOCUMENT_JSON)).toEqual({ ok: true });
    expect(validateDocumentEditorJson({ type: "doc", content: [{ type: "table" }] })).toEqual({
      ok: false,
      code: "INVALID_DOCUMENT_SCHEMA",
    });
  });

  it("onChange recibe exactamente editor.getJSON() y nunca HTML", async () => {
    const user = userEvent.setup();
    const updates = [];
    const { ref } = renderEditor({ onChange: (json) => updates.push(json) });
    const textbox = await screen.findByRole("textbox", { name: "Documento de trabajo" });

    await user.type(textbox, "Documento vivo");
    await waitFor(() => expect(updates.length).toBeGreaterThan(0));
    expect(updates.at(-1)).toEqual(ref.current.getJSON());
    expect(JSON.stringify(updates.at(-1))).not.toContain("<p>");
  });

  it("expone insertManualEntry y delega la generación segura de ID y createdAt al comando", async () => {
    const { ref } = renderEditor();
    await screen.findByRole("textbox", { name: "Documento de trabajo" });

    expect(ref.current.insertManualEntry({ value: "17,50 unidades", source: "Fuente sintética" })).toBe(true);
    // `at(-2)`, no `at(-1)`: `trailingNode` (hallazgo de revisión manual
    // F8-02, `lib/document/schema.js`) garantiza un párrafo vacío después
    // de cualquier nodo atómico al final del documento — el último nodo
    // real ahora es siempre ese párrafo, no el `manualEntry` insertado.
    await waitFor(() => expect(ref.current.getJSON().content.at(-2).type).toBe("manualEntry"));

    const attrs = ref.current.getJSON().content.at(-2).attrs;
    expect(attrs).toMatchObject({ value: "17,50 unidades", text: null, source: "Fuente sintética" });
    expect(attrs.manualEntryId).toEqual(expect.any(String));
    expect(attrs.createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  });

  // F8-02-R1 — regresión conductual de D-5 (revisión manual F8-02): con
  // `trailingNode` deshabilitado, insertar un nodo atómico al final del
  // documento y luego escribir con el editor real (no manipular JSON a
  // mano) SELECCIONABA el nodo completo — sin cursor de texto posible tras
  // él — y escribir lo REEMPLAZABA por completo. Estas dos pruebas buscan
  // el nodo por TIPO/ATRIBUTO (`nodesOfType`), nunca por índice fijo, y
  // ejercen la interacción real que disparaba el defecto: insertar (que ya
  // deja el editor enfocado al final, `DocumentEditor.jsx:insertEvidenceCitation`/
  // `insertManualEntry`) y escribir de inmediato con `userEvent`.
  it("D-5: escribir con el editor real justo después de insertar una cita al final conserva la cita y el texto en un párrafo posterior", async () => {
    const user = userEvent.setup();
    const { ref } = renderEditor();
    const textbox = await screen.findByRole("textbox", { name: "Documento de trabajo" });

    const citationId = "citation-doc-editor-d5-001";
    expect(ref.current.insertEvidenceCitation(realCitationPayload(citationId))).toBe(true);
    await waitFor(() => expect(nodesOfType(ref.current.getJSON(), "evidenceCitation")).toHaveLength(1));
    const citationBeforeTyping = nodesOfType(ref.current.getJSON(), "evidenceCitation")[0];
    expect(citationBeforeTyping.attrs.citationId).toBe(citationId);

    // `insertEvidenceCitation` deja la selección de ProseMirror en el
    // párrafo final de forma síncrona, pero Tiptap difiere el foco DOM real
    // a un `requestAnimationFrame` (`@tiptap/core/commands/focus.ts`, "For
    // React we have to focus asynchronously"). Si `userEvent.type` escribe
    // antes de que ese foco aterrice, sintetiza su propio clic sobre un
    // `contenteditable` sin geometría real (jsdom) y puede reubicar el
    // cursor de forma impredecible. Se espera el foco real observable, no
    // un tiempo fijo.
    await waitFor(() => expect(document.activeElement).toBe(textbox));

    const typedText = "Texto escrito justo despues de insertar la cita.";
    await user.type(textbox, typedText);

    await waitFor(() => {
      const json = ref.current.getJSON();
      const citationsAfter = nodesOfType(json, "evidenceCitation");
      expect(citationsAfter).toHaveLength(1);
      expect(citationsAfter[0]).toEqual(citationBeforeTyping); // la MISMA cita, intacta

      const citationIndex = json.content.findIndex((node) => node.type === "evidenceCitation");
      const nodesAfterCitation = json.content.slice(citationIndex + 1);
      const typedTextLanded = nodesAfterCitation.some(
        (node) =>
          node.type === "paragraph" &&
          (node.content ?? []).some((inline) => inline.text?.includes(typedText)),
      );
      expect(typedTextLanded).toBe(true);
    });
  });

  it("D-5: escribir con el editor real justo después de insertar un aporte manual al final conserva el aporte y el texto en un párrafo posterior", async () => {
    const user = userEvent.setup();
    const { ref } = renderEditor();
    const textbox = await screen.findByRole("textbox", { name: "Documento de trabajo" });

    expect(
      ref.current.insertManualEntry({ value: "42 unidades sintéticas D-5", source: "Fuente sintética D-5" }),
    ).toBe(true);
    await waitFor(() => expect(nodesOfType(ref.current.getJSON(), "manualEntry")).toHaveLength(1));
    const manualBeforeTyping = nodesOfType(ref.current.getJSON(), "manualEntry")[0];

    // Ver comentario equivalente en el caso D-5 de EvidenceCitation: el
    // foco DOM real llega en un `requestAnimationFrame` posterior a la
    // selección de ProseMirror. Se espera esa condición observable antes
    // de escribir, no un tiempo fijo.
    await waitFor(() => expect(document.activeElement).toBe(textbox));

    const typedText = "Texto escrito justo despues del aporte manual.";
    await user.type(textbox, typedText);

    await waitFor(() => {
      const json = ref.current.getJSON();
      const manualAfter = nodesOfType(json, "manualEntry");
      expect(manualAfter).toHaveLength(1);
      expect(manualAfter[0]).toEqual(manualBeforeTyping); // el MISMO aporte, intacto

      const manualIndex = json.content.findIndex((node) => node.type === "manualEntry");
      const nodesAfterManual = json.content.slice(manualIndex + 1);
      const typedTextLanded = nodesAfterManual.some(
        (node) =>
          node.type === "paragraph" &&
          (node.content ?? []).some((inline) => inline.text?.includes(typedText)),
      );
      expect(typedTextLanded).toBe(true);
    });
  });
});
