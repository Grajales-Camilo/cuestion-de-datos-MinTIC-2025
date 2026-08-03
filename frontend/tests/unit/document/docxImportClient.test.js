import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzeDocxFile } from "../../../lib/document/docxImportClient.js";
import { DOCX_IMPORT_ERROR_CODES, DOCX_IMPORT_MAX_BYTES } from "../../../lib/document/docxImportPolicy.js";

function fileDouble({ name = "sintetico.docx", size = 4, type = "", bytes = [1, 2, 3, 4] } = {}) {
  return { name, size, type, arrayBuffer: vi.fn(async () => new Uint8Array(bytes).buffer) };
}

function successfulWorker() {
  const listeners = new Map();
  return {
    addEventListener(type, listener) { listeners.set(type, listener); },
    postMessage(_message) {
      queueMicrotask(() => listeners.get("message")?.({
        data: {
          type: "success",
          result: { html: "<p>Texto local</p>", warnings: [] },
        },
      }));
    },
    terminate: vi.fn(),
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("analyzeDocxFile — worker local, límites y cancelación", () => {
  it("transfiere el ArrayBuffer al worker y no usa ninguna solicitud de red", async () => {
    const worker = successfulWorker();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const result = await analyzeDocxFile(fileDouble(), { workerFactory: () => worker });
    expect(result.model.templateId).toBe("libre");
    expect(result.model.sections[0].content.content[0].content[0].text).toBe("Texto local");
    expect(worker.terminate).toHaveBeenCalledTimes(1);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it.each([
    [fileDouble({ name: "sintetico.pdf" }), DOCX_IMPORT_ERROR_CODES.INVALID_EXTENSION],
    [fileDouble({ size: DOCX_IMPORT_MAX_BYTES + 1 }), DOCX_IMPORT_ERROR_CODES.FILE_TOO_LARGE],
  ])("rechaza metadatos antes de leer o crear el worker", async (file, code) => {
    const workerFactory = vi.fn();
    await expect(analyzeDocxFile(file, { workerFactory })).rejects.toMatchObject({ code });
    expect(file.arrayBuffer).not.toHaveBeenCalled();
    expect(workerFactory).not.toHaveBeenCalled();
  });

  it("termina el worker al superar el timeout seguro", async () => {
    vi.useFakeTimers();
    const worker = { addEventListener: vi.fn(), postMessage: vi.fn(), terminate: vi.fn() };
    const promise = analyzeDocxFile(fileDouble(), { workerFactory: () => worker, timeoutMs: 50 });
    const assertion = expect(promise).rejects.toMatchObject({ code: DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED });
    await vi.advanceTimersByTimeAsync(51);
    await assertion;
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });

  it("abortar termina el worker sin producir un modelo", async () => {
    const controller = new AbortController();
    const worker = {
      addEventListener: vi.fn(),
      postMessage: vi.fn(() => controller.abort()),
      terminate: vi.fn(),
    };
    const promise = analyzeDocxFile(fileDouble(), { workerFactory: () => worker, signal: controller.signal });
    await expect(promise).rejects.toMatchObject({ code: DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED });
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });
});
