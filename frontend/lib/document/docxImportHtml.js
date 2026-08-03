import { validateDocumentEditorJson } from "./documentSchema.js";
import {
  DOCUMENT_MODEL_VERSION,
  FREE_TEMPLATE_ID,
  validateDocumentModel,
} from "./documentModel.js";
import { DOCX_IMPORT_ERROR_CODES, DOCX_IMPORT_WARNING_CODES, DocxImportError } from "./docxImportPolicy.js";
import { getSafeImportedLink } from "./safeImportedLink.js";

const MAX_MODEL_NODES = 20_000;
const MAX_MODEL_DEPTH = 32;
const MAX_TEXT_CHARS = 1_000_000;
const BLOCK_TAGS = new Set(["P", "H1", "H2", "H3", "H4", "H5", "H6", "UL", "OL", "TABLE"]);
const DISCARDED_TAGS = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "SVG", "MATH", "IMG"]);

function sanitizeText(value) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/gu, "")
    .replace(/[\u202a-\u202e\u2066-\u2069]/gu, "")
    .replace(/\r\n?/gu, "\n");
}

export function sanitizeImportedFilename(filename) {
  const withoutExtension = String(filename ?? "").replace(/\.docx$/iu, "");
  const cleaned = withoutExtension
    .normalize("NFKC")
    .replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/gu, " ")
    .replace(/\s+/gu, " ")
    .replace(/^[. ]+|[. ]+$/gu, "")
    .slice(0, 120)
    .trim();
  return cleaned || "Documento importado";
}

function appendWarning(warnings, code, disposition = "simplificado", count = 1) {
  const existing = warnings.find((item) => item.code === code);
  if (existing) existing.count += count;
  else warnings.push({ code, count, disposition });
}

function marksEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function appendText(target, text, marks, stats) {
  const sanitized = sanitizeText(text);
  if (!sanitized) return;
  stats.textChars += sanitized.length;
  if (stats.textChars > MAX_TEXT_CHARS) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
  }
  const previous = target.at(-1);
  if (previous?.type === "text" && marksEqual(previous.marks ?? [], marks)) {
    previous.text += sanitized;
    return;
  }
  const node = { type: "text", text: sanitized };
  if (marks.length > 0) node.marks = marks;
  target.push(node);
  stats.nodes += 1;
}

function inlineNodes(domNode, marks, context, depth) {
  if (depth > MAX_MODEL_DEPTH) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
  }
  const output = [];
  for (const child of Array.from(domNode.childNodes ?? [])) {
    if (child.nodeType === 3) {
      appendText(output, child.nodeValue, marks, context.stats);
      continue;
    }
    if (child.nodeType !== 1) continue;
    if (DISCARDED_TAGS.has(child.tagName)) continue;
    if (child.tagName === "BR") {
      appendText(output, "\n", marks, context.stats);
      continue;
    }

    let nextMarks = marks;
    if (child.tagName === "STRONG" || child.tagName === "B") {
      nextMarks = [...marks, { type: "bold" }];
    } else if (child.tagName === "EM" || child.tagName === "I") {
      nextMarks = [...marks, { type: "italic" }];
    } else if (child.tagName === "A") {
      const href = getSafeImportedLink(child.getAttribute("href"));
      if (href) nextMarks = [...marks, { type: "link", attrs: { href, target: "_blank", rel: "noopener noreferrer" } }];
      else appendWarning(context.warnings, DOCX_IMPORT_WARNING_CODES.UNSAFE_LINKS_DISCARDED, "descartado");
    } else if (["U", "S", "DEL", "SUB", "SUP"].includes(child.tagName)) {
      appendWarning(context.warnings, DOCX_IMPORT_WARNING_CODES.UNSUPPORTED_STYLES_SIMPLIFIED);
    }
    output.push(...inlineNodes(child, nextMarks, context, depth + 1));
  }
  return output;
}

function paragraphNode(element, context, type = "paragraph", attrs) {
  const content = inlineNodes(element, [], context, 0);
  context.stats.nodes += 1;
  const node = { type };
  if (attrs) node.attrs = attrs;
  if (content.length > 0) node.content = content;
  return node;
}

function listNode(element, context, ordered, depth) {
  if (depth > MAX_MODEL_DEPTH) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
  }
  const items = [];
  for (const child of Array.from(element.children)) {
    if (child.tagName !== "LI") continue;
    const content = [];
    const inlineContainer = child.cloneNode(false);
    for (const node of Array.from(child.childNodes)) {
      if (node.nodeType === 1 && (node.tagName === "UL" || node.tagName === "OL")) {
        content.push(listNode(node, context, node.tagName === "OL", depth + 1));
      } else if (node.nodeType === 1 && BLOCK_TAGS.has(node.tagName)) {
        content.push(...blockNodes(node, context, depth + 1));
      } else {
        inlineContainer.appendChild(node.cloneNode(true));
      }
    }
    const inline = inlineNodes(inlineContainer, [], context, depth + 1);
    if (inline.length > 0 || content.length === 0) {
      content.unshift(inline.length > 0 ? { type: "paragraph", content: inline } : { type: "paragraph" });
    }
    items.push({ type: "listItem", content });
    context.stats.nodes += 2;
  }
  context.stats.nodes += 1;
  return { type: ordered ? "orderedList" : "bulletList", content: items };
}

function tableNodes(element, context) {
  appendWarning(context.warnings, DOCX_IMPORT_WARNING_CODES.TABLES_SIMPLIFIED);
  const paragraphs = [];
  for (const row of Array.from(element.querySelectorAll("tr"))) {
    const cells = Array.from(row.querySelectorAll(":scope > th, :scope > td"))
      .map((cell) => sanitizeText(cell.textContent).replace(/\s+/gu, " ").trim())
      .filter(Boolean);
    if (cells.length === 0) continue;
    const paragraph = { type: "paragraph", content: [] };
    appendText(paragraph.content, cells.join(" | "), [], context.stats);
    paragraphs.push(paragraph);
    context.stats.nodes += 1;
  }
  return paragraphs;
}

function blockNodes(element, context, depth = 0) {
  switch (element.tagName) {
    case "P":
      return [paragraphNode(element, context)];
    case "H1":
    case "H2":
    case "H3":
    case "H4":
    case "H5":
    case "H6": {
      const sourceLevel = Number(element.tagName.slice(1));
      const level = Math.min(4, sourceLevel + 1);
      return [paragraphNode(element, context, "heading", { level })];
    }
    case "UL":
      return [listNode(element, context, false, depth)];
    case "OL":
      return [listNode(element, context, true, depth)];
    case "TABLE":
      return tableNodes(element, context);
    default: {
      const nested = [];
      for (const child of Array.from(element.children ?? [])) nested.push(...blockNodes(child, context, depth + 1));
      if (nested.length > 0) return nested;
      const paragraph = paragraphNode(element, context);
      return paragraph.content ? [paragraph] : [];
    }
  }
}

/** Convierte el HTML NO confiable de Mammoth recorriendo nodos; nunca lo
 * monta ni usa `dangerouslySetInnerHTML`. */
export function convertMammothHtmlToDocument(html, { filename, warnings = [] } = {}) {
  if (typeof DOMParser === "undefined") {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED);
  }
  const parsed = new DOMParser().parseFromString(`<body>${String(html ?? "")}</body>`, "text/html");
  const body = parsed.body;
  const context = { warnings: warnings.map((item) => ({ ...item })), stats: { nodes: 0, textChars: 0 } };
  const content = [];
  for (const child of Array.from(body.children)) {
    if (DISCARDED_TAGS.has(child.tagName)) continue;
    content.push(...blockNodes(child, context));
    if (context.stats.nodes > MAX_MODEL_NODES) {
      throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.PROCESSING_LIMIT_EXCEEDED);
    }
  }
  if (content.length === 0) content.push({ type: "paragraph" });

  const editorJson = { type: "doc", content };
  if (!validateDocumentEditorJson(editorJson).ok) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED);
  }

  const model = {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: sanitizeImportedFilename(filename),
    sections: [
      {
        sectionId: "contenido-importado",
        title: "Contenido importado",
        description: "Contenido convertido localmente. Revisa las advertencias antes de continuar.",
        content: editorJson,
      },
    ],
  };
  if (!validateDocumentModel(model).ok) {
    throw new DocxImportError(DOCX_IMPORT_ERROR_CODES.CONVERSION_FAILED);
  }

  const recognized = {
    headings: content.filter((node) => node.type === "heading").length,
    paragraphs: content.filter((node) => node.type === "paragraph").length,
    orderedLists: content.filter((node) => node.type === "orderedList").length,
    unorderedLists: content.filter((node) => node.type === "bulletList").length,
    bold: JSON.stringify(editorJson).match(/"type":"bold"/gu)?.length ?? 0,
    italic: JSON.stringify(editorJson).match(/"type":"italic"/gu)?.length ?? 0,
    links: JSON.stringify(editorJson).match(/"type":"link"/gu)?.length ?? 0,
  };

  return { model, warnings: context.warnings, recognized };
}
