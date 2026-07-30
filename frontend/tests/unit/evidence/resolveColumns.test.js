import { describe, expect, it } from "vitest";
import { resolveEvidenceColumns } from "../../../lib/evidence/resolveColumns.js";
import fixture from "../../fixtures/completed-with-claims.json";

/**
 * Dobles sintéticos de este archivo: estructuras mínimas construidas a
 * mano para ejercitar ramas del tokenizador (funciones agregadas, comas
 * anidadas, cadenas con comas/`where`, mayúsculas variables, alias no
 * resoluble, SoQL ausente) que NO existen en ningún fixture real
 * capturado todavía. Se documentan explícitamente aquí, nunca se guardan
 * en `tests/fixtures/`, y no se presentan en ningún lugar como evidencia
 * real ni se usan para prescindir de la verificación con el fixture real.
 */
function syntheticEvidence(overrides = {}) {
  return {
    evidence_id: "synthetic-evidence-1",
    columns: [],
    rows: [],
    soql_query: "",
    ...overrides,
  };
}

describe("resolveEvidenceColumns — fixture real (completed-with-claims.json)", () => {
  it("resuelve dim_1…dim_8 a sus nombres de columna reales del SoQL canónico", () => {
    const [evidence] = fixture.answer.evidence;
    const result = resolveEvidenceColumns(evidence, { claims: fixture.answer.claims });

    const expected = {
      dim_1: "nombre_empresa",
      dim_2: "id_de_la_empresa",
      dim_3: "estado_nueca",
      dim_4: "nueca",
      dim_5: "departamento",
      dim_6: "fecha_de_certificaci_n",
      dim_7: "fecha_estado",
      dim_8: "fecha_inicio_de_operaci_n",
    };

    expect(result.unresolved).toEqual([]);
    expect(result.columns).toHaveLength(8);
    for (const column of result.columns) {
      expect(column.resolved).toBe(true);
      expect(column.fieldName).toBe(expected[column.key]);
      expect(column.kind).toBe("dimension");
      // Nunca un alias crudo dim_N visible en la etiqueta cuando resolvió.
      expect(column.label).not.toMatch(/^dim_\d+$/);
    }
  });

  it("nunca fabrica un nombre de columna: cada fieldName resuelto aparece literalmente en el SoQL real", () => {
    const [evidence] = fixture.answer.evidence;
    const result = resolveEvidenceColumns(evidence, { claims: fixture.answer.claims });
    for (const column of result.columns) {
      if (column.resolved && column.fieldName) {
        expect(evidence.soql_query).toContain(column.fieldName);
      }
    }
  });
});

describe("resolveEvidenceColumns — funciones agregadas (dobles sintéticos)", () => {
  it("sum(campo) AS metric_sum_1 resuelve a metric/sum/campo", () => {
    const evidence = syntheticEvidence({
      columns: ["metric_sum_1"],
      soql_query: "SELECT sum(valor) AS metric_sum_1 WHERE departamento = 'Antioquia'",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column).toMatchObject({ key: "metric_sum_1", fieldName: "valor", kind: "metric", operation: "sum", resolved: true });
    expect(column.label).toBe("Suma de Valor");
  });

  it("avg, min y max resuelven con su operación y campo", () => {
    const evidence = syntheticEvidence({
      columns: ["metric_avg_1", "metric_min_1", "metric_max_1"],
      soql_query: "SELECT avg(edad) AS metric_avg_1, min(edad) AS metric_min_1, max(edad) AS metric_max_1",
    });
    const { columns } = resolveEvidenceColumns(evidence);
    expect(columns[0]).toMatchObject({ operation: "avg", fieldName: "edad", kind: "metric", resolved: true });
    expect(columns[1]).toMatchObject({ operation: "min", fieldName: "edad", kind: "metric", resolved: true });
    expect(columns[2]).toMatchObject({ operation: "max", fieldName: "edad", kind: "metric", resolved: true });
  });

  it("count(*) AS group_count resuelve como count sin fieldName, con etiqueta honesta", () => {
    const evidence = syntheticEvidence({
      columns: ["group_count"],
      soql_query: "SELECT municipio AS dim_1, count(*) AS group_count GROUP BY municipio",
    });
    const { columns } = resolveEvidenceColumns(evidence);
    const groupCount = columns.find((c) => c.key === "group_count");
    expect(groupCount).toMatchObject({ fieldName: null, kind: "count", operation: "count", resolved: true });
    expect(groupCount.label).toBe("Número de registros del grupo");
  });
});

describe("resolveEvidenceColumns — F4-01-R1 defecto 1: semántica correcta de count(...)", () => {
  it("count(*) es exclusivamente 'número de registros', nunca se confunde con count(campo)", () => {
    const evidence = syntheticEvidence({
      columns: ["group_count"],
      soql_query: "SELECT count(*) AS group_count",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column).toMatchObject({ kind: "count", fieldName: null, resolved: true });
    expect(column.label).toBe("Número de registros del grupo");
  });

  it("count(campo) cuenta valores NO NULOS de esa columna — etiqueta distinta de count(*)", () => {
    const evidence = syntheticEvidence({
      columns: ["metric_count_1"],
      soql_query: "SELECT count(correo_electronico) AS metric_count_1",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column).toMatchObject({ kind: "count", fieldName: "correo_electronico", resolved: true });
    expect(column.label).toBe("Número de valores no vacíos de Correo electronico");
    expect(column.label).not.toBe("Número de registros del grupo");
  });

  it("count(distinct campo) cuenta valores DISTINTOS no nulos — semántica propia, nunca 'registros'", () => {
    const evidence = syntheticEvidence({
      columns: ["metric_count_distinct_1"],
      soql_query: "SELECT count(distinct municipio) AS metric_count_distinct_1",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column).toMatchObject({ kind: "count", fieldName: "municipio", resolved: true });
    expect(column.label).toBe("Número de valores distintos no vacíos de Municipio");
    expect(column.label).not.toBe("Número de registros del grupo");
  });

  it("count(distinct campo) con mayúsculas/espacios variables también resuelve", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1"],
      soql_query: "SELECT COUNT( DISTINCT   municipio ) AS dim_1",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column).toMatchObject({ kind: "count", fieldName: "municipio", resolved: true });
  });

  it("count(if(...)) — forma no comprendida con certeza — queda unresolved, nunca se presenta como conteo de registros", () => {
    const evidence = syntheticEvidence({
      columns: ["metric_count_2"],
      soql_query: "SELECT count(if(estado = 'activo', 1, 0)) AS metric_count_2",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column.resolved).toBe(false);
    expect(column.label).toBe("metric_count_2"); // alias crudo, no "Número de registros..."
    expect(column.label).not.toContain("registros");
  });

  it("F4-01-R2: count(if(...)) clasificado como incierto NUNCA se refuerza con claims[].columns, aunque el nombre del claim aparezca dentro de la expresión", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["group_count"],
      soql_query: "SELECT count(if(activo, campo, null)) AS group_count",
    });
    const claims = [{ evidence_id: "ev-1", columns: ["campo"] }];
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    expect(columns[0]).toEqual({
      key: "group_count",
      fieldName: null,
      label: "group_count",
      kind: "unknown",
      operation: null,
      resolved: false,
    });
  });

  it("F4-01-R2: el refuerzo válido de una expresión no agregada (upper(codigo_postal)) sigue funcionando", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_9"],
      soql_query: "SELECT upper(codigo_postal) AS dim_9",
    });
    const claims = [{ evidence_id: "ev-1", columns: ["codigo_postal"] }];
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    expect(columns[0]).toMatchObject({ key: "dim_9", fieldName: "codigo_postal", resolved: true });
  });

  it("count con múltiples argumentos (forma no soportada) queda unresolved", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1"],
      soql_query: "SELECT count(a, b) AS dim_1",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column.resolved).toBe(false);
    expect(column.kind).not.toBe("count");
  });

  it("count(distinct <expresión no identificador>) no se resuelve — solo el identificador simple está soportado", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1"],
      soql_query: "SELECT count(distinct upper(municipio)) AS dim_1",
    });
    const [column] = resolveEvidenceColumns(evidence).columns;
    expect(column.resolved).toBe(false);
  });
});

describe("resolveEvidenceColumns — comas anidadas dentro de funciones/expresiones", () => {
  it("una coma dentro de paréntesis no rompe la separación de columnas del SELECT", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1", "dim_2"],
      soql_query: "SELECT nombre AS dim_1, coalesce(a, b) AS dim_2 WHERE activo = true",
    });
    const { columns } = resolveEvidenceColumns(evidence);
    expect(columns).toHaveLength(2);
    expect(columns[0]).toMatchObject({ key: "dim_1", fieldName: "nombre", resolved: true });
    // coalesce(a, b) no es una función agregada reconocida: se acepta
    // como forma no resoluble en vez de adivinar cuál de los dos
    // identificadores es "el" campo.
    expect(columns[1]).toMatchObject({ key: "dim_2", resolved: false, label: "dim_2" });
  });
});

describe("resolveEvidenceColumns — cadenas entre comillas con comas o palabras clave", () => {
  it("una cadena literal con comas y la palabra 'where' dentro del SELECT no confunde el tokenizador", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1", "dim_2"],
      soql_query:
        "SELECT nombre AS dim_1, 'valor, con comas y la palabra where' AS dim_2 WHERE estado = 'activo'",
    });
    const { columns } = resolveEvidenceColumns(evidence);
    expect(columns).toHaveLength(2);
    expect(columns[0]).toMatchObject({ key: "dim_1", fieldName: "nombre", resolved: true });
    // La cláusula SELECT completa (incluida la cadena con "where" y comas
    // dentro) se extrajo correctamente: dim_2 existe como su propio item,
    // no se fusionó con dim_1 ni se cortó antes de tiempo.
    expect(columns[1].key).toBe("dim_2");
  });
});

describe("resolveEvidenceColumns — alias y AS con variaciones de mayúsculas", () => {
  it("select/as en minúsculas y alias en mayúsculas mixtas resuelven igual", () => {
    const evidence = syntheticEvidence({
      columns: ["Dim_1"],
      soql_query: "select Nombre_Empresa as Dim_1",
    });
    const { columns } = resolveEvidenceColumns(evidence);
    expect(columns[0]).toMatchObject({ key: "Dim_1", fieldName: "Nombre_Empresa", resolved: true });
  });
});

describe("resolveEvidenceColumns — refuerzo verificable con claims[].columns", () => {
  it("un alias que el tokenizador no resuelve se refuerza si el nombre real aparece como identificador dentro de SU PROPIA expresión SELECT aislada", () => {
    // La expresión es una forma no reconocida por el tokenizador (una
    // función no agregada), pero el nombre real declarado por el claim
    // SÍ aparece como identificador completo dentro de la expresión
    // `upper(codigo_postal)` que el tokenizador ya aisló para "dim_9" —
    // correspondencia verificable, no confianza ciega en el claim.
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_9"],
      soql_query: "SELECT upper(codigo_postal) AS dim_9",
    });
    const claims = [{ evidence_id: "ev-1", columns: ["codigo_postal"] }];
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    expect(columns[0]).toMatchObject({ key: "dim_9", fieldName: "codigo_postal", resolved: true });
  });

  it("un nombre de claim que NO aparece junto al alias en el SoQL no se acepta (no verificable)", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_9"],
      soql_query: "SELECT upper(codigo_postal) AS dim_9",
    });
    const claims = [{ evidence_id: "ev-1", columns: ["otro_campo_no_relacionado"] }];
    const { columns, unresolved } = resolveEvidenceColumns(evidence, { claims });
    expect(columns[0].resolved).toBe(false);
    expect(unresolved).toEqual(["dim_9"]);
  });

  it("claims de otra evidencia (evidence_id distinto) nunca se usan para reforzar", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_9"],
      soql_query: "SELECT upper(codigo_postal) AS dim_9",
    });
    const claims = [{ evidence_id: "ev-OTRA", columns: ["codigo_postal"] }];
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    expect(columns[0].resolved).toBe(false);
  });
});

describe("resolveEvidenceColumns — F4-01-R1 defecto 2: nunca una coincidencia parcial dentro de otro identificador", () => {
  it("reproducción exacta: comentario antes de SELECT impide aislar la cláusula; 'foo' NUNCA resuelve por ser subcadena de 'barfoo'", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_1"],
      soql_query: "/* comentario */ SELECT barfoo AS dim_1",
    });
    const claims = [{ evidence_id: "ev-1", columns: ["foo"] }];
    const { columns, unresolved } = resolveEvidenceColumns(evidence, { claims });

    expect(columns[0].resolved).toBe(false);
    expect(columns[0].fieldName).not.toBe("foo");
    expect(columns[0].label).toBe("dim_1"); // alias crudo, nunca "Foo"
    expect(unresolved).toEqual(["dim_1"]);
  });

  it("el caso válido upper(codigo_postal) AS dim_9 reforzado por el claim codigo_postal sigue verde", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_9"],
      soql_query: "SELECT upper(codigo_postal) AS dim_9",
    });
    const claims = [{ evidence_id: "ev-1", columns: ["codigo_postal"] }];
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    expect(columns[0]).toMatchObject({ key: "dim_9", fieldName: "codigo_postal", resolved: true });
  });

  it("cuando el alias no aparece en absoluto en el SELECT analizado, no hay refuerzo posible (sin búsqueda permisiva en el SoQL completo)", () => {
    const evidence = syntheticEvidence({
      evidence_id: "ev-1",
      columns: ["dim_1", "dim_no_declarado"],
      soql_query: "SELECT nombre AS dim_1",
    });
    // "nombre" también aparece cerca de dim_no_declarado en ningún lado,
    // pero incluso si un claim declarara un nombre que casualmente
    // apareciera en OTRO punto del SoQL, no debe usarse: no hay
    // `rawExpression` aislada para "dim_no_declarado".
    const claims = [{ evidence_id: "ev-1", columns: ["nombre"] }];
    const { columns } = resolveEvidenceColumns(evidence, { claims });
    const noDeclarado = columns.find((c) => c.key === "dim_no_declarado");
    expect(noDeclarado.resolved).toBe(false);
    expect(noDeclarado.fieldName).toBeNull();
  });
});

describe("resolveEvidenceColumns — alias no resoluble", () => {
  it("conserva el alias original crudo, resolved:false, sin inventar significado", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_5"],
      soql_query: "SELECT case when a > 1 then a else b end AS dim_5",
    });
    const { columns, unresolved } = resolveEvidenceColumns(evidence);
    expect(columns[0]).toEqual({
      key: "dim_5",
      fieldName: null,
      label: "dim_5",
      kind: "unknown",
      operation: null,
      resolved: false,
    });
    expect(unresolved).toEqual(["dim_5"]);
  });

  it("un alias que ni siquiera aparece en el SELECT también queda sin resolver, sin lanzar", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1", "dim_no_declarado"],
      soql_query: "SELECT nombre AS dim_1",
    });
    expect(() => resolveEvidenceColumns(evidence)).not.toThrow();
    const { columns } = resolveEvidenceColumns(evidence);
    expect(columns[1]).toMatchObject({ key: "dim_no_declarado", resolved: false, label: "dim_no_declarado" });
  });
});

describe("resolveEvidenceColumns — SoQL ausente o no parseable", () => {
  it("soql_query ausente: todas las columnas quedan sin resolver, no lanza", () => {
    const evidence = syntheticEvidence({ columns: ["dim_1", "dim_2"], soql_query: undefined });
    expect(() => resolveEvidenceColumns(evidence)).not.toThrow();
    const { columns, unresolved } = resolveEvidenceColumns(evidence);
    expect(unresolved).toEqual(["dim_1", "dim_2"]);
    expect(columns.every((c) => !c.resolved)).toBe(true);
  });

  it("soql_query con texto no-SQL en absoluto no lanza", () => {
    const evidence = syntheticEvidence({ columns: ["dim_1"], soql_query: "esto no es SQL en absoluto" });
    expect(() => resolveEvidenceColumns(evidence)).not.toThrow();
    expect(resolveEvidenceColumns(evidence).unresolved).toEqual(["dim_1"]);
  });

  it("evidence sin columns en absoluto: devuelve listas vacías, no lanza", () => {
    expect(() => resolveEvidenceColumns({})).not.toThrow();
    expect(resolveEvidenceColumns({})).toEqual({ columns: [], unresolved: [] });
  });
});

describe("resolveEvidenceColumns — nunca fabrica un nombre de columna (dobles sintéticos)", () => {
  it("un fieldName resuelto siempre es un identificador que aparece tal cual en el SoQL de entrada", () => {
    const evidence = syntheticEvidence({
      columns: ["dim_1", "metric_sum_1"],
      soql_query: "SELECT nombre_real AS dim_1, sum(cantidad_real) AS metric_sum_1",
    });
    const { columns } = resolveEvidenceColumns(evidence);
    for (const column of columns) {
      if (column.fieldName) {
        expect(evidence.soql_query).toContain(column.fieldName);
      }
    }
  });
});
