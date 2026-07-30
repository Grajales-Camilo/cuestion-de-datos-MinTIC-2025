import { useId, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { cx } from "../ui/cx";
import {
  APPROVED_TEMPLATE_IDS,
  FREE_TEMPLATE_ID,
  MGA_TEMPLATE_ID,
  PLAN_DE_DESARROLLO_TEMPLATE_ID,
} from "../../lib/document/documentModel";

/**
 * Copy propia del selector (RF-101-02): describe brevemente el PROPÓSITO de
 * cada plantilla, nunca duplica las tablas de secciones aprobadas en
 * ADR-0004/ADR-0005 (ni sus títulos ni sus descripciones literales), no
 * promete que el agente completará ninguna sección y no inventa requisitos
 * legales ni contenido institucional.
 */
const TEMPLATE_OPTIONS = [
  {
    templateId: FREE_TEMPLATE_ID,
    label: "Libre",
    description: "Un documento en blanco, sin secciones predefinidas. Tú decides la estructura.",
  },
  {
    templateId: MGA_TEMPLATE_ID,
    label: "MGA",
    description:
      "Siete secciones para formular un proyecto de inversión según la Metodología General Ajustada del DNP.",
  },
  {
    templateId: PLAN_DE_DESARROLLO_TEMPLATE_ID,
    label: "Plan de desarrollo",
    description: "Cinco secciones para un plan de desarrollo territorial.",
  },
];

// Verificación en tiempo de carga del módulo: si documentModel.js cambiara
// APPROVED_TEMPLATE_IDS sin actualizar TEMPLATE_OPTIONS (o viceversa), esto
// falla de forma ruidosa en desarrollo/pruebas en vez de dejar que el
// selector ofrezca un ID no aprobado o le falte uno aprobado en silencio.
if (
  TEMPLATE_OPTIONS.length !== APPROVED_TEMPLATE_IDS.length ||
  !TEMPLATE_OPTIONS.every((option) => APPROVED_TEMPLATE_IDS.includes(option.templateId))
) {
  throw new Error("TemplatePicker: TEMPLATE_OPTIONS no coincide con APPROVED_TEMPLATE_IDS de documentModel.js");
}

/**
 * Selector visual accesible de plantilla (RF-101-02). Aparece EXCLUSIVAMENTE
 * cuando no hay documento restaurado que abrir (ver `pages/app.js`); nunca
 * se usa para cambiar la plantilla de un documento ya abierto — ese control
 * no existe en este incremento a propósito.
 *
 * Tres opciones mutuamente excluyentes con semántica nativa
 * (`fieldset`/`legend` + `input type="radio"` reales): el navegador entrega
 * gratis la navegación por flechas dentro del grupo, la activación con
 * espacio/click y el anuncio de "seleccionado" al lector de pantalla — no
 * se reimplementa un patrón ARIA `radiogroup` a mano. Cada tarjeta completa
 * es un `<label>` (área activable ≥44×44px), pero la selección nunca depende
 * solo del color: se refuerza con el icono `CheckCircle2` + peso de fuente.
 *
 * `onCreateDocument(templateId)` se llama UNA sola vez, exclusivamente con
 * uno de los tres IDs aprobados (los únicos que este componente puede
 * producir, por construcción de `TEMPLATE_OPTIONS`).
 */
export function TemplatePicker({ onCreateDocument }) {
  const [selectedTemplateId, setSelectedTemplateId] = useState(null);
  const baseId = useId();
  const legendId = `${baseId}-legend`;
  const groupName = `${baseId}-template`;

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!selectedTemplateId) return;
    onCreateDocument(selectedTemplateId);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-cdt-4" aria-labelledby={legendId}>
      <fieldset className="m-0 flex flex-col gap-cdt-3 border-0 p-0">
        <legend id={legendId} className="px-0 text-cdt-lg font-cdt-bold text-cdt-blue-900">
          Elige una plantilla para tu documento
        </legend>
        <div className="flex flex-col gap-cdt-3 sm:flex-row sm:flex-wrap">
          {TEMPLATE_OPTIONS.map((option) => {
            const isSelected = selectedTemplateId === option.templateId;
            const inputId = `${baseId}-${option.templateId}`;
            return (
              <Card
                key={option.templateId}
                as="label"
                htmlFor={inputId}
                className={cx(
                  "flex min-h-cdt-tap cursor-pointer flex-col gap-cdt-2 p-cdt-4 sm:w-64",
                  isSelected ? "!border-cdt-blue-700" : null,
                )}
              >
                <span className="flex items-center gap-cdt-2">
                  <input
                    id={inputId}
                    type="radio"
                    name={groupName}
                    value={option.templateId}
                    checked={isSelected}
                    onChange={() => setSelectedTemplateId(option.templateId)}
                    className="h-4 w-4 flex-shrink-0"
                  />
                  <span className="font-cdt-bold text-cdt-sm text-cdt-slate-900">{option.label}</span>
                  {isSelected ? (
                    <CheckCircle2 className="h-4 w-4 text-cdt-blue-700" aria-hidden="true" focusable="false" />
                  ) : null}
                </span>
                <span className="text-cdt-xs text-cdt-slate-600">{option.description}</span>
              </Card>
            );
          })}
        </div>
      </fieldset>
      <Button type="submit" variant="primary" disabled={!selectedTemplateId} className="self-start">
        Crear documento
      </Button>
    </form>
  );
}
