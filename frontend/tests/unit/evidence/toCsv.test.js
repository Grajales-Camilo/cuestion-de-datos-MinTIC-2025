import { describe, expect, it } from "vitest";
import { toEvidenceCsv } from "../../../lib/evidence/toCsv.js";
import { resolveEvidenceColumns } from "../../../lib/evidence/resolveColumns.js";
import fixture from "../../fixtures/completed-with-claims.json";

const BOM = "﻿";

/** Doble sintético: evidencia mínima construida a mano para ejercitar
 * escapado/neutralización que no aparece en el fixture real disponible.
 * No se guarda en `tests/fixtures/` ni se presenta como evidencia real. */
function syntheticEvidence(overrides = {}) {
  return {
    dataset_name: "Dataset de prueba",
    publisher: "Publicador de prueba",
    soql_query: "SELECT a AS dim_1",
    executed_at: "2026-01-01T00:00:00Z",
    source_url: "https://www.datos.gov.co/d/xxxx",
    data_updated_at: "2026-01-01T00:00:00Z",
    data_cutoff_basis: "data_cutoff_at",
    data_cutoff_at: "2026-01-01T00:00:00Z",
    rows: [],
    ...overrides,
  };
}

describe("toEvidenceCsv — fixture real (completed-with-claims.json)", () => {
  it("BOM UTF-8, encabezados visibles resueltos y filas con los valores originales sin redondear", () => {
    const [evidence] = fixture.answer.evidence;
    const { columns } = resolveEvidenceColumns(evidence, { claims: fixture.answer.claims });
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });

    expect(csv.startsWith(BOM)).toBe(true);
    const body = csv.slice(BOM.length);
    const lines = body.split("\r\n");

    expect(lines[0]).toBe(columns.map((c) => c.label).join(","));
    // dim_4 (nueca) conserva el valor crudo de la fila, no el
    // display_value formateado del claim ("2.368.705.607").
    const nuecaIndex = columns.findIndex((c) => c.fieldName === "nueca");
    const firstDataRow = lines[1].split(",");
    expect(firstDataRow[nuecaIndex]).toBe("2368705607");
    expect(body).not.toContain("2.368.705.607");
  });

  it("el bloque de cita incluye dataset, publicador, SoQL, ejecución, URL, actualización y corte", () => {
    const [evidence] = fixture.answer.evidence;
    const { columns } = resolveEvidenceColumns(evidence, { claims: fixture.answer.claims });
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });

    expect(csv).toContain(evidence.dataset_name);
    expect(csv).toContain(evidence.publisher);
    expect(csv).toContain(evidence.executed_at);
    expect(csv).toContain(evidence.source_url);
    // El fallback temporal no atribuye un corte falso a esa fecha.
    expect(csv).toContain("Corte estadístico desconocido.");
  });
});

describe("toEvidenceCsv — escapado CSV", () => {
  it("comas, comillas y saltos de línea se escapan correctamente", () => {
    const evidence = syntheticEvidence({
      rows: [{ dim_1: 'texto con "comillas", una coma\ny un salto de línea' }],
    });
    const columns = [{ key: "dim_1", label: "Campo" }];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    const body = csv.slice(BOM.length);

    expect(body).toContain('"texto con ""comillas"", una coma\ny un salto de línea"');
  });
});

/** Extrae el contenido real de una celda CSV (sin comillas envolventes ni
 * des-escapado de comillas dobles) a partir del carácter donde empieza,
 * para poder inspeccionar directamente cuál es su primer carácter tal
 * como quedó en el CSV final. */
function firstCharOfCell(csvLine, cellIndex) {
  const cell = csvLine.split(",")[cellIndex] ?? "";
  return cell.startsWith('"') ? cell[1] : cell[0];
}

const DANGEROUS_PREFIXES = [
  "=SUMA(A1)",
  "+1",
  "-1",
  "@usuario",
  "\tmalicioso",
  "\rmalicioso",
  "\nmalicioso",
  "＝malicioso",
  "＋malicioso",
  "－malicioso",
  "＠malicioso",
];

describe("toEvidenceCsv — F4-01-R1: neutralización completa de fórmulas (encabezados, filas y bloque de cita)", () => {
  it.each(DANGEROUS_PREFIXES)("un valor de FILA que empieza por %j se antepone con un apóstrofo; el prefijo deja de ser el primer carácter", (raw) => {
    const evidence = syntheticEvidence({ rows: [{ dim_1: raw }] });
    const columns = [{ key: "dim_1", label: "Campo" }];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    const dataLine = csv.split("\r\n")[1];

    expect(dataLine).toContain(`'${raw}`);
    expect(firstCharOfCell(dataLine, 0)).toBe("'");
  });

  it.each(DANGEROUS_PREFIXES)("un ENCABEZADO (label resuelto) que empieza por %j también se neutraliza", (raw) => {
    const evidence = syntheticEvidence({ rows: [] });
    const columns = [{ key: "dim_1", label: raw }];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    const headerLine = csv.slice(BOM.length).split("\r\n")[0];

    expect(firstCharOfCell(headerLine, 0)).toBe("'");
  });

  it("un valor PELIGROSO dentro del BLOQUE DE CITA (no en evidence.rows) también se neutraliza", () => {
    // dataset_name viaja directo al bloque de cita, no a las filas de
    // datos — si solo se protegieran las filas, esto seguiría siendo
    // explotable.
    const evidence = syntheticEvidence({ dataset_name: "=cmd|' /C calc'!A1", rows: [] });
    const columns = [{ key: "dim_1", label: "Campo" }];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    const citationLine = csv.split("\r\n").find((line) => line.includes("cmd"));

    expect(citationLine).toBeDefined();
    expect(firstCharOfCell(citationLine, 1)).toBe("'"); // columna 1 = el valor, columna 0 = "Dataset"
    expect(citationLine).not.toMatch(/^Dataset,=/);
  });

  it("un valor que no empieza por ninguno de esos caracteres no se altera", () => {
    const evidence = syntheticEvidence({ rows: [{ dim_1: "valor normal" }] });
    const columns = [{ key: "dim_1", label: "Campo" }];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    expect(csv.split("\r\n")[1]).toBe("valor normal");
  });
});

describe("toEvidenceCsv — corte estadístico con fallback temporal", () => {
  it("data_updated_at_fallback nunca atribuye un corte falso en el bloque de cita", () => {
    const evidence = syntheticEvidence({
      data_cutoff_basis: "data_updated_at_fallback",
      data_cutoff_at: null,
      data_updated_at: "2024-10-17T19:36:28Z",
    });
    const columns = [];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    expect(csv).toContain("Fecha de actualización del portal: 17 de octubre de 2024. Corte estadístico desconocido.");
  });
});

describe("toEvidenceCsv — display_value y valores numéricos no se redondean ni recalculan", () => {
  it("el valor de la celda es exactamente row[key], sin pasar por ningún formateador de cifras", () => {
    const evidence = syntheticEvidence({ rows: [{ dim_1: 3.14159265358979 }, { dim_1: "153.427" }] });
    const columns = [{ key: "dim_1", label: "Valor" }];
    const csv = toEvidenceCsv({ evidence, resolvedColumns: columns });
    const [, row1, row2] = csv.split("\r\n");
    expect(row1).toBe("3.14159265358979");
    expect(row2).toBe("153.427");
  });

  it("sin filas: el CSV solo tiene encabezado y bloque de cita, no lanza", () => {
    const evidence = syntheticEvidence({ rows: [] });
    const columns = [{ key: "dim_1", label: "Campo" }];
    expect(() => toEvidenceCsv({ evidence, resolvedColumns: columns })).not.toThrow();
  });
});
