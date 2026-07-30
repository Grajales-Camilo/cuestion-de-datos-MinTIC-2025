/**
 * Recorrido ProseMirror → árbol `docx` (F6-02A, RF-102/RF-103). Puro: sin
 * React, sin DOM, sin `fetch`. Nunca llamado directamente por UI — solo por
 * `exportDocx.js`, que ya validó el `DocumentModel` completo con la fuente de
 * verdad (`documentModel.js`) antes de invocar este módulo. Este árbol NO
 * repite esa validación de forma, pero sí falla cerrado (lanza
 * `UnsupportedContentError`) ante cualquier nodo que no reconozca — nunca
 * ignora, repara ni completa contenido en silencio.
 *
 * Notas al pie (RF-103): cada `evidenceCitation` recibe un id de nota
 * secuencial asignado en el ORDEN DE RECORRIDO del documento (profundidad,
 * sección por sección) — nunca del orden de iteración de un objeto/mapa —
 * así que dos citas distintas siempre quedan en un orden determinista y
 * reproducible entre corridas.
 */

import {
  AlignmentType,
  Document,
  ExternalHyperlink,
  FootnoteReferenceRun,
  HeadingLevel,
  LevelFormat,
  Paragraph,
  TextRun,
} from "docx";
import { getSafeExternalUrl } from "../evidence/safeExternalUrl.js";
import { validateManualEntryAttrs } from "./manualEntry.js";

const HEADING_LEVELS = Object.freeze({
  2: HeadingLevel.HEADING_2,
  3: HeadingLevel.HEADING_3,
  4: HeadingLevel.HEADING_4,
});

const ORDERED_LIST_REFERENCE = "cdd-export-ordered-list";
const MAX_LIST_LEVELS = 4;
const BLOCKQUOTE_INDENT_TWIPS = 720;

export class UnsupportedContentError extends Error {
  constructor(reason) {
    super("UNSUPPORTED_CONTENT");
    this.name = "UnsupportedContentError";
    this.reason = reason;
  }
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function runsFromInline(content) {
  if (content === undefined) return [];
  if (!Array.isArray(content)) throw new UnsupportedContentError("inline_content_not_array");

  return content.map((node) => {
    if (!isPlainObject(node) || node.type !== "text" || typeof node.text !== "string") {
      throw new UnsupportedContentError(`inline_node:${node?.type ?? "unknown"}`);
    }
    const marks = Array.isArray(node.marks) ? node.marks : [];
    return new TextRun({
      text: node.text,
      bold: marks.some((mark) => mark?.type === "bold"),
      italics: marks.some((mark) => mark?.type === "italic"),
    });
  });
}

function paragraphOptionsForContext(ctx) {
  const options = {};
  if (ctx.list) {
    if (ctx.list.kind === "bullet") {
      options.bullet = { level: ctx.list.level };
    } else {
      options.numbering = { reference: ORDERED_LIST_REFERENCE, level: ctx.list.level };
    }
  }
  if (ctx.blockquote) {
    options.indent = { left: BLOCKQUOTE_INDENT_TWIPS };
  }
  return options;
}

function buildParagraph(inlineContent, ctx, extra = {}) {
  const runs = runsFromInline(inlineContent);
  return new Paragraph({
    children: runs.length > 0 ? runs : [new TextRun("")],
    ...paragraphOptionsForContext(ctx),
    ...extra,
  });
}

function buildList(node, ctx, kind) {
  const items = Array.isArray(node.content) ? node.content : [];
  const level = (ctx.list?.level ?? -1) + 1;
  if (level >= MAX_LIST_LEVELS) throw new UnsupportedContentError("list_nesting_too_deep");

  return items.flatMap((item) => {
    if (!isPlainObject(item) || item.type !== "listItem") {
      throw new UnsupportedContentError(`list_item:${item?.type ?? "unknown"}`);
    }
    const children = Array.isArray(item.content) ? item.content : [];
    return children.flatMap((child) => buildParagraphsForBlock(child, { ...ctx, list: { kind, level } }));
  });
}

function labeledParagraph(label, value, ctx) {
  return new Paragraph({
    children: [new TextRun({ text: `${label}: `, bold: true }), new TextRun(String(value))],
    ...paragraphOptionsForContext(ctx),
  });
}

/** Construye un párrafo de URL con hipervínculo. El atributo YA fue validado
 * por la fuente de verdad correspondiente antes de invocar este módulo; esta
 * llamada a `getSafeExternalUrl` es una segunda barrera defensiva. Si no pasa,
 * la construcción entera del documento se aborta, nunca se degrada a texto
 * plano con una URL insegura. */
function sourceUrlParagraph(sourceUrl, label = "Fuente") {
  const safeUrl = getSafeExternalUrl(sourceUrl);
  if (safeUrl === null) throw new UnsupportedContentError("unsafe_source_url");

  return new Paragraph({
    children: [
      new TextRun(`${label}: `),
      new ExternalHyperlink({ children: [new TextRun({ text: safeUrl, style: "Hyperlink" })], link: safeUrl }),
    ],
  });
}

/** Cuerpo de la nota al pie de una cita (RF-103): los 6 campos obligatorios
 * (F5-01) tal cual están almacenados, sin reformular ni completar, más los
 * metadatos temporales/de calidad que el nodo realmente tenga. Nunca inventa
 * un campo ausente: los opcionales solo aparecen si el atributo existe. */
function buildFootnoteBody(attrs) {
  const lines = [
    labeledParagraph("Conjunto de datos", `${attrs.datasetName} (${attrs.datasetId})`, {}),
    labeledParagraph("Entidad publicadora", attrs.publisher, {}),
    labeledParagraph("Consulta SoQL", attrs.soqlQuery, {}),
    labeledParagraph("Fecha de consulta", attrs.executedAt, {}),
    sourceUrlParagraph(attrs.sourceUrl),
  ];

  if (attrs.dataUpdatedAt !== undefined && attrs.dataUpdatedAt !== null) {
    lines.push(labeledParagraph("Fecha de actualización de la fuente", attrs.dataUpdatedAt, {}));
  }
  if (attrs.dataCutoffAt !== undefined && attrs.dataCutoffAt !== null) {
    lines.push(labeledParagraph("Corte de los datos", attrs.dataCutoffAt, {}));
  }
  if (attrs.dataCutoffBasis !== undefined && attrs.dataCutoffBasis !== null) {
    lines.push(labeledParagraph("Base del corte", attrs.dataCutoffBasis, {}));
  }
  if (attrs.qualityScore !== undefined && attrs.qualityScore !== null) {
    lines.push(labeledParagraph("Puntaje de calidad", attrs.qualityScore, {}));
  }
  if (attrs.qualityClassification !== undefined && attrs.qualityClassification !== null) {
    lines.push(labeledParagraph("Clasificación de calidad", attrs.qualityClassification, {}));
  }
  if (attrs.warningRequired === true) {
    lines.push(
      new Paragraph({
        children: [
          new TextRun({
            text: "Advertencia: esta evidencia no es recomendada. Revísela con especial cuidado antes de citarla.",
            bold: true,
          }),
        ],
      }),
    );
  }

  return lines;
}

/** `claim.label === null` es un estado LEGÍTIMO (evidenceCitation.js:
 * `claim.label === null || isNonEmptyString(claim.label)`), no un error ni
 * un dato ausente que haya que rellenar. F6-02A-R1: nunca se fabrica una
 * etiqueta ("Etiqueta no confirmada", "Sin etiqueta", ni ninguna
 * reconstrucción desde `claimId`/columnas/dataset/SoQL) — se muestra
 * `displayValue`/`unit` tal cual, sin prefijo, cuando no hay `label`. */
function formatClaimText(claim) {
  const value = `${claim.displayValue}${claim.unit ? ` ${claim.unit}` : ""}`;
  return claim.label !== null ? `${claim.label}: ${value}` : value;
}

/** Párrafo(s) del cuerpo para un `evidenceCitation` + registro de su nota al
 * pie asociada (RF-103). `ctx.footnotes`/`ctx.footnoteCounter` son
 * compartidos por referencia durante todo el recorrido del documento. */
function buildCitationParagraphs(node, ctx) {
  const attrs = isPlainObject(node.attrs) ? node.attrs : {};
  ctx.footnoteCounter.value += 1;
  const footnoteId = ctx.footnoteCounter.value;

  const claims = Array.isArray(attrs.claims) ? attrs.claims : [];
  const claimsText =
    claims.length > 0
      ? claims.map((claim) => formatClaimText(claim)).join("; ")
      : `Evidencia citada: ${attrs.datasetName ?? "conjunto de datos"}`;

  const bodyRuns = [];
  if (attrs.warningRequired === true) {
    bodyRuns.push(new TextRun({ text: "Advertencia — evidencia no recomendada: ", bold: true }));
  }
  bodyRuns.push(new TextRun(claimsText));
  bodyRuns.push(new FootnoteReferenceRun(footnoteId));

  ctx.footnotes[String(footnoteId)] = { children: buildFootnoteBody(attrs) };

  return [new Paragraph({ children: bodyRuns, ...paragraphOptionsForContext(ctx) })];
}

function manualEntryValueText(attrs) {
  const values = [];
  if (attrs.value !== undefined && attrs.value !== null) values.push(String(attrs.value));
  if (attrs.text !== undefined && attrs.text !== null) values.push(attrs.text);
  return values.join(" — ");
}

function buildManualEntryFootnoteBody(attrs) {
  const validation = validateManualEntryAttrs(attrs);
  if (!validation.ok) throw new UnsupportedContentError("invalid_manual_entry");

  const lines = [labeledParagraph("Fuente declarada", attrs.source, {})];
  if (attrs.url !== undefined && attrs.url !== null) {
    lines.push(sourceUrlParagraph(attrs.url, "URL declarada"));
  }
  if (attrs.date !== undefined && attrs.date !== null) {
    lines.push(labeledParagraph("Fecha declarada", attrs.date, {}));
  }
  return lines;
}

function buildManualEntryParagraphs(node, ctx) {
  const attrs = isPlainObject(node.attrs) ? node.attrs : {};
  const validation = validateManualEntryAttrs(attrs);
  if (!validation.ok) throw new UnsupportedContentError("invalid_manual_entry");

  ctx.footnoteCounter.value += 1;
  const footnoteId = ctx.footnoteCounter.value;
  const bodyRuns = [
    new TextRun({ text: "Aporte manual — no verificado por el agente", bold: true }),
    new TextRun(" — "),
    new TextRun(manualEntryValueText(attrs)),
    new FootnoteReferenceRun(footnoteId),
  ];

  ctx.footnotes[String(footnoteId)] = {
    children: buildManualEntryFootnoteBody(attrs),
  };
  return [new Paragraph({ children: bodyRuns, ...paragraphOptionsForContext(ctx) })];
}

function buildParagraphsForBlock(node, ctx) {
  if (!isPlainObject(node) || typeof node.type !== "string") {
    throw new UnsupportedContentError("invalid_node");
  }

  switch (node.type) {
    case "paragraph":
      return [buildParagraph(node.content, ctx)];
    case "heading": {
      const heading = HEADING_LEVELS[node.attrs?.level];
      if (!heading) throw new UnsupportedContentError(`heading_level:${node.attrs?.level}`);
      return [buildParagraph(node.content, ctx, { heading })];
    }
    case "blockquote": {
      const children = Array.isArray(node.content) ? node.content : [];
      return children.flatMap((child) => buildParagraphsForBlock(child, { ...ctx, blockquote: true }));
    }
    case "bulletList":
      return buildList(node, ctx, "bullet");
    case "orderedList":
      return buildList(node, ctx, "number");
    case "evidenceCitation":
      return buildCitationParagraphs(node, ctx);
    case "manualEntry":
      return buildManualEntryParagraphs(node, ctx);
    default:
      throw new UnsupportedContentError(`node_type:${node.type}`);
  }
}

/**
 * Construye el `docx.Document` completo a partir de un `DocumentModel` YA
 * VALIDADO por `validateDocumentModel` (F6-02A: esta función no vuelve a
 * validar forma, solo construye). Lanza `UnsupportedContentError` ante
 * cualquier nodo que no reconozca — el llamador debe tratar cualquier
 * excepción como un rechazo completo, nunca como una construcción parcial.
 */
export function buildDocxDocument(documentModel) {
  const ctx = {
    footnotes: {},
    footnoteCounter: { value: 0 },
    list: null,
    blockquote: false,
  };

  const bodyChildren = [new Paragraph({ text: documentModel.title, heading: HeadingLevel.TITLE })];

  for (const section of documentModel.sections) {
    bodyChildren.push(new Paragraph({ text: section.title, heading: HeadingLevel.HEADING_1 }));
    if (typeof section.description === "string" && section.description.trim() !== "") {
      bodyChildren.push(new Paragraph({ children: [new TextRun(section.description)] }));
    }

    const contentNodes = Array.isArray(section.content?.content) ? section.content.content : [];
    for (const node of contentNodes) {
      bodyChildren.push(...buildParagraphsForBlock(node, ctx));
    }
  }

  return new Document({
    footnotes: ctx.footnotes,
    numbering: {
      config: [
        {
          reference: ORDERED_LIST_REFERENCE,
          levels: Array.from({ length: MAX_LIST_LEVELS }, (_, level) => ({
            level,
            format: LevelFormat.DECIMAL,
            text: `%${level + 1}.`,
            alignment: AlignmentType.START,
          })),
        },
      ],
    },
    sections: [{ children: bodyChildren }],
  });
}
