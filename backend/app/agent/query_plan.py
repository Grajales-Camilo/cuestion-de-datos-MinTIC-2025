"""Modelos cerrados para el plan de consulta determinista.

Este módulo no conoce LangGraph, proveedores LLM, Socrata ni PostgreSQL. Su
responsabilidad termina en representar una selección estructurada, comprobar
referencias contra opciones enumeradas y producir una identidad canónica.

Satisface RF-201 y RF-208 al crear una frontera tipada y reproducible entre la
interpretación de la pregunta y las etapas deterministas posteriores.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.quality.grounded_facts import (
    CategorySelectionRule,
    TextualFactOperation,
    TextualFactTiePolicy,
)

PLAN_SCHEMA_VERSION = "query-plan.v1"
PLAN_HASH_ALGORITHM = "sha256"
MAX_CANDIDATES = 10
MAX_COLUMNS_PER_CANDIDATE = 250
MAX_DIMENSIONS = 8
MAX_METRICS = 8
MAX_FILTERS = 16
MAX_ORDER_ITEMS = 8
MAX_QUERY_LIMIT = 5000
MAX_TEXTUAL_REQUESTS = 8
MAX_TEXTUAL_SOURCE_ROWS = 100


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnDataType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    LOCATION = "location"
    UNKNOWN = "unknown"


class PiiRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    BLOCKED = "blocked"


class QueryOperation(StrEnum):
    LOOKUP = "lookup"
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    BETWEEN = "between"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ScalarType(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class SortTargetKind(StrEnum):
    DIMENSION = "dimension"
    METRIC = "metric"


class SelectionOrigin(StrEnum):
    USER = "user"
    INTENT = "intent"
    RETRIEVAL = "retrieval"
    SCHEMA = "schema"
    EXPLORATION = "exploration"
    POLICY = "policy"


class ColumnOption(_ClosedModel):
    index: int = Field(ge=0)
    field_name: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=500)
    data_type: ColumnDataType
    pii_risk_level: PiiRiskLevel


class DatasetOption(_ClosedModel):
    index: int = Field(ge=0)
    dataset_id: str = Field(pattern=r"^[a-z0-9]{4}-[a-z0-9]{4}$")
    title: str = Field(min_length=1, max_length=1000)
    publisher: str = Field(min_length=1, max_length=1000)
    columns: tuple[ColumnOption, ...] = Field(min_length=1, max_length=MAX_COLUMNS_PER_CANDIDATE)

    @model_validator(mode="after")
    def _column_indexes_are_contiguous(self) -> Self:
        indexes = [column.index for column in self.columns]
        if indexes != list(range(len(indexes))):
            raise ValueError("los índices de columnas deben ser únicos, contiguos y empezar en 0")
        return self


class EnumeratedPlanningContext(_ClosedModel):
    """Opciones reales que un LLM puede seleccionar únicamente por índice."""

    version: Literal["planning-context.v1"] = "planning-context.v1"
    candidates: tuple[DatasetOption, ...] = Field(min_length=1, max_length=MAX_CANDIDATES)

    @model_validator(mode="after")
    def _candidate_indexes_are_contiguous(self) -> Self:
        indexes = [candidate.index for candidate in self.candidates]
        if indexes != list(range(len(indexes))):
            raise ValueError("los índices de candidatos deben ser únicos, contiguos y empezar en 0")
        return self

    def validate_references(self, plan: QueryPlan) -> None:
        """Rechaza índices inventados sin hacer validación semántica de fase 1B."""

        if plan.dataset_index >= len(self.candidates):
            raise ValueError(f"dataset_index inexistente: {plan.dataset_index}")
        candidate = self.candidates[plan.dataset_index]
        available = len(candidate.columns)
        for reference in plan.column_references():
            if reference.column_index >= available:
                raise ValueError(
                    "column_index inexistente para el candidato "
                    f"{plan.dataset_index}: {reference.column_index}"
                )


class SelectionProvenance(_ClosedModel):
    origin: SelectionOrigin
    source_text: str | None = Field(default=None, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ColumnReference(_ClosedModel):
    column_index: int = Field(ge=0)


class DimensionSelection(_ClosedModel):
    column: ColumnReference
    provenance: SelectionProvenance


class MetricSelection(_ClosedModel):
    operation: QueryOperation
    column: ColumnReference | None = None
    provenance: SelectionProvenance

    @model_validator(mode="after")
    def _operation_has_the_expected_column_shape(self) -> Self:
        if self.operation is QueryOperation.COUNT and self.column is not None:
            raise ValueError("count representa exclusivamente count(*) y no acepta columna")
        if (
            self.operation
            in {
                QueryOperation.SUM,
                QueryOperation.AVG,
                QueryOperation.MIN,
                QueryOperation.MAX,
            }
            and self.column is None
        ):
            raise ValueError(f"{self.operation.value} requiere una referencia de columna")
        if self.operation is QueryOperation.LOOKUP:
            raise ValueError("lookup es una operación del plan, no una métrica")
        return self


class ScalarValue(_ClosedModel):
    """Literal tipado en forma textual; el renderer decidirá su serialización."""

    type: ScalarType
    value: str = Field(min_length=1, max_length=2000)


class FilterSelection(_ClosedModel):
    column: ColumnReference
    operator: FilterOperator
    values: tuple[ScalarValue, ...] = Field(default_factory=tuple, max_length=100)
    provenance: SelectionProvenance

    @model_validator(mode="after")
    def _operator_has_the_expected_arity(self) -> Self:
        arity = len(self.values)
        if self.operator in {FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL}:
            valid = arity == 0
        elif self.operator is FilterOperator.BETWEEN:
            valid = arity == 2
        elif self.operator is FilterOperator.IN:
            valid = arity >= 1
        else:
            valid = arity == 1
        if not valid:
            raise ValueError(
                f"el operador {self.operator.value} recibió {arity} valores con aridad inválida"
            )
        return self


class SortSelection(_ClosedModel):
    target_kind: SortTargetKind
    target_index: int = Field(ge=0)
    direction: SortDirection = SortDirection.ASC


class _TextualSelection(_ClosedModel):
    source_row_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(
        min_length=1,
        max_length=MAX_TEXTUAL_SOURCE_ROWS,
    )

    @model_validator(mode="after")
    def _source_rows_are_unique(self) -> Self:
        if len(set(self.source_row_indexes)) != len(self.source_row_indexes):
            raise ValueError("source_row_indexes no admite duplicados")
        return self


class DirectTextSelection(_TextualSelection):
    operation: Literal[TextualFactOperation.DIRECT_TEXT] = TextualFactOperation.DIRECT_TEXT
    column: ColumnReference


class ValuePresenceSelection(_TextualSelection):
    operation: Literal[TextualFactOperation.VALUE_PRESENCE] = TextualFactOperation.VALUE_PRESENCE
    column: ColumnReference
    target_raw: str = Field(min_length=1, max_length=2000)


class CategorySelection(_TextualSelection):
    operation: Literal[TextualFactOperation.CATEGORY_SELECTION] = (
        TextualFactOperation.CATEGORY_SELECTION
    )
    column: ColumnReference
    rule: CategorySelectionRule


class ArgmaxLabelSelection(_TextualSelection):
    operation: Literal[TextualFactOperation.ARGMAX_LABEL] = TextualFactOperation.ARGMAX_LABEL
    label_column: ColumnReference
    metric_column: ColumnReference
    tie_policy: Literal[TextualFactTiePolicy.REJECT] = TextualFactTiePolicy.REJECT

    @model_validator(mode="after")
    def _columns_are_distinct(self) -> Self:
        if self.label_column == self.metric_column:
            raise ValueError("label_column y metric_column deben ser diferentes")
        return self


class ArgminLabelSelection(_TextualSelection):
    operation: Literal[TextualFactOperation.ARGMIN_LABEL] = TextualFactOperation.ARGMIN_LABEL
    label_column: ColumnReference
    metric_column: ColumnReference
    tie_policy: Literal[TextualFactTiePolicy.REJECT] = TextualFactTiePolicy.REJECT

    @model_validator(mode="after")
    def _columns_are_distinct(self) -> Self:
        if self.label_column == self.metric_column:
            raise ValueError("label_column y metric_column deben ser diferentes")
        return self


class CanonicalTextSetSelection(_TextualSelection):
    operation: Literal[TextualFactOperation.CANONICAL_TEXT_SET] = (
        TextualFactOperation.CANONICAL_TEXT_SET
    )
    column: ColumnReference


TextualSelection = Annotated[
    DirectTextSelection
    | ValuePresenceSelection
    | CategorySelection
    | ArgmaxLabelSelection
    | ArgminLabelSelection
    | CanonicalTextSetSelection,
    Field(discriminator="operation"),
]


class QueryPlan(_ClosedModel):
    """Selección estructurada independiente de SoQL y de IDs inventables."""

    version: Literal["query-plan.v1"] = PLAN_SCHEMA_VERSION
    dataset_index: int = Field(ge=0)
    operation: QueryOperation
    dimensions: tuple[DimensionSelection, ...] = Field(
        default_factory=tuple, max_length=MAX_DIMENSIONS
    )
    metrics: tuple[MetricSelection, ...] = Field(default_factory=tuple, max_length=MAX_METRICS)
    filters: tuple[FilterSelection, ...] = Field(default_factory=tuple, max_length=MAX_FILTERS)
    order_by: tuple[SortSelection, ...] = Field(default_factory=tuple, max_length=MAX_ORDER_ITEMS)
    textual_requests: tuple[TextualSelection, ...] = Field(
        default_factory=tuple,
        max_length=MAX_TEXTUAL_REQUESTS,
    )
    limit: int = Field(default=100, ge=1, le=MAX_QUERY_LIMIT)
    needs_value_exploration: bool = False
    purpose: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _plan_shape_is_coherent(self) -> Self:
        if self.operation is QueryOperation.LOOKUP:
            if not self.dimensions:
                raise ValueError("lookup requiere al menos una columna en dimensions")
            if self.metrics:
                raise ValueError("lookup no acepta métricas agregadas")
        else:
            if not self.metrics:
                raise ValueError("un plan agregado requiere al menos una métrica")
            if any(metric.operation is not self.operation for metric in self.metrics):
                raise ValueError(
                    "todas las métricas deben coincidir con operation en query-plan.v1"
                )

        for item in self.order_by:
            size = (
                len(self.dimensions)
                if item.target_kind is SortTargetKind.DIMENSION
                else len(self.metrics)
            )
            if item.target_index >= size:
                raise ValueError(
                    f"order_by referencia {item.target_kind.value}[{item.target_index}] inexistente"
                )
        return self

    def column_references(self) -> tuple[ColumnReference, ...]:
        references = [dimension.column for dimension in self.dimensions]
        references.extend(metric.column for metric in self.metrics if metric.column is not None)
        references.extend(item.column for item in self.filters)
        for request in self.textual_requests:
            if isinstance(request, (ArgmaxLabelSelection, ArgminLabelSelection)):
                references.extend((request.label_column, request.metric_column))
            else:
                references.append(request.column)
        return tuple(references)

    def canonical_json(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=False)
        if not self.textual_requests:
            payload.pop("textual_requests")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def plan_hash(self) -> str:
        prefix = f"{PLAN_HASH_ALGORITHM}:{PLAN_SCHEMA_VERSION}:".encode()
        material = prefix + self.canonical_json().encode("utf-8")
        return hashlib.sha256(material).hexdigest()
