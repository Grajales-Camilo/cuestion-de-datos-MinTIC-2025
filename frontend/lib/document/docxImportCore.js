import { DOMParser as XmlDomParser } from "@xmldom/xmldom";
import JSZip from "jszip";
// Entrada de navegador explícita: la entrada `main` de Mammoth espera rutas
// o Buffer de Node. El bundle oficial usa `arrayBuffer` y no contiene acceso
// al sistema de archivos (documentación oficial, API browser).
import mammoth from "mammoth/mammoth.browser.js";
import { getSafeImportedLink } from "./safeImportedLink.js";
import {
  DOCX_IMPORT_ERROR_CODES,
  DOCX_IMPORT_MAX_BYTES,
  DOCX_IMPORT_MAX_COMPRESSION_RATIO,
  DOCX_IMPORT_MAX_ENTRIES,
  DOCX_IMPORT_MAX_ENTRY_BYTES,
  DOCX_IMPORT_MAX_HTML_CHARS,
  DOCX_IMPORT_MAX_UNCOMPRESSED_BYTES,
  DOCX_IMPORT_WARNING_CODES,
  DocxImportError,
} from "./docxImportPolicy.js";

const ACCEPTED_MIME_TYPES = new Set([
  "",
  "application/octet-stream",
  "application/zip",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

const DOCX_MAIN_CONTENT_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml";
const OFFICE_DOCUMENT_RELATIONSHIP_SUFFIX = "/officeDocument";
const HYPERLINK_RELATIONSHIP_SUFFIX = "/hyperlink";

function countMatches(value, pattern) {
  return value.match(pattern)?.length ?? 0;
}

function warning(code, count, disposition) {
  return { code, count, disposition };
}

function bytesStartWith(bytes, signature) {
  return signature.every((byte, index) => bytes[index] === byte);
}

function assertFileMetadata(metadata) {
  if (!metadata || typeof metadata.name !== "string" || !/\.docx$/iu.test(metadata.name)) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.INVALID_EXTENSION);
  }
  if (!ACCEPTED_MIME_TYPES.has(String(metadata.type ?? "").toLowerCase())) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.INVALID_MIME_TYPE);
  }
  if (!Number.isSafeInteger(metadata.size) || metadata.size <= 0) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.EMPTY_FILE);
  }
  if (metadata.size > DOCX_IMPORT_MAX_BYTES) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.FILE_TOO_LARGE);
  }
}

function assertPackageSignature(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer, 0, Math.min(arrayBuffer.byteLength, 8));
  if (bytesStartWith(bytes, [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1])) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.ENCRYPTED_DOCUMENT);
  }
  if (!bytesStartWith(bytes, [0x50, 0x4b, 0x03, 0x04])) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.INVALID_SIGNATURE);
  }
}

function assertSafeEntryName(entry) {
  const originalName = entry.unsafeOriginalName ?? entry.name;
  if (
    typeof originalName !== "string" ||
    originalName.includes("\\") ||
    originalName.includes("\0") ||
    originalName.startsWith("/") ||
    /^[a-z]:/iu.test(originalName) ||
    originalName.split("/").some((segment) => segment === "..")
  ) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.UNSAFE_PACKAGE);
  }
}

function assertPackageLimits(zip) {
  const entries = Object.values(zip.files);
  if (entries.length > DOCX_IMPORT_MAX_ENTRIES) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
  }

  let totalUncompressed = 0;
  let totalCompressed = 0;
  for (const entry of entries) {
    assertSafeEntryName(entry);
    if (entry.dir) continue;
    const uncompressed = entry._data?.uncompressedSize;
    const compressed = entry._data?.compressedSize;
    if (!Number.isSafeInteger(uncompressed) || !Number.isSafeInteger(compressed)) {
      throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.UNSAFE_PACKAGE);
    }
    if (uncompressed > DOCX_IMPORT_MAX_ENTRY_BYTES) {
      throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
    }
    totalUncompressed += uncompressed;
    totalCompressed += compressed;
  }

  const ratio = totalUncompressed / Math.max(totalCompressed, 1);
  if (
    totalUncompressed > DOCX_IMPORT_MAX_UNCOMPRESSED_BYTES ||
    ratio > DOCX_IMPORT_MAX_COMPRESSION_RATIO
  ) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
  }
}

async function readRequiredText(zip, path) {
  const entry = zip.file(path);
  if (!entry) throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  try {
    return await entry.async("string");
  } catch {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  }
}

async function readOptionalText(zip, path) {
  const entry = zip.file(path);
  if (!entry) return null;
  try {
    return await entry.async("string");
  } catch {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  }
}

function parseXml(xml) {
  const errors = [];
  const document = new XmlDomParser({
    errorHandler: {
      warning() {},
      error(message) {
        errors.push(message);
      },
      fatalError(message) {
        errors.push(message);
      },
    },
  }).parseFromString(xml, "application/xml");
  if (errors.length > 0 || !document?.documentElement) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  }
  return document;
}

function elementsByLocalName(document, localName) {
  return Array.from(document.getElementsByTagName("*")).filter(
    (element) => element.localName === localName || element.nodeName.split(":").at(-1) === localName,
  );
}

function assertDocxContentType(contentTypesXml) {
  const document = parseXml(contentTypesXml);
  const overrides = elementsByLocalName(document, "Override");
  const main = overrides.find((element) => element.getAttribute("PartName") === "/word/document.xml");
  if (main?.getAttribute("ContentType") !== DOCX_MAIN_CONTENT_TYPE) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.UNSUPPORTED_DOCUMENT_TYPE);
  }
}

function inspectRelationships(xml, { requireOfficeDocument = false } = {}) {
  const document = parseXml(xml);
  const relationships = elementsByLocalName(document, "Relationship");
  let hasOfficeDocument = false;
  let unsafeLinkCount = 0;

  for (const relationship of relationships) {
    const type = relationship.getAttribute("Type") ?? "";
    const target = relationship.getAttribute("Target") ?? "";
    const isExternal = relationship.getAttribute("TargetMode")?.toLowerCase() === "external";
    if (type.endsWith(OFFICE_DOCUMENT_RELATIONSHIP_SUFFIX) && !isExternal) {
      hasOfficeDocument = true;
    }
    if (!isExternal) continue;
    if (!type.endsWith(HYPERLINK_RELATIONSHIP_SUFFIX)) {
      throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.EXTERNAL_RELATIONSHIP);
    }
    if (getSafeImportedLink(target) === null) unsafeLinkCount += 1;
  }

  if (requireOfficeDocument && !hasOfficeDocument) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  }
  return unsafeLinkCount;
}

function collectUnsupportedWarnings(zip, documentXml, unsafeLinkCount) {
  const names = Object.keys(zip.files);
  const counts = {
    tables: countMatches(documentXml, /<w:tbl\b/giu),
    images:
      countMatches(documentXml, /<(?:w:drawing|w:pict)\b/giu) +
      names.filter((name) => /^word\/media\//iu.test(name)).length,
    headersFooters: names.filter((name) => /^word\/(?:header|footer)\d*\.xml$/iu.test(name)).length,
    // `docx` y Word pueden incluir parts vacíos de comments/footnotes como
    // infraestructura del paquete. Solo advertimos cuando el documento
    // principal contiene una referencia real, para no fabricar descartes.
    comments: countMatches(documentXml, /<w:comment(?:RangeStart|RangeEnd|Reference)\b/giu),
    trackedChanges: countMatches(documentXml, /<w:(?:ins|del|moveFrom|moveTo)\b/giu),
    notes: countMatches(documentXml, /<w:(?:footnoteReference|endnoteReference)\b/giu),
    equations: countMatches(documentXml, /<m:oMath(?:Para)?\b/giu),
    fields: countMatches(documentXml, /<w:(?:fldSimple|instrText)\b/giu),
    embeddedObjects:
      names.filter((name) => /^word\/embeddings\//iu.test(name)).length +
      countMatches(documentXml, /<w:object\b/giu),
  };

  return [
    counts.tables && warning(DOCX_IMPORT_WARNING_CODES.TABLES_SIMPLIFIED, counts.tables, "simplificado"),
    counts.images && warning(DOCX_IMPORT_WARNING_CODES.IMAGES_DISCARDED, counts.images, "descartado"),
    counts.headersFooters &&
      warning(DOCX_IMPORT_WARNING_CODES.HEADERS_FOOTERS_DISCARDED, counts.headersFooters, "descartado"),
    counts.comments && warning(DOCX_IMPORT_WARNING_CODES.COMMENTS_DISCARDED, counts.comments, "descartado"),
    counts.trackedChanges &&
      warning(DOCX_IMPORT_WARNING_CODES.TRACK_CHANGES_SIMPLIFIED, counts.trackedChanges, "simplificado"),
    counts.notes && warning(DOCX_IMPORT_WARNING_CODES.NOTES_SIMPLIFIED, counts.notes, "simplificado"),
    counts.equations && warning(DOCX_IMPORT_WARNING_CODES.EQUATIONS_DISCARDED, counts.equations, "descartado"),
    counts.fields && warning(DOCX_IMPORT_WARNING_CODES.FIELDS_SIMPLIFIED, counts.fields, "simplificado"),
    counts.embeddedObjects &&
      warning(DOCX_IMPORT_WARNING_CODES.EMBEDDED_OBJECTS_DISCARDED, counts.embeddedObjects, "descartado"),
    unsafeLinkCount &&
      warning(DOCX_IMPORT_WARNING_CODES.UNSAFE_LINKS_DISCARDED, unsafeLinkCount, "descartado"),
  ].filter(Boolean);
}

function normalizeMammothWarnings(messages) {
  const count = Array.isArray(messages)
    ? messages.filter((message) => message?.type === "warning").length
    : 0;
  return count > 0
    ? [warning(DOCX_IMPORT_WARNING_CODES.UNSUPPORTED_STYLES_SIMPLIFIED, count, "simplificado")]
    : [];
}

/**
 * Preflight estructural + conversión semántica. En la aplicación se ejecuta
 * exclusivamente dentro de `docxImport.worker.js`; se exporta para pruebas
 * unitarias sintéticas. JSZip inspecciona el contenedor y Mammoth realiza la
 * conversión OOXML real: este módulo no implementa un parser de Word propio.
 */
export async function convertDocxArrayBuffer(arrayBuffer, metadata) {
  assertFileMetadata(metadata);
  if (!(arrayBuffer instanceof ArrayBuffer) || arrayBuffer.byteLength !== metadata.size) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  }
  assertPackageSignature(arrayBuffer);

  let zip;
  try {
    zip = await JSZip.loadAsync(arrayBuffer, { createFolders: false });
  } catch (error) {
    const message = String(error?.message ?? "").toLowerCase();
    throw new DocxImportError(
      message.includes("encrypt")
        ? DOCX_IMPORT_ERROR_CODES.ENCRYPTED_DOCUMENT
        : DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT,
    );
  }
  assertPackageLimits(zip);

  if (zip.file("EncryptionInfo") || zip.file("EncryptedPackage") || zip.file("word/vbaProject.bin")) {
    throw new DocxImportError(
      zip.file("word/vbaProject.bin")
        ? DOCX_IMPORT_ERROR_CODES.UNSUPPORTED_DOCUMENT_TYPE
        : DOCX_IMPORT_ERROR_CODES.ENCRYPTED_DOCUMENT,
    );
  }

  // CRC completo solo DESPUÉS de verificar tamaños/ratio; evita que una
  // bomba ZIP se descomprima antes de aplicar límites.
  try {
    await JSZip.loadAsync(arrayBuffer, { checkCRC32: true, createFolders: false });
  } catch {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CORRUPT_DOCUMENT);
  }

  const contentTypesXml = await readRequiredText(zip, "[Content_Types].xml");
  const rootRelationshipsXml = await readRequiredText(zip, "_rels/.rels");
  const documentXml = await readRequiredText(zip, "word/document.xml");
  assertDocxContentType(contentTypesXml);
  inspectRelationships(rootRelationshipsXml, { requireOfficeDocument: true });

  let unsafeLinkCount = 0;
  for (const path of Object.keys(zip.files).filter((name) => name.endsWith(".rels"))) {
    const xml = path === "_rels/.rels" ? rootRelationshipsXml : await readOptionalText(zip, path);
    if (xml !== null) unsafeLinkCount += inspectRelationships(xml);
  }

  let result;
  try {
    result = await mammoth.convertToHtml(
      { arrayBuffer },
      {
        externalFileAccess: false,
        includeEmbeddedStyleMap: false,
        includeDefaultStyleMap: true,
        ignoreEmptyParagraphs: false,
        convertImage: () => [],
      },
    );
  } catch {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED);
  }

  if (typeof result?.value !== "string" || result.value.length > DOCX_IMPORT_MAX_HTML_CHARS) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
  }

  return {
    html: result.value,
    warnings: [
      ...collectUnsupportedWarnings(zip, documentXml, unsafeLinkCount),
      ...normalizeMammothWarnings(result.messages),
    ],
  };
}
