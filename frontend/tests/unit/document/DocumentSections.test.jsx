import { createRef, useState } from "react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DocumentSections } from "../../../components/document";
import { EMPTY_DOCUMENT_JSON } from "../../../components/canvas/editor";

// ProseMirror mide la selección al desplazar el cursor. jsdom no implementa
// estas geometrías; el doble local evita convertir una deuda ambiental en
// un falso fallo de la lógica del componente (mismo doble que
// `DocumentEditor.test.jsx`).
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
  document.elementFromPoint = () => document.querySelector('[role="textbox"]') ?? document.body;
}

const fixture = JSON.parse(
  readFileSync(path.resolve(process.cwd(), "tests/fixtures/completed-with-claims.json"), "utf8"),
);

function fixtureEvidence() {
  return structuredClone(fixture.answer.evidence[0]);
}

function fixtureClaims() {
  return structuredClone(fixture.answer.claims);
}

// Doble sintético INLINE del modelo documental (estructura mínima de dos
// secciones); la evidencia insertada, en cambio, usa el fixture real
// `completed-with-claims.json` (mismo patrón que `EvidenceInsertionFlow.test.jsx`).
function twoSectionDocument() {
  return {
    version: 1,
    templateId: "libre",
    title: "Documento libre",
    sections: [
      { sectionId: "s1", title: "Sección Uno", content: structuredClone(EMPTY_DOCUMENT_JSON) },
      { sectionId: "s2", title: "Sección Dos", content: structuredClone(EMPTY_DOCUMENT_JSON) },
    ],
  };
}

function citationNodes(json) {
  return json.content.filter((node) => node.type === "evidenceCitation");
}

function manualNodes(json) {
  return json.content.filter((node) => node.type === "manualEntry");
}

function Harness({ initialDocument, onInvestigateSection, sectionsRef, disabled = false }) {
  const [document, setDocument] = useState(initialDocument);

  function handleSectionChange(sectionId, json) {
    setDocument((previous) => ({
      ...previous,
      sections: previous.sections.map((section) =>
        section.sectionId === sectionId ? { ...section, content: json } : section,
      ),
    }));
  }

  return (
    <div className="cdt-v2">
      <DocumentSections
        ref={sectionsRef}
        document={document}
        onSectionChange={handleSectionChange}
        onInvestigateSection={onInvestigateSection}
        disabled={disabled}
      />
    </div>
  );
}

describe("DocumentSections — F5-03A, RF-104", () => {
  it("mantiene el aporte manual disponible aunque la investigación esté deshabilitada", async () => {
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} disabled />);

    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    expect(screen.getAllByRole("button", { name: "Investigar esta sección" })[0]).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Agregar dato manual" })[0]).toBeEnabled();
  });

  it("una sección sin contenido útil no abre la vista previa ni inicia la investigación", async () => {
    const user = userEvent.setup();
    const onInvestigateSection = vi.fn();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={onInvestigateSection} />);

    const [firstButton] = screen.getAllByRole("button", { name: "Investigar esta sección" });
    await user.click(firstButton);

    expect(screen.getByRole("alert")).toHaveTextContent("no tiene contenido suficiente para investigar");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onInvestigateSection).not.toHaveBeenCalled();
  });

  it("la vista previa muestra exactamente el context_hint que se enviaría, y cancelar no llama a onInvestigateSection", async () => {
    const user = userEvent.setup();
    const onInvestigateSection = vi.fn();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={onInvestigateSection} />);

    const sectionOneEditor = await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    const sectionText = "Diagnostico de cobertura educativa en el municipio.";
    await user.click(sectionOneEditor);
    await user.type(sectionOneEditor, sectionText);

    const [firstButton] = screen.getAllByRole("button", { name: "Investigar esta sección" });
    await user.click(firstButton);

    const dialog = await screen.findByRole("dialog", { name: "Investigar esta sección: Sección Uno" });
    const preview = screen.getByRole("region", { name: "Contexto que se enviará (texto literal de la sección)" });
    expect(preview).toHaveTextContent(sectionText);
    expect(preview.textContent).toBe(sectionText);

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(dialog).not.toBeInTheDocument();
    expect(onInvestigateSection).not.toHaveBeenCalled();
  });

  it("confirmar exige una pregunta humana y produce exactamente una llamada con el context_hint literal", async () => {
    const user = userEvent.setup();
    const onInvestigateSection = vi.fn();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={onInvestigateSection} />);

    const sectionOneEditor = await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    const sectionText = "Diagnostico de cobertura educativa en el municipio.";
    await user.click(sectionOneEditor);
    await user.type(sectionOneEditor, sectionText);

    const [firstButton] = screen.getAllByRole("button", { name: "Investigar esta sección" });
    await user.click(firstButton);
    await screen.findByRole("dialog", { name: "Investigar esta sección: Sección Uno" });

    // Sin pregunta escrita por el humano: no fabrica una, no envía nada.
    await user.click(screen.getByRole("button", { name: "Investigar con este contexto" }));
    expect(onInvestigateSection).not.toHaveBeenCalled();
    expect(screen.getByText("La pregunta es obligatoria.")).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Pregunta para investigar"),
      "¿Cuál fue la cobertura educativa reportada este año?",
    );
    await user.click(screen.getByRole("button", { name: "Investigar con este contexto" }));

    expect(onInvestigateSection).toHaveBeenCalledTimes(1);
    expect(onInvestigateSection).toHaveBeenCalledWith(
      { question: "¿Cuál fue la cobertura educativa reportada este año?", contextHint: sectionText },
      "s1",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("con una selección de texto real en la sección, el contexto enviado es solo esa selección", async () => {
    const user = userEvent.setup();
    const onInvestigateSection = vi.fn();
    const ref = createRef();
    render(
      <Harness initialDocument={twoSectionDocument()} onInvestigateSection={onInvestigateSection} sectionsRef={ref} />,
    );

    const sectionOneEditor = await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    const sectionText = "Diagnostico de cobertura educativa en el municipio.";
    await user.click(sectionOneEditor);
    await user.type(sectionOneEditor, sectionText);

    // Selecciona solo "cobertura educativa" mediante el comando real de
    // ProseMirror (mismo patrón que `tests/unit/document/exportDocx.test.js`):
    // jsdom no implementa la geometría de texto que un arrastre de mouse
    // necesitaría para una selección realista.
    const selectedFragment = "cobertura educativa";
    const from = sectionText.indexOf(selectedFragment) + 1; // +1: posición 1 = inicio del texto dentro del párrafo
    const to = from + selectedFragment.length;
    act(() => {
      ref.current.getActiveEditor().commands.setTextSelection({ from, to });
    });

    const [firstButton] = screen.getAllByRole("button", { name: "Investigar esta sección" });
    await user.click(firstButton);

    const dialog = await screen.findByRole("dialog", { name: "Investigar esta sección: Sección Uno" });
    const preview = screen.getByRole("region", { name: "Contexto que se enviará (texto seleccionado en la sección)" });
    expect(preview.textContent).toBe(selectedFragment);

    await user.type(screen.getByLabelText("Pregunta para investigar"), "¿Cuál fue la cobertura reportada?");
    await user.click(screen.getByRole("button", { name: "Investigar con este contexto" }));

    expect(onInvestigateSection).toHaveBeenCalledWith(
      { question: "¿Cuál fue la cobertura reportada?", contextHint: selectedFragment },
      "s1",
    );
    expect(dialog).not.toBeInTheDocument();
  });

  it("sin selección (solo cursor), el comportamiento previo se conserva: se envía la sección completa", async () => {
    const user = userEvent.setup();
    const onInvestigateSection = vi.fn();
    const ref = createRef();
    render(
      <Harness initialDocument={twoSectionDocument()} onInvestigateSection={onInvestigateSection} sectionsRef={ref} />,
    );

    const sectionOneEditor = await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    const sectionText = "Diagnostico de cobertura educativa en el municipio.";
    await user.click(sectionOneEditor);
    await user.type(sectionOneEditor, sectionText);

    // Cursor colapsado al final de la escritura (`from === to`): no cuenta
    // como selección real.
    act(() => {
      const editor = ref.current.getActiveEditor();
      editor.commands.setTextSelection(editor.state.doc.content.size);
    });

    const [firstButton] = screen.getAllByRole("button", { name: "Investigar esta sección" });
    await user.click(firstButton);

    const preview = screen.getByRole("region", { name: "Contexto que se enviará (texto literal de la sección)" });
    expect(preview.textContent).toBe(sectionText);
  });

  it("insertEvidenceCitation inserta solo en la sección indicada, nunca en otra", async () => {
    const ref = createRef();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} sectionsRef={ref} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Dos" });

    const payload = { runId: fixture.run_id, evidence: fixtureEvidence(), claims: fixtureClaims() };
    const inserted = ref.current.insertEvidenceCitation("s2", payload);
    expect(inserted).toBe(true);

    await waitFor(() => expect(citationNodes(ref.current.getSectionJSON("s2"))).toHaveLength(1));
    expect(citationNodes(ref.current.getSectionJSON("s1"))).toHaveLength(0);
  });

  it("una sección de origen inexistente falla cerrado: no inserta en ninguna sección", async () => {
    const ref = createRef();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} sectionsRef={ref} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });

    const payload = { runId: fixture.run_id, evidence: fixtureEvidence(), claims: fixtureClaims() };
    const inserted = ref.current.insertEvidenceCitation("seccion-eliminada", payload);

    expect(inserted).toBe(false);
    expect(citationNodes(ref.current.getSectionJSON("s1"))).toHaveLength(0);
    expect(citationNodes(ref.current.getSectionJSON("s2"))).toHaveLength(0);
  });

  it("insertManualEntry inserta en la sección exacta y nunca en la otra", async () => {
    const ref = createRef();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} sectionsRef={ref} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Dos" });

    expect(ref.current.insertManualEntry("s2", { value: "17,50 unidades", source: "Fuente sintética" })).toBe(true);
    await waitFor(() => expect(manualNodes(ref.current.getSectionJSON("s2"))).toHaveLength(1));
    expect(manualNodes(ref.current.getSectionJSON("s1"))).toHaveLength(0);

    expect(ref.current.insertManualEntry("s1", { text: "Texto sintético", source: "Otra fuente sintética" })).toBe(true);
    await waitFor(() => expect(manualNodes(ref.current.getSectionJSON("s1"))).toHaveLength(1));
    expect(manualNodes(ref.current.getSectionJSON("s2"))).toHaveLength(1);
  });

  it("openManualEntry prellena y guarda solo en la sección indicada; éxito enfoca su editor", async () => {
    const user = userEvent.setup();
    const ref = createRef();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} sectionsRef={ref} />);
    const sectionTwoEditor = await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Dos" });
    const suggestion = {
      entidad: "Entidad oficial sintética",
      url: "https://datos.example.gov.co/recurso",
      por_que: "Puede contener el dato solicitado.",
    };

    expect(ref.current.openManualEntry("s2", suggestion)).toBe(true);
    expect(await screen.findByLabelText(/^Fuente/)).toHaveValue(suggestion.entidad);
    expect(screen.getByLabelText("URL de la fuente (opcional)")).toHaveValue(suggestion.url);
    expect(screen.getByLabelText("Valor (opcional)")).toHaveValue("");
    expect(screen.getByLabelText("Texto o descripción (opcional)")).toHaveValue("");
    expect(screen.getByLabelText("Fecha de la fuente (opcional)")).toHaveValue("");
    expect(screen.getByText(suggestion.por_que)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Valor (opcional)"), "17,50 unidades sintéticas");
    await user.click(screen.getByRole("button", { name: "Guardar aporte manual" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(sectionTwoEditor).toHaveFocus());
    expect(manualNodes(ref.current.getSectionJSON("s1"))).toHaveLength(0);
    expect(manualNodes(ref.current.getSectionJSON("s2"))).toHaveLength(1);
  });

  it("openManualEntry falla cerrado con sección inexistente o sugerencia insegura", async () => {
    const ref = createRef();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} sectionsRef={ref} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    const safe = {
      entidad: "Entidad sintética",
      url: "https://datos.example.gov.co/recurso",
      por_que: "Razón sintética.",
    };

    expect(ref.current.openManualEntry("seccion-eliminada", safe)).toBe(false);
    expect(ref.current.openManualEntry("s1", { ...safe, url: "http://insegura.example" })).toBe(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(manualNodes(ref.current.getSectionJSON("s1"))).toHaveLength(0);
    expect(manualNodes(ref.current.getSectionJSON("s2"))).toHaveLength(0);
  });

  it("la apertura manual desde la sección conserva el formulario vacío", async () => {
    const user = userEvent.setup();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });
    await user.click(screen.getAllByRole("button", { name: "Agregar dato manual" })[0]);
    expect(await screen.findByLabelText(/^Fuente/)).toHaveValue("");
    expect(screen.getByLabelText("URL de la fuente (opcional)")).toHaveValue("");
  });

  it("una sección inexistente falla cerrado sin modificar ningún editor", async () => {
    const ref = createRef();
    render(<Harness initialDocument={twoSectionDocument()} onInvestigateSection={vi.fn()} sectionsRef={ref} />);
    await screen.findByRole("textbox", { name: "Documento de trabajo: Sección Uno" });

    expect(ref.current.insertManualEntry("seccion-eliminada", { value: "dato sintético", source: "Fuente sintética" })).toBe(false);
    expect(manualNodes(ref.current.getSectionJSON("s1"))).toHaveLength(0);
    expect(manualNodes(ref.current.getSectionJSON("s2"))).toHaveLength(0);
  });
});
