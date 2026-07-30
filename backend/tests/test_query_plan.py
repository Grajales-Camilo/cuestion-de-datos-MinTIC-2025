import json

import pytest
from pydantic import ValidationError

from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    ColumnReference,
    DatasetOption,
    DimensionSelection,
    EnumeratedPlanningContext,
    FilterOperator,
    FilterSelection,
    MetricSelection,
    PiiRiskLevel,
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


def provenance() -> SelectionProvenance:
    return SelectionProvenance(origin=SelectionOrigin.USER, source_text="total por municipio")


def context() -> EnumeratedPlanningContext:
    return EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="abcd-1234",
                title="Dataset de prueba",
                publisher="Entidad oficial",
                columns=(
                    ColumnOption(
                        index=0,
                        field_name="municipio",
                        display_name="Municipio",
                        data_type=ColumnDataType.TEXT,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                    ColumnOption(
                        index=1,
                        field_name="valor",
                        display_name="Valor",
                        data_type=ColumnDataType.NUMBER,
                        pii_risk_level=PiiRiskLevel.LOW,
                    ),
                ),
            ),
        )
    )


def sum_plan(**overrides: object) -> QueryPlan:
    values: dict[str, object] = {
        "dataset_index": 0,
        "operation": QueryOperation.SUM,
        "dimensions": (
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
        ),
        "metrics": (
            MetricSelection(
                operation=QueryOperation.SUM,
                column=ColumnReference(column_index=1),
                provenance=provenance(),
            ),
        ),
        "filters": (
            FilterSelection(
                column=ColumnReference(column_index=0),
                operator=FilterOperator.EQ,
                values=(ScalarValue(type=ScalarType.TEXT, value="Pasto"),),
                provenance=provenance(),
            ),
        ),
        "order_by": (
            SortSelection(
                target_kind=SortTargetKind.METRIC,
                target_index=0,
                direction=SortDirection.DESC,
            ),
        ),
        "limit": 20,
        "purpose": "Sumar el valor por municipio",
    }
    values.update(overrides)
    return QueryPlan.model_validate(values)


def test_context_accepts_contiguous_enumerated_options() -> None:
    assert context().candidates[0].columns[1].field_name == "valor"


def test_context_rejects_non_contiguous_candidate_and_column_indexes() -> None:
    candidate = context().candidates[0].model_copy(update={"index": 1})
    with pytest.raises(ValidationError, match="candidatos"):
        EnumeratedPlanningContext(candidates=(candidate,))

    bad_columns = (
        context().candidates[0].columns[0],
        context().candidates[0].columns[1].model_copy(update={"index": 3}),
    )
    with pytest.raises(ValidationError, match="columnas"):
        DatasetOption(
            index=0,
            dataset_id="abcd-1234",
            title="Dataset",
            publisher="Entidad",
            columns=bad_columns,
        )


def test_context_rejects_invented_dataset_and_column_references() -> None:
    with pytest.raises(ValueError, match="dataset_index inexistente"):
        context().validate_references(sum_plan(dataset_index=1))

    bad_dimension = DimensionSelection(
        column=ColumnReference(column_index=99), provenance=provenance()
    )
    with pytest.raises(ValueError, match="column_index inexistente"):
        context().validate_references(sum_plan(dimensions=(bad_dimension,)))


def test_models_forbid_unknown_fields_and_operations() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        QueryPlan.model_validate({**sum_plan().model_dump(), "soql": "select *"})
    with pytest.raises(ValidationError):
        sum_plan(operation="median")


def test_count_only_represents_count_star() -> None:
    valid = MetricSelection(operation=QueryOperation.COUNT, provenance=provenance())
    assert valid.column is None
    with pytest.raises(ValidationError, match=r"count\(\*\)"):
        MetricSelection(
            operation=QueryOperation.COUNT,
            column=ColumnReference(column_index=1),
            provenance=provenance(),
        )


def test_aggregate_operations_require_a_column_except_count() -> None:
    for operation in (
        QueryOperation.SUM,
        QueryOperation.AVG,
        QueryOperation.MIN,
        QueryOperation.MAX,
    ):
        with pytest.raises(ValidationError, match="requiere"):
            MetricSelection(operation=operation, provenance=provenance())


def test_lookup_requires_dimensions_and_rejects_metrics() -> None:
    with pytest.raises(ValidationError, match="al menos una columna"):
        QueryPlan(dataset_index=0, operation=QueryOperation.LOOKUP, purpose="Buscar fila")
    with pytest.raises(ValidationError, match="no acepta métricas"):
        QueryPlan(
            dataset_index=0,
            operation=QueryOperation.LOOKUP,
            dimensions=(
                DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
            ),
            metrics=sum_plan().metrics,
            purpose="Buscar fila",
        )


@pytest.mark.parametrize(
    ("operator", "values"),
    [
        (FilterOperator.EQ, ()),
        (FilterOperator.BETWEEN, (ScalarValue(type=ScalarType.INTEGER, value="1"),)),
        (FilterOperator.IS_NULL, (ScalarValue(type=ScalarType.TEXT, value="x"),)),
    ],
)
def test_filter_operators_reject_invalid_arity(
    operator: FilterOperator, values: tuple[ScalarValue, ...]
) -> None:
    with pytest.raises(ValidationError, match="aridad inválida"):
        FilterSelection(
            column=ColumnReference(column_index=0),
            operator=operator,
            values=values,
            provenance=provenance(),
        )


def test_order_references_an_existing_dimension_or_metric() -> None:
    with pytest.raises(ValidationError, match=r"metric\[1\] inexistente"):
        sum_plan(
            order_by=(
                SortSelection(target_kind=SortTargetKind.METRIC, target_index=1),
            )
        )


def test_operational_limits_are_closed() -> None:
    with pytest.raises(ValidationError):
        sum_plan(limit=5001)
    with pytest.raises(ValidationError):
        sum_plan(filters=sum_plan().filters * 17)


def test_canonical_json_is_compact_sorted_and_round_trips() -> None:
    plan = sum_plan()
    canonical = plan.canonical_json()
    assert '": ' not in canonical
    assert '", ' not in canonical
    assert canonical == json.dumps(
        json.loads(canonical), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert QueryPlan.model_validate_json(canonical) == plan


def test_equivalent_plans_have_the_same_versioned_hash() -> None:
    plan = sum_plan()
    reordered_input = {
        "purpose": plan.purpose,
        "limit": plan.limit,
        "filters": [item.model_dump() for item in plan.filters],
        "metrics": [item.model_dump() for item in plan.metrics],
        "dimensions": [item.model_dump() for item in plan.dimensions],
        "operation": plan.operation.value,
        "dataset_index": plan.dataset_index,
        "order_by": [item.model_dump() for item in plan.order_by],
        "needs_value_exploration": False,
        "version": "query-plan.v1",
    }
    equivalent = QueryPlan.model_validate(reordered_input)
    assert equivalent.canonical_json() == plan.canonical_json()
    assert equivalent.plan_hash() == plan.plan_hash()
    assert len(plan.plan_hash()) == 64


def test_material_change_changes_hash() -> None:
    assert sum_plan().plan_hash() != sum_plan(limit=21).plan_hash()
