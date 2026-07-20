"""Nodo determinista T7 `construir_afirmaciones` (T-403, contracts/agent-tools.md §T7, RF-208).

Módulo puro: sin I/O, sin LLM, sin acceso a Socrata/DB. Recibe las filas ya
validadas de una Evidencia (T6, `EvidenceContext`) y una lista de `ClaimSpec`
propuestas por el LLM (columnas, fórmula DSL, redondeo deseado); este nodo
las calcula, verifica y devuelve, en el mismo estilo que `validator.py`
(dataclasses puros, no el sobre `{"ok": ...}` de T1-T5: T6/T7 son nodos
internos del grafo, no herramientas invocables por el LLM). Serializar al
formato JSON del contrato es responsabilidad de quien integre el grafo
(T-303); igual que T7 no incluye `claim_text` en su salida (data-model.md lo
exige en `quantitative_claims`, pero el contrato de T7 no lo produce): T-303
lo construye combinando `description` + `display_value`.

Decisiones de diseño no evidentes en el contrato (documentadas aquí porque
son la única fuente; el PR las resume):

1. **Resolución de `{"col": "<columna>"}` cuando `source_row_indexes` tiene
   más de una fila.** El contrato no dice cómo resolver una columna simple
   cuando el claim referencia varias filas (su propio ejemplo de T7 usa
   `source_row_indexes: [0, 1]` con `{"col": "desertores"}`/`{"col":
   "matriculados"}` sin agregación). Se adopta: un nodo `col` recolecta los
   valores NO NULOS de esa columna entre las filas de `source_row_indexes`;
   si hay exactamente un valor no nulo distinto, ese es el resultado (cubre
   tanto el caso normal de una sola fila como el ejemplo del contrato, donde
   cada columna aparece con un único valor no nulo entre las dos filas
   referenciadas); si hay cero valores no nulos, se rechaza como "operando
   nulo"; si hay más de un valor DISTINTO, se rechaza pidiendo `agg`
   explícito (una columna con valores distintos entre varias filas no puede
   colapsarse implícitamente a un escalar). Los nodos `agg` sí reducen
   explícitamente sobre todas las filas de `source_row_indexes` (suma,
   promedio, mínimo, máximo o conteo de no nulos) y NO toleran nulos salvo
   en `count`, evitando que el evaluador descarte datos en silencio (Art. I).

2. **`ratio` vs `div`.** El contrato no define una semántica matemática
   distinta para ambos; se implementan de forma idéntica (a/b, división por
   cero rechazada) — `ratio` existe como alias semántico en el DSL para
   claims que representan una tasa/proporción, sin inventar comportamiento
   no especificado (Art. III, YAGNI).

3. **Canonicalización de `source_hash` y orden de filas.** Siguiendo
   data-model.md ("usa `source_row_indexes` ordenados de forma ascendente"),
   `source_row_indexes` se ordena ascendentemente antes de calcular el hash.
   Esto es seguro porque, bajo este DSL, el ORDEN de los índices nunca afecta
   `raw_value`: `col` es una búsqueda de valor único (no depende de
   posición) y las agregaciones (`sum/avg/min/max/count`) son conmutativas.
   Por tanto, reordenar `source_row_indexes` en la especificación de entrada
   (p. ej. `[1, 0]` vs `[0, 1]`) no es "semánticamente relevante" y produce
   el MISMO hash (pruebas.md §2.1); lo que sí cambia el hash es el
   CONTENIDO de las filas referenciadas (`rows_subset_canonical`) o el
   conjunto de índices referenciado, que se recalculan siempre desde
   `evidence_results.rows` sobre los índices ya ordenados.

4. **Detector de cifras huérfanas.** No existe un parser semántico de
   lenguaje natural; se usa un detector basado en expresiones regulares con
   enmascarado previo de patrones no-cifra (UUID, id de dataset Socrata
   `xxxx-xxxx`, fechas ISO y fechas largas en español) y dos heurísticas
   adicionales: un entero con cero a la izquierda (`05148`) se trata como
   código (DIVIPOLA u otro) y no como cifra; un entero simple inmediatamente
   precedido por una palabra de referencia de sección (sección, artículo,
   numeral, etc.) tampoco cuenta como cifra. Estas heurísticas son
   deliberadamente conservadoras y están documentadas como límite conocido,
   no como cobertura exhaustiva de lenguaje natural.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, DecimalException

from app.quality.claim_labels import LabelStatus, derive_claim_label

#: v2.0.0 (T-617C-R1, RF-212): la identidad de columnas embebida en el hash
#: pasa de alias de ejecución (`dim_N`/`metric_N`) a nombre de columna fuente
#: real. v1.0.0 sigue siendo verificable explícitamente vía
#: `compute_legacy_source_hash` para claims persistidos antes de esta
#: enmienda -- nunca se invalida evidencia histórica en silencio.
CLAIMS_ALGORITHM_VERSION = "2.0.0"
LEGACY_CLAIMS_ALGORITHM_VERSION = "1.0.0"

ALLOWED_AGG_FUNCTIONS = {"sum", "avg", "count", "min", "max"}
ALLOWED_OPS = {"add", "sub", "mul", "div", "ratio", "pct_change"}


# --- Modelos de entrada/salida ----------------------------------------------


@dataclass(frozen=True)
class ClaimSpec:
    claim_type: str
    description: str
    source_row_indexes: tuple[int, ...]
    columns: tuple[str, ...]
    unit: str | None = None
    rounding: int | None = None
    formula: dict | None = None
    #: Mapeo del alias de ejecución (p. ej. `dim_2`) usado en `columns` hacia
    #: el nombre de columna fuente real (p. ej. `genero_hombre`). `columns`
    #: sigue siendo el alias interno necesario para leer `EvidenceContext.rows`
    #: y reproducir `source_hash`; este mapeo solo alimenta los campos
    #: públicos `public_columns`/`label` (RF-212). Sin entrada para un alias
    #: dado, ese alias se usa tal cual como nombre público (compatibilidad
    #: retroactiva con specs que ya declaran nombres reales directamente).
    column_field_names: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceContext:
    dataset_id: str
    canonical_soql: str
    rows: tuple[dict, ...]


@dataclass(frozen=True)
class BuiltClaim:
    claim_type: str
    description: str
    raw_value: Decimal
    display_value: str
    unit: str | None
    rounding: int
    formula: dict | None
    source_row_indexes: tuple[int, ...]
    #: Alias de ejecución interno (p. ej. `dim_2`); NUNCA se expone tal cual
    #: en un campo público (RF-212). Se conserva porque `compute_source_hash`
    #: y la reverificación de hechos fundamentados dependen de que coincida
    #: con las claves de `EvidenceContext.rows`/`evidence_results.rows`.
    columns_used: tuple[str, ...]
    source_hash: str
    #: Nombre(s) de columna fuente real(es) usados por el claim, derivados de
    #: `ClaimSpec.column_field_names` (RF-212). Este es el campo que debe
    #: exponerse públicamente como `columns`/`columns_used`, nunca `columns_used`.
    public_columns: tuple[str, ...] = ()
    #: Etiqueta humana verificable (RF-212, `contracts/api-rest.md` §4c) o
    #: `None` si `label_status="ambiguous"`.
    label: str | None = None
    label_status: LabelStatus = "ambiguous"


@dataclass(frozen=True)
class RejectedClaim:
    description: str
    reason: str


@dataclass(frozen=True)
class ClaimsBuildResult:
    claims: tuple[BuiltClaim, ...]
    rejected: tuple[RejectedClaim, ...]


class ClaimRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- Evaluador seguro del DSL ------------------------------------------------


def _row_scope(evidence: EvidenceContext, spec: ClaimSpec) -> list[dict]:
    rows: list[dict] = []
    for idx in spec.source_row_indexes:
        if idx < 0 or idx >= len(evidence.rows):
            raise ClaimRejected(f"índice de fila {idx} fuera de rango de la evidencia")
        rows.append(evidence.rows[idx])
    return rows


def _to_decimal(value: object, *, column: str) -> Decimal:
    """Hallazgo real (2026-07-12, pilot-004-justicia-presupuesto, dataset
    `f4a5-ab9q`, confirmado contra Socrata real): columnas monetarias de
    datasets del Estado suelen llegar como texto con separador de miles
    ("3,893,283,514,468.00"), porque el propio dataset las publica como
    `Text`, no `Number`. `Decimal(...)` no admite comas, así que un claim
    `direct` sobre ese valor se rechazaba como "no numérico" incluso con la
    fila y columna exactas -- lo que empujaba al router a intentar
    `CAST`/`TO_NUMBER`/`REPLACE` en el SoQL, ninguno permitido por
    `soql_parser.ALLOWED_FUNCTIONS` (`SOQL_FORBIDDEN`). La comparación
    correcta no está en el SoQL (Socrata expone el dato como texto tal cual
    lo público la entidad): es aquí, al convertir la celda ya traída a
    `Decimal`. Se retira solo la coma como separador de miles -- nunca
    ambiguo en los datasets reales inspeccionados (siempre coma=miles,
    punto=decimal), y una cadena sin comas queda intacta.
    """
    if value is None:
        raise ClaimRejected(f"operando nulo: la columna '{column}' no tiene valor en la fila usada")
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except (DecimalException, ValueError):
        raise ClaimRejected(f"operando no numérico: la columna '{column}' no es numérica") from None
    if not result.is_finite():
        raise ClaimRejected(f"operando no numérico: la columna '{column}' no es numérica")
    return result


def _resolve_col(rows: list[dict], columns: tuple[str, ...], name: str, used: set[str]) -> Decimal:
    if name not in columns:
        raise ClaimRejected(f"la columna '{name}' no está declarada en 'columns'")
    if not any(name in row for row in rows):
        raise ClaimRejected(f"la columna '{name}' no existe en la evidencia")
    used.add(name)
    non_null = [row[name] for row in rows if row.get(name) is not None]
    if not non_null:
        raise ClaimRejected(
            f"operando nulo: la columna '{name}' no tiene valor en las filas fuente"
        )
    values = {_to_decimal(v, column=name) for v in non_null}
    if len(values) > 1:
        raise ClaimRejected(
            f"la columna '{name}' tiene valores distintos entre las filas fuente; "
            "use 'agg' para reducir explícitamente"
        )
    return next(iter(values))


def _resolve_agg(
    rows: list[dict], columns: tuple[str, ...], func: str, name: str, used: set[str]
) -> Decimal:
    if func not in ALLOWED_AGG_FUNCTIONS:
        raise ClaimRejected(
            f"operación DSL no permitida: agregación '{func}' no está en la lista blanca"
        )
    if name not in columns:
        raise ClaimRejected(f"la columna '{name}' no está declarada en 'columns'")
    if not any(name in row for row in rows):
        raise ClaimRejected(f"la columna '{name}' no existe en la evidencia")
    used.add(name)

    if func == "count":
        return Decimal(sum(1 for row in rows if row.get(name) is not None))

    values: list[Decimal] = []
    for row in rows:
        if row.get(name) is None:
            raise ClaimRejected(
                f"operando nulo: la columna '{name}' tiene una fila sin valor usada en '{func}'"
            )
        values.append(_to_decimal(row[name], column=name))

    if func == "sum":
        return sum(values, Decimal(0))
    if func == "avg":
        return sum(values, Decimal(0)) / Decimal(len(values))
    if func == "min":
        return min(values)
    return max(values)  # func == "max"


def _eval_node(node: object, rows: list[dict], columns: tuple[str, ...], used: set[str]) -> Decimal:
    if not isinstance(node, dict):
        raise ClaimRejected("operación DSL no permitida: nodo de fórmula inválido")
    keys = set(node.keys())

    if keys == {"const"}:
        value = node["const"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ClaimRejected("operando no numérico: 'const' debe ser un número")
        return Decimal(str(value))

    if keys == {"col"}:
        name = node["col"]
        if not isinstance(name, str):
            raise ClaimRejected("operación DSL no permitida: 'col' debe ser un nombre de columna")
        return _resolve_col(rows, columns, name, used)

    if keys == {"agg", "col"}:
        func, name = node["agg"], node["col"]
        if not isinstance(func, str) or not isinstance(name, str):
            raise ClaimRejected("operación DSL no permitida: 'agg'/'col' inválidos")
        return _resolve_agg(rows, columns, func, name, used)

    if keys == {"op", "args"}:
        op, args = node["op"], node["args"]
        if op not in ALLOWED_OPS:
            raise ClaimRejected(f"operación DSL no permitida: '{op}' no está en la lista blanca")
        if not isinstance(args, list) or not args:
            raise ClaimRejected(
                f"operación DSL no permitida: '{op}' requiere una lista de argumentos"
            )
        values = [_eval_node(arg, rows, columns, used) for arg in args]
        return _apply_op(op, values)

    raise ClaimRejected("operación DSL no permitida: forma de nodo desconocida")


def _apply_op(op: str, values: list[Decimal]) -> Decimal:
    if op == "add":
        if len(values) < 2:
            raise ClaimRejected("operación DSL no permitida: 'add' requiere al menos 2 argumentos")
        return sum(values, Decimal(0))
    if op == "mul":
        if len(values) < 2:
            raise ClaimRejected("operación DSL no permitida: 'mul' requiere al menos 2 argumentos")
        result = Decimal(1)
        for value in values:
            result *= value
        return result
    if op == "sub":
        if len(values) < 2:
            raise ClaimRejected("operación DSL no permitida: 'sub' requiere al menos 2 argumentos")
        result = values[0]
        for value in values[1:]:
            result -= value
        return result
    if op in ("div", "ratio"):
        if len(values) != 2:
            raise ClaimRejected(
                f"operación DSL no permitida: '{op}' requiere exactamente 2 argumentos"
            )
        numerator, denominator = values
        if denominator == 0:
            raise ClaimRejected("división por cero")
        return numerator / denominator
    if op == "pct_change":
        if len(values) != 2:
            raise ClaimRejected(
                "operación DSL no permitida: 'pct_change' requiere exactamente 2 argumentos"
            )
        old, new = values
        if old == 0:
            raise ClaimRejected("división por cero")
        return (new - old) / old * Decimal(100)
    raise ClaimRejected(  # pragma: no cover -- op ya validado contra ALLOWED_OPS
        f"operación DSL no permitida: '{op}' no está en la lista blanca"
    )


# --- Construcción de claims ---------------------------------------------------


def _build_direct(evidence: EvidenceContext, spec: ClaimSpec) -> tuple[Decimal, set[str]]:
    if len(spec.source_row_indexes) != 1 or len(spec.columns) != 1:
        raise ClaimRejected(
            "un claim 'direct' requiere exactamente una fila en 'source_row_indexes' y una "
            "columna en 'columns'"
        )
    rows = _row_scope(evidence, spec)
    name = spec.columns[0]
    if name not in rows[0]:
        raise ClaimRejected(f"la columna '{name}' no existe en la evidencia")
    raw = _to_decimal(rows[0].get(name), column=name)
    return raw, {name}


def _build_derived(evidence: EvidenceContext, spec: ClaimSpec) -> tuple[Decimal, set[str]]:
    if spec.formula is None:
        raise ClaimRejected("un claim 'derived' requiere 'formula'")
    rows = _row_scope(evidence, spec)
    used: set[str] = set()
    raw = _eval_node(spec.formula, rows, spec.columns, used)
    if not raw.is_finite():
        raise ClaimRejected("operando no numérico: el resultado de la fórmula no es finito")
    return raw, used


def _infer_direct_rounding(raw_value: Decimal) -> int:
    """Hallazgo real (pilot-034-eolica-jepirachi, dataset `vy9n-w6hc`): un
    claim `direct` sin `rounding` explícito (el pipeline determinista, T7,
    nunca lo fija -- `deterministic_pipeline._claim_specs`) caía en el
    default `0` de abajo y presentaba `Capacidad: 18` para una fuente
    `18.42`, una contradicción material (RNF-003) aunque el dato subyacente
    fuera correcto. Un claim `direct` es una lectura literal de una celda
    (`_build_direct`), no un cálculo (`derived`): su precisión debe ser la
    escala decimal ya presente en `raw_value` (vía `_to_decimal`), nunca una
    inferida desde `case_id`, nombre de columna o dataset. `Decimal` conserva
    los ceros decimales de la fuente tal cual se escribieron (p. ej.
    `"18.4200"` -> exponente -4 -> redondeo 4), así que esta política es
    determinista y reproducible sin heurísticas adicionales."""

    exponent = raw_value.as_tuple().exponent
    if not isinstance(exponent, int):
        return 0
    return max(0, -exponent)


def _build_one_claim(evidence: EvidenceContext, spec: ClaimSpec) -> BuiltClaim:
    if spec.claim_type not in ("direct", "derived"):
        raise ClaimRejected(f"claim_type '{spec.claim_type}' no reconocido")
    if not spec.source_row_indexes:
        raise ClaimRejected("'source_row_indexes' no puede estar vacío")
    if not spec.columns:
        raise ClaimRejected("'columns' no puede estar vacío")

    if spec.claim_type == "direct":
        raw_value, used_columns = _build_direct(evidence, spec)
        default_rounding = _infer_direct_rounding(raw_value)
    else:
        raw_value, used_columns = _build_derived(evidence, spec)
        default_rounding = 0

    rounding = spec.rounding if spec.rounding is not None else default_rounding
    display_value = format_es_co(raw_value, rounding, spec.unit)
    sorted_indexes = tuple(sorted(spec.source_row_indexes))

    sorted_alias_columns = tuple(sorted(used_columns))
    public_columns = tuple(
        spec.column_field_names.get(alias, alias) for alias in sorted_alias_columns
    )
    label, label_status = derive_claim_label(public_columns)

    source_hash = compute_source_hash(
        dataset_id=evidence.dataset_id,
        canonical_soql=evidence.canonical_soql,
        source_row_indexes=sorted_indexes,
        rows=evidence.rows,
        execution_columns=sorted_alias_columns,
        public_columns=public_columns,
        formula=spec.formula,
        raw_value=raw_value,
        unit=spec.unit,
        rounding=rounding,
    )

    return BuiltClaim(
        claim_type=spec.claim_type,
        description=spec.description,
        raw_value=raw_value,
        display_value=display_value,
        unit=spec.unit,
        rounding=rounding,
        formula=spec.formula,
        source_row_indexes=sorted_indexes,
        columns_used=sorted_alias_columns,
        source_hash=source_hash,
        public_columns=public_columns,
        label=label,
        label_status=label_status,
    )


def build_claims(evidence: EvidenceContext, claim_specs: Sequence[ClaimSpec]) -> ClaimsBuildResult:
    claims: list[BuiltClaim] = []
    rejected: list[RejectedClaim] = []
    for spec in claim_specs:
        try:
            claims.append(_build_one_claim(evidence, spec))
        except ClaimRejected as exc:
            rejected.append(RejectedClaim(description=spec.description, reason=exc.reason))
        except (DecimalException, TypeError, KeyError, IndexError) as exc:
            rejected.append(
                RejectedClaim(description=spec.description, reason=f"operando inválido: {exc}")
            )
    return ClaimsBuildResult(claims=tuple(claims), rejected=tuple(rejected))


# --- Formato es-CO -----------------------------------------------------------


def format_es_co(raw_value: Decimal, rounding: int, unit: str | None) -> str:
    quantizer = Decimal(1).scaleb(-rounding) if rounding > 0 else Decimal(1)
    rounded = raw_value.quantize(quantizer, rounding=ROUND_HALF_UP)
    negative = rounded < 0
    rounded = abs(rounded)

    plain = format(rounded, "f")
    int_part, _, dec_part = plain.partition(".")
    grouped_int = f"{int(int_part):,}".replace(",", ".")

    if rounding > 0:
        dec_part = dec_part.ljust(rounding, "0")[:rounding]
        number_str = f"{grouped_int},{dec_part}"
    else:
        number_str = grouped_int

    if negative:
        number_str = f"-{number_str}"
    return f"{number_str} {unit}" if unit else number_str


# --- source_hash --------------------------------------------------------------


def _row_subset_canonical_legacy(
    rows: tuple[dict, ...], indexes: tuple[int, ...], columns: tuple[str, ...]
) -> list[dict]:
    return [{col: rows[idx].get(col) for col in columns} for idx in indexes]


def _row_subset_canonical(
    rows: tuple[dict, ...],
    indexes: tuple[int, ...],
    execution_columns: tuple[str, ...],
    public_columns: tuple[str, ...],
) -> list[dict]:
    """Extrae el subconjunto canónico de filas leyendo por alias de
    ejecución (única clave presente en `rows`, ver `EvidenceContext`), pero
    reindexa el resultado por nombre de columna público (RF-212): el alias
    nunca queda embebido en el material que produce `source_hash`."""

    pairs = tuple(zip(execution_columns, public_columns, strict=True))
    return [{public: rows[idx].get(alias) for alias, public in pairs} for idx in indexes]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_source_hash(
    *,
    dataset_id: str,
    canonical_soql: str,
    source_row_indexes: tuple[int, ...],
    rows: tuple[dict, ...],
    execution_columns: tuple[str, ...],
    public_columns: tuple[str, ...],
    formula: dict | None,
    raw_value: Decimal,
    unit: str | None,
    rounding: int,
) -> str:
    """Hash reproducible v2.0.0 (RF-212): la identidad de columnas embebida
    en el material (`"columns"`, `rows_subset_canonical`) es el nombre de
    columna fuente real (`public_columns`), nunca el alias de ejecución
    (`execution_columns`) usado solo para leer `rows`. Para claims
    persistidos antes de esta versión usar `compute_legacy_source_hash`."""

    sorted_indexes = tuple(sorted(source_row_indexes))
    payload = {
        "algorithm_version": CLAIMS_ALGORITHM_VERSION,
        "dataset_id": dataset_id,
        "canonical_soql": canonical_soql,
        "source_row_indexes": list(sorted_indexes),
        "rows_subset_canonical": _row_subset_canonical(
            rows, sorted_indexes, execution_columns, public_columns
        ),
        "columns": list(public_columns),
        "formula_dsl_canonical": formula,
        "raw_value": format(raw_value, "f"),
        "unit": unit,
        "rounding": rounding,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_legacy_source_hash(
    *,
    dataset_id: str,
    canonical_soql: str,
    source_row_indexes: tuple[int, ...],
    rows: tuple[dict, ...],
    columns: tuple[str, ...],
    formula: dict | None,
    raw_value: Decimal,
    unit: str | None,
    rounding: int,
) -> str:
    """Reproduce el hash v1.0.0 (columns = alias de ejecución) bit a bit,
    exclusivamente para reverificar claims persistidos antes de T-617C-R1.
    No usar para claims nuevos."""

    sorted_indexes = tuple(sorted(source_row_indexes))
    payload = {
        "algorithm_version": LEGACY_CLAIMS_ALGORITHM_VERSION,
        "dataset_id": dataset_id,
        "canonical_soql": canonical_soql,
        "source_row_indexes": list(sorted_indexes),
        "rows_subset_canonical": _row_subset_canonical_legacy(rows, sorted_indexes, columns),
        "columns": list(columns),
        "formula_dsl_canonical": formula,
        "raw_value": format(raw_value, "f"),
        "unit": unit,
        "rounding": rounding,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


# --- Detector de cifras huérfanas ---------------------------------------------

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_DATASET_ID_RE = re.compile(r"\b[0-9a-z]{4}-[0-9a-z]{4}\b")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MESES_PATTERN = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre"
)
_LONG_DATE_RE = re.compile(
    rf"\b\d{{1,2}}\s+de\s+(?:{_MESES_PATTERN})\s+de\s+\d{{4}}\b", re.IGNORECASE
)

_SECTION_WORDS = (
    "sección",
    "seccion",
    "artículo",
    "articulo",
    "numeral",
    "literal",
    "capítulo",
    "capitulo",
    "anexo",
    "página",
    "pagina",
    "pág",
    "pag",
    "núm",
    "num",
    "no.",
)

_RANGE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:-|a)\s*(\d+(?:[.,]\d+)?)\b")

_FIGURE_CANDIDATE_RE = re.compile(
    r"(?<![\w.,-])"
    r"\$?\s?"
    r"(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?"
    r"|\d+[.,]\d+"
    r"|\d+)"
    r"(?:\s?%)?"
    r"(?![\w])"
)


def _mask_non_figures(text: str) -> str:
    masked = text
    for pattern in (_UUID_RE, _LONG_DATE_RE, _ISO_DATE_RE, _DATASET_ID_RE):
        masked = pattern.sub(lambda m: " " * len(m.group(0)), masked)
    return masked


def _looks_like_code(token: str) -> bool:
    core = token.strip().lstrip("$").rstrip("%").strip()
    return len(core) > 1 and core[0] == "0" and "." not in core and "," not in core


def _is_section_reference(text: str, start: int) -> bool:
    prefix = text[max(0, start - 20) : start].lower()
    return any(prefix.rstrip().endswith(word) for word in _SECTION_WORDS)


def find_figures(text: str) -> tuple[str, ...]:
    """Cifra (definición normativa, contracts/agent-tools.md §T7): cualquier token
    numérico visible en español o formato internacional -- enteros, decimales
    con coma o punto, porcentajes, monedas, miles, tasas, rangos y años usados
    como valor analítico. Excluye IDs técnicos, UUID, fechas completas de cita,
    códigos DIVIPOLA y números de sección sin dato sustantivo.
    """
    masked = _mask_non_figures(text)
    tokens: list[str] = []

    def _consume_range(match: re.Match[str]) -> str:
        tokens.append(match.group(1))
        tokens.append(match.group(2))
        return " " * len(match.group(0))

    masked = _RANGE_RE.sub(_consume_range, masked)

    for match in _FIGURE_CANDIDATE_RE.finditer(masked):
        token = match.group(0)
        if _looks_like_code(token):
            continue
        is_plain_integer = "." not in token and "," not in token and "%" not in token
        if is_plain_integer and _is_section_reference(text, match.start()):
            continue
        tokens.append(token.strip())

    return tuple(tokens)


def _numeric_core(token: str) -> str:
    core = token.strip()
    if core.endswith("%"):
        core = core[:-1].strip()
    if core.startswith("$"):
        core = core[1:].strip()
    return core


def find_orphan_figures(text: str, accepted_display_values: Iterable[str]) -> tuple[str, ...]:
    """Una cifra en el texto sin `display_value` de un claim aceptado que la respalde
    es un defecto bloqueante (RF-208, RNF-003)."""
    allowed_cores = {
        _numeric_core(token)
        for display_value in accepted_display_values
        for token in find_figures(display_value)
    }
    return tuple(token for token in find_figures(text) if _numeric_core(token) not in allowed_cores)
