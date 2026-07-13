"""Contratos estructurados y acotados para la participación del LLM."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.query_plan import (
    ColumnDataType,
    ColumnReference,
    DimensionSelection,
    EnumeratedPlanningContext,
    FilterOperator,
    FilterSelection,
    MetricSelection,
    QueryOperation,
    QueryPlan,
    ScalarType,
    ScalarValue,
    SelectionOrigin,
    SelectionProvenance,
    SortDirection,
    SortSelection,
    SortTargetKind,
)
from app.quality.claims import BuiltClaim, find_orphan_figures


class _LLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntentExtraction(_LLMOutput):
    topic: str = Field(min_length=1, max_length=300)
    operation: QueryOperation
    territory: str | None = Field(default=None, max_length=200)
    entity: str | None = Field(default=None, max_length=300)
    period: str | None = Field(default=None, max_length=100)
    administrative_terms: tuple[str, ...] = Field(default_factory=tuple, max_length=8)


class CandidateRanking(_LLMOutput):
    ranked_candidate_indexes: tuple[int, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def _indexes_are_unique(self) -> CandidateRanking:
        if len(set(self.ranked_candidate_indexes)) != len(self.ranked_candidate_indexes):
            raise ValueError("ranked_candidate_indexes no admite duplicados")
        if any(index < 0 for index in self.ranked_candidate_indexes):
            raise ValueError("los índices de candidatos deben ser no negativos")
        return self


class MetricChoice(_LLMOutput):
    operation: QueryOperation
    column_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _shape(self) -> MetricChoice:
        if self.operation is QueryOperation.COUNT and self.column_index is not None:
            raise ValueError("count representa count(*) y no selecciona columna")
        requires_column = self.operation not in {
            QueryOperation.COUNT,
            QueryOperation.LOOKUP,
        }
        if requires_column and self.column_index is None:
            raise ValueError(f"{self.operation.value} requiere column_index")
        if self.operation is QueryOperation.LOOKUP:
            raise ValueError("lookup se representa mediante dimension_column_indexes")
        return self


class FilterChoice(_LLMOutput):
    column_index: int = Field(ge=0)
    operator: FilterOperator
    value_type: ScalarType | None = None
    values: tuple[str, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def _shape(self) -> FilterChoice:
        if self.operator in {FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL}:
            if self.value_type is not None or self.values:
                raise ValueError("los filtros null no aceptan tipo ni valores")
        elif self.value_type is None:
            raise ValueError("un filtro con valores requiere value_type")
        return self


class SortChoice(_LLMOutput):
    target_kind: SortTargetKind
    target_index: int = Field(ge=0)
    direction: SortDirection = SortDirection.ASC


class EnumeratedPlanSelection(_LLMOutput):
    dataset_index: int = Field(ge=0)
    operation: QueryOperation
    dimension_column_indexes: tuple[int, ...] = Field(default_factory=tuple, max_length=8)
    metrics: tuple[MetricChoice, ...] = Field(default_factory=tuple, max_length=8)
    filters: tuple[FilterChoice, ...] = Field(default_factory=tuple, max_length=16)
    order_by: tuple[SortChoice, ...] = Field(default_factory=tuple, max_length=8)
    limit: int = Field(default=100, ge=1, le=5000)
    needs_value_exploration: bool = False


class GroundedSynthesis(_LLMOutput):
    answer: str = Field(min_length=1, max_length=8_000)
    cited_claim_indexes: tuple[int, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def _unique_claims(self) -> GroundedSynthesis:
        if len(set(self.cited_claim_indexes)) != len(self.cited_claim_indexes):
            raise ValueError("cited_claim_indexes no admite duplicados")
        if any(index < 0 for index in self.cited_claim_indexes):
            raise ValueError("los índices de claims deben ser no negativos")
        return self


def validate_candidate_ranking(
    ranking: CandidateRanking, context: EnumeratedPlanningContext
) -> None:
    available = len(context.candidates)
    invalid = [index for index in ranking.ranked_candidate_indexes if index >= available]
    if invalid:
        raise ValueError(f"ranking contiene índices inexistentes: {invalid}")


def validate_grounded_synthesis(
    synthesis: GroundedSynthesis,
    claims: tuple[BuiltClaim, ...],
) -> None:
    invalid = [index for index in synthesis.cited_claim_indexes if index >= len(claims)]
    if invalid:
        raise ValueError(f"síntesis cita claims inexistentes: {invalid}")
    accepted = tuple(claims[index].display_value for index in synthesis.cited_claim_indexes)
    orphan_figures = find_orphan_figures(synthesis.answer, accepted)
    if orphan_figures:
        raise ValueError(f"síntesis contiene cifras huérfanas: {orphan_figures}")


def normalize_temporal_year_filters(
    selection: EnumeratedPlanSelection,
    context: EnumeratedPlanningContext,
) -> EnumeratedPlanSelection:
    """Expande igualdad temporal `YYYY` a un rango anual ISO verificable."""

    if selection.dataset_index >= len(context.candidates):
        return selection
    columns = context.candidates[selection.dataset_index].columns
    normalized: list[FilterChoice] = []
    for item in selection.filters:
        if item.column_index >= len(columns):
            normalized.append(item)
            continue
        column_type = columns[item.column_index].data_type
        is_year_eq = (
            item.operator is FilterOperator.EQ
            and len(item.values) == 1
            and len(item.values[0]) == 4
            and item.values[0].isdigit()
        )
        if not is_year_eq or column_type not in {
            ColumnDataType.DATE,
            ColumnDataType.DATETIME,
        }:
            normalized.append(item)
            continue
        year = item.values[0]
        if column_type is ColumnDataType.DATE:
            values = (f"{year}-01-01", f"{year}-12-31")
            value_type = ScalarType.DATE
        else:
            values = (f"{year}-01-01T00:00:00", f"{year}-12-31T23:59:59")
            value_type = ScalarType.DATETIME
        normalized.append(
            item.model_copy(
                update={
                    "operator": FilterOperator.BETWEEN,
                    "value_type": value_type,
                    "values": values,
                }
            )
        )
    return selection.model_copy(update={"filters": tuple(normalized)})


def normalize_system_owned_operation(
    selection: EnumeratedPlanSelection,
    intent: IntentExtraction,
) -> EnumeratedPlanSelection:
    """Materializa operaciones sin columna cuya semántica ya fijó la intención."""

    if intent.operation is QueryOperation.COUNT:
        return selection.model_copy(
            update={
                "operation": QueryOperation.COUNT,
                "metrics": (MetricChoice(operation=QueryOperation.COUNT),),
            }
        )
    if intent.operation is QueryOperation.LOOKUP:
        metric_columns = tuple(
            item.column_index for item in selection.metrics if item.column_index is not None
        )
        dimensions = tuple(
            dict.fromkeys((*selection.dimension_column_indexes, *metric_columns))
        )
        return selection.model_copy(
            update={
                "operation": QueryOperation.LOOKUP,
                "dimension_column_indexes": dimensions,
                "metrics": (),
            }
        )
    return selection


def materialize_query_plan(
    selection: EnumeratedPlanSelection,
    *,
    intent: IntentExtraction,
    context: EnumeratedPlanningContext,
) -> QueryPlan:
    if selection.operation is not intent.operation:
        raise ValueError(
            "operation del plan debe coincidir con la intención: "
            f"{selection.operation.value} != {intent.operation.value}"
        )
    provenance = SelectionProvenance(
        origin=SelectionOrigin.INTENT,
        source_text=intent.topic,
    )
    plan = QueryPlan(
        dataset_index=selection.dataset_index,
        operation=selection.operation,
        dimensions=tuple(
            DimensionSelection(
                column=ColumnReference(column_index=index),
                provenance=provenance,
            )
            for index in selection.dimension_column_indexes
        ),
        metrics=tuple(
            MetricSelection(
                operation=item.operation,
                column=(
                    ColumnReference(column_index=item.column_index)
                    if item.column_index is not None
                    else None
                ),
                provenance=provenance,
            )
            for item in selection.metrics
        ),
        filters=tuple(
            FilterSelection(
                column=ColumnReference(column_index=item.column_index),
                operator=item.operator,
                values=tuple(
                    ScalarValue(type=item.value_type, value=value)
                    for value in item.values
                    if item.value_type is not None
                ),
                provenance=provenance,
            )
            for item in selection.filters
        ),
        order_by=tuple(
            SortSelection(
                target_kind=item.target_kind,
                target_index=item.target_index,
                direction=item.direction,
            )
            for item in selection.order_by
        ),
        limit=selection.limit,
        needs_value_exploration=selection.needs_value_exploration,
        purpose=f"{intent.operation.value}: {intent.topic}",
    )
    context.validate_references(plan)
    return plan
