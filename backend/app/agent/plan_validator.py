"""Validación pura de QueryPlan contra opciones y esquema observados.

Satisface RF-201, RF-208 y RF-401: ninguna consulta puede renderizarse antes
de resolver sus referencias y aplicar tipos, elegibilidad y privacidad.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.agent.query_plan import (
    ColumnDataType,
    EligibilityStatus,
    EnumeratedPlanningContext,
    FilterOperator,
    PiiRiskLevel,
    QueryOperation,
    QueryPlan,
    ScalarType,
    SortDirection,
    SortTargetKind,
)


class _ValidatedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlanValidationCode(StrEnum):
    UNKNOWN_REFERENCE = "UNKNOWN_REFERENCE"
    DATASET_MISMATCH = "DATASET_MISMATCH"
    DATASET_NOT_ELIGIBLE = "DATASET_NOT_ELIGIBLE"
    TYPE_MISMATCH = "TYPE_MISMATCH"
    INVALID_LITERAL = "INVALID_LITERAL"
    PII_BLOCKED = "PII_BLOCKED"
    PII_REQUIRES_AGGREGATION = "PII_REQUIRES_AGGREGATION"


class PlanValidationError(ValueError):
    def __init__(self, code: PlanValidationCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class ObservedColumn(_ValidatedModel):
    field_name: str
    data_type: ColumnDataType
    pii_risk_level: PiiRiskLevel


class ObservedDatasetSchema(_ValidatedModel):
    dataset_id: str
    eligibility_status: EligibilityStatus
    pii_risk_level: PiiRiskLevel
    columns: tuple[ObservedColumn, ...]


class ValidatedDimension(_ValidatedModel):
    field_name: str
    data_type: ColumnDataType


class ValidatedMetric(_ValidatedModel):
    operation: QueryOperation
    field_name: str | None
    data_type: ColumnDataType | None


class ValidatedScalar(_ValidatedModel):
    type: ScalarType
    value: str


class ValidatedFilter(_ValidatedModel):
    field_name: str
    data_type: ColumnDataType
    operator: FilterOperator
    values: tuple[ValidatedScalar, ...]


class ValidatedSort(_ValidatedModel):
    target_kind: SortTargetKind
    target_index: int
    direction: SortDirection


class ValidatedQueryPlan(_ValidatedModel):
    version: Literal["validated-query-plan.v1"] = "validated-query-plan.v1"
    source_plan_hash: str
    dataset_id: str
    operation: QueryOperation
    dimensions: tuple[ValidatedDimension, ...]
    metrics: tuple[ValidatedMetric, ...]
    filters: tuple[ValidatedFilter, ...]
    order_by: tuple[ValidatedSort, ...]
    limit: int
    include_group_count: bool
    purpose: str


_NUMERIC_TYPES = {ColumnDataType.NUMBER, ColumnDataType.INTEGER}
_ORDERED_TYPES = _NUMERIC_TYPES | {ColumnDataType.DATE, ColumnDataType.DATETIME}
_SCALAR_TO_COLUMN = {
    ScalarType.TEXT: {ColumnDataType.TEXT, ColumnDataType.UNKNOWN},
    ScalarType.NUMBER: _NUMERIC_TYPES,
    ScalarType.INTEGER: _NUMERIC_TYPES,
    ScalarType.BOOLEAN: {ColumnDataType.BOOLEAN},
    ScalarType.DATE: {ColumnDataType.DATE, ColumnDataType.DATETIME},
    ScalarType.DATETIME: {ColumnDataType.DATETIME},
}


def _raise(code: PlanValidationCode, message: str) -> None:
    raise PlanValidationError(code, message)


def _column(schema: ObservedDatasetSchema, index: int) -> ObservedColumn:
    try:
        return schema.columns[index]
    except IndexError:
        _raise(PlanValidationCode.UNKNOWN_REFERENCE, f"column_index inexistente: {index}")


def _validate_metric_type(operation: QueryOperation, column: ObservedColumn | None) -> None:
    if operation is QueryOperation.COUNT:
        return
    assert column is not None
    allowed = (
        _NUMERIC_TYPES
        if operation in {QueryOperation.SUM, QueryOperation.AVG}
        else _ORDERED_TYPES
    )
    if column.data_type not in allowed:
        _raise(
            PlanValidationCode.TYPE_MISMATCH,
            f"{operation.value} no admite la columna {column.field_name!r} "
            f"de tipo {column.data_type.value}",
        )


def _validate_scalar_literal(value_type: ScalarType, value: str) -> None:
    try:
        if value_type is ScalarType.NUMBER:
            parsed = Decimal(value)
            if not parsed.is_finite():
                raise ValueError
        elif value_type is ScalarType.INTEGER:
            parsed = Decimal(value)
            if not parsed.is_finite() or parsed != parsed.to_integral_value():
                raise ValueError
        elif value_type is ScalarType.BOOLEAN:
            if value.casefold() not in {"true", "false"}:
                raise ValueError
        elif value_type is ScalarType.DATE:
            date.fromisoformat(value)
        elif value_type is ScalarType.DATETIME:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (InvalidOperation, ValueError) as exc:
        labels = {
            ScalarType.NUMBER: "numérico",
            ScalarType.INTEGER: "entero",
            ScalarType.BOOLEAN: "booleano",
            ScalarType.DATE: "de fecha",
            ScalarType.DATETIME: "datetime",
        }
        _raise(
            PlanValidationCode.INVALID_LITERAL,
            f"literal {labels[value_type]} inválido: {value!r}",
        )
        raise AssertionError("_raise siempre lanza") from exc


def validate_query_plan(
    plan: QueryPlan,
    *,
    context: EnumeratedPlanningContext,
    schema: ObservedDatasetSchema,
) -> ValidatedQueryPlan:
    """Resuelve índices y aplica las políticas previas al renderer."""

    try:
        context.validate_references(plan)
    except ValueError as exc:
        _raise(PlanValidationCode.UNKNOWN_REFERENCE, str(exc))

    candidate = context.candidates[plan.dataset_index]
    if candidate.dataset_id != schema.dataset_id:
        _raise(
            PlanValidationCode.DATASET_MISMATCH,
            f"el esquema {schema.dataset_id!r} no corresponde al "
            f"candidato {candidate.dataset_id!r}",
        )
    if schema.eligibility_status is not EligibilityStatus.ELIGIBLE:
        _raise(
            PlanValidationCode.DATASET_NOT_ELIGIBLE,
            f"el dataset tiene elegibilidad {schema.eligibility_status.value}",
        )
    if len(schema.columns) != len(candidate.columns) or any(
        observed.field_name != option.field_name
        for observed, option in zip(schema.columns, candidate.columns, strict=True)
    ):
        _raise(
            PlanValidationCode.DATASET_MISMATCH,
            "el esquema observado difiere del contexto enumerado",
        )

    dimensions = tuple(
        ValidatedDimension(
            field_name=(column := _column(schema, item.column.column_index)).field_name,
            data_type=column.data_type,
        )
        for item in plan.dimensions
    )
    metrics: list[ValidatedMetric] = []
    for item in plan.metrics:
        column = _column(schema, item.column.column_index) if item.column is not None else None
        _validate_metric_type(item.operation, column)
        metrics.append(
            ValidatedMetric(
                operation=item.operation,
                field_name=column.field_name if column else None,
                data_type=column.data_type if column else None,
            )
        )

    filters: list[ValidatedFilter] = []
    selected_columns = [
        *(_column(schema, item.column.column_index) for item in plan.dimensions),
        *(
            _column(schema, item.column.column_index)
            for item in plan.metrics
            if item.column is not None
        ),
        *(_column(schema, item.column.column_index) for item in plan.filters),
    ]
    for item in plan.filters:
        column = _column(schema, item.column.column_index)
        for value in item.values:
            if column.data_type not in _SCALAR_TO_COLUMN[value.type]:
                _raise(
                    PlanValidationCode.TYPE_MISMATCH,
                    f"literal {value.type.value} incompatible con {column.field_name!r}",
                )
            _validate_scalar_literal(value.type, value.value)
        filters.append(
            ValidatedFilter(
                field_name=column.field_name,
                data_type=column.data_type,
                operator=item.operator,
                values=tuple(
                    ValidatedScalar(type=value.type, value=value.value) for value in item.values
                ),
            )
        )

    risks = {schema.pii_risk_level, *(column.pii_risk_level for column in selected_columns)}
    if risks & {PiiRiskLevel.HIGH, PiiRiskLevel.UNKNOWN}:
        _raise(PlanValidationCode.PII_BLOCKED, "el plan usa columnas PII high o unknown")
    medium_pii = PiiRiskLevel.MEDIUM in risks
    if medium_pii and plan.operation is QueryOperation.LOOKUP:
        _raise(
            PlanValidationCode.PII_REQUIRES_AGGREGATION,
            "las columnas PII medium requieren agregación y tamaño de grupo",
        )

    return ValidatedQueryPlan(
        source_plan_hash=plan.plan_hash(),
        dataset_id=schema.dataset_id,
        operation=plan.operation,
        dimensions=dimensions,
        metrics=tuple(metrics),
        filters=tuple(filters),
        order_by=tuple(
            ValidatedSort(
                target_kind=item.target_kind,
                target_index=item.target_index,
                direction=item.direction,
            )
            for item in plan.order_by
        ),
        limit=plan.limit,
        include_group_count=medium_pii,
        purpose=plan.purpose,
    )
