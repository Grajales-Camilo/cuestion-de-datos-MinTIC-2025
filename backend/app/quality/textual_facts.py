"""Normalización, operaciones y hash puros para texto factual (T-615D, RF-210).

No persiste, no consulta PostgreSQL y no se integra con runtime, API o síntesis.
La canonicalización JSON se delega íntegramente a ``rfc8785``.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

import rfc8785
from pydantic import JsonValue

from app.quality.grounded_facts import (
    CategorySelectionParams,
    CategorySelectionRule,
    EmptyTextualFactOperationParams,
    ExtremumLabelParams,
    TextNormalizationProfile,
    TextualFactAlgorithmVersion,
    TextualFactOperation,
    TextualFactOperationParams,
    ValuePresenceParams,
)

TEXTUAL_SOURCE_HASH_PREFIX = "sha256-jcs-v1"
MAX_SOURCE_ROWS = 100
MAX_NORMALIZED_VALUES = 50
_ORDER_BY_PATTERN = re.compile(r"\border\s+by\b", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)


class TextualOperationError(ValueError):
    """Rechazo tipado y estable del constructor determinista."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class NormalizedText:
    raw: str
    display: str
    comparison: str


@dataclass(frozen=True, slots=True)
class TextualEvidence:
    dataset_id: str
    canonical_soql: str
    rows: tuple[Mapping[str, JsonValue], ...]
    validated_order_is_total: bool = False


@dataclass(frozen=True, slots=True)
class TextualFactSpec:
    operation: TextualFactOperation
    source_row_indexes: tuple[int, ...]
    columns: tuple[str, ...]
    operation_params: TextualFactOperationParams


@dataclass(frozen=True, slots=True)
class _EvaluatedValues:
    raw_values: tuple[str, ...]
    normalized_values: tuple[str, ...]
    display_value: str
    operation_params: TextualFactOperationParams


@dataclass(frozen=True, slots=True)
class TextualOperationResult:
    """Resultado puro; T-615D no crea todavía un ``TextualFact``."""

    operation: TextualFactOperation
    source_row_indexes: tuple[int, ...]
    columns: tuple[str, ...]
    raw_values: tuple[str, ...]
    normalized_values: tuple[str, ...]
    display_value: str
    normalization_profile: TextNormalizationProfile
    operation_params: TextualFactOperationParams
    algorithm_version: TextualFactAlgorithmVersion
    source_hash: str


def normalize_text_es_v1(value: str | None) -> NormalizedText:
    """Conserva fuente y deriva presentación y comparación por separado."""

    if value is None:
        raise TextualOperationError("textual_null_value", "el valor textual es null")
    if not isinstance(value, str):
        raise TextualOperationError(
            "textual_non_string_value",
            "el valor textual debe ser una cadena",
        )
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise TextualOperationError(
            "textual_invalid_unicode",
            "el valor textual no es Unicode UTF-8 válido",
        ) from exc

    nfc = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    display = " ".join(nfc.split())
    if not display:
        raise TextualOperationError(
            "textual_empty_value",
            "el valor textual queda vacío después de normalizar",
        )
    comparison = unicodedata.normalize("NFC", display.casefold())
    return NormalizedText(raw=value, display=display, comparison=comparison)


def canonicalize_jcs(value: JsonValue) -> bytes:
    """Serializa mediante RFC 8785/JCS; no implementa una variante local."""

    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, UnicodeEncodeError, TypeError) as exc:
        raise TextualOperationError(
            "textual_jcs_invalid",
            "el material no pertenece al dominio I-JSON admitido por RFC 8785",
        ) from exc


def evaluate_textual_operation(
    *,
    evidence: TextualEvidence,
    spec: TextualFactSpec,
) -> TextualOperationResult:
    """Evalúa operación y hash sin construir, verificar ni persistir hechos."""

    indexes = _canonical_indexes(spec.source_row_indexes, len(evidence.rows))
    columns = _validate_columns(spec.columns)
    selected_rows = tuple(evidence.rows[index] for index in indexes)
    _require_columns(selected_rows, columns)
    result = _execute_operation(
        evidence=evidence,
        operation=spec.operation,
        indexes=indexes,
        columns=columns,
        rows=selected_rows,
        params=spec.operation_params,
    )
    rows_subset = _canonical_rows_subset(selected_rows, columns)
    source_hash = _compute_source_hash(
        operation=spec.operation,
        evidence=evidence,
        indexes=indexes,
        columns=columns,
        rows_subset=rows_subset,
        result=result,
    )
    return TextualOperationResult(
        operation=spec.operation,
        source_row_indexes=indexes,
        columns=columns,
        raw_values=result.raw_values,
        normalized_values=result.normalized_values,
        display_value=result.display_value,
        normalization_profile=TextNormalizationProfile.TEXT_ES_V1,
        operation_params=result.operation_params,
        algorithm_version=TextualFactAlgorithmVersion.TEXTUAL_FACT_V1,
        source_hash=source_hash,
    )


def _canonical_indexes(indexes: tuple[int, ...], row_count: int) -> tuple[int, ...]:
    if not indexes:
        raise TextualOperationError(
            "textual_source_rows_empty",
            "source_row_indexes no puede estar vacío",
        )
    if len(indexes) > MAX_SOURCE_ROWS:
        raise TextualOperationError(
            "textual_cardinality_exceeded",
            f"un hecho textual admite máximo {MAX_SOURCE_ROWS} filas fuente",
        )
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indexes):
        raise TextualOperationError(
            "textual_invalid_row_index",
            "cada índice de fila debe ser un entero",
        )
    if len(set(indexes)) != len(indexes):
        raise TextualOperationError(
            "textual_duplicate_row_index",
            "source_row_indexes no admite duplicados",
        )
    canonical = tuple(sorted(indexes))
    if canonical[0] < 0 or canonical[-1] >= row_count:
        raise TextualOperationError(
            "textual_invalid_row_index",
            "source_row_indexes contiene una fila fuera de rango",
        )
    return canonical


def _validate_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    if not columns:
        raise TextualOperationError("textual_columns_empty", "columns no puede estar vacío")
    if any(not isinstance(column, str) or not column for column in columns):
        raise TextualOperationError(
            "textual_invalid_column",
            "cada columna debe ser una cadena no vacía",
        )
    if len(set(columns)) != len(columns):
        raise TextualOperationError(
            "textual_duplicate_column",
            "columns no admite duplicados",
        )
    return columns


def _require_columns(
    rows: tuple[Mapping[str, JsonValue], ...],
    columns: tuple[str, ...],
) -> None:
    for row in rows:
        missing = [column for column in columns if column not in row]
        if missing:
            raise TextualOperationError(
                "textual_missing_column",
                f"columnas ausentes en una fila fuente: {missing}",
            )


def _execute_operation(
    *,
    evidence: TextualEvidence,
    operation: TextualFactOperation,
    indexes: tuple[int, ...],
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, JsonValue], ...],
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    if operation is TextualFactOperation.DIRECT_TEXT:
        return _direct_text(indexes, columns, rows, params)
    if operation is TextualFactOperation.VALUE_PRESENCE:
        return _value_presence(columns, rows, params)
    if operation is TextualFactOperation.CATEGORY_SELECTION:
        return _category_selection(evidence, indexes, columns, rows, params)
    if operation is TextualFactOperation.ARGMAX_LABEL:
        return _extremum_label(operation, columns, rows, params)
    if operation is TextualFactOperation.ARGMIN_LABEL:
        return _extremum_label(operation, columns, rows, params)
    if operation is TextualFactOperation.CANONICAL_TEXT_SET:
        return _canonical_text_set(columns, rows, params)
    raise TextualOperationError("textual_unknown_operation", "operación textual desconocida")


def _require_empty_params(
    operation: TextualFactOperation,
    params: TextualFactOperationParams,
) -> EmptyTextualFactOperationParams:
    if not isinstance(params, EmptyTextualFactOperationParams):
        raise TextualOperationError(
            "textual_invalid_operation_params",
            f"operation_params no corresponde a {operation.value}",
        )
    return params


def _require_one_column(
    operation: TextualFactOperation,
    columns: tuple[str, ...],
) -> str:
    if len(columns) != 1:
        raise TextualOperationError(
            "textual_invalid_column_cardinality",
            f"{operation.value} requiere exactamente una columna",
        )
    return columns[0]


def _normalized_cell(value: JsonValue) -> NormalizedText:
    if value is None:
        raise TextualOperationError("textual_null_value", "la celda textual es null")
    if not isinstance(value, str):
        raise TextualOperationError(
            "textual_non_string_value",
            "la celda textual no contiene una cadena",
        )
    return normalize_text_es_v1(value)


def _normalized_non_null_values(
    rows: tuple[Mapping[str, JsonValue], ...],
    column: str,
) -> tuple[NormalizedText, ...]:
    values: list[NormalizedText] = []
    for row in rows:
        value = row[column]
        if value is None:
            continue
        values.append(_normalized_cell(value))
    if not values:
        raise TextualOperationError(
            "textual_no_values",
            "no quedan valores textuales después de eliminar null",
        )
    return tuple(values)


def _representatives(
    values: tuple[NormalizedText, ...],
) -> Mapping[str, NormalizedText]:
    representatives: dict[str, NormalizedText] = {}
    for value in values:
        current = representatives.get(value.comparison)
        if current is None or _raw_representative_key(value.raw) < _raw_representative_key(
            current.raw
        ):
            representatives[value.comparison] = value
    return MappingProxyType(representatives)


def _raw_representative_key(value: str) -> tuple[bytes, bytes]:
    """Ordena por bruto tras NFC y desempata por los bytes fuente exactos."""

    return (unicodedata.normalize("NFC", value).encode("utf-8"), value.encode("utf-8"))


def _single_result(
    value: NormalizedText,
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    return _EvaluatedValues(
        raw_values=(value.raw,),
        normalized_values=(value.comparison,),
        display_value=value.display,
        operation_params=params,
    )


def _direct_text(
    indexes: tuple[int, ...],
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, JsonValue], ...],
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    canonical_params = _require_empty_params(TextualFactOperation.DIRECT_TEXT, params)
    column = _require_one_column(TextualFactOperation.DIRECT_TEXT, columns)
    if len(indexes) != 1:
        raise TextualOperationError(
            "textual_invalid_row_cardinality",
            "direct_text requiere exactamente una fila",
        )
    return _single_result(_normalized_cell(rows[0][column]), canonical_params)


def _value_presence(
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, JsonValue], ...],
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    column = _require_one_column(TextualFactOperation.VALUE_PRESENCE, columns)
    if not isinstance(params, ValuePresenceParams):
        raise TextualOperationError(
            "textual_invalid_operation_params",
            "operation_params no corresponde a value_presence",
        )
    target = normalize_text_es_v1(params.target_raw)
    if params.target_normalized != target.comparison:
        raise TextualOperationError(
            "textual_invalid_target",
            "target_normalized no corresponde a target_raw bajo text-es-v1",
        )
    values = _normalized_non_null_values(rows, column)
    representatives = _representatives(values)
    representative = representatives.get(target.comparison)
    if representative is None:
        raise TextualOperationError(
            "textual_value_absent",
            "el valor objetivo no está presente en las filas referenciadas",
        )
    canonical_params = ValuePresenceParams(
        target_raw=target.raw,
        target_normalized=target.comparison,
    )
    return _single_result(representative, canonical_params)


def _category_selection(
    evidence: TextualEvidence,
    indexes: tuple[int, ...],
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, JsonValue], ...],
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    column = _require_one_column(TextualFactOperation.CATEGORY_SELECTION, columns)
    if not isinstance(params, CategorySelectionParams):
        raise TextualOperationError(
            "textual_invalid_operation_params",
            "operation_params no corresponde a category_selection",
        )
    values = _normalized_non_null_values(rows, column)
    if params.rule is CategorySelectionRule.UNIQUE_NORMALIZED_VALUE:
        representatives = _representatives(values)
        if len(representatives) != 1:
            raise TextualOperationError(
                "textual_ambiguous_category",
                "unique_normalized_value requiere una única categoría distinta",
            )
        _normalized, representative = next(iter(representatives.items()))
        return _single_result(representative, params)

    if len(indexes) != 1:
        raise TextualOperationError(
            "textual_invalid_row_cardinality",
            "first_by_validated_order requiere exactamente una fila ganadora",
        )
    if (
        not evidence.validated_order_is_total
        or _ORDER_BY_PATTERN.search(evidence.canonical_soql) is None
        or _LIMIT_PATTERN.search(evidence.canonical_soql) is None
    ):
        raise TextualOperationError(
            "textual_order_not_validated",
            "first_by_validated_order exige ORDER BY total y LIMIT validados",
        )
    return _single_result(values[0], params)


def _extremum_label(
    operation: TextualFactOperation,
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, JsonValue], ...],
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    if not isinstance(params, ExtremumLabelParams):
        raise TextualOperationError(
            "textual_invalid_operation_params",
            f"operation_params no corresponde a {operation.value}",
        )
    expected_columns = (params.label_column, params.metric_column)
    if columns != expected_columns:
        raise TextualOperationError(
            "textual_invalid_extremum_columns",
            "columns debe corresponder a label_column y metric_column",
        )

    candidates: list[tuple[Decimal, NormalizedText]] = []
    for row in rows:
        label = _normalized_cell(row[params.label_column])
        metric = _finite_decimal(row[params.metric_column])
        candidates.append((metric, label))
    metrics = [candidate[0] for candidate in candidates]
    extremum = max(metrics) if operation is TextualFactOperation.ARGMAX_LABEL else min(metrics)
    winners = [label for metric, label in candidates if metric == extremum]
    if len(winners) != 1:
        raise TextualOperationError(
            "textual_extremum_tie",
            f"{operation.value} rechaza empates por tie_policy=reject",
        )
    return _single_result(winners[0], params)


def _finite_decimal(value: JsonValue) -> Decimal:
    if value is None or isinstance(value, bool):
        raise TextualOperationError(
            "textual_invalid_metric",
            "la métrica debe ser numérica y finita",
        )
    try:
        metric = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TextualOperationError(
            "textual_invalid_metric",
            "la métrica debe ser numérica y finita",
        ) from exc
    if not metric.is_finite():
        raise TextualOperationError(
            "textual_invalid_metric",
            "la métrica debe ser numérica y finita",
        )
    return metric


def _canonical_text_set(
    columns: tuple[str, ...],
    rows: tuple[Mapping[str, JsonValue], ...],
    params: TextualFactOperationParams,
) -> _EvaluatedValues:
    canonical_params = _require_empty_params(TextualFactOperation.CANONICAL_TEXT_SET, params)
    column = _require_one_column(TextualFactOperation.CANONICAL_TEXT_SET, columns)
    representatives = _representatives(_normalized_non_null_values(rows, column))
    if len(representatives) > MAX_NORMALIZED_VALUES:
        raise TextualOperationError(
            "textual_cardinality_exceeded",
            f"un hecho textual admite máximo {MAX_NORMALIZED_VALUES} valores distintos",
        )
    ordered = sorted(
        representatives.items(),
        key=lambda item: (item[0], _raw_representative_key(item[1].raw)),
    )
    normalized_values = tuple(normalized for normalized, _representative in ordered)
    raw_values = tuple(representative.raw for _normalized, representative in ordered)
    display_values = tuple(representative.display for _normalized, representative in ordered)
    return _EvaluatedValues(
        raw_values=raw_values,
        normalized_values=normalized_values,
        display_value="; ".join(display_values),
        operation_params=canonical_params,
    )


def _canonical_rows_subset(
    rows: tuple[Mapping[str, JsonValue], ...],
    columns: tuple[str, ...],
) -> list[dict[str, JsonValue]]:
    return [{column: _canonical_json_value(row[column]) for column in columns} for row in rows]


def _canonical_json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, float) and not math.isfinite(value):
        raise TextualOperationError(
            "textual_jcs_invalid",
            "JCS no admite números no finitos",
        )
    if isinstance(value, list):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical_json_value(item) for key, item in value.items()}
    return value


def _compute_source_hash(
    *,
    operation: TextualFactOperation,
    evidence: TextualEvidence,
    indexes: tuple[int, ...],
    columns: tuple[str, ...],
    rows_subset: list[dict[str, JsonValue]],
    result: _EvaluatedValues,
) -> str:
    payload: dict[str, JsonValue] = {
        "algorithm_version": TextualFactAlgorithmVersion.TEXTUAL_FACT_V1.value,
        "operation": operation.value,
        "normalization_profile": TextNormalizationProfile.TEXT_ES_V1.value,
        "dataset_id": evidence.dataset_id,
        "canonical_soql": evidence.canonical_soql,
        "source_row_indexes": list(indexes),
        "rows_subset_canonical": rows_subset,
        "columns_used": list(columns),
        "raw_values": list(result.raw_values),
        "normalized_values": list(result.normalized_values),
        "display_value": result.display_value,
        "operation_params": result.operation_params.model_dump(mode="json"),
    }
    digest = hashlib.sha256(canonicalize_jcs(payload)).hexdigest()
    return f"{TEXTUAL_SOURCE_HASH_PREFIX}:{digest}"
