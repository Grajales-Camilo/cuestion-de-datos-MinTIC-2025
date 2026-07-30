import { describe, expect, it } from "vitest";
import { buildEvidenceChartSpec } from "../../../lib/evidence/chartSpec.js";
import { resolveEvidenceColumns } from "../../../lib/evidence/resolveColumns.js";
import fixture from "../../fixtures/completed-with-claims.json";

/**
 * Dobles sintéticos de este archivo (F4-03): estructuras mínimas construidas
 * a mano para ejercitar ramas de `chartSpec.js` que NO existen todavía en
 * ningún fixture real capturado (1 dimensión + 1 métrica + ≥3 filas,
 * `chart_suggestion` poblado — siempre `null` en el runtime real por la
 * divergencia D-4). Se documentan explícitamente aquí, nunca se guardan en
 * `tests/fixtures/`, y no se presentan en ningún lugar como evidencia real.
 */
function syntheticEligibleEvidence(overrides = {}) {
  return {
    evidence_id: "synthetic-chart-evidence",
    dataset_name: "Dataset sintético",
    columns: [],
    rows: [],
    soql_query: "",
    quality: { eligibility_status: "eligible" },
    ...overrides,
  };
}

function resolvedColumnsFor(evidence, claims = []) {
  return resolveEvidenceColumns(evidence, { claims }).columns;
}

const ONE_DIM_ONE_METRIC = syntheticEligibleEvidence({
  columns: ["dim_1", "metric_sum_1"],
  soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1 GROUP BY municipio",
  rows: [
    { dim_1: "Sonsón", metric_sum_1: 12.5 },
    { dim_1: "Rionegro", metric_sum_1: "30" },
    { dim_1: "Marinilla", metric_sum_1: 7 },
  ],
});

describe("buildEvidenceChartSpec — fixture real (completed-with-claims.json)", () => {
  it("regla 1/4: 8 dimensiones resueltas y 0 métricas → null, nunca inventa una gráfica", () => {
    const [evidence] = fixture.answer.evidence;
    const resolvedColumns = resolvedColumnsFor(evidence, fixture.answer.claims);
    // Confirma la premisa: el fixture real tiene 8 dimensiones, no 1.
    expect(resolvedColumns.filter((c) => c.resolved && c.kind === "dimension")).toHaveLength(8);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });
});

describe("buildEvidenceChartSpec — fallback D-4 (doble sintético: 1 dimensión + 1 métrica + ≥3 filas)", () => {
  it("produce una gráfica válida, tipo bar, con labels/values en el orden original de las filas", () => {
    const resolvedColumns = resolvedColumnsFor(ONE_DIM_ONE_METRIC);
    const spec = buildEvidenceChartSpec({ evidence: ONE_DIM_ONE_METRIC, resolvedColumns });
    expect(spec).toEqual({
      type: "bar",
      datasetName: "Dataset sintético",
      xLabel: "Municipio",
      yLabel: "Suma de Valor",
      labels: ["Sonsón", "Rionegro", "Marinilla"],
      values: [12.5, 30, 7],
      source: "fallback",
    });
  });

  it("regla 6.b (no reformatea): '30' (cadena numérica canónica) se convierte a Number(30), no se recalcula ni redondea", () => {
    const resolvedColumns = resolvedColumnsFor(ONE_DIM_ONE_METRIC);
    const spec = buildEvidenceChartSpec({ evidence: ONE_DIM_ONE_METRIC, resolvedColumns });
    expect(spec.values[1]).toBe(30);
    expect(typeof spec.values[1]).toBe("number");
  });

  it("regla 7: no ordena — un orden de filas deliberadamente no alfabético se conserva tal cual", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1",
      rows: [
        { dim_1: "Zeta", metric_sum_1: 3 },
        { dim_1: "Alfa", metric_sum_1: 1 },
        { dim_1: "Medio", metric_sum_1: 2 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec.labels).toEqual(["Zeta", "Alfa", "Medio"]);
    expect(spec.values).toEqual([3, 1, 2]);
  });

  it("2 dimensiones resueltas → null (no adivina cuál es 'la' dimensión)", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "dim_2", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, departamento AS dim_2, sum(valor) AS metric_sum_1",
      rows: [
        { dim_1: "a", dim_2: "x", metric_sum_1: 1 },
        { dim_1: "b", dim_2: "y", metric_sum_1: 2 },
        { dim_1: "c", dim_2: "z", metric_sum_1: 3 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it("2 métricas resueltas → null (no adivina cuál es 'la' métrica)", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1", "metric_avg_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1, avg(edad) AS metric_avg_1",
      rows: [
        { dim_1: "a", metric_sum_1: 1, metric_avg_1: 10 },
        { dim_1: "b", metric_sum_1: 2, metric_avg_1: 20 },
        { dim_1: "c", metric_sum_1: 3, metric_avg_1: 30 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it("menos de 3 filas → null", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1",
      rows: [
        { dim_1: "a", metric_sum_1: 1 },
        { dim_1: "b", metric_sum_1: 2 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it("columna unresolved/unknown en el candidato a métrica → null (nunca participa en la gráfica)", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "dim_2"],
      // dim_2 es una expresión no reconocida por el tokenizador: queda
      // `kind:"unknown"`, `resolved:false` — nunca puede ser la métrica.
      soql_query: "SELECT municipio AS dim_1, case when a > 1 then a else b end AS dim_2",
      rows: [
        { dim_1: "a", dim_2: 1 },
        { dim_1: "b", dim_2: 2 },
        { dim_1: "c", dim_2: 3 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(resolvedColumns.find((c) => c.key === "dim_2").resolved).toBe(false);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it.each([
    ["null", null],
    ["texto no numérico", "no-es-un-numero"],
    ["cadena ambigua con separador de miles", "1,234"],
    ["NaN", NaN],
    ["Infinity", Infinity],
    ["-Infinity", -Infinity],
    ["undefined", undefined],
    ["objeto", {}],
  ])("valor de métrica %s en CUALQUIER fila invalida la especificación COMPLETA (nunca parcial)", (_label, badValue) => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1",
      rows: [
        { dim_1: "a", metric_sum_1: 1 },
        { dim_1: "b", metric_sum_1: badValue },
        { dim_1: "c", metric_sum_1: 3 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });
});

describe("buildEvidenceChartSpec — chart_suggestion (contrato api-rest.md §5; F4-03-R1: reglas propias, distintas del fallback D-4)", () => {
  it("sugerencia válida y utilizable se respeta tal cual, incluido el tipo declarado, aunque y NO clasifique como metric/count", () => {
    // `metric_sum_1` NO se usa aquí: `dim_2` es otra dimensión (bare
    // identifier), demostrando que la sugerencia es la autoridad
    // semántica sobre los ejes — no depende de `kind`.
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "dim_2"],
      soql_query: "SELECT municipio AS dim_1, valor AS dim_2",
      chart_suggestion: { type: "line", x: "dim_1", y: "dim_2" },
      rows: [
        { dim_1: "a", dim_2: 1 },
        { dim_1: "b", dim_2: 2 },
      ], // solo 2 filas: probaría fallback D-4 (exige ≥3), pero la sugerencia no lo requiere
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(resolvedColumns.find((c) => c.key === "dim_2").kind).toBe("dimension"); // confirma la premisa
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).toMatchObject({ type: "line", source: "chart_suggestion", labels: ["a", "b"], values: [1, 2] });
  });

  it("REQUISITO 1 — ejemplo EXACTO normativo de contracts/api-rest.md §5: nunca null (defecto reproducido y corregido)", () => {
    // Forma literal del ejemplo del contrato: `columns` como
    // `[{field,type}]`, SoQL `SELECT a_o, desercion_transicion WHERE ...`
    // (ambas columnas bare-identifier → ambas clasifican HOY como
    // "dimension"), `chart_suggestion: {type:"line", x:"a_o",
    // y:"desercion_transicion"}`.
    const evidence = {
      evidence_id: "9a2b...",
      dataset_id: "nudc-7mev",
      dataset_name: "MEN_ESTADISTICAS_EN_EDUCACION_EN_PREESCOLAR",
      publisher: "Ministerio de Educación Nacional",
      soql_query: "SELECT a_o, desercion_transicion WHERE codigo_municipio='05756' ORDER BY a_o DESC LIMIT 10",
      columns: [
        { field: "a_o", type: "number" },
        { field: "desercion_transicion", type: "number" },
      ],
      rows: [{ a_o: "2025", desercion_transicion: "3.2" }],
      chart_suggestion: { type: "line", x: "a_o", y: "desercion_transicion" },
      quality: { eligibility_status: "eligible" },
    };
    const resolvedColumns = resolvedColumnsFor(evidence);
    // Confirma la premisa del defecto: ambas columnas son "dimension".
    expect(resolvedColumns.find((c) => c.key === "a_o").kind).toBe("dimension");
    expect(resolvedColumns.find((c) => c.key === "desercion_transicion").kind).toBe("dimension");

    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).not.toBeNull();
    expect(spec).toMatchObject({
      type: "line",
      source: "chart_suggestion",
      labels: ["2025"],
      values: [3.2],
    });
  });

  it("REQUISITO 2 — campo aditivo desconocido (p. ej. 'title') se ignora: la sugerencia sigue funcionando y el campo NO aparece en el ChartSpec", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1",
      chart_suggestion: { type: "bar", x: "dim_1", y: "metric_sum_1", title: "Ignorar este campo" },
      rows: [
        { dim_1: "a", metric_sum_1: 1 },
        { dim_1: "b", metric_sum_1: 2 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).not.toBeNull();
    expect(spec).not.toHaveProperty("title");
    expect(JSON.stringify(spec)).not.toContain("Ignorar este campo");
  });

  it("REQUISITO 3 — sugerencia por fieldName ('nueca') mientras las filas usan alias ('dim_4') como clave: resuelve y lee vía key", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "dim_4"],
      soql_query: "SELECT municipio AS dim_1, nueca AS dim_4",
      // La sugerencia cita el NOMBRE REAL de columna, no el alias.
      chart_suggestion: { type: "bar", x: "municipio", y: "nueca" },
      rows: [
        { dim_1: "a", dim_4: 10 },
        { dim_1: "b", dim_4: 20 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).toMatchObject({ source: "chart_suggestion", labels: ["a", "b"], values: [10, 20] });
  });
});

describe("buildEvidenceChartSpec — F4-03-R2: desambiguación fail-closed de referencias por fieldName", () => {
  // sum(valor) Y avg(valor) resuelven el MISMO fieldName:"valor" — el
  // defecto reproducido: `y:"valor"` no puede elegir arbitrariamente
  // "la primera" entre metric_sum_1/metric_avg_1.
  const TWO_METRICS_SAME_FIELDNAME = syntheticEligibleEvidence({
    columns: ["dim_1", "metric_sum_1", "metric_avg_1"],
    soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1, avg(valor) AS metric_avg_1",
    rows: [
      { dim_1: "a", metric_sum_1: 10, metric_avg_1: 5 },
      { dim_1: "b", metric_sum_1: 20, metric_avg_1: 10 },
    ],
  });

  it("REQUISITO 1 — reproducción exacta: y:'valor' (fieldName ambiguo entre 2 métricas) → null, nunca adivina", () => {
    const evidence = { ...TWO_METRICS_SAME_FIELDNAME, chart_suggestion: { type: "bar", x: "municipio", y: "valor" } };
    const resolvedColumns = resolvedColumnsFor(evidence);
    // Confirma la premisa del defecto: ambas métricas comparten fieldName.
    expect(resolvedColumns.find((c) => c.key === "metric_sum_1").fieldName).toBe("valor");
    expect(resolvedColumns.find((c) => c.key === "metric_avg_1").fieldName).toBe("valor");
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it("REQUISITO 2 — y:'metric_sum_1' (key exacto) selecciona la suma, no la ambigüedad de fieldName", () => {
    const evidence = { ...TWO_METRICS_SAME_FIELDNAME, chart_suggestion: { type: "bar", x: "dim_1", y: "metric_sum_1" } };
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).toMatchObject({ source: "chart_suggestion", values: [10, 20] });
  });

  it("REQUISITO 3 — y:'metric_avg_1' (key exacto) selecciona el promedio, no la ambigüedad de fieldName", () => {
    const evidence = { ...TWO_METRICS_SAME_FIELDNAME, chart_suggestion: { type: "bar", x: "dim_1", y: "metric_avg_1" } };
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).toMatchObject({ source: "chart_suggestion", values: [5, 10] });
  });

  it("REQUISITO 4 — una única columna con fieldName:'valor' (sin ambigüedad) sigue resolviendo por fieldName", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1",
      chart_suggestion: { type: "bar", x: "municipio", y: "valor" },
      rows: [
        { dim_1: "a", metric_sum_1: 10 },
        { dim_1: "b", metric_sum_1: 20 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).toMatchObject({ source: "chart_suggestion", values: [10, 20] });
  });
});

describe("buildEvidenceChartSpec — chart_suggestion: sugerencias inválidas y su fallback a D-4", () => {
  it.each([
    ["tipo no soportado", { type: "pie", x: "dim_1", y: "metric_sum_1" }],
    ["falta 'type'", { x: "dim_1", y: "metric_sum_1" }],
    ["falta 'x'", { type: "bar", y: "metric_sum_1" }],
    ["falta 'y'", { type: "bar", x: "dim_1" }],
    ["x === y (misma cadena)", { type: "bar", x: "dim_1", y: "dim_1" }],
    ["x no apunta a columna resuelta", { type: "bar", x: "dim_no_declarado", y: "metric_sum_1" }],
    ["y no apunta a columna resuelta", { type: "bar", x: "dim_1", y: "metric_no_declarado" }],
  ])("sugerencia inválida (%s) NUNCA se usa tal cual; solo cae al fallback si este cumple D-4", (_label, badSuggestion) => {
    // Filas insuficientes para el fallback (2 < 3): con la sugerencia
    // inválida descartada, el resultado debe ser null, no una gráfica
    // fabricada a partir de una sugerencia rota.
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT municipio AS dim_1, sum(valor) AS metric_sum_1",
      chart_suggestion: badSuggestion,
      rows: [
        { dim_1: "a", metric_sum_1: 1 },
        { dim_1: "b", metric_sum_1: 2 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it("REQUISITO 4 — x e y que terminan resolviendo a la MISMA columna (por key vs. fieldName) → null, aunque las cadenas difieran", () => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "dim_4"],
      soql_query: "SELECT municipio AS dim_1, nueca AS dim_4",
      // "dim_4" (key) y "nueca" (fieldName de esa MISMA columna) son
      // cadenas distintas mencionadas en x/y, pero apuntan a un único eje.
      chart_suggestion: { type: "bar", x: "dim_4", y: "nueca" },
      rows: [
        { dim_1: "a", dim_4: 10 },
        { dim_1: "b", dim_4: 20 },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it.each([
    ["null", null],
    ["texto no numérico", "no-es-un-numero"],
    ["NaN", NaN],
    ["Infinity", Infinity],
  ])("REQUISITO 5 — y=%s en CUALQUIER fila invalida la sugerencia, aunque y no sea kind metric/count", (_label, badValue) => {
    const evidence = syntheticEligibleEvidence({
      columns: ["dim_1", "dim_2"],
      soql_query: "SELECT municipio AS dim_1, valor AS dim_2",
      chart_suggestion: { type: "bar", x: "dim_1", y: "dim_2" },
      rows: [
        { dim_1: "a", dim_2: 1 },
        { dim_1: "b", dim_2: badValue },
      ],
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });

  it("sugerencia inválida SÍ cae al fallback cuando este cumple D-4 (1 dim + 1 métrica + ≥3 filas)", () => {
    const evidence = syntheticEligibleEvidence({
      ...ONE_DIM_ONE_METRIC,
      chart_suggestion: { type: "pie", x: "dim_1", y: "metric_sum_1" }, // "pie" no soportado
    });
    const resolvedColumns = resolvedColumnsFor(evidence);
    const spec = buildEvidenceChartSpec({ evidence, resolvedColumns });
    expect(spec).toMatchObject({ type: "bar", source: "fallback" });
  });
});

describe("buildEvidenceChartSpec — REQUISITO 6: el fallback D-4 permanece sin cambios (regresión F4-03-R1)", () => {
  it("sigue exigiendo exactamente 1 dimensión + 1 métrica/count + ≥3 filas, sin agregación/orden/cálculo", () => {
    const resolvedColumns = resolvedColumnsFor(ONE_DIM_ONE_METRIC);
    const spec = buildEvidenceChartSpec({ evidence: ONE_DIM_ONE_METRIC, resolvedColumns });
    expect(spec).toEqual({
      type: "bar",
      datasetName: "Dataset sintético",
      xLabel: "Municipio",
      yLabel: "Suma de Valor",
      labels: ["Sonsón", "Rionegro", "Marinilla"],
      values: [12.5, 30, 7],
      source: "fallback",
    });
  });
});

describe("buildEvidenceChartSpec — elegibilidad fail-closed (F4-02-R1, aplica también a la gráfica)", () => {
  it.each([
    ["blocked", "blocked"],
    ["diagnostic_only", "diagnostic_only"],
    ["ausente", undefined],
    ["desconocido", "algo-no-reconocido"],
  ])("%s: nunca produce una especificación, aunque los datos por lo demás calificarían", (_label, eligibilityStatus) => {
    const evidence = {
      ...ONE_DIM_ONE_METRIC,
      quality: eligibilityStatus === undefined ? {} : { eligibility_status: eligibilityStatus },
    };
    const resolvedColumns = resolvedColumnsFor(evidence);
    expect(buildEvidenceChartSpec({ evidence, resolvedColumns })).toBeNull();
  });
});
