import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";

/** Texto de confirmación exigido antes de cualquier DELETE (RF-803): explícito,
 * irreversible, nunca implícito por cierre del drawer o desmontaje. */
export const DELETE_RUN_WARNING =
  "Esta acción borrará de forma completa e irreversible la investigación, sus pasos y sus evidencias. No se puede deshacer.";

export function DeleteRunDialog({ open, question, pending, onConfirm, onCancel }) {
  return (
    <Modal open={open} onClose={onCancel} title="Borrar esta investigación">
      <div className="flex flex-col gap-cdt-4 text-cdt-sm text-cdt-slate-900">
        <p>{DELETE_RUN_WARNING}</p>
        {question ? (
          <p className="rounded-cdt-md border border-cdt-blue-100 bg-cdt-blue-50 p-cdt-2 text-cdt-sm">{question}</p>
        ) : null}
        <div className="flex justify-end gap-cdt-2">
          <Button variant="secondary" onClick={onCancel} disabled={pending}>
            Cancelar
          </Button>
          <Button variant="destructive" onClick={onConfirm} loading={pending}>
            Borrar de forma irreversible
          </Button>
        </div>
      </div>
    </Modal>
  );
}
