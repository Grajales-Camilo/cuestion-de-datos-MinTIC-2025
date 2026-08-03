import { useId, useState } from "react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { MAX_QUESTION_LENGTH, MIN_QUESTION_LENGTH, validateQuestion } from "../../lib/agent/questionValidation";
import { SECTION_CONTEXT_HINT_MAX_LENGTH } from "../../lib/document/sectionContextHint";

/**
 * Vista previa y confirmación de "Investigar esta sección" (F5-03A,
 * RF-104). Muestra el `context_hint` LITERAL que se enviaría — nunca lo
 * edita ni lo recalcula — y pide la pregunta al humano: este incremento no
 * usa un LLM ni fabrica la pregunta automáticamente.
 *
 * Ningún `POST` ocurre mientras este modal está abierto: `onConfirm` es la
 * única vía hacia `useAgentRun().start`, y solo se invoca tras validar la
 * pregunta en el propio formulario. "Cancelar" (o Escape/cerrar) nunca la
 * invoca.
 */
export function SectionInvestigateModal({ sectionTitle, contextHint, contextSource = "section", onCancel, onConfirm }) {
  const questionId = useId();
  const [question, setQuestion] = useState("");
  const [touched, setTouched] = useState(false);

  const { trimmed, tooShort, isValid } = validateQuestion(question);

  function handleSubmit(event) {
    event.preventDefault();
    setTouched(true);
    if (!isValid) return;
    onConfirm(trimmed);
  }

  return (
    <Modal open onClose={onCancel} title={`Investigar esta sección: ${sectionTitle}`}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-cdt-3" noValidate>
        <p className="text-cdt-sm text-cdt-slate-600">
          Sección activa: <strong>{sectionTitle}</strong>
        </p>

        <div>
          <p id={`${questionId}-context-label`} className="mb-cdt-1 text-cdt-sm font-cdt-bold text-cdt-slate-900">
            {contextSource === "selection"
              ? "Contexto que se enviará (texto seleccionado en la sección)"
              : "Contexto que se enviará (texto literal de la sección)"}
          </p>
          <div
            role="region"
            aria-labelledby={`${questionId}-context-label`}
            className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-cdt-md border border-cdt-blue-100 bg-cdt-blue-50 p-cdt-2 text-cdt-sm text-cdt-slate-900"
          >
            {contextHint.value}
          </div>
          <p className="mt-cdt-1 text-cdt-xs text-cdt-slate-600">
            {contextHint.value.length}/{SECTION_CONTEXT_HINT_MAX_LENGTH} caracteres
          </p>
          {contextHint.truncated ? (
            <p role="status" className="mt-cdt-1 text-cdt-xs text-cdt-warning">
              El contexto de esta sección se acortó a {SECTION_CONTEXT_HINT_MAX_LENGTH} caracteres.
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor={questionId} className="mb-cdt-1 block text-cdt-sm font-cdt-bold text-cdt-slate-900">
            Pregunta para investigar
          </label>
          <textarea
            id={questionId}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onBlur={() => setTouched(true)}
            maxLength={MAX_QUESTION_LENGTH}
            rows={3}
            required
            aria-describedby={`${questionId}-count`}
            aria-invalid={touched && !isValid ? "true" : undefined}
            className="w-full rounded-cdt-md border border-cdt-blue-100 p-cdt-2 text-cdt-base text-cdt-slate-900"
          />
          <p id={`${questionId}-count`} className="mt-cdt-1 text-cdt-xs text-cdt-slate-600">
            {trimmed.length}/{MAX_QUESTION_LENGTH} caracteres (mínimo {MIN_QUESTION_LENGTH})
          </p>
          {touched && tooShort ? (
            <p role="alert" className="text-cdt-xs text-cdt-error">
              La pregunta debe tener al menos {MIN_QUESTION_LENGTH} caracteres.
            </p>
          ) : null}
          {touched && trimmed.length === 0 ? (
            <p role="alert" className="text-cdt-xs text-cdt-error">
              La pregunta es obligatoria.
            </p>
          ) : null}
        </div>

        <div className="flex justify-end gap-cdt-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary">
            Investigar con este contexto
          </Button>
        </div>
      </form>
    </Modal>
  );
}
