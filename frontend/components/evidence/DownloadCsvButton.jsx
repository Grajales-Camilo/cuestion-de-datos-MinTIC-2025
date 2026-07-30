import { useCallback } from "react";
import { Button } from "../ui/Button";
import { resolveEvidenceColumns, toEvidenceCsv } from "../../lib/evidence";

/** Nombre de archivo seguro y determinista: solo [a-zA-Z0-9_-], colapsando
 * separadores repetidos — nunca vacío (cae a "evidencia"). */
function sanitizeFilenamePart(value) {
  const text = typeof value === "string" && value.trim() !== "" ? value.trim() : "";
  const cleaned = text.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
  return cleaned || "evidencia";
}

/**
 * Descarga la evidencia como CSV (RF-501): mismas columnas/filas que
 * `EvidenceTable` + bloque de cita (`toEvidenceCsv` ya lo compone con BOM
 * UTF-8). El object URL creado para la descarga se revoca inmediatamente
 * después del click.
 */
export function DownloadCsvButton({ evidence, claims }) {
  const handleClick = useCallback(() => {
    if (!evidence) return;
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const filename = `evidencia-${sanitizeFilenamePart(evidence.dataset_id ?? evidence.evidence_id)}.csv`;

    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [evidence, claims]);

  if (!evidence) return null;

  return (
    <Button variant="secondary" onClick={handleClick}>
      Descargar CSV
    </Button>
  );
}
