import { useEffect, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import {
  MANUAL_ENTRY_ERROR_CODES,
  validateManualEntryInput,
} from "../../lib/document/manualEntry.js";
import { toManualEntryInitialValues } from "../../lib/agent/externalSources.js";

const ERROR_MESSAGES = Object.freeze({
  [MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE]: "La fuente es obligatoria.",
  [MANUAL_ENTRY_ERROR_CODES.MISSING_VALUE_OR_TEXT]: "Escribe un valor o una descripción.",
  [MANUAL_ENTRY_ERROR_CODES.INVALID_VALUE]: "Escribe un valor o una descripción.",
  [MANUAL_ENTRY_ERROR_CODES.UNSAFE_URL]: "La URL debe ser una dirección HTTPS segura y absoluta.",
  [MANUAL_ENTRY_ERROR_CODES.INVALID_DATE]: "La fecha de la fuente no es válida.",
  [MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED]:
    "No pudimos guardar el aporte porque contiene información sensible.",
});

function formPayload(state) {
  return {
    value: state.value === "" ? null : state.value,
    text: state.text === "" ? null : state.text,
    source: state.source,
    url: state.url === "" ? null : state.url,
    date: state.date === "" ? null : state.date,
  };
}

const FIELD_CLASS =
  "mt-cdt-1 w-full rounded-cdt-md border border-cdt-blue-100 bg-cdt-white px-cdt-3 py-cdt-2 text-cdt-sm text-cdt-slate-900 focus:border-cdt-blue-500 focus:outline-none focus:ring-2 focus:ring-cdt-blue-500";

/**
 * Modal de captura local. Solo entrega los cinco campos que el usuario puede
 * escribir; la generación de identidad y timestamp pertenece al comando
 * seguro de Tiptap (T-506, RF-102, ESC-08, RNF-007/RNF-012).
 */
export function ManualDataEntry({ open, onClose, onSubmit, sectionTitle, initialValues = null }) {
  const initialFocusRef = useRef(null);
  const restoreFocusRef = useRef(true);
  const [state, setState] = useState({ value: "", text: "", source: "", url: "", date: "" });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [suggestionContext, setSuggestionContext] = useState("");

  useEffect(() => {
    if (!open) return;
    const prefill = initialValues ? toManualEntryInitialValues(initialValues) : null;
    setState({
      value: "",
      text: "",
      source: prefill?.source ?? "",
      url: prefill?.url ?? "",
      date: "",
    });
    setSuggestionContext(prefill?.suggestionContext ?? "");
    setFieldErrors({});
    setFormError("");
    restoreFocusRef.current = true;
  }, [open, initialValues]);

  function updateField(name, value) {
    setState((previous) => ({ ...previous, [name]: value }));
    setFieldErrors((previous) => ({ ...previous, [name]: "", value: "" }));
    setFormError("");
  }

  function handleSubmit(event) {
    event.preventDefault();
    const payload = formPayload(state);
    const validation = validateManualEntryInput(payload);
    if (!validation.ok) {
      const message =
        ERROR_MESSAGES[validation.code] ??
        "No pudimos validar el aporte. Revisa los campos e inténtalo de nuevo.";
      const valueAndTextEmpty = payload.value === null && payload.text === null;
      setFieldErrors({
        source: validation.code === MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE ? message : "",
        value:
          validation.code === MANUAL_ENTRY_ERROR_CODES.MISSING_VALUE_OR_TEXT ||
          validation.code === MANUAL_ENTRY_ERROR_CODES.INVALID_VALUE ||
          (validation.code === MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE && valueAndTextEmpty)
            ? validation.code === MANUAL_ENTRY_ERROR_CODES.MISSING_SOURCE && valueAndTextEmpty
              ? ERROR_MESSAGES[MANUAL_ENTRY_ERROR_CODES.MISSING_VALUE_OR_TEXT]
              : message
            : "",
        url: validation.code === MANUAL_ENTRY_ERROR_CODES.UNSAFE_URL ? message : "",
        date: validation.code === MANUAL_ENTRY_ERROR_CODES.INVALID_DATE ? message : "",
      });
      setFormError(
        validation.code === MANUAL_ENTRY_ERROR_CODES.SENSITIVE_DATA_DETECTED ? message : "",
      );
      return;
    }

    try {
      const inserted = onSubmit?.(payload);
      if (inserted !== true) {
        setFormError("No pudimos guardar el aporte. El documento no cambió.");
        return;
      }
      restoreFocusRef.current = false;
      onClose?.();
    } catch {
      setFormError("No pudimos guardar el aporte. El documento no cambió.");
    }
  }

  const title = "Agregar dato manual";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      initialFocusRef={initialFocusRef}
      restoreFocusRef={restoreFocusRef}
    >
      <p className="mb-cdt-4 text-cdt-sm text-cdt-slate-600">
        {sectionTitle ? `Sección: ${sectionTitle}. ` : ""}
        Este aporte quedará identificado como escrito por ti y no será verificado por el agente.
      </p>
      {suggestionContext ? (
        <div
          role="note"
          aria-label="Contexto de la fuente sugerida"
          className="mb-cdt-4 min-w-0 rounded-cdt-md bg-cdt-blue-50 p-cdt-3 text-cdt-sm text-cdt-slate-900"
        >
          <p className="font-cdt-bold text-cdt-blue-900">Por qué se sugirió esta fuente</p>
          <p className="mt-cdt-1 break-words">{suggestionContext}</p>
          <p className="mt-cdt-2 text-cdt-xs text-cdt-slate-600">
            Este contexto no se copiará al aporte. Escribe tú el valor o texto que quieras incorporar.
          </p>
        </div>
      ) : null}
      <form onSubmit={handleSubmit} noValidate className="flex min-w-0 flex-col gap-cdt-4">
        <div>
          <label htmlFor="manual-entry-value" className="text-cdt-sm font-cdt-bold text-cdt-slate-900">
            Valor <span className="font-cdt-normal text-cdt-slate-600">(opcional)</span>
          </label>
          <input
            ref={initialFocusRef}
            id="manual-entry-value"
            name="value"
            type="text"
            value={state.value}
            onChange={(event) => updateField("value", event.target.value)}
            aria-invalid={fieldErrors.value ? "true" : undefined}
            aria-describedby={fieldErrors.value ? "manual-entry-value-error" : undefined}
            className={FIELD_CLASS}
          />
          {fieldErrors.value ? <p id="manual-entry-value-error" role="alert" className="mt-cdt-1 text-cdt-xs text-cdt-error">{fieldErrors.value}</p> : null}
        </div>

        <div>
          <label htmlFor="manual-entry-text" className="text-cdt-sm font-cdt-bold text-cdt-slate-900">
            Texto o descripción <span className="font-cdt-normal text-cdt-slate-600">(opcional)</span>
          </label>
          <textarea
            id="manual-entry-text"
            name="text"
            rows={4}
            value={state.text}
            onChange={(event) => updateField("text", event.target.value)}
            aria-invalid={fieldErrors.value ? "true" : undefined}
            aria-describedby={fieldErrors.value ? "manual-entry-value-error" : undefined}
            className={FIELD_CLASS}
          />
        </div>

        <div>
          <label htmlFor="manual-entry-source" className="text-cdt-sm font-cdt-bold text-cdt-slate-900">
            Fuente <span aria-hidden="true" className="text-cdt-error">*</span>
          </label>
          <input
            id="manual-entry-source"
            name="source"
            type="text"
            required
            aria-required="true"
            value={state.source}
            onChange={(event) => updateField("source", event.target.value)}
            aria-invalid={fieldErrors.source ? "true" : undefined}
            aria-describedby={fieldErrors.source ? "manual-entry-source-error" : undefined}
            className={FIELD_CLASS}
          />
          {fieldErrors.source ? <p id="manual-entry-source-error" role="alert" className="mt-cdt-1 text-cdt-xs text-cdt-error">{fieldErrors.source}</p> : null}
        </div>

        <div>
          <label htmlFor="manual-entry-url" className="text-cdt-sm font-cdt-bold text-cdt-slate-900">
            URL de la fuente <span className="font-cdt-normal text-cdt-slate-600">(opcional)</span>
          </label>
          <input
            id="manual-entry-url"
            name="url"
            type="url"
            inputMode="url"
            value={state.url}
            onChange={(event) => updateField("url", event.target.value)}
            aria-invalid={fieldErrors.url ? "true" : undefined}
            aria-describedby={fieldErrors.url ? "manual-entry-url-error" : undefined}
            className={FIELD_CLASS}
          />
          {fieldErrors.url ? <p id="manual-entry-url-error" role="alert" className="mt-cdt-1 text-cdt-xs text-cdt-error">{fieldErrors.url}</p> : null}
        </div>

        <div>
          <label htmlFor="manual-entry-date" className="text-cdt-sm font-cdt-bold text-cdt-slate-900">
            Fecha de la fuente <span className="font-cdt-normal text-cdt-slate-600">(opcional)</span>
          </label>
          <input
            id="manual-entry-date"
            name="date"
            type="date"
            value={state.date}
            onChange={(event) => updateField("date", event.target.value)}
            aria-invalid={fieldErrors.date ? "true" : undefined}
            aria-describedby={fieldErrors.date ? "manual-entry-date-error" : undefined}
            className={FIELD_CLASS}
          />
          {fieldErrors.date ? <p id="manual-entry-date-error" role="alert" className="mt-cdt-1 text-cdt-xs text-cdt-error">{fieldErrors.date}</p> : null}
        </div>

        {formError ? <p role="alert" className="rounded-cdt-md bg-cdt-blue-50 p-cdt-3 text-cdt-sm font-cdt-bold text-cdt-error">{formError}</p> : null}

        <div className="flex flex-wrap justify-end gap-cdt-3">
          <Button type="button" variant="quiet" onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary">Guardar aporte manual</Button>
        </div>
      </form>
    </Modal>
  );
}

export default ManualDataEntry;
