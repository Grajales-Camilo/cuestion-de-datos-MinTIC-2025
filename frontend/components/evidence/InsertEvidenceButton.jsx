import { useRef, useState } from "react";
import { AlertTriangle, FileInput } from "lucide-react";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";

function userWarnings(evidence) {
  const warnings = evidence?.quality?.warnings_user;
  if (!Array.isArray(warnings)) return [];
  return warnings.filter((warning) => typeof warning === "string" && warning.trim() !== "");
}

/**
 * Única acción visual de inserción desde `EvidenceCard`. Para RF-404, una
 * evidencia `no_recomendada` abre confirmación y no llama al callback antes
 * del segundo clic explícito.
 */
export function InsertEvidenceButton({ evidence, claims, onInsertEvidence }) {
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [inserting, setInserting] = useState(false);
  const cancelButtonRef = useRef(null);

  if (typeof onInsertEvidence !== "function") return null;

  const requiresWarning = evidence?.quality?.classification === "no_recomendada";
  const warnings = userWarnings(evidence);

  async function insert() {
    setInserting(true);
    try {
      await onInsertEvidence({ evidence, claims });
    } finally {
      setInserting(false);
      setConfirmationOpen(false);
    }
  }

  function handlePrimaryAction() {
    if (requiresWarning) {
      setConfirmationOpen(true);
      return;
    }
    void insert();
  }

  return (
    <>
      <Button variant="primary" onClick={handlePrimaryAction} loading={inserting}>
        <FileInput className="h-4 w-4" aria-hidden="true" focusable="false" />
        Insertar en el documento
      </Button>

      <Modal
        open={confirmationOpen}
        onClose={() => setConfirmationOpen(false)}
        title="Insertar evidencia no recomendada"
        initialFocusRef={cancelButtonRef}
      >
        <div className="flex flex-col gap-cdt-4">
          <p className="flex items-start gap-cdt-3 text-cdt-sm text-cdt-slate-900">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-cdt-warning" aria-hidden="true" focusable="false" />
            Esta evidencia puede usarse, pero requiere cautela. La advertencia quedará visible dentro del documento.
          </p>
          {warnings.length > 0 ? (
            <ul className="list-disc space-y-cdt-2 pl-cdt-6 text-cdt-sm text-cdt-slate-600">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <div className="flex flex-col-reverse gap-cdt-2 sm:flex-row sm:justify-end">
            <Button
              ref={cancelButtonRef}
              variant="secondary"
              onClick={() => setConfirmationOpen(false)}
              disabled={inserting}
            >
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => void insert()} loading={inserting}>
              Insertar con advertencia
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
