import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocumentPersistenceStatus } from "../../../components/document/DocumentPersistenceStatus";
import { DOCUMENT_AUTOSAVE_STATUS } from "../../../hooks/useDocumentAutosave";
import { createFreeTemplateDocument } from "../../../lib/document/documentModel";

describe("DocumentPersistenceStatus — mensajes y descarga (F6-01-R1, PARTE 5)", () => {
  let createObjectURLSpy;
  let revokeObjectURLSpy;

  beforeEach(() => {
    createObjectURLSpy = vi.fn(() => "blob:mock-url");
    revokeObjectURLSpy = vi.fn();
    window.URL.createObjectURL = createObjectURLSpy;
    window.URL.revokeObjectURL = revokeObjectURLSpy;
  });

  it("invalid_document: ofrece 'Descargar documento actual' cuando currentDocument es serializable (antes: el botón no aparecía)", async () => {
    const user = userEvent.setup();
    const currentDocument = createFreeTemplateDocument();
    render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.ERROR}
        error="invalid_document"
        notice={null}
        blockedEnvelope={null}
        currentDocument={currentDocument}
      />
    );

    expect(screen.getByText(/Descarga una copia para no perderlos\./)).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Descargar documento actual" });
    await user.click(button);
    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURLSpy).toHaveBeenCalledWith("blob:mock-url");
  });

  it("invalid_document sin currentDocument: el mensaje no menciona descargar y el botón no aparece (mensaje nunca ordena una acción imposible)", () => {
    render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.ERROR}
        error="invalid_document"
        notice={null}
        blockedEnvelope={null}
        currentDocument={null}
      />
    );

    expect(screen.queryByText(/Descarga una copia/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Descargar documento actual" })).not.toBeInTheDocument();
  });

  it("un valor no serializable para descarga falla de forma controlada, sin lanzar", async () => {
    const user = userEvent.setup();
    const circular = {};
    circular.self = circular; // JSON.stringify lanza TypeError sobre esto
    render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.ERROR}
        error="quota_exceeded"
        notice={null}
        blockedEnvelope={null}
        currentDocument={circular}
      />
    );

    const button = screen.getByRole("button", { name: "Descargar documento actual" });
    await expect(user.click(button)).resolves.toBeUndefined();
    expect(screen.getByText("No se pudo preparar la descarga. Intenta de nuevo.")).toBeInTheDocument();
    expect(createObjectURLSpy).not.toHaveBeenCalled();
  });

  it("future_version y migration_failed muestran mensajes DISTINTOS, ambos con descarga", () => {
    const blockedEnvelope = { schemaVersion: 999, createdAt: "x", updatedAt: "y", document: {} };

    const { unmount } = render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION}
        error={null}
        notice={{ reason: "future_version" }}
        blockedEnvelope={blockedEnvelope}
        currentDocument={null}
      />
    );
    const futureVersionText = screen.getByText(/versión más nueva/).textContent;
    expect(screen.getByRole("button", { name: "Descargar archivo intacto" })).toBeInTheDocument();
    unmount();

    render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION}
        error={null}
        notice={{ reason: "migration_failed" }}
        blockedEnvelope={blockedEnvelope}
        currentDocument={null}
      />
    );
    const migrationFailedText = screen.getByText(/No pudimos actualizar de forma segura/).textContent;
    expect(screen.getByRole("button", { name: "Descargar archivo intacto" })).toBeInTheDocument();

    expect(futureVersionText).not.toBe(migrationFailedText);
  });

  it("F6-02A PARTE 1.1: future_version NO muestra el aviso genérico ni el botón 'Entendido' (con onDismissNotice presente, como en pages/app.js)", () => {
    const blockedEnvelope = { schemaVersion: 999, createdAt: "x", updatedAt: "y", document: {} };
    const onDismissNotice = vi.fn();
    render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION}
        error={null}
        notice={{ reason: "future_version" }}
        blockedEnvelope={blockedEnvelope}
        currentDocument={null}
        onDismissNotice={onDismissNotice}
      />
    );

    // Exactamente un aviso: el específico de "future_version".
    expect(screen.getByText(/versión más nueva/)).toBeInTheDocument();
    expect(screen.queryByText(/Hubo un problema al recuperar el documento guardado anteriormente/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entendido" })).not.toBeInTheDocument();
  });

  it("F6-02A PARTE 1.1: migration_failed NO muestra el aviso genérico ni el botón 'Entendido'", () => {
    const blockedEnvelope = { schemaVersion: 1, createdAt: "x", updatedAt: "y", document: {} };
    const onDismissNotice = vi.fn();
    render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION}
        error={null}
        notice={{ reason: "migration_failed" }}
        blockedEnvelope={blockedEnvelope}
        currentDocument={null}
        onDismissNotice={onDismissNotice}
      />
    );

    expect(screen.getByText(/No pudimos actualizar de forma segura/)).toBeInTheDocument();
    expect(screen.queryByText(/Hubo un problema al recuperar el documento guardado anteriormente/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entendido" })).not.toBeInTheDocument();
  });

  it("F6-02A PARTE 1.1: corrupt/invalid/unavailable SIGUEN mostrando el aviso + 'Entendido' (no se rompió el comportamiento existente)", () => {
    const onDismissNotice = vi.fn();
    for (const reason of ["corrupt", "invalid", "unavailable"]) {
      const { unmount } = render(
        <DocumentPersistenceStatus
          status={DOCUMENT_AUTOSAVE_STATUS.IDLE}
          error={null}
          notice={{ reason }}
          blockedEnvelope={null}
          currentDocument={null}
          onDismissNotice={onDismissNotice}
        />
      );
      expect(screen.getByRole("button", { name: "Entendido" })).toBeInTheDocument();
      unmount();
    }
  });

  it("el aviso de corrupción nunca renderiza el raw crudo en el DOM, pero sí ofrece descargarlo", () => {
    const rawWithSecret = '{"token":"cdt_rt_no_debe_verse_en_pantalla", roto';
    const { container } = render(
      <DocumentPersistenceStatus
        status={DOCUMENT_AUTOSAVE_STATUS.IDLE}
        error={null}
        notice={{ reason: "corrupt", raw: rawWithSecret, diagnosticKey: "cdd.doc.v1.corrupt.1" }}
        blockedEnvelope={null}
        currentDocument={null}
      />
    );

    expect(container.innerHTML).not.toContain("cdt_rt_no_debe_verse_en_pantalla");
    expect(screen.getByRole("button", { name: "Descargar copia recuperable" })).toBeInTheDocument();
  });
});
