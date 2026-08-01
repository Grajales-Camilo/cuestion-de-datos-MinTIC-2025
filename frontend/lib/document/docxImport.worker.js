import { convertDocxArrayBuffer } from "./docxImportCore.js";
import { DOCX_IMPORT_ERROR_CODES } from "./docxImportPolicy.js";

self.addEventListener("message", async (event) => {
  const { arrayBuffer, metadata } = event.data ?? {};
  try {
    const result = await convertDocxArrayBuffer(arrayBuffer, metadata);
    self.postMessage({ type: "success", result });
  } catch (error) {
    self.postMessage({
      type: "error",
      code: typeof error?.code === "string" ? error.code : DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED,
    });
  }
});
