/**
 * Texto de corte estadístico compartido por `quality.js` (vista de
 * calidad) y `toCsv.js` (bloque de cita) — una sola fuente de verdad para
 * no divergir entre ambos consumidores.
 *
 * Aclaración normativa de este incremento (F4-01, jerarquía documental):
 * `implementation-plan.md` (no normativo) dice que no debe aparecer la
 * palabra "corte"; el contrato superior (`contracts/api-rest.md` §5 y
 * `contracts/validacion-calidad.md` §4) exige explicar que la fecha es la
 * de actualización del portal y que el corte estadístico es desconocido.
 * Se aplica la fuente de mayor jerarquía: el mensaje SÍ puede nombrar
 * "corte" siempre que dis­tinga con claridad que es DESCONOCIDO cuando
 * `data_cutoff_basis === "data_updated_at_fallback"` — nunca presenta la
 * fecha de actualización del portal como si fuera el corte real.
 */

const SPANISH_MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** Formatea una fecha ISO como "17 de octubre de 2024" en UTC — nunca
 * depende de `Intl`/la zona horaria del entorno, para que el resultado
 * sea el mismo en cualquier máquina (determinismo, `pruebas.md`). Nunca
 * lanza: una fecha inválida o ausente devuelve `null`. */
export function formatSpanishDate(isoString) {
  if (typeof isoString !== "string" || isoString.trim() === "") return null;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getUTCDate()} de ${SPANISH_MONTHS[date.getUTCMonth()]} de ${date.getUTCFullYear()}`;
}

/**
 * Lee los metadatos de corte tolerando las dos ubicaciones observadas:
 * `evidence.quality.data_cutoff.*` (forma del contrato,
 * `validacion-calidad.md` §4) o los campos planos `evidence.data_cutoff_*`
 * (forma real observada en los fixtures capturados — divergencia H1,
 * `implementation-plan.md`). Nunca inventa un valor ausente en ninguna
 * de las dos formas.
 */
function readCutoffMeta(evidence) {
  const nested = evidence?.quality?.data_cutoff;
  const updatedAt = evidence?.data_updated_at ?? evidence?.citation?.data_updated_at ?? null;
  if (nested && typeof nested === "object") {
    return {
      basis: typeof nested.basis === "string" ? nested.basis : null,
      cutoffAt: typeof nested.data_cutoff_at === "string" ? nested.data_cutoff_at : null,
      updatedAt,
    };
  }
  return {
    basis: typeof evidence?.data_cutoff_basis === "string" ? evidence.data_cutoff_basis : null,
    cutoffAt: typeof evidence?.data_cutoff_at === "string" ? evidence.data_cutoff_at : null,
    updatedAt,
  };
}

/**
 * Devuelve el texto de corte a mostrar. Regla dura (§5 del contrato):
 * si `basis === "data_updated_at_fallback"`, nunca se llama "corte" a la
 * fecha de actualización del portal — se nombra explícitamente como
 * actualización y el corte se declara desconocido.
 */
export function describeCutoff(evidence) {
  const { basis, cutoffAt, updatedAt } = readCutoffMeta(evidence);

  if (basis === "data_updated_at_fallback") {
    const formattedUpdate = formatSpanishDate(updatedAt);
    return formattedUpdate
      ? `Fecha de actualización del portal: ${formattedUpdate}. Corte estadístico desconocido.`
      : "Corte estadístico desconocido.";
  }

  const formattedCutoff = formatSpanishDate(cutoffAt);
  if (formattedCutoff) {
    return `Corte estadístico: ${formattedCutoff}.`;
  }

  return "Corte estadístico desconocido.";
}
