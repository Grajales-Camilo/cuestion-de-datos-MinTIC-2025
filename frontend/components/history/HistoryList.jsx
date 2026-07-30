import { useState } from "react";
import { Card, CardBody } from "../ui/Card";
import { Button } from "../ui/Button";
import { DeleteRunDialog } from "./DeleteRunDialog";

const IN_PROGRESS_STATUSES = new Set(["streaming", "running", "reconnecting", "disconnected"]);

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-CO", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

const DELETE_ERROR_MESSAGES = {
  no_credential: "Ya no se puede acceder a esta investigación desde este equipo.",
  unauthorized: "El acceso a esta investigación ya no es válido; no se pudo confirmar el borrado en el servidor.",
  error: "No se pudo borrar la investigación. Intenta de nuevo en unos minutos.",
};

/**
 * Historial de investigaciones de la sesión (RF-502). Nunca muestra
 * `runId` ni token en la superficie primaria — solo pregunta, estado en
 * español, fecha y resumen. El borrado exige confirmación explícita
 * (`DeleteRunDialog`) y nunca retira el registro antes de conocer el
 * resultado real del `DELETE`.
 */
export function HistoryList({ runs, onRerun, onRefine, onDelete, onResume, isDeletingRun }) {
  const [confirmRunId, setConfirmRunId] = useState(null);
  const [deleteErrors, setDeleteErrors] = useState({});

  if (!runs || runs.length === 0) {
    return <p className="text-cdt-sm text-cdt-slate-600">Todavía no has hecho ninguna investigación en esta sesión.</p>;
  }

  const confirmRecord = runs.find((r) => r.runId === confirmRunId) ?? null;

  async function handleConfirmDelete() {
    if (!confirmRecord) return;
    const runId = confirmRecord.runId;
    const result = await onDelete(runId);
    if (result?.ok) {
      setConfirmRunId(null);
      setDeleteErrors((prev) => {
        const next = { ...prev };
        delete next[runId];
        return next;
      });
      return;
    }
    setConfirmRunId(null);
    setDeleteErrors((prev) => ({ ...prev, [runId]: DELETE_ERROR_MESSAGES[result?.reason] ?? DELETE_ERROR_MESSAGES.error }));
  }

  return (
    <ul className="flex flex-col gap-cdt-3" aria-label="Historial de investigaciones">
      {runs.map((run) => {
        const canResume = IN_PROGRESS_STATUSES.has(run.status) && !run.credentialExpired;
        const canDelete = !run.credentialExpired;
        const pending = isDeletingRun?.(run.runId) ?? false;

        return (
          <li key={run.runId}>
            <Card as="div">
              <CardBody className="flex flex-col gap-cdt-2">
                <p className="text-cdt-sm font-cdt-bold text-cdt-slate-900">{run.question}</p>
                <div className="flex flex-wrap items-center gap-cdt-2 text-cdt-xs text-cdt-slate-600">
                  <span>{run.summary}</span>
                  <span aria-hidden="true">·</span>
                  <span>{formatDate(run.updatedAt)}</span>
                </div>
                {run.credentialExpired ? (
                  <p className="text-cdt-xs text-cdt-warning">Ya no se puede acceder a esta investigación desde este equipo.</p>
                ) : null}
                {deleteErrors[run.runId] ? (
                  <p role="alert" className="text-cdt-xs text-cdt-error">
                    {deleteErrors[run.runId]}
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-cdt-2">
                  <Button variant="secondary" onClick={() => onRerun(run.runId)}>
                    Reejecutar
                  </Button>
                  <Button variant="secondary" onClick={() => onRefine(run.runId)}>
                    Refinar
                  </Button>
                  {canResume ? (
                    <Button variant="secondary" onClick={() => onResume(run.runId)}>
                      Reanudar
                    </Button>
                  ) : null}
                  {canDelete ? (
                    <Button variant="destructive" onClick={() => setConfirmRunId(run.runId)} disabled={pending}>
                      Borrar esta investigación
                    </Button>
                  ) : null}
                </div>
              </CardBody>
            </Card>
          </li>
        );
      })}

      <DeleteRunDialog
        open={confirmRecord !== null}
        question={confirmRecord?.question}
        pending={confirmRecord ? (isDeletingRun?.(confirmRecord.runId) ?? false) : false}
        onConfirm={handleConfirmDelete}
        onCancel={() => setConfirmRunId(null)}
      />
    </ul>
  );
}
