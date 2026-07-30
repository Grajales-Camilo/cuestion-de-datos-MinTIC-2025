import { Disclosure } from "../ui/Disclosure";
import { describeCutoff, formatSpanishDate, getSafeExternalUrl } from "../../lib/evidence";

/**
 * Bloque de cita: dataset, publicador, fecha de ejecución, URL (enlace
 * externo seguro), fecha de actualización y descripción honesta del corte
 * (`describeCutoff`, ya distingue "corte desconocido" de "fecha de
 * actualización del portal"). La consulta SoQL vive en un `<Disclosure>`
 * técnico, no en la superficie primaria.
 *
 * F4-02-R1: la URL solo se convierte en `<a>` si `getSafeExternalUrl` la
 * acepta (absoluta, `https:` — nunca `javascript:`/`data:`/`file:`/
 * `vbscript:`/relativa). Si no es segura o está ausente, se muestra "URL
 * no disponible" como texto plano, sin elemento navegable.
 */
export function CitationBlock({ evidence }) {
  if (!evidence || typeof evidence !== "object") return null;

  const dataset = evidence.dataset_name ?? "No disponible";
  const publisher = evidence.publisher ?? "No disponible";
  const executedAt = formatSpanishDate(evidence.executed_at) ?? evidence.executed_at ?? "No disponible";
  const updatedAt = formatSpanishDate(evidence.data_updated_at) ?? evidence.data_updated_at ?? "No disponible";
  const safeUrl = getSafeExternalUrl(evidence.source_url);

  return (
    <div className="flex flex-col gap-cdt-1 text-cdt-sm text-cdt-slate-900">
      <p>
        <span className="font-cdt-bold">Dataset: </span>
        {dataset}
      </p>
      <p>
        <span className="font-cdt-bold">Publicador: </span>
        {publisher}
      </p>
      <p>
        <span className="font-cdt-bold">Fecha de ejecución: </span>
        {executedAt}
      </p>
      <p>
        <span className="font-cdt-bold">URL: </span>
        {safeUrl ? (
          <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="break-all text-cdt-blue-700 underline">
            {safeUrl}
          </a>
        ) : (
          "URL no disponible"
        )}
      </p>
      <p>
        <span className="font-cdt-bold">Fecha de actualización: </span>
        {updatedAt}
      </p>
      <p>{describeCutoff(evidence)}</p>
      <Disclosure summary="Ver consulta SoQL">
        <pre className="mt-cdt-2 overflow-x-auto rounded-cdt-md bg-cdt-blue-50 p-cdt-2 text-cdt-xs text-cdt-slate-900">
          {evidence.soql_query ?? "No disponible"}
        </pre>
      </Disclosure>
    </div>
  );
}
