import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { buildCitationText } from "../../lib/evidence/citationText.js";

const STATUS_MESSAGES = {
  success: "Cita copiada.",
  error: "No se pudo copiar la cita.",
};

/**
 * Copia la cita completa como texto plano (nunca HTML) vía
 * `navigator.clipboard.writeText`. El resultado se informa en español a
 * través de un estado accesible (`role="status"`, `aria-live="polite"`).
 */
export function CopyCitationButton({ evidence }) {
  const [status, setStatus] = useState(null); // null | "success" | "error"
  const timeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const handleClick = useCallback(async () => {
    if (!evidence) return;
    const text = buildCitationText(evidence);
    try {
      await navigator.clipboard.writeText(text);
      setStatus("success");
    } catch {
      setStatus("error");
    }
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setStatus(null), 4000);
  }, [evidence]);

  if (!evidence) return null;

  return (
    <div className="flex items-center gap-cdt-2">
      <Button variant="secondary" onClick={handleClick}>
        Copiar cita
      </Button>
      <span role="status" aria-live="polite" className="text-cdt-xs text-cdt-slate-600">
        {status ? STATUS_MESSAGES[status] : ""}
      </span>
    </div>
  );
}
