/**
 * Resolución de columnas de evidencia (H1, `implementation-plan.md` §4.7):
 * traduce los alias internos de la consulta SoQL determinista (`dim_1`,
 * `metric_sum_1`, `group_count`…) a nombres de columna reales y etiquetas
 * legibles, analizando la propia cláusula `SELECT` del `soql_query`
 * canónico de la evidencia — nunca infiriendo un significado que no esté
 * verificablemente presente en esa consulta.
 *
 * Módulo puro: sin red, sin React, sin `window`/`document`, determinista
 * (misma entrada ⇒ misma salida).
 */
import { humanizeField } from "./humanizeField.js";

const CLAUSE_BOUNDARY_KEYWORDS = ["WHERE", "GROUP", "ORDER", "LIMIT", "OFFSET"];
// "count" queda fuera deliberadamente: tiene su propia clasificación
// (`classifyCountArgs`) porque, a diferencia de sum/avg/min/max, sus
// variantes (`*`, campo, `distinct campo`) tienen semánticas distintas
// entre sí (F4-01-R1, defecto 1).
const AGGREGATE_FUNCTIONS = new Set(["sum", "avg", "min", "max"]);
const AGGREGATE_LABELS = { sum: "Suma de", avg: "Promedio de", min: "Mínimo de", max: "Máximo de" };
const BARE_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;
const COUNT_STAR_LABEL = "Número de registros del grupo";

function isWordChar(ch) {
  return /[A-Za-z0-9_]/.test(ch);
}

/** Devuelve el índice justo después de `keyword` si aparece en `str` a
 * partir de `start` como palabra completa (no pegada a otro carácter de
 * palabra), ignorando mayúsculas/minúsculas — o `-1`. */
function matchKeywordAt(str, start, keyword) {
  const end = start + keyword.length;
  if (end > str.length) return -1;
  if (str.slice(start, end).toUpperCase() !== keyword) return -1;
  const before = start > 0 ? str[start - 1] : "";
  const after = end < str.length ? str[end] : "";
  if (isWordChar(before) || isWordChar(after)) return -1;
  return end;
}

/**
 * Escáner genérico de un solo paso que expone, en cada posición, si el
 * carácter cae dentro de una cadena `'...'` (con `''` como apóstrofo
 * escapado) o un identificador entre backticks `` `...` `` — ambos casos
 * "atómicos" en los que comas, palabras clave y paréntesis no cuentan.
 * `visitor(index, char, { depth, atomic })` decide qué hacer con cada
 * carácter; el escáner solo lleva la contabilidad de paréntesis y comillas.
 */
function scanSql(str, visitor) {
  let depth = 0;
  let inSingleQuote = false;
  let inBacktick = false;
  for (let i = 0; i < str.length; i += 1) {
    const ch = str[i];

    if (inSingleQuote) {
      if (ch === "'") {
        if (str[i + 1] === "'") {
          visitor(i, ch, { depth, atomic: true });
          i += 1;
          visitor(i, str[i], { depth, atomic: true });
          continue;
        }
        inSingleQuote = false;
      }
      visitor(i, ch, { depth, atomic: true });
      continue;
    }
    if (inBacktick) {
      if (ch === "`") inBacktick = false;
      visitor(i, ch, { depth, atomic: true });
      continue;
    }
    if (ch === "'") {
      inSingleQuote = true;
      visitor(i, ch, { depth, atomic: false });
      continue;
    }
    if (ch === "`") {
      inBacktick = true;
      visitor(i, ch, { depth, atomic: false });
      continue;
    }
    if (ch === "(") {
      visitor(i, ch, { depth, atomic: false });
      depth += 1;
      continue;
    }
    if (ch === ")") {
      depth = Math.max(0, depth - 1);
      visitor(i, ch, { depth, atomic: false });
      continue;
    }
    visitor(i, ch, { depth, atomic: false });
  }
}

/** Divide `str` por `separator` (un solo carácter) solo en profundidad 0
 * y fuera de cadenas/backticks. */
function splitTopLevel(str, separator) {
  const parts = [];
  let current = "";
  scanSql(str, (_i, ch, { depth, atomic }) => {
    if (!atomic && depth === 0 && ch === separator) {
      parts.push(current);
      current = "";
      return;
    }
    current += ch;
  });
  parts.push(current);
  return parts;
}

/** Índice donde empieza la primera palabra clave de cierre de cláusula
 * (WHERE/GROUP/ORDER/LIMIT/OFFSET) en profundidad 0 y fuera de
 * cadenas/backticks — o `str.length` si no aparece ninguna. */
function findClauseBoundary(str) {
  let boundary = str.length;
  let stopped = false;
  scanSql(str, (i, _ch, { depth, atomic }) => {
    if (stopped || atomic || depth !== 0) return;
    for (const kw of CLAUSE_BOUNDARY_KEYWORDS) {
      if (matchKeywordAt(str, i, kw) !== -1) {
        boundary = Math.min(boundary, i);
        stopped = true;
        return;
      }
    }
  });
  return boundary;
}

/** Extrae el texto de la cláusula SELECT (entre `SELECT` y la primera
 * palabra clave de cierre), o `null` si `soql` no es una cadena que
 * empiece por `SELECT`. Nunca lanza. */
function extractSelectClause(soql) {
  if (typeof soql !== "string") return null;
  const match = /^\s*SELECT\b/i.exec(soql);
  if (!match) return null;
  const afterSelect = match[0].length;
  const rest = soql.slice(afterSelect);
  const boundary = findClauseBoundary(rest);
  return rest.slice(0, boundary).trim();
}

/** Divide un item `expresión [AS alias]` en `{expression, alias}`,
 * buscando `AS` como palabra completa en profundidad 0 fuera de cadenas.
 * Sin `AS`, la expresión completa hace de alias (referencia sin alias
 * explícito). */
function splitExpressionAndAlias(item) {
  let asIndex = -1;
  scanSql(item, (i, _ch, { depth, atomic }) => {
    if (asIndex !== -1 || atomic || depth !== 0) return;
    if (matchKeywordAt(item, i, "AS") !== -1) asIndex = i;
  });
  if (asIndex === -1) {
    const trimmed = item.trim();
    return { expression: trimmed, alias: trimmed };
  }
  return {
    expression: item.slice(0, asIndex).trim(),
    alias: item.slice(asIndex + 2).trim(),
  };
}

function unquoteIdentifier(text) {
  if (text.length >= 2 && text.startsWith("`") && text.endsWith("`")) return text.slice(1, -1);
  if (text.length >= 2 && text.startsWith('"') && text.endsWith('"')) return text.slice(1, -1);
  return text;
}

function firstTopLevelIdentifier(argsText) {
  const [first = ""] = splitTopLevel(argsText, ",");
  const candidate = unquoteIdentifier(first.trim());
  return BARE_IDENTIFIER.test(candidate) ? candidate : null;
}

/**
 * Clasifica los argumentos de `count(...)` con certeza o no en absoluto —
 * nunca a medias. Variantes reconocidas, cada una con su propia semántica
 * SoQL real (F4-01-R1, defecto 1):
 * - `*`            → número de filas del grupo.
 * - `campo`        → número de valores NO NULOS de `campo` (SoQL: count
 *                    de una columna cuenta valores no nulos, no filas).
 * - `distinct campo` → número de valores DISTINTOS no nulos de `campo`.
 * Cualquier otra forma (`count(if(...))`, expresiones aritméticas,
 * múltiples argumentos, funciones anidadas no reconocidas…) devuelve
 * `certain:false`: el llamador debe tratarlo como no resuelto, nunca
 * como un conteo de registros por defecto.
 */
function classifyCountArgs(rawArgs) {
  const args = rawArgs.trim();

  if (args === "*") {
    return { certain: true, fieldName: null, countVariant: "star" };
  }

  const distinctMatch = /^distinct\s+([\s\S]+)$/i.exec(args);
  if (distinctMatch) {
    const candidate = unquoteIdentifier(distinctMatch[1].trim());
    if (BARE_IDENTIFIER.test(candidate)) {
      return { certain: true, fieldName: candidate, countVariant: "distinct_field" };
    }
    return { certain: false };
  }

  const candidate = unquoteIdentifier(args);
  if (BARE_IDENTIFIER.test(candidate)) {
    return { certain: true, fieldName: candidate, countVariant: "field" };
  }

  return { certain: false };
}

/** Clasifica una expresión SELECT ya separada de su alias. Nunca lanza:
 * una forma no reconocida cae en `kind:"unknown"`. */
function classifyExpression(expression) {
  const trimmed = expression.trim();
  const bareCandidate = unquoteIdentifier(trimmed);
  if (BARE_IDENTIFIER.test(bareCandidate)) {
    return { kind: "dimension", operation: null, fieldName: bareCandidate, countVariant: null };
  }

  const fnMatch = /^([A-Za-z]+)\s*\(([\s\S]*)\)$/.exec(trimmed);
  if (fnMatch) {
    const fnName = fnMatch[1].toLowerCase();

    if (fnName === "count") {
      const result = classifyCountArgs(fnMatch[2]);
      if (!result.certain) {
        // `count(...)` de forma no comprendida con certeza: NUNCA se
        // presenta como conteo de registros (defecto 1, regla 5) — y
        // NUNCA se refuerza después con `claims[].columns` (F4-01-R2):
        // `reinforceable:false` lo distingue de una expresión genuinamente
        // desconocida (p. ej. una función no agregada), que sí admite
        // refuerzo verificable.
        return { kind: "unknown", operation: null, fieldName: null, countVariant: null, reinforceable: false };
      }
      return { kind: "count", operation: "count", fieldName: result.fieldName, countVariant: result.countVariant };
    }

    if (AGGREGATE_FUNCTIONS.has(fnName)) {
      const fieldName = firstTopLevelIdentifier(fnMatch[2]);
      return { kind: "metric", operation: fnName, fieldName, countVariant: null };
    }
  }

  return { kind: "unknown", operation: null, fieldName: null, countVariant: null };
}

function parseSelectClause(selectClause) {
  const items = splitTopLevel(selectClause, ",");
  const parsed = new Map();
  for (const rawItem of items) {
    const item = rawItem.trim();
    if (!item) continue;
    const { expression, alias: rawAlias } = splitExpressionAndAlias(item);
    const alias = unquoteIdentifier(rawAlias);
    if (!alias) continue;
    const entry = { ...classifyExpression(expression), rawExpression: expression };
    parsed.set(alias, entry);
    parsed.set(alias.toLowerCase(), entry);
  }
  return parsed;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Refuerzo verificable con `claims[].columns` (F4-01-R1, defecto 2: nunca
 * una coincidencia parcial). Nunca se confía en un claim por sí solo: el
 * nombre de columna real que declara debe aparecer como identificador
 * COMPLETO (con límites de palabra a ambos lados) dentro de la EXPRESIÓN
 * SELECT concreta que el tokenizador ya aisló para ese alias — p. ej.
 * `codigo_postal` dentro de `upper(codigo_postal)` para `AS dim_9`.
 *
 * Si esa expresión no se pudo aislar (el alias no apareció en absoluto en
 * el `SELECT` analizado, o la cláusula `SELECT` completa no se pudo
 * extraer del SoQL — p. ej. por un comentario antes de `SELECT` que este
 * tokenizador no quita), NO hay refuerzo: se deja `unresolved`. Se
 * eliminó deliberadamente cualquier respaldo que buscara el nombre en el
 * SoQL completo sin aislar — esa búsqueda permisiva es exactamente la que
 * permitía que `foo` "reforzara" un alias dentro de `barfoo` (`foo` es
 * subcadena de `barfoo`, pero nunca un identificador propio ahí). Si más
 * de un candidato verifica, tampoco se puede desambiguar sin adivinar.
 */
function reinforceFromClaims({ rawExpression, evidenceId, claims }) {
  if (typeof rawExpression !== "string") return null;
  if (!Array.isArray(claims) || claims.length === 0) return null;

  const candidates = new Set();
  for (const claim of claims) {
    if (evidenceId && claim?.evidence_id !== evidenceId) continue;
    for (const col of Array.isArray(claim?.columns) ? claim.columns : []) {
      if (typeof col === "string" && col.trim()) candidates.add(col.trim());
    }
  }
  if (candidates.size === 0) return null;

  const verified = [...candidates].filter((name) => {
    const identifier = new RegExp(`(^|[^A-Za-z0-9_])${escapeRegExp(name)}([^A-Za-z0-9_]|$)`, "i");
    return identifier.test(rawExpression);
  });
  return verified.length === 1 ? verified[0] : null;
}

/** Una columna está resuelta cuando su significado quedó verificablemente
 * establecido: `count` siempre lo está (nunca se llega a `kind:"count"`
 * salvo que `classifyCountArgs` haya sido `certain`); `dimension`/
 * `metric` solo cuando se identificó un nombre de campo real. */
function isResolvedKind(kind, fieldName) {
  if (kind === "count") return true;
  if (kind === "dimension" || kind === "metric") return Boolean(fieldName);
  return false;
}

/** Etiqueta honesta por variante de `count` (F4-01-R1, defecto 1): un
 * conteo de filas (`*`) nunca se confunde con un conteo de valores no
 * nulos de una columna concreta, ni con un conteo de valores distintos. */
function labelForCount(countVariant, fieldName) {
  if (countVariant === "field") return `Número de valores no vacíos de ${humanizeField(fieldName)}`;
  if (countVariant === "distinct_field") return `Número de valores distintos no vacíos de ${humanizeField(fieldName)}`;
  return COUNT_STAR_LABEL; // countVariant === "star"
}

function labelFor({ kind, operation, fieldName, alias, resolved, countVariant }) {
  if (!resolved) return alias; // alias crudo: nunca se inventa un significado
  if (kind === "count") return labelForCount(countVariant, fieldName);
  const base = humanizeField(fieldName);
  if (kind === "metric" && operation && AGGREGATE_LABELS[operation]) {
    return `${AGGREGATE_LABELS[operation]} ${base}`;
  }
  return base;
}

/**
 * @param {object} evidence - objeto Evidencia (`contracts/api-rest.md` §5);
 *   forma real observada: `columns` es `string[]` de alias, `rows[i]` usa
 *   esos mismos alias como claves.
 * @param {{claims?: object[]}} [options]
 * @returns {{columns: Array<{key:string, fieldName:string|null, label:string, kind:string, operation:string|null, resolved:boolean}>, unresolved: string[]}}
 */
export function resolveEvidenceColumns(evidence, { claims = [] } = {}) {
  const rawColumns = Array.isArray(evidence?.columns) ? evidence.columns : [];
  const aliases = rawColumns
    .map((entry) => (typeof entry === "string" ? entry : (entry && typeof entry === "object" ? entry.field : null)))
    .filter((alias) => typeof alias === "string" && alias.length > 0);

  const soql = typeof evidence?.soql_query === "string" ? evidence.soql_query : evidence?.citation?.soql_query;
  const selectClause = extractSelectClause(soql);
  const parsedByAlias = selectClause ? parseSelectClause(selectClause) : new Map();

  const columns = aliases.map((alias) => {
    const found = parsedByAlias.get(alias) ?? parsedByAlias.get(alias.toLowerCase());
    let kind = found?.kind ?? "unknown";
    let operation = found?.operation ?? null;
    let fieldName = found?.fieldName ?? null;
    const countVariant = found?.countVariant ?? null;
    let resolved = isResolvedKind(kind, fieldName);

    // `reinforceable === false` marca una expresión `count(...)` clasificada
    // con certeza como incierta (F4-01-R2): ese alias nunca se refuerza con
    // `claims[].columns`, aunque el nombre real del claim aparezca dentro de
    // su propia expresión aislada — el refuerzo es para expresiones cuyo
    // significado el tokenizador simplemente no reconoce, no para un
    // `count(...)` cuya semántica ya se determinó y descartó.
    if (!resolved && found?.reinforceable !== false) {
      const reinforced = reinforceFromClaims({
        rawExpression: found?.rawExpression,
        evidenceId: evidence?.evidence_id,
        claims,
      });
      if (reinforced) {
        fieldName = reinforced;
        if (kind === "unknown") kind = "dimension";
        resolved = isResolvedKind(kind, fieldName);
      }
    }

    return {
      key: alias,
      fieldName,
      label: labelFor({ kind, operation, fieldName, alias, resolved, countVariant }),
      kind,
      operation,
      resolved,
    };
  });

  const unresolved = columns.filter((c) => !c.resolved).map((c) => c.key);
  return { columns, unresolved };
}
