import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";
import { resolveEvidenceColumns, buildEvidenceChartSpec } from "../../lib/evidence";

// Registro mínimo: solo los elementos que los dos tipos soportados por
// `chartSpec.js` (`bar`/`line`) necesitan — nunca `chart.js/auto`, que
// registraría el catálogo completo sin usarlo.
ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip);

const CHART_COMPONENT_BY_TYPE = { bar: Bar, line: Line };

/**
 * Gráfica determinista de evidencia (RF-503,
 * `implementation-plan.md` §8.2 punto 6). Renderiza SOLO cuando
 * `buildEvidenceChartSpec` produce una especificación válida — replica
 * exactamente los valores de `EvidenceTable`, nunca calcula nada. La tabla
 * (ya renderizada antes que esta gráfica en `EvidenceCard`) sigue siendo
 * la alternativa textual autoritativa (`pruebas.md` §5); esta gráfica es
 * un complemento visual, no un reemplazo. Sin especificación válida,
 * devuelve `null`: nunca un contenedor vacío ni un encabezado huérfano.
 */
export function EvidenceChart({ evidence, claims }) {
  const { columns: resolvedColumns } = resolveEvidenceColumns(evidence, { claims });
  const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
  if (!spec) return null;

  const ChartComponent = CHART_COMPONENT_BY_TYPE[spec.type];
  if (!ChartComponent) return null; // fail-safe: chartSpec.js nunca produce otro tipo en la práctica

  const accessibleName = spec.datasetName
    ? `Gráfica de ${spec.yLabel} por ${spec.xLabel} — ${spec.datasetName}`
    : `Gráfica de ${spec.yLabel} por ${spec.xLabel}`;

  const data = {
    labels: spec.labels,
    datasets: [
      {
        label: spec.yLabel,
        data: spec.values,
        backgroundColor: "#1d4e89",
        borderColor: "#1d4e89",
      },
    ],
  };

  // Animación desactivada por completo (no solo bajo `prefers-reduced-motion`):
  // no hay ninguna animación ornamental que mostrar u ocultar. Leyenda
  // desactivada: una sola serie no necesita distinguirse de otras: el eje X
  // (categoría) y el eje Y (valor, con su propio título) ya identifican el
  // dato sin depender del color.
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: false },
    },
    scales: {
      x: { title: { display: true, text: spec.xLabel } },
      y: { title: { display: true, text: spec.yLabel } },
    },
  };

  return (
    <div className="h-64 w-full max-w-full overflow-hidden rounded-cdt-md border border-cdt-blue-100 p-cdt-2">
      <ChartComponent role="img" aria-label={accessibleName} data={data} options={options} redraw={false} />
    </div>
  );
}
