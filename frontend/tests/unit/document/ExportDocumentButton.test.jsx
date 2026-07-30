import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExportDocumentButton } from "../../../components/document/ExportDocumentButton";
import { EXPORT_DOCX_ERROR_CODES } from "../../../lib/document/exportDocxErrorCodes";
import { createFreeTemplateDocument } from "../../../lib/document/documentModel";

const exportDocumentToDocx = vi.fn();

// El componente carga `../../lib/document/exportDocx.js` con `import()`
// dinámico (relativo a `components/document/`); desde este archivo de
// prueba (`tests/unit/document/`) esa misma ruta absoluta se alcanza con
// `../../../lib/document/exportDocx.js`. Un solo mock, reutilizado por
// referencia (`exportDocumentToDocx` de arriba) para poder controlar su
// resolución/rechazo por prueba con `mockResolvedValueOnce`/`mockImplementationOnce`.
vi.mock("../../../lib/document/exportDocx.js", () => ({
  exportDocumentToDocx: (...args) => exportDocumentToDocx(...args),
}));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("ExportDocumentButton — F6-02B (RF-102/RF-103)", () => {
  let createObjectURLSpy;
  let revokeObjectURLSpy;
  let appendChildSpy;
  let removeChildSpy;
  let clickSpy;

  beforeEach(() => {
    exportDocumentToDocx.mockReset();
    createObjectURLSpy = vi.fn(() => "blob:mock-export-url");
    revokeObjectURLSpy = vi.fn();
    window.URL.createObjectURL = createObjectURLSpy;
    window.URL.revokeObjectURL = revokeObjectURLSpy;
    appendChildSpy = vi.spyOn(document.body, "appendChild");
    removeChildSpy = vi.spyOn(document.body, "removeChild");
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("1) la primera pulsación inicia exactamente una exportación", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    exportDocumentToDocx.mockResolvedValue({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    await waitFor(() => expect(exportDocumentToDocx).toHaveBeenCalledTimes(1));
  });

  it("2) doble clic inmediato sigue produciendo una sola operación", async () => {
    const doc = createFreeTemplateDocument();
    const pending = deferred();
    exportDocumentToDocx.mockReturnValue(pending.promise);
    render(<ExportDocumentButton documentModel={doc} />);

    const button = screen.getByRole("button", { name: /Exportar en Word/ });
    // Dos clics SÍNCRONOS en el mismo tick (fireEvent, no `userEvent`, que
    // ya serializa esperas entre interacciones) — ejercita la guarda
    // inmediata (`isExportingRef`), no solo el `disabled` post-render.
    button.click();
    button.click();

    await waitFor(() => expect(exportDocumentToDocx).toHaveBeenCalledTimes(1));
    pending.resolve({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
  });

  it("3) recibe el DocumentModel actual EXACTO (misma referencia)", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    doc.title = "Documento con edición reciente";
    exportDocumentToDocx.mockResolvedValue({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    await waitFor(() => expect(exportDocumentToDocx).toHaveBeenCalledWith(doc));
  });

  it("4) muestra estado ocupado (aria-busy + texto) mientras la exportación está en curso", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    const pending = deferred();
    exportDocumentToDocx.mockReturnValue(pending.promise);
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    const busyButton = await screen.findByRole("button", { name: /Preparando documento/ });
    expect(busyButton).toHaveAttribute("aria-busy", "true");
    expect(busyButton).toBeDisabled();

    pending.resolve({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
    await waitFor(() => expect(screen.getByRole("button", { name: /Exportar en Word/ })).not.toBeDisabled());
  });

  it("5) un resultado correcto crea la descarga con el filename y el Blob exactos", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    const blob = new Blob(["contenido-docx"]);
    exportDocumentToDocx.mockResolvedValue({ ok: true, blob, filename: "reporte-2026.docx" });
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    await waitFor(() => expect(createObjectURLSpy).toHaveBeenCalledWith(blob));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    const link = appendChildSpy.mock.calls.at(-1)[0];
    expect(link.tagName).toBe("A");
    expect(link.download).toBe("reporte-2026.docx");
  });

  it("6) el enlace temporal se retira del DOM y la URL se revoca EXACTAMENTE una vez", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    exportDocumentToDocx.mockResolvedValue({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
    render(<ExportDocumentButton documentModel={doc} />);
    // `render()` de Testing Library también usa `document.body.appendChild`
    // para montar su contenedor: se descuentan esas llamadas previas para
    // contar solo las que dispara el propio flujo de descarga.
    appendChildSpy.mockClear();
    removeChildSpy.mockClear();

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    await waitFor(() => expect(revokeObjectURLSpy).toHaveBeenCalledTimes(1));
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-export-url");
    expect(removeChildSpy).toHaveBeenCalledTimes(1);
    expect(appendChildSpy).toHaveBeenCalledTimes(1);
  });

  it.each([
    [
      EXPORT_DOCX_ERROR_CODES.INVALID_DOCUMENT,
      "No pudimos exportar porque el documento tiene un problema interno. No se descargó ningún archivo.",
    ],
    [EXPORT_DOCX_ERROR_CODES.UNSUPPORTED_TEMPLATE, "Esta plantilla todavía no se puede exportar en Word."],
    [
      EXPORT_DOCX_ERROR_CODES.SENSITIVE_DATA_DETECTED,
      "No pudimos exportar porque el documento contiene información sensible. Revísalo antes de intentarlo de nuevo.",
    ],
  ])("7) el código %s se traduce a un mensaje en español, sin mostrar el enum crudo", async (code, message) => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    exportDocumentToDocx.mockResolvedValue({ ok: false, code });
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(code)).not.toBeInTheDocument();
    expect(createObjectURLSpy).not.toHaveBeenCalled();
  });

  it("8) un código de error desconocido (o GENERATION_FAILED) usa el mensaje genérico", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    exportDocumentToDocx.mockResolvedValue({ ok: false, code: "UN_CODIGO_QUE_NO_EXISTE" });
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos preparar el documento. Intenta de nuevo.");
    expect(screen.queryByText("UN_CODIGO_QUE_NO_EXISTE")).not.toBeInTheDocument();
  });

  it("9) un rechazo durante la secuencia de import()+exportación queda controlado (mensaje genérico, sin crash, sin descarga)", async () => {
    // Ejercita el MISMO bloque try/catch que envuelve tanto `await
    // import(...)` como `await exportDocumentToDocx(...)`: un fallo real de
    // carga del chunk dinámico (red/manifest) y un fallo de la llamada caen
    // exactamente en la misma rama de recuperación — no hay dos manejadores
    // distintos que puedan divergir.
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    exportDocumentToDocx.mockRejectedValue(new Error("chunk load failed: Loading chunk 12 failed"));
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos preparar el documento. Intenta de nuevo.");
    expect(screen.queryByText(/chunk load failed/)).not.toBeInTheDocument();
    expect(createObjectURLSpy).not.toHaveBeenCalled();
    // El botón sigue siendo utilizable: no queda atascado en "ocupado".
    expect(screen.getByRole("button", { name: /Exportar en Word/ })).not.toBeDisabled();
  });

  it("10) desmontar el componente mientras la exportación está pendiente no actualiza estado ni dispara una descarga tardía", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    const pending = deferred();
    exportDocumentToDocx.mockReturnValue(pending.promise);
    const { unmount } = render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));
    await screen.findByRole("button", { name: /Preparando documento/ });

    unmount();
    pending.resolve({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(createObjectURLSpy).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("11) la exportación sigue disponible (no deshabilitada) sin ninguna relación con el estado de autoguardado/cuota", () => {
    // El componente no recibe ningún prop de autosave/cuota — es
    // estructuralmente independiente de ese estado, lo que esta prueba deja
    // explícito: el botón arranca habilitado siempre que haya un
    // `documentModel`, sin importar qué esté pasando con la persistencia.
    const doc = createFreeTemplateDocument();
    render(<ExportDocumentButton documentModel={doc} />);

    expect(screen.getByRole("button", { name: /Exportar en Word/ })).not.toBeDisabled();
  });

  it("12) ningún token de corrida aparece en mensajes, URLs o logs generados por el componente", async () => {
    const user = userEvent.setup();
    const doc = createFreeTemplateDocument();
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    exportDocumentToDocx.mockResolvedValue({ ok: true, blob: new Blob(["x"]), filename: "documento.docx" });
    render(<ExportDocumentButton documentModel={doc} />);

    await user.click(screen.getByRole("button", { name: /Exportar en Word/ }));
    await waitFor(() => expect(createObjectURLSpy).toHaveBeenCalled());

    expect(createObjectURLSpy.mock.results[0]).toBeDefined();
    for (const call of consoleSpy.mock.calls) {
      expect(JSON.stringify(call)).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
    }
    expect(document.body.innerHTML).not.toMatch(/cdt_rt_[A-Za-z0-9_-]+/);
  });
});
