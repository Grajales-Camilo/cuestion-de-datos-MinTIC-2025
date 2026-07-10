"""Nodo determinista T6 `validar_evidencia` (T-401, contracts/validacion-calidad.md).

Módulo puro: sin I/O, sin LLM, sin acceso a Socrata/DB. Recibe un
`EvidenceDraft` ya construido por el llamador (T-303) con los metadatos que
el contrato exige como entrada (§1) y produce el objeto `quality` (§4).

Reutiliza, no recalcula, la clasificación PII/publicador ya hecha en la
ingesta: `app.quality.eligibility.compute_column_eligibility` combina el
`pii_risk_level` de cada columna seleccionada con las razones YA vigentes a
nivel de dataset (`dataset_eligibility_reasons`, calculadas por T-201 con el
mismo módulo). Este módulo NO llama a `compute_dataset_eligibility`: el
estado de dataset llega ya resuelto en el draft.

Decisión de diseño no evidente en el contrato (D2 completeness): la tabla
de `completeness.null_ratio` lista "Puntos: 60" pero su regla interna usa una
escala 0-100 (`<=5% -> 100`, `<=20% -> 60`, `<=50% -> 30`, `>50% -> 0`). Se
interpreta esa escala como un PORCENTAJE del máximo de 60 puntos del check
(ej. `<=20%` de nulos -> 60% de 60 = 36 puntos), sumado a los puntos ya
directos de `completeness.placeholder_values` (0 o 40) -- así D2 llega a 100
solo si ambos checks son perfectos. El ejemplo JSON del contrato (`score:
60`) parece una ilustración abreviada que no refleja el check de
placeholders; se siguió el texto normativo, no el ejemplo, por jerarquía
(constitution.md > ... > contracts/).

Otra decisión: cuando `row_count == 0`, además de forzar D1=0 (regla
explícita del contrato), se fuerza `classification="no_recomendada"` -- el
contrato dice que esa evidencia "no se presenta como hallazgo", lo cual un
`score_total` numérico por sí solo no garantiza (D1=0 con las otras tres
dimensiones perfectas podría dar exactamente 75 = "alta").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.quality.cutoff import infer_data_cutoff
from app.quality.eligibility import compute_column_eligibility
from app.quality.messages_es import (
    empty_result_warning,
    missing_source_warning,
    null_ratio_warning,
    pii_aggregation_insufficient_warning,
    placeholder_warning,
    publisher_not_verified_warning,
    timeliness_warning,
)
from app.quality.placeholders import (
    ColumnValues,
    PlaceholdersFixture,
    detect_placeholders,
    load_placeholder_patterns,
)
from app.tools.soql_parser import (
    AGG_FUNCTIONS,
    BoolOp,
    Column,
    Comparison,
    FuncCall,
    Literal,
    Not,
    ParsedQuery,
    SoqlGuardError,
    parse_soql,
)

VALIDATOR_VERSION = "1.0.0"
DEFAULT_PLACEHOLDER_MIN_RATIO = 0.30
MIN_AGGREGATION_COUNT = 5

_PII_SEVERITY = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
_ELIGIBILITY_SEVERITY = {"eligible": 0, "diagnostic_only": 1, "blocked": 2}
_NUMERIC_COMPARISON_OPS = {"<", "<=", ">", ">="}


@dataclass(frozen=True)
class SelectedColumn:
    field_name: str
    pii_risk_level: str
    known_placeholder_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceDraft:
    dataset_id: str
    dataset_name: str
    publisher: str | None
    source_url: str | None
    dataset_pii_risk_level: str
    dataset_eligibility_status: str
    dataset_eligibility_reasons: tuple[str, ...]
    canonical_soql: str
    selected_columns: tuple[SelectedColumn, ...]
    rows: tuple[dict, ...]
    row_count: int
    data_updated_at: datetime | None
    evaluated_at: datetime


@dataclass(frozen=True)
class CheckResult:
    check: str
    passed: bool
    detail: str
    basis: str | None = None


@dataclass(frozen=True)
class DimensionResult:
    score: int
    checks: tuple[CheckResult, ...]


@dataclass(frozen=True)
class DataCutoffInfo:
    data_cutoff_at: datetime | None
    method: str | None
    column: str | None
    confidence: float | None
    basis: str
    inferred_at: datetime


@dataclass(frozen=True)
class RowPolicy:
    contains_individual_rows: bool
    aggregation_min_count: int | None
    pii_policy: str


@dataclass(frozen=True)
class QualityResult:
    score_total: int
    classification: str
    eligibility_status: str
    eligibility_reasons: tuple[str, ...]
    validator_version: str
    data_cutoff: DataCutoffInfo
    row_policy: RowPolicy
    dimensions: dict[str, DimensionResult]
    warnings_user: tuple[str, ...] = field(default_factory=tuple)


def _flatten_conditions(condition: object) -> list[object]:
    if condition is None:
        return []
    if isinstance(condition, BoolOp):
        result: list[object] = []
        for operand in condition.operands:
            result.extend(_flatten_conditions(operand))
        return result
    if isinstance(condition, Not):
        return _flatten_conditions(condition.inner)
    return [condition]


def _output_field_names(parsed: ParsedQuery | None) -> list[str]:
    """Nombres de columna tal como aparecen en las `rows` devueltas por Socrata.

    Un item con alias sale bajo ese alias; una columna simple sale con su
    propio nombre; una funcion sin alias no tiene una clave predecible y se
    omite (no participa en `null_ratio`/`columns_present`).
    """
    if parsed is None:
        return []
    names: list[str] = []
    for item in parsed.select_items:
        if item.alias:
            names.append(item.alias)
        elif isinstance(item.expr, Column):
            names.append(item.expr.name)
    return names


def _numeric_expected_columns(parsed: ParsedQuery | None) -> set[str]:
    """Columnas de SALIDA cuyo valor debe ser numerico.

    Para agregados (`avg`/`sum`/...) se valida el propio alias de salida --
    la columna cruda dentro de la funcion no viaja en `rows` cuando hay
    `GROUP BY` (Socrata ya la redujo al agregado). Para comparaciones
    numericas en WHERE/HAVING se valida la columna cruda solo si tambien
    aparece como salida (si no, no hay celda que verificar y el check no
    aplica sobre ella).
    """
    if parsed is None:
        return set()
    columns: set[str] = set()
    for item in parsed.select_items:
        if isinstance(item.expr, FuncCall) and item.expr.name in AGG_FUNCTIONS and item.alias:
            columns.add(item.alias)
    output_names = set(_output_field_names(parsed))
    for condition in _flatten_conditions(parsed.where) + _flatten_conditions(parsed.having):
        if isinstance(condition, Comparison) and condition.op in _NUMERIC_COMPARISON_OPS:
            left, right = condition.left, condition.right
            if isinstance(left, Column) and isinstance(right, Literal) and right.kind == "number":
                if left.name in output_names:
                    columns.add(left.name)
            if isinstance(right, Column) and isinstance(left, Literal) and left.kind == "number":
                if right.name in output_names:
                    columns.add(right.name)
    return columns


def _is_parseable_number(value: object) -> bool:
    if value is None:
        return False
    try:
        float(str(value).replace(",", ""))
    except ValueError:
        return False
    return True


def _score_types_coherent(parsed: ParsedQuery | None, rows: tuple[dict, ...]) -> CheckResult:
    numeric_columns = _numeric_expected_columns(parsed)
    if not numeric_columns or not rows:
        return CheckResult(
            "schema.types_coherent", passed=True, detail="Sin columnas de uso numérico que validar"
        )
    worst_ratio = 1.0
    worst_column = None
    for column in numeric_columns:
        values = [row.get(column) for row in rows if row.get(column) is not None]
        if not values:
            continue
        parseable = sum(1 for value in values if _is_parseable_number(value))
        ratio = parseable / len(values)
        if ratio < worst_ratio:
            worst_ratio = ratio
            worst_column = column
    passed = worst_ratio >= 0.95
    detail = (
        "Todas las columnas numéricas tienen valores parseables"
        if passed
        else f"'{worst_column}' tiene valores no numéricos en más del 5% de filas no nulas"
    )
    return CheckResult("schema.types_coherent", passed=passed, detail=detail)


def _score_columns_present(parsed: ParsedQuery | None, rows: tuple[dict, ...]) -> CheckResult:
    if parsed is None or not rows:
        return CheckResult(
            "schema.columns_present", passed=True, detail="Sin filas para verificar columnas"
        )
    expected = _output_field_names(parsed)
    missing = [name for name in expected if name not in rows[0]]
    passed = not missing
    detail = (
        f"{len(expected) - len(missing)}/{len(expected)} columnas presentes"
        if expected
        else "Sin columnas nombradas que verificar"
    )
    return CheckResult("schema.columns_present", passed=passed, detail=detail)


def _score_schema(parsed: ParsedQuery | None, draft: EvidenceDraft) -> DimensionResult:
    columns_present = _score_columns_present(parsed, draft.rows)
    types_coherent = _score_types_coherent(parsed, draft.rows)
    non_empty = CheckResult(
        "schema.non_empty_result",
        passed=draft.row_count > 0,
        detail=f"{draft.row_count} filas devueltas",
    )
    if draft.row_count == 0:
        return DimensionResult(score=0, checks=(columns_present, types_coherent, non_empty))
    score = (
        (40 if columns_present.passed else 0)
        + (40 if types_coherent.passed else 0)
        + (20 if non_empty.passed else 0)
    )
    return DimensionResult(score=score, checks=(columns_present, types_coherent, non_empty))


def _null_ratio(rows: tuple[dict, ...], columns: list[str]) -> float:
    if not rows or not columns:
        return 0.0
    total = 0
    empty = 0
    for row in rows:
        for column in columns:
            total += 1
            value = row.get(column)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                empty += 1
    return empty / total if total else 0.0


def _null_ratio_bucket_pct(ratio: float) -> int:
    if ratio <= 0.05:
        return 100
    if ratio <= 0.20:
        return 60
    if ratio <= 0.50:
        return 30
    return 0


def _score_completeness(
    parsed: ParsedQuery | None,
    draft: EvidenceDraft,
    placeholders_fixture: PlaceholdersFixture,
    placeholder_min_ratio: float,
) -> tuple[DimensionResult, list[str]]:
    known_columns_by_name = {column.field_name: column for column in draft.selected_columns}
    output_columns = _output_field_names(parsed) or list(known_columns_by_name)

    ratio = _null_ratio(draft.rows, output_columns)
    bucket_pct = _null_ratio_bucket_pct(ratio)
    null_ratio_points = round(60 * bucket_pct / 100)
    null_ratio_check = CheckResult(
        "completeness.null_ratio",
        passed=ratio <= 0.05,
        detail=f"{round(ratio * 100)}% de celdas vacías en las columnas citadas",
    )

    column_values = [
        ColumnValues(
            field_name=field_name,
            values=tuple(row.get(field_name) for row in draft.rows),
            known_placeholder_codes=known_columns_by_name[field_name].known_placeholder_codes
            if field_name in known_columns_by_name
            else (),
        )
        for field_name in output_columns
    ]
    detections = detect_placeholders(column_values, placeholders_fixture, placeholder_min_ratio)
    placeholder_points = 0 if detections else 40
    placeholder_check = CheckResult(
        "completeness.placeholder_values",
        passed=not detections,
        detail=(
            "; ".join(f"'{d.value}' en '{d.column}'" for d in detections)
            if detections
            else "Sin placeholders detectados"
        ),
    )

    warnings: list[str] = []
    if null_ratio_check.passed is False:
        worst_column = _worst_null_ratio_column(draft.rows, output_columns)
        warnings.append(null_ratio_warning(worst_column, ratio))
    for detection in detections:
        warnings.append(placeholder_warning(detection.column, detection.value))

    score = null_ratio_points + placeholder_points
    return DimensionResult(score=score, checks=(null_ratio_check, placeholder_check)), warnings


def _worst_null_ratio_column(rows: tuple[dict, ...], columns: list[str]) -> str:
    if not columns:
        return ""
    worst_column = columns[0]
    worst_ratio = -1.0
    for column in columns:
        ratio = _null_ratio(rows, [column])
        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_column = column
    return worst_column


def _months_between(later: datetime, earlier: datetime) -> int:
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if later.day < earlier.day:
        months -= 1
    return max(months, 0)


def _age_score(age_months: int | None) -> int:
    if age_months is None:
        return 15
    if age_months <= 12:
        return 100
    if age_months <= 24:
        return 70
    if age_months <= 48:
        return 40
    return 15


def _score_timeliness(draft: EvidenceDraft) -> tuple[DimensionResult, DataCutoffInfo, list[str]]:
    cutoff = infer_data_cutoff(list(draft.rows), draft.evaluated_at) if draft.rows else None
    if cutoff is not None:
        basis = "data_cutoff_at"
        base_date = cutoff.data_cutoff_at
    elif draft.data_updated_at is not None:
        basis = "data_updated_at_fallback"
        base_date = draft.data_updated_at
    else:
        basis = "unknown"
        base_date = None

    age_months = _months_between(draft.evaluated_at, base_date) if base_date else None
    score = _age_score(age_months)
    detail = (
        f"Corte {'estadístico' if basis == 'data_cutoff_at' else 'de actualización'}: "
        f"{base_date.date().isoformat()} (~{age_months} meses)"
        if base_date is not None
        else "Sin fecha de corte ni de actualización disponible"
    )
    check = CheckResult("timeliness.data_age", passed=score >= 70, detail=detail, basis=basis)

    data_cutoff_info = DataCutoffInfo(
        data_cutoff_at=base_date,
        method=cutoff.method if cutoff else None,
        column=cutoff.column if cutoff else None,
        confidence=cutoff.confidence if cutoff else None,
        basis=basis,
        inferred_at=draft.evaluated_at,
    )

    warnings = [timeliness_warning(basis, base_date)] if score <= 70 else []
    return DimensionResult(score=score, checks=(check,)), data_cutoff_info, warnings


def _score_traceability(
    draft: EvidenceDraft, query_reproducible: bool
) -> tuple[DimensionResult, bool]:
    source_complete = bool(draft.dataset_id and draft.dataset_name and draft.source_url)
    source_check = CheckResult(
        "traceability.source_complete",
        passed=source_complete,
        detail="" if source_complete else "Falta dataset_id, nombre o source_url",
    )
    query_check = CheckResult(
        "traceability.query_reproducible",
        passed=query_reproducible,
        detail="" if query_reproducible else "El SoQL registrado no es sintácticamente válido",
    )
    score = (60 if source_complete else 0) + (40 if query_reproducible else 0)
    return DimensionResult(score=score, checks=(source_check, query_check)), source_complete


def classify_score(score_total: int) -> str:
    if score_total >= 75:
        return "alta"
    if score_total >= 55:
        return "media"
    if score_total >= 35:
        return "baja"
    return "no_recomendada"


def _worst_eligibility(statuses: list[str]) -> str:
    return max(statuses, key=lambda status: _ELIGIBILITY_SEVERITY[status])


def _worst_pii_level(levels: list[str]) -> str:
    return max(levels, key=lambda level: _PII_SEVERITY[level])


def _count_alias(parsed: ParsedQuery | None) -> str | None:
    if parsed is None:
        return None
    for item in parsed.select_items:
        if isinstance(item.expr, FuncCall) and item.expr.name == "count":
            if item.alias:
                return item.alias
    return None


def _is_aggregated_query(parsed: ParsedQuery | None) -> bool:
    if parsed is None:
        return False
    return any(
        isinstance(item.expr, FuncCall) and item.expr.name in AGG_FUNCTIONS
        for item in parsed.select_items
    )


def _aggregation_min_count(parsed: ParsedQuery | None, rows: tuple[dict, ...]) -> int | None:
    alias = _count_alias(parsed)
    if alias is None or not rows:
        return None
    values: list[int] = []
    for row in rows:
        raw = row.get(alias)
        if raw is None:
            return None
        try:
            values.append(int(float(raw)))
        except (TypeError, ValueError):
            return None
    return min(values) if values else None


def validate_evidence(
    draft: EvidenceDraft,
    *,
    placeholders_fixture: PlaceholdersFixture | None = None,
    placeholder_min_ratio: float = DEFAULT_PLACEHOLDER_MIN_RATIO,
) -> QualityResult:
    if placeholders_fixture is None:
        placeholders_fixture = load_placeholder_patterns()

    try:
        parsed = parse_soql(draft.canonical_soql)
        query_reproducible = True
    except SoqlGuardError:
        parsed = None
        query_reproducible = False

    schema_dim = _score_schema(parsed, draft)
    completeness_dim, completeness_warnings = _score_completeness(
        parsed, draft, placeholders_fixture, placeholder_min_ratio
    )
    timeliness_dim, data_cutoff_info, timeliness_warnings = _score_timeliness(draft)
    traceability_dim, source_complete = _score_traceability(draft, query_reproducible)

    score_total = round(
        0.25 * schema_dim.score
        + 0.25 * completeness_dim.score
        + 0.30 * timeliness_dim.score
        + 0.20 * traceability_dim.score
    )
    classification = classify_score(score_total)
    if not source_complete:
        classification = "no_recomendada"
    if draft.row_count == 0:
        classification = "no_recomendada"

    column_eligibilities = [
        compute_column_eligibility(list(draft.dataset_eligibility_reasons), column.pii_risk_level)
        for column in draft.selected_columns
    ]
    reasons: list[str] = list(draft.dataset_eligibility_reasons)
    for result in column_eligibilities:
        for reason in result.eligibility_reasons:
            if reason not in reasons:
                reasons.append(reason)
    statuses = [draft.dataset_eligibility_status] + [
        result.eligibility_status for result in column_eligibilities
    ]
    eligibility_status = _worst_eligibility(statuses)

    is_medium_pii = "pii_medium_requires_aggregation" in reasons
    aggregation_min_count = _aggregation_min_count(parsed, draft.rows)
    if is_medium_pii and (
        aggregation_min_count is None or aggregation_min_count < MIN_AGGREGATION_COUNT
    ):
        eligibility_status = "blocked"
        if "pii_aggregation_insufficient" not in reasons:
            reasons.append("pii_aggregation_insufficient")

    warnings: list[str] = []
    if draft.row_count == 0:
        warnings.append(empty_result_warning())
    if not source_complete:
        warnings.append(missing_source_warning())
    if "publisher_unknown" in reasons or "publisher_private" in reasons:
        warnings.append(publisher_not_verified_warning())
    warnings.extend(completeness_warnings)
    warnings.extend(timeliness_warnings)
    if "pii_aggregation_insufficient" in reasons:
        warnings.append(pii_aggregation_insufficient_warning())

    row_policy = RowPolicy(
        contains_individual_rows=not _is_aggregated_query(parsed),
        aggregation_min_count=aggregation_min_count,
        pii_policy=_worst_pii_level(
            [draft.dataset_pii_risk_level] + [c.pii_risk_level for c in draft.selected_columns]
        ),
    )

    return QualityResult(
        score_total=score_total,
        classification=classification,
        eligibility_status=eligibility_status,
        eligibility_reasons=tuple(reasons),
        validator_version=VALIDATOR_VERSION,
        data_cutoff=data_cutoff_info,
        row_policy=row_policy,
        dimensions={
            "schema": schema_dim,
            "completeness": completeness_dim,
            "timeliness": timeliness_dim,
            "traceability": traceability_dim,
        },
        warnings_user=tuple(warnings),
    )
