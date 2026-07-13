import pytest

from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    ValidatedQueryPlan,
    validate_query_plan,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnReference,
    DimensionSelection,
    EligibilityStatus,
    FilterOperator,
    FilterSelection,
    MetricSelection,
    PiiRiskLevel,
    QueryOperation,
    QueryPlan,
    ScalarType,
    ScalarValue,
    SortDirection,
    SortSelection,
    SortTargetKind,
)
from app.agent.soql_renderer import render_soql
from app.tools.soql_parser import parse_soql
from tests.test_query_plan import context, provenance, sum_plan


def schema(*, medium: bool = False) -> ObservedDatasetSchema:
    return ObservedDatasetSchema(
        dataset_id="abcd-1234",
        eligibility_status=EligibilityStatus.ELIGIBLE,
        columns=(
            ObservedColumn(
                field_name="municipio",
                data_type=ColumnDataType.TEXT,
                pii_risk_level=PiiRiskLevel.LOW,
            ),
            ObservedColumn(
                field_name="valor",
                data_type=ColumnDataType.NUMBER,
                pii_risk_level=PiiRiskLevel.MEDIUM if medium else PiiRiskLevel.LOW,
            ),
        ),
    )


def validated(plan: QueryPlan | None = None, *, medium: bool = False) -> ValidatedQueryPlan:
    return validate_query_plan(plan or sum_plan(), context=context(), schema=schema(medium=medium))


def test_sum_group_filter_order_and_limit_are_stable() -> None:
    first = render_soql(validated())
    second = render_soql(validated())
    assert first == second
    assert first.canonical_soql == (
        "select municipio as dim_1, sum(valor) as metric_sum_1 "
        "where municipio = 'Pasto' group by municipio "
        "order by metric_sum_1 desc limit 20"
    )
    parse_soql(first.canonical_soql)


def test_medium_pii_adds_stable_group_count() -> None:
    rendered = render_soql(validated(medium=True))
    assert "count(*) as group_count" in rendered.canonical_soql
    assert rendered.group_count_alias == "group_count"
    parse_soql(rendered.canonical_soql)


@pytest.mark.parametrize(
    "operation",
    [
        QueryOperation.COUNT,
        QueryOperation.SUM,
        QueryOperation.AVG,
        QueryOperation.MIN,
        QueryOperation.MAX,
    ],
)
def test_all_closed_aggregate_operations(operation: QueryOperation) -> None:
    metric = MetricSelection(
        operation=operation,
        column=None if operation is QueryOperation.COUNT else ColumnReference(column_index=1),
        provenance=provenance(),
    )
    plan = sum_plan(operation=operation, metrics=(metric,), order_by=())
    rendered = render_soql(validated(plan))
    expression = "count(*)" if operation is QueryOperation.COUNT else f"{operation.value}(valor)"
    assert f"{expression} as metric_{operation.value}_1" in rendered.canonical_soql
    parse_soql(rendered.canonical_soql)


def test_lookup_selects_direct_columns_without_grouping() -> None:
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        filters=sum_plan().filters,
        limit=1,
        purpose="Consultar un valor textual directo",
    )
    rendered = render_soql(validated(plan))
    assert rendered.canonical_soql == (
        "select valor as dim_1 where municipio = 'Pasto' limit 1"
    )
    parse_soql(rendered.canonical_soql)


def test_text_literal_escapes_single_quotes() -> None:
    filter_item = sum_plan().filters[0].model_copy(
        update={"values": (ScalarValue(type=ScalarType.TEXT, value="O'Brien"),)}
    )
    rendered = render_soql(validated(sum_plan(filters=(filter_item,))))
    assert "municipio = 'O''Brien'" in rendered.canonical_soql
    parse_soql(rendered.canonical_soql)


@pytest.mark.parametrize(
    ("operator", "values", "expected"),
    [
        (FilterOperator.IN, ("1", "2"), "(valor = 1 or valor = 2)"),
        (FilterOperator.BETWEEN, ("1", "2"), "(valor >= 1 and valor <= 2)"),
        (FilterOperator.IS_NULL, (), "valor is null"),
        (FilterOperator.IS_NOT_NULL, (), "valor is not null"),
    ],
)
def test_filter_shapes(
    operator: FilterOperator, values: tuple[str, ...], expected: str
) -> None:
    item = FilterSelection(
        column=ColumnReference(column_index=1),
        operator=operator,
        values=tuple(ScalarValue(type=ScalarType.NUMBER, value=value) for value in values),
        provenance=provenance(),
    )
    rendered = render_soql(validated(sum_plan(filters=(item,))))
    assert expected in rendered.canonical_soql
    parse_soql(rendered.canonical_soql)


def test_renderer_rejects_unvalidated_plan() -> None:
    with pytest.raises(TypeError, match="ValidatedQueryPlan"):
        render_soql(sum_plan())  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "abc", "1; drop table x"])
def test_rejects_invalid_numeric_literals(value: str) -> None:
    item = FilterSelection(
        column=ColumnReference(column_index=1),
        operator=FilterOperator.EQ,
        values=(ScalarValue(type=ScalarType.NUMBER, value=value),),
        provenance=provenance(),
    )
    with pytest.raises(ValueError, match="numérico"):
        render_soql(validated(sum_plan(filters=(item,))))


def test_renderer_cannot_emit_forbidden_free_functions() -> None:
    rendered = render_soql(validated())
    forbidden = ("cast", "to_number", "replace", "::", ";")
    assert not any(token in rendered.canonical_soql.casefold() for token in forbidden)


def test_order_aliases_are_deterministic_for_dimensions() -> None:
    plan = sum_plan(
        order_by=(
            SortSelection(
                target_kind=SortTargetKind.DIMENSION,
                target_index=0,
                direction=SortDirection.ASC,
            ),
        )
    )
    assert "order by dim_1 asc" in render_soql(validated(plan)).canonical_soql
