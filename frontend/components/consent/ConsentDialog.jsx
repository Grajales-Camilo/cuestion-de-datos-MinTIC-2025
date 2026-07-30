import { useEffect, useId, useState } from "react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { normalizeContextHint } from "../../lib/agent/contextHint";

const MAX_CONTEXT_HINT_LENGTH = 1000;

/** Título y cuerpo literales de D-9, aprobados por Juan Camilo Grajales B.
 * (`docs/frontend-v2/adr/`). No parafrasear ni resumir: es texto legal de
 * consentimiento, se muestra exactamente como fue aprobado. */
export const CONSENT_TITLE = "Antes de iniciar tu primera investigación";

const CONSENT_PARAGRAPHS = [
  "Cuestión de Datos enviará y almacenará tu pregunta y, si la incluyes, un fragmento editable de contexto de máximo 1.000 caracteres. También conservará los pasos de la investigación, las trazas técnicas, las evidencias y el resultado para prestar el servicio y evaluar técnicamente su funcionamiento.",
  "Las investigaciones de usuario se conservan hasta 90 días y después se eliminan. Mientras una investigación aparezca en tu historial, puedes borrarla de forma completa e irreversible con la opción «Borrar esta investigación».",
  "El documento completo en el que trabajas no se envía al servidor.",
];

const REMEMBER_LABEL =
  "Recordar mis investigaciones en este equipo. Si activas esta opción, las credenciales de acceso permanecerán guardadas en este navegador después de cerrar la pestaña. Úsala solo en un equipo personal o de confianza.";

/**
 * Modal de consentimiento versionado (D-9, RF-802). Se abre con el borrador
 * exacto (`draft.question`/`draft.contextHint`) que `startRun` recibirá si
 * el usuario acepta — nunca un resumen ni una reformulación. El contexto es
 * editable aquí mismo y pasa por la misma `normalizeContextHint` que
 * `QuestionComposer`, así que el valor final de aceptar es, byte a byte, el
 * que se envía.
 *
 * Reutiliza `Modal` (F1): trampa de foco, `Escape`, restauración de foco y
 * `role="dialog"` ya están resueltos ahí. El foco inicial cae en el botón
 * "Cerrar" del propio `Modal` (primer elemento enfocable del DOM), nunca en
 * "Aceptar e investigar" — y no hay `<form>` que un `Enter` pueda enviar
 * implícitamente: los dos botones son manejadores explícitos.
 */
export function ConsentDialog({ open, draft, rememberRuns, onRememberRunsChange, onAccept, onCancel }) {
  const rememberId = useId();
  const normalizedInitial = normalizeContextHint(draft?.contextHint ?? "", { maxLength: MAX_CONTEXT_HINT_LENGTH });
  const [contextHint, setContextHint] = useState(normalizedInitial.value);
  const [truncated, setTruncated] = useState(normalizedInitial.truncated);

  useEffect(() => {
    if (!open) return;
    const normalized = normalizeContextHint(draft?.contextHint ?? "", { maxLength: MAX_CONTEXT_HINT_LENGTH });
    setContextHint(normalized.value);
    setTruncated(normalized.truncated);
    // Se re-sincroniza cada vez que el modal se abre con un borrador nuevo,
    // nunca en cada tecleo del propio modal (eso lo maneja handleChange).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, draft?.question, draft?.contextHint]);

  function handleContextChange(event) {
    const normalized = normalizeContextHint(event.target.value, { maxLength: MAX_CONTEXT_HINT_LENGTH });
    setContextHint(normalized.value);
    setTruncated(normalized.truncated);
  }

  if (!draft) return null;

  return (
    <Modal open={open} onClose={onCancel} title={CONSENT_TITLE} className="max-w-lg">
      <div className="flex flex-col gap-cdt-4 text-cdt-sm text-cdt-slate-900">
        {CONSENT_PARAGRAPHS.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}

        <div>
          <p className="mb-cdt-1 text-cdt-xs font-cdt-bold text-cdt-slate-600">Tu pregunta</p>
          <p className="rounded-cdt-md border border-cdt-blue-100 bg-cdt-blue-50 p-cdt-2 text-cdt-sm text-cdt-slate-900">
            {draft.question}
          </p>
        </div>

        <div>
          <label htmlFor={`${rememberId}-context`} className="mb-cdt-1 block text-cdt-xs font-cdt-bold text-cdt-slate-600">
            Contexto que se enviará (editable)
          </label>
          <textarea
            id={`${rememberId}-context`}
            value={contextHint}
            onChange={handleContextChange}
            rows={3}
            aria-describedby={truncated ? `${rememberId}-truncated` : undefined}
            className="w-full rounded-cdt-md border border-cdt-blue-100 p-cdt-2 text-cdt-sm text-cdt-slate-900"
          />
          <p className="mt-cdt-1 text-cdt-xs text-cdt-slate-600">
            {contextHint.length}/{MAX_CONTEXT_HINT_LENGTH} caracteres
          </p>
          {truncated ? (
            <p id={`${rememberId}-truncated`} role="status" className="mt-cdt-1 text-cdt-xs text-cdt-warning">
              El contexto se acortó a {MAX_CONTEXT_HINT_LENGTH} caracteres.
            </p>
          ) : null}
        </div>

        <label htmlFor={rememberId} className="flex items-start gap-cdt-2 text-cdt-xs text-cdt-slate-600">
          <input
            id={rememberId}
            type="checkbox"
            checked={rememberRuns}
            onChange={(event) => onRememberRunsChange(event.target.checked)}
            className="mt-cdt-1 h-4 w-4 shrink-0"
          />
          <span>{REMEMBER_LABEL}</span>
        </label>

        <div className="flex justify-end gap-cdt-2">
          <Button variant="secondary" onClick={onCancel}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={() => onAccept({ contextHint: contextHint.trim() ? contextHint.trim() : undefined })}>
            Aceptar e investigar
          </Button>
        </div>
      </div>
    </Modal>
  );
}
