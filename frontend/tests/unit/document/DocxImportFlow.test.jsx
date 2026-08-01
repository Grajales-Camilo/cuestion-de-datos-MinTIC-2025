import { createRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocxImportFlow } from "../../../components/document/DocxImportFlow.jsx";
import { createFreeTemplateDocument } from "../../../lib/document/documentModel.js";
import { DOCX_IMPORT_ERROR_CODES, DocxImportError } from "../../../lib/document/docxImportPolicy.js";
import { analyzeDocxFile } from "../../../lib/document/docxImportClient.js";

vi.mock("../../../lib/document/docxImportClient.js", () => ({
  analyzeDocxFile: vi.fn(),
  createDocxImportWorker: vi.fn(),
}));

function importedResult() {
  const model = createFreeTemplateDocument();
  model.title = "archivo-sintetico";
  model.sections[0] = {
    sectionId: "contenido-importado",
    title: "Contenido importado",
    content: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "Texto importado" }] }] },
  };
  return {
    model,
    file: { name: "archivo-sintetico.docx", size: 2048, type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
    recognized: { headings: 1, paragraphs: 2, bold: 1, italic: 1, orderedLists: 1, unorderedLists: 1, links: 1 },
    warnings: [{ code: "IMAGES_DISCARDED", count: 1, disposition: "descartado" }],
  };
}

function currentDocument({ withContent = true } = {}) {
  const document = createFreeTemplateDocument();
  if (withContent) {
    document.sections[0].content = {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "Contenido actual" }] }],
    };
  }
  return document;
}

function Harness({ document = currentDocument(), onImport = vi.fn(), onFeedback = vi.fn() }) {
  const flowRef = createRef();
  const returnFocusRef = createRef();
  return (
    <div className="cdt-v2">
      <button ref={returnFocusRef} type="button" onClick={() => flowRef.current.selectFile()}>Importar</button>
      <DocxImportFlow
        ref={flowRef}
        currentDocument={document}
        onImport={onImport}
        onFeedback={onFeedback}
        returnFocusRef={returnFocusRef}
      />
    </div>
  );
}

async function uploadSyntheticFile(container) {
  const input = container.querySelector('input[type="file"]');
  const file = new File([new Uint8Array([1, 2, 3])], "archivo-sintetico.docx", {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("DocxImportFlow — DOCX-IMPORT-01", () => {
  beforeEach(() => vi.clearAllMocks());

  it("muestra resumen, contenido reconocido, advertencias y privacidad antes de reemplazar", async () => {
    analyzeDocxFile.mockResolvedValue(importedResult());
    const { container } = render(<Harness />);
    await uploadSyntheticFile(container);

    expect(await screen.findByRole("dialog", { name: "Resumen de importación" })).toBeInTheDocument();
    expect(screen.getByText("archivo-sintetico.docx")).toBeInTheDocument();
    expect(screen.getByText("1 encabezados")).toBeInTheDocument();
    expect(screen.getByText("Las imágenes se descartaron.")).toBeInTheDocument();
    expect(screen.getByText(/no se convertirá en evidencia verificada/i)).toBeInTheDocument();
  });

  it("cancelar o cerrar el resumen no modifica el documento y devuelve el foco", async () => {
    const user = userEvent.setup();
    const onImport = vi.fn();
    const original = currentDocument();
    const snapshot = structuredClone(original);
    analyzeDocxFile.mockResolvedValue(importedResult());
    const { container } = render(<Harness document={original} onImport={onImport} />);
    const trigger = screen.getByRole("button", { name: "Importar" });
    trigger.focus();
    await uploadSyntheticFile(container);
    await screen.findByRole("dialog", { name: "Resumen de importación" });
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    expect(onImport).not.toHaveBeenCalled();
    expect(original).toEqual(snapshot);
  });

  it("un error deja intacto el documento y se anuncia con recuperación clara", async () => {
    const onImport = vi.fn();
    const onFeedback = vi.fn();
    const original = currentDocument();
    const snapshot = structuredClone(original);
    analyzeDocxFile.mockRejectedValue(new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT));
    const { container } = render(<Harness document={original} onImport={onImport} onFeedback={onFeedback} />);
    await uploadSyntheticFile(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("corrupto o incompleto");
    expect(screen.getByText("El documento actual no cambió.")).toBeInTheDocument();
    expect(onFeedback).toHaveBeenLastCalledWith(expect.stringContaining("Error de importación"));
    expect(onImport).not.toHaveBeenCalled();
    expect(original).toEqual(snapshot);
  });

  it("con contenido actual exige una segunda confirmación antes de crear el documento libre", async () => {
    const user = userEvent.setup();
    const onImport = vi.fn();
    analyzeDocxFile.mockResolvedValue(importedResult());
    const { container } = render(<Harness onImport={onImport} />);
    await uploadSyntheticFile(container);
    await screen.findByRole("dialog", { name: "Resumen de importación" });

    await user.click(screen.getByRole("button", { name: "Abrir como documento nuevo" }));
    expect(screen.getByRole("dialog", { name: "¿Reemplazar el documento actual?" })).toBeInTheDocument();
    expect(onImport).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "Cerrar" })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "Sí, reemplazar" }));

    expect(onImport).toHaveBeenCalledTimes(1);
    expect(onImport.mock.calls[0][0]).toMatchObject({ templateId: "libre", title: "archivo-sintetico" });
  });

  it("sin contenido actual abre tras confirmar el resumen, sin confirmación redundante", async () => {
    const user = userEvent.setup();
    const onImport = vi.fn();
    analyzeDocxFile.mockResolvedValue(importedResult());
    const { container } = render(<Harness document={currentDocument({ withContent: false })} onImport={onImport} />);
    await uploadSyntheticFile(container);
    await screen.findByRole("dialog", { name: "Resumen de importación" });
    await user.click(screen.getByRole("button", { name: "Abrir como documento nuevo" }));
    expect(onImport).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog", { name: "¿Reemplazar el documento actual?" })).not.toBeInTheDocument();
  });

  it("Escape cancela el diálogo por teclado y restaura el foco", async () => {
    const user = userEvent.setup();
    const onImport = vi.fn();
    analyzeDocxFile.mockResolvedValue(importedResult());
    const { container } = render(<Harness onImport={onImport} />);
    const trigger = screen.getByRole("button", { name: "Importar" });
    trigger.focus();
    await uploadSyntheticFile(container);
    await screen.findByRole("dialog", { name: "Resumen de importación" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    expect(onImport).not.toHaveBeenCalled();
  });
});
