import { useState } from "react";
import { Table } from "../ui/Table";
import { Button } from "../ui/Button";
import { resolveEvidenceColumns } from "../../lib/evidence";

const VISIBLE_ROWS_DEFAULT = 10;

/**
 * Tabla accesible de filas de evidencia (`implementation-plan.md` §4.7,
 * §8.2). Encabezados resueltos por `resolveEvidenceColumns`; un alias no
 * resuelto muestra el alias crudo junto a "Nombre técnico de la consulta"
 * en vez de inventar una etiqueta. Máximo 10 filas visibles + "Ver
 * todas"/"Ver menos". Usa `row[column.key]` sin reformatear (delegado a
 * `Table`, que ya hace exactamente eso quand no se pasa `render`).
 */
export function EvidenceTable({ evidence, claims }) {
  const [expanded, setExpanded] = useState(false);
  const rows = Array.isArray(evidence?.rows) ? evidence.rows : [];
  if (rows.length === 0) return null;

  const { columns: resolvedColumns } = resolveEvidenceColumns(evidence, { claims });
  const tableColumns = resolvedColumns.map((column) => ({
    key: column.key,
    header: column.resolved ? (
      column.label
    ) : (
      <span className="flex flex-col">
        <span>{column.label}</span>
        <span className="text-cdt-xs font-cdt-normal normal-case text-cdt-slate-600">
          Nombre técnico de la consulta
        </span>
      </span>
    ),
  }));

  const canExpand = rows.length > VISIBLE_ROWS_DEFAULT;
  const visibleRows = expanded ? rows : rows.slice(0, VISIBLE_ROWS_DEFAULT);

  return (
    <div className="flex flex-col gap-cdt-2">
      <Table
        caption={`Filas de evidencia — ${evidence?.dataset_name ?? "dataset"} (${rows.length} en total)`}
        columns={tableColumns}
        rows={visibleRows}
        getRowKey={(_row, index) => index}
      />
      {canExpand ? (
        <Button variant="quiet" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Ver menos" : `Ver todas (${rows.length})`}
        </Button>
      ) : null}
    </div>
  );
}
