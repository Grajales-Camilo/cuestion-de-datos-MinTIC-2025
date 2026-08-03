import { useEffect, useId, useState } from "react";
import { Button } from "../ui/Button";
import { normalizeContextHint } from "../../lib/agent/contextHint";
import { MAX_QUESTION_LENGTH, MIN_QUESTION_LENGTH, validateQuestion } from "../../lib/agent/questionValidation";

// Límite del contrato (`contracts/api-rest.md` §2): context_hint <=2000
// caracteres. Los límites de `question` viven en `questionValidation.js`,
// compartidos con el flujo de "Investigar esta sección" (F5-03A).
const MAX_CONTEXT_HINT_LENGTH = 2000;

function normalize(text) {
  return normalizeContextHint(text ?? "", { maxLength: MAX_CONTEXT_HINT_LENGTH });
}

/**
 * Formulario simple, no una metáfora de chat: una pregunta, un contexto
 * opcional visible y editable, un botón "Investigar". Nunca envía el
 * documento completo — solo estos dos campos acotados. Bloquea el submit
 * sin consentimiento antes de invocar `onSubmit` (que el padre conecta a
 * `useAgentRun().start`, o intercepta para abrir el modal de
 * consentimiento con este mismo borrador — F3-7B).
 *
 * `contextHint` se normaliza con la misma función pura
 * (`lib/agent/contextHint.js`) tanto al recibir `initialContextHint` como
 * en cada edición del usuario: el valor mostrado en el `<textarea>` es,
 * byte a byte, el que llega a `onSubmit` — nunca un truncamiento distinto
 * hecho por el atributo nativo `maxLength` a mitad de palabra.
 *
 * `prefill` (opcional) permite precargar pregunta/contexto desde una
 * investigación anterior ("Refinar", F3-7B). Cambiar `prefill.nonce`
 * fuerza una nueva aplicación aunque los valores sean idénticos a los ya
 * mostrados.
 */
export function QuestionComposer({
  onSubmit,
  consentGranted,
  disabled = false,
  initialContextHint = "",
  prefill = null,
}) {
  const questionId = useId();
  const contextId = useId();
  const initialNormalized = normalize(initialContextHint);
  const [question, setQuestion] = useState("");
  const [contextHint, setContextHint] = useState(initialNormalized.value);
  const [contextTruncated, setContextTruncated] = useState(initialNormalized.truncated);
  const [contextFieldVisible, setContextFieldVisible] = useState(Boolean(initialContextHint));
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!prefill) return;
    setQuestion(prefill.question ?? "");
    const normalized = normalize(prefill.contextHint ?? "");
    setContextHint(normalized.value);
    setContextTruncated(normalized.truncated);
    if (prefill.contextHint) setContextFieldVisible(true);
    setTouched(false);
    // Solo re-aplicar cuando cambia explícitamente el borrador (`nonce`),
    // nunca por una referencia nueva del mismo objeto en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill?.nonce]);

  function handleContextChange(event) {
    const normalized = normalize(event.target.value);
    setContextHint(normalized.value);
    setContextTruncated(normalized.truncated);
  }

  const { trimmed, tooShort, isValid } = validateQuestion(question);

  function handleSubmit(event) {
    event.preventDefault();
    setTouched(true);
    if (!isValid || consentGranted !== true || disabled) return;
    onSubmit({
      question: trimmed,
      contextHint: contextHint.trim() ? contextHint.trim() : undefined,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-cdt-3" noValidate>
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

      {contextFieldVisible ? (
        <div>
          <label htmlFor={contextId} className="mb-cdt-1 block text-cdt-sm font-cdt-bold text-cdt-slate-900">
            Contexto de la sección (editable)
          </label>
          <textarea
            id={contextId}
            value={contextHint}
            onChange={handleContextChange}
            rows={2}
            aria-describedby={contextTruncated ? `${contextId}-truncated` : undefined}
            className="w-full rounded-cdt-md border border-cdt-blue-100 p-cdt-2 text-cdt-sm text-cdt-slate-900"
          />
          <p className="mt-cdt-1 text-cdt-xs text-cdt-slate-600">
            {contextHint.length}/{MAX_CONTEXT_HINT_LENGTH} caracteres
          </p>
          {contextTruncated ? (
            <p id={`${contextId}-truncated`} role="status" className="mt-cdt-1 text-cdt-xs text-cdt-warning">
              El contexto se acortó a {MAX_CONTEXT_HINT_LENGTH} caracteres. Puedes editarlo antes de investigar.
            </p>
          ) : null}
        </div>
      ) : null}

      <Button type="submit" variant="primary" disabled={disabled}>
        Investigar
      </Button>
      {consentGranted !== true ? (
        <p className="text-cdt-xs text-cdt-slate-600">Debes aceptar el aviso de almacenamiento antes de investigar.</p>
      ) : null}
    </form>
  );
}
