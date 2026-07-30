import { StrictMode } from "react";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DOCUMENT_AUTOSAVE_STATUS, useDocumentAutosave } from "../../../hooks/useDocumentAutosave";
import { DOCUMENT_STORAGE_KEY, saveStoredDocument } from "../../../lib/document/documentStorage";
import { createFreeTemplateDocument } from "../../../lib/document/documentModel";

function makeMemoryStorage() {
  const map = new Map();
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
    get length() {
      return map.size;
    },
    key: (i) => [...map.keys()][i] ?? null,
  };
}

function docWithText(text) {
  const doc = createFreeTemplateDocument();
  doc.sections[0].content.content.push({ type: "paragraph", content: [{ type: "text", text }] });
  return doc;
}

let capturedApi = null;
function Harness({ storage, now, debounceMs }) {
  const autosave = useDocumentAutosave({ storage, now, debounceMs });
  capturedApi = autosave;
  return (
    <div>
      <p data-testid="status">{autosave.status}</p>
      <p data-testid="restored">{autosave.restoredDocument ? "yes" : "no"}</p>
      <p data-testid="notice">{autosave.notice?.reason ?? ""}</p>
    </div>
  );
}

beforeEach(() => {
  capturedApi = null;
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useDocumentAutosave — barrera load-before-save y restauración (F6-01, PARTE 2)", () => {
  it("restaura un documento persistido antes de habilitar el autoguardado; no lo sobrescribe con uno vacío", () => {
    const storage = makeMemoryStorage();
    const persisted = docWithText("Ya guardado");
    saveStoredDocument(storage, persisted, { now: () => 1000 });
    const rawBefore = storage.getItem(DOCUMENT_STORAGE_KEY);

    render(<Harness storage={storage} now={() => 2000} />);

    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.SAVED);
    expect(capturedApi.restoredDocument).toEqual(persisted);

    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe(rawBefore);
  });

  it("versión futura: el autoguardado nunca se habilita durante la sesión", () => {
    const storage = makeMemoryStorage();
    const futureEnvelope = {
      schemaVersion: 999,
      createdAt: "2026-01-01T00:00:00.000Z",
      updatedAt: "2026-01-01T00:00:00.000Z",
      document: { version: 1, templateId: "libre", title: "Futuro", sections: [] },
    };
    storage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(futureEnvelope));

    render(<Harness storage={storage} now={() => 3000} />);
    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.FUTURE_VERSION);
    expect(capturedApi.blockedEnvelope).toEqual(futureEnvelope);

    act(() => {
      capturedApi.notifyChange(docWithText("intento de edición"));
    });
    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe(JSON.stringify(futureEnvelope));
  });

  it("corrupción al restaurar: expone un notice redactado, abre un documento nuevo y permite descartarlo", () => {
    const storage = makeMemoryStorage();
    storage.setItem(DOCUMENT_STORAGE_KEY, "{roto");

    render(<Harness storage={storage} now={() => 4000} />);
    expect(capturedApi.notice).toMatchObject({ reason: "corrupt" });
    expect(capturedApi.restoredDocument).toBeNull();
    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.IDLE);

    act(() => {
      capturedApi.dismissNotice();
    });
    expect(capturedApi.notice).toBeNull();

    // El autoguardado SÍ queda habilitado (a diferencia de future_version):
    // se decidió explícitamente que no había nada recuperable.
    const doc = docWithText("documento nuevo tras corrupción");
    act(() => {
      capturedApi.notifyChange(doc);
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY)).document).toEqual(doc);
  });
});

describe("useDocumentAutosave — debounce ≤5s (F6-01, PARTE 3)", () => {
  it("autoguarda dentro de los 5s siguientes al último cambio, con reloj falso", () => {
    const storage = makeMemoryStorage();
    render(<Harness storage={storage} now={() => 5000} />);
    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.IDLE);

    const doc = docWithText("Cambio real");
    act(() => {
      capturedApi.notifyChange(doc);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBeNull();

    act(() => {
      vi.advanceTimersByTime(4999);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBeNull();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY)).document).toEqual(doc);
    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.SAVED);
  });

  it("cambios consecutivos reinician el debounce (cuenta desde el ÚLTIMO cambio, no del primero)", () => {
    const storage = makeMemoryStorage();
    render(<Harness storage={storage} now={() => 0} />);

    const docA = docWithText("A");
    act(() => {
      capturedApi.notifyChange(docA);
    });
    act(() => {
      vi.advanceTimersByTime(4000);
    });

    const docB = docWithText("B");
    act(() => {
      capturedApi.notifyChange(docB);
    });
    act(() => {
      vi.advanceTimersByTime(4000); // 8s desde A, pero solo 4s desde B
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBeNull();

    act(() => {
      vi.advanceTimersByTime(1000); // 5s desde B
    });
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY)).document).toEqual(docB);
  });

  it("un documento sin cambios reales no vuelve a escribirse", () => {
    const storage = makeMemoryStorage();
    render(<Harness storage={storage} now={() => 0} />);
    const doc = docWithText("Igual");

    act(() => {
      capturedApi.notifyChange(doc);
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    const rawAfterFirstSave = storage.getItem(DOCUMENT_STORAGE_KEY);

    act(() => {
      capturedApi.notifyChange(doc); // mismo contenido exacto
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe(rawAfterFirstSave);
  });

  it("notifyChange con un documento inválido marca error de inmediato y no programa escritura", () => {
    const storage = makeMemoryStorage();
    render(<Harness storage={storage} now={() => 0} />);

    act(() => {
      capturedApi.notifyChange({ version: 1 });
    });
    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.ERROR);
    expect(capturedApi.error).toBe("invalid_document");

    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBeNull();
  });

  it("desmontar limpia el timer pendiente y vacía de forma síncrona un cambio sin persistir", () => {
    const storage = makeMemoryStorage();
    const { unmount } = render(<Harness storage={storage} now={() => 0} />);
    const doc = docWithText("Pendiente");

    act(() => {
      capturedApi.notifyChange(doc);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBeNull();

    unmount();
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY)).document).toEqual(doc);

    const rawAfterUnmount = storage.getItem(DOCUMENT_STORAGE_KEY);
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe(rawAfterUnmount);
  });
});

describe("useDocumentAutosave — createdAt estable entre autoguardados (F6-01-R1, PARTE 4)", () => {
  it("dos autoguardados sucesivos conservan createdAt y actualizan updatedAt", () => {
    const storage = makeMemoryStorage();
    let currentTime = 1000;
    render(<Harness storage={storage} now={() => currentTime} />);

    act(() => {
      capturedApi.notifyChange(docWithText("A"));
    });
    currentTime = 6000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    const envelope1 = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));
    expect(envelope1.createdAt).toBe(new Date(6000).toISOString());
    expect(envelope1.updatedAt).toBe(new Date(6000).toISOString());

    act(() => {
      capturedApi.notifyChange(docWithText("B"));
    });
    currentTime = 20_000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    const envelope2 = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));
    expect(envelope2.createdAt).toBe(envelope1.createdAt);
    expect(envelope2.updatedAt).toBe(new Date(20_000).toISOString());
    expect(envelope2.updatedAt).not.toBe(envelope1.updatedAt);
  });

  it("restaurar un documento y luego editarlo conserva su createdAt original", () => {
    const storage = makeMemoryStorage();
    const persisted = docWithText("Ya guardado");
    saveStoredDocument(storage, persisted, { now: () => 1000 });
    const originalCreatedAt = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY)).createdAt;

    let currentTime = 50_000;
    render(<Harness storage={storage} now={() => currentTime} />);
    expect(capturedApi.restoredDocument).toEqual(persisted);

    act(() => {
      capturedApi.notifyChange(docWithText("Ya guardado, editado"));
    });
    currentTime = 55_000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    const envelope = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));
    expect(envelope.createdAt).toBe(originalCreatedAt);
    expect(envelope.updatedAt).toBe(new Date(55_000).toISOString());
  });

  it("QuotaExceededError no altera el sobre anterior ni el createdAt de referencia para el siguiente intento", () => {
    const storage = makeMemoryStorage();
    let currentTime = 1000;
    render(<Harness storage={storage} now={() => currentTime} />);

    act(() => {
      capturedApi.notifyChange(docWithText("A"));
    });
    currentTime = 6000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    const envelope1 = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));

    const originalSetItem = storage.setItem;
    storage.setItem = () => {
      const error = new Error("cuota agotada");
      error.name = "QuotaExceededError";
      throw error;
    };

    act(() => {
      capturedApi.notifyChange(docWithText("B (fallará al guardar)"));
    });
    currentTime = 12_000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByTestId("status")).toHaveTextContent(DOCUMENT_AUTOSAVE_STATUS.ERROR);
    expect(storage.getItem(DOCUMENT_STORAGE_KEY)).toBe(JSON.stringify(envelope1));

    storage.setItem = originalSetItem;
    act(() => {
      capturedApi.notifyChange(docWithText("C (ahora sí se guarda)"));
    });
    currentTime = 20_000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    const envelope3 = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));
    expect(envelope3.createdAt).toBe(envelope1.createdAt);
    expect(envelope3.updatedAt).toBe(new Date(20_000).toISOString());
  });

  it("el flush de desmontaje conserva el createdAt del último sobre persistido", () => {
    const storage = makeMemoryStorage();
    let currentTime = 1000;
    const { unmount } = render(<Harness storage={storage} now={() => currentTime} />);

    act(() => {
      capturedApi.notifyChange(docWithText("A"));
    });
    currentTime = 6000;
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    const envelope1 = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));

    act(() => {
      capturedApi.notifyChange(docWithText("B pendiente al desmontar"));
    });
    currentTime = 6500;

    unmount();

    const envelopeAfterUnmount = JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY));
    expect(envelopeAfterUnmount.createdAt).toBe(envelope1.createdAt);
    expect(envelopeAfterUnmount.updatedAt).toBe(new Date(6500).toISOString());
  });
});

describe("useDocumentAutosave — React Strict Mode (F6-01, PARTE 2)", () => {
  it("no duplica la restauración ni las escrituras bajo doble montaje de efectos", () => {
    const storage = makeMemoryStorage();
    const persisted = createFreeTemplateDocument();
    saveStoredDocument(storage, persisted, { now: () => 1000 });
    const setItemSpy = vi.spyOn(storage, "setItem");
    setItemSpy.mockClear();

    render(
      <StrictMode>
        <Harness storage={storage} now={() => 2000} />
      </StrictMode>
    );

    expect(capturedApi.restoredDocument).toEqual(persisted);
    expect(setItemSpy).not.toHaveBeenCalled();

    const changed = docWithText("Uno");
    act(() => {
      capturedApi.notifyChange(changed);
    });
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(setItemSpy).toHaveBeenCalledTimes(1);
    expect(JSON.parse(storage.getItem(DOCUMENT_STORAGE_KEY)).document).toEqual(changed);
  });
});
