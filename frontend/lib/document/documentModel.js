/**
 * Modelo documental versionado y puro (F5-03A, RF-101/RF-104/RF-101-01). Sin
 * React, sin `fetch`, sin acceso a `document`/almacenamiento — igual que
 * `lib/document/evidenceCitation.js` y `lib/agent/contextHint.js`.
 *
 * Forma:
 * {
 *   version, templateId, title,
 *   sections: [{ sectionId, title, description?, content: ProseMirrorJSON }]
 * }
 *
 * RF-101-01 implementa las tres plantillas aprobadas de RF-101: "libre",
 * "mga" (estructura y contenido de sección aprobados en
 * `docs/frontend-v2/adr/ADR-0005-plantilla-mga.md`) y "plan-de-desarrollo"
 * (`docs/frontend-v2/adr/ADR-0004-plantilla-plan-de-desarrollo.md`). Los
 * `sectionId`/`title`/`description` de MGA y plan de desarrollo son los
 * literales aprobados en esos ADR, reproducidos aquí sin reinterpretarlos.
 * No se reutiliza `frontend/data/policyTemplates.js` (legacy, cubre solo
 * contenidos del módulo de Identificación de la MGA oficial — ver ADR-0005
 * §Contexto). `DOCUMENT_MODEL_VERSION` no cambia: las tres plantillas
 * comparten exactamente la misma forma plana de documento.
 */

import { EMPTY_DOCUMENT_JSON, validateDocumentEditorJson } from "./documentSchema.js";

export const DOCUMENT_MODEL_VERSION = 1;
export const FREE_TEMPLATE_ID = "libre";
export const MGA_TEMPLATE_ID = "mga";
export const PLAN_DE_DESARROLLO_TEMPLATE_ID = "plan-de-desarrollo";

/** IDs canónicos exactos aprobados por RF-101. Ninguna variante (mayúsculas,
 * espacios, sinónimos) se normaliza ni se acepta — ver `validateDocumentModel`. */
export const APPROVED_TEMPLATE_IDS = Object.freeze([
  FREE_TEMPLATE_ID,
  MGA_TEMPLATE_ID,
  PLAN_DE_DESARROLLO_TEMPLATE_ID,
]);

const APPROVED_TEMPLATE_ID_SET = new Set(APPROVED_TEMPLATE_IDS);

export const DOCUMENT_MODEL_ERROR_CODES = Object.freeze({
  INVALID_DOCUMENT: "INVALID_DOCUMENT",
  INVALID_VERSION: "INVALID_VERSION",
  INVALID_TEMPLATE_ID: "INVALID_TEMPLATE_ID",
  INVALID_TITLE: "INVALID_TITLE",
  INVALID_SECTIONS: "INVALID_SECTIONS",
  INVALID_SECTION_ID: "INVALID_SECTION_ID",
  DUPLICATE_SECTION_ID: "DUPLICATE_SECTION_ID",
  INVALID_SECTION_CONTENT: "INVALID_SECTION_CONTENT",
});

/** Código de error de `createTemplateDocument` para un `templateId` que no
 * está en `APPROVED_TEMPLATE_IDS` — nunca cae a "libre" ni a ningún otro
 * valor por defecto. */
export const TEMPLATE_DOCUMENT_ERROR_CODES = Object.freeze({
  UNKNOWN_TEMPLATE_ID: "UNKNOWN_TEMPLATE_ID",
});

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

/**
 * Valida el documento completo. Una sola sección inválida invalida el
 * documento entero: no hay carga parcial (F5-03A, regla explícita).
 *
 * @param {unknown} doc
 * @returns {{ok: true}|{ok: false, code: string, sectionId?: string}}
 */
export function validateDocumentModel(doc) {
  if (!isPlainObject(doc)) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_DOCUMENT };
  }
  if (doc.version !== DOCUMENT_MODEL_VERSION) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_VERSION };
  }
  // Exclusivamente los tres IDs de APPROVED_TEMPLATE_IDS en
  // DOCUMENT_MODEL_VERSION=1 (F5-03A-R1, RF-101-01). Comparación estricta
  // por pertenencia a un Set, sin normalizar mayúsculas/espacios ni reparar
  // el valor: "MGA", " libre", "Plan-De-Desarrollo" o cualquier ID no
  // aprobado quedan rechazados explícitamente, fail-closed.
  if (typeof doc.templateId !== "string" || !APPROVED_TEMPLATE_ID_SET.has(doc.templateId)) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_TEMPLATE_ID };
  }
  if (!isNonEmptyString(doc.title)) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_TITLE };
  }
  if (!Array.isArray(doc.sections) || doc.sections.length === 0) {
    return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS };
  }

  const seenSectionIds = new Set();
  const seenManualEntryIds = new Set();
  for (const section of doc.sections) {
    if (!isPlainObject(section)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS };
    }
    if (!isNonEmptyString(section.sectionId)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTION_ID };
    }
    if (seenSectionIds.has(section.sectionId)) {
      return {
        ok: false,
        code: DOCUMENT_MODEL_ERROR_CODES.DUPLICATE_SECTION_ID,
        sectionId: section.sectionId,
      };
    }
    seenSectionIds.add(section.sectionId);

    if (!isNonEmptyString(section.title)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS, sectionId: section.sectionId };
    }
    if (section.description !== undefined && !isNonEmptyString(section.description)) {
      return { ok: false, code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTIONS, sectionId: section.sectionId };
    }

    const contentValidation = validateDocumentEditorJson(section.content, {
      seenManualEntryIds,
    });
    if (!contentValidation.ok) {
      return {
        ok: false,
        code: DOCUMENT_MODEL_ERROR_CODES.INVALID_SECTION_CONTENT,
        sectionId: section.sectionId,
      };
    }
  }

  return { ok: true };
}

/**
 * Especificaciones de sección de MGA y plan de desarrollo: literales
 * `sectionId`/`title`/`description` reproducidos EXACTAMENTE de la tabla
 * "Decisión" de sus respectivos ADR, sin reinterpretarlos ni resumirlos.
 * `Object.freeze` (objeto y arreglo) previene mutación accidental de la
 * fuente compartida entre invocaciones — la copia real ocurre en
 * `buildSectionsFromSpec`, nunca aquí.
 */
const MGA_TEMPLATE_SECTION_SPECS = Object.freeze([
  Object.freeze({
    sectionId: "problematica",
    title: "Problemática",
    description: "Describe el problema central, sus causas, efectos y la situación que se busca transformar.",
  }),
  Object.freeze({
    sectionId: "participantes_poblacion_localizacion",
    title: "Participantes, población y localización",
    description:
      "Identifica los actores involucrados, la población afectada y objetivo, y la localización del proyecto.",
  }),
  Object.freeze({
    sectionId: "objetivos",
    title: "Objetivos",
    description: "Define el objetivo general y los objetivos específicos relacionados con las causas del problema.",
  }),
  Object.freeze({
    sectionId: "alternativas",
    title: "Alternativas de solución",
    description: "Formula y compara las alternativas consideradas para alcanzar los objetivos.",
  }),
  Object.freeze({
    sectionId: "preparacion",
    title: "Preparación",
    description:
      "Desarrolla las necesidades, análisis técnico, localización, cadena de valor, costos, riesgos, ingresos y beneficios aplicables.",
  }),
  Object.freeze({
    sectionId: "evaluacion_ex_ante",
    title: "Evaluación ex ante",
    description:
      "Presenta el flujo de caja, los indicadores de evaluación financiera, económica o social aplicables y la justificación de la alternativa seleccionada.",
  }),
  Object.freeze({
    sectionId: "programacion",
    title: "Programación",
    description:
      "Define productos, indicadores de producto y gestión, metas, fuentes de verificación, supuestos y fuentes de financiación.",
  }),
]);

const PLAN_DE_DESARROLLO_TEMPLATE_SECTION_SPECS = Object.freeze([
  Object.freeze({
    sectionId: "diagnostico",
    title: "Diagnóstico",
    description: "Describe la situación actual, las problemáticas, brechas y líneas base que sustentan el plan.",
  }),
  Object.freeze({
    sectionId: "vision_articulacion",
    title: "Visión y articulación estratégica",
    description:
      "Define la visión de desarrollo, el objetivo general y su articulación con los instrumentos de planeación aplicables.",
  }),
  Object.freeze({
    sectionId: "programas_metas",
    title: "Programas, indicadores y metas",
    description:
      "Formula las líneas estratégicas, programas, objetivos específicos, indicadores de resultado y producto, y sus metas.",
  }),
  Object.freeze({
    sectionId: "ppi",
    title: "Plan plurianual de inversiones (PPI)",
    description: "Relaciona los programas con sus fuentes de financiación, recursos estimados y vigencias.",
  }),
  Object.freeze({
    sectionId: "seguimiento_evaluacion",
    title: "Seguimiento y evaluación",
    description:
      "Define los indicadores, responsables, periodicidad y mecanismos para revisar el avance y los resultados.",
  }),
]);

/**
 * Construye secciones nuevas (sin referencias compartidas entre secciones
 * ni entre invocaciones) a partir de una especificación congelada: cada
 * `content` es un `structuredClone` independiente de `EMPTY_DOCUMENT_JSON`
 * — ninguna sección arranca con contenido de dominio fabricado.
 */
function buildSectionsFromSpec(sectionSpecs) {
  return sectionSpecs.map(({ sectionId, title, description }) => ({
    sectionId,
    title,
    description,
    content: structuredClone(EMPTY_DOCUMENT_JSON),
  }));
}

/**
 * Plantilla libre: única plantilla real hasta RF-101-01. Una sección vacía,
 * sin contenido fabricado: el humano redacta, el agente no inventa
 * estructura de dominio.
 */
export function createFreeTemplateDocument() {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: FREE_TEMPLATE_ID,
    title: "Documento libre",
    sections: [
      {
        sectionId: "seccion-1",
        title: "Sección 1",
        content: structuredClone(EMPTY_DOCUMENT_JSON),
      },
    ],
  };
}

/**
 * Plantilla MGA (RF-101-01): las siete secciones aprobadas en ADR-0005,
 * todas vacías. No reutiliza `frontend/data/policyTemplates.js` (legacy,
 * cubre solo contenidos del módulo de Identificación) ni añade ejemplos.
 */
export function createMgaTemplateDocument() {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: MGA_TEMPLATE_ID,
    title: "Documento MGA",
    sections: buildSectionsFromSpec(MGA_TEMPLATE_SECTION_SPECS),
  };
}

/**
 * Plantilla plan de desarrollo (RF-101-01): las cinco secciones aprobadas
 * en ADR-0004, todas vacías.
 */
export function createPlanDeDesarrolloTemplateDocument() {
  return {
    version: DOCUMENT_MODEL_VERSION,
    templateId: PLAN_DE_DESARROLLO_TEMPLATE_ID,
    title: "Documento plan de desarrollo",
    sections: buildSectionsFromSpec(PLAN_DE_DESARROLLO_TEMPLATE_SECTION_SPECS),
  };
}

/**
 * Registro cerrado de factorías, una por ID aprobado. `Map`, no un objeto
 * plano: evita que un `templateId` como `"constructor"` o `"toString"`
 * resuelva accidentalmente contra `Object.prototype` en vez de fallar. Solo
 * este módulo puede registrar factorías — no hay forma de extenderlo desde
 * fuera.
 */
const TEMPLATE_DOCUMENT_FACTORIES = new Map([
  [FREE_TEMPLATE_ID, createFreeTemplateDocument],
  [MGA_TEMPLATE_ID, createMgaTemplateDocument],
  [PLAN_DE_DESARROLLO_TEMPLATE_ID, createPlanDeDesarrolloTemplateDocument],
]);

/**
 * Factoría pública única que despacha por `templateId`. Un ID que no esté
 * en `APPROVED_TEMPLATE_IDS` falla determinísticamente (lanza) — nunca cae
 * a "libre" ni a ningún otro valor por defecto. Cada llamada devuelve un
 * documento nuevo, con secciones y contenido ProseMirror propios (ver
 * `buildSectionsFromSpec`).
 *
 * @param {unknown} templateId
 * @returns {object} un DocumentModel nuevo y válido.
 * @throws {Error} si `templateId` no está en `APPROVED_TEMPLATE_IDS`.
 */
export function createTemplateDocument(templateId) {
  const factory = TEMPLATE_DOCUMENT_FACTORIES.get(templateId);
  if (typeof factory !== "function") {
    throw new Error(
      `${TEMPLATE_DOCUMENT_ERROR_CODES.UNKNOWN_TEMPLATE_ID}: ${JSON.stringify(templateId)}`,
    );
  }
  return factory();
}
