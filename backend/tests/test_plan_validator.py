import pytest
from pydantic import ValidationError

from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    PlanValidationCode,
    PlanValidationError,
    validate_query_plan,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnReference,
    DimensionSelection,
    EligibilityStatus,
    FilterOperator,
    FilterSelection,
    PiiRiskLevel,
    QueryOperation,
    QueryPlan,
    ScalarType,
    ScalarValue,
)
from tests.test_query_plan import context, provenance, sum_plan


def schema(
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    value_type: ColumnDataType = ColumnDataType.NUMBER,
    value_pii: PiiRiskLevel = PiiRiskLevel.LOW,
) -> ObservedDatasetSchema:
    return ObservedDatasetSchema(
        dataset_id="abcd-1234",
        eligibility_status=eligibility,
        pii_risk_level=value_pii,
        columns=(
            ObservedColumn(
                field_name="municipio",
                data_type=ColumnDataType.TEXT,
                pii_risk_level=PiiRiskLevel.LOW,
            ),
            ObservedColumn(
                field_name="valor",
                data_type=value_type,
                pii_risk_level=value_pii,
            ),
        ),
    )


def assert_code(expected: PlanValidationCode, function: object) -> None:
    with pytest.raises(PlanValidationError) as captured:
        function()  # type: ignore[operator]
    assert captured.value.code is expected


def test_resolves_indexes_to_real_dataset_and_column_names() -> None:
    validated = validate_query_plan(sum_plan(), context=context(), schema=schema())
    assert validated.dataset_id == "abcd-1234"
    assert validated.dimensions[0].field_name == "municipio"
    assert validated.metrics[0].field_name == "valor"
    assert validated.source_plan_hash == sum_plan().plan_hash()
    assert validated.include_group_count is False


def test_rejects_schema_for_a_different_dataset() -> None:
    wrong = schema().model_copy(update={"dataset_id": "wxyz-9876"})
    assert_code(
        PlanValidationCode.DATASET_MISMATCH,
        lambda: validate_query_plan(sum_plan(), context=context(), schema=wrong),
    )


@pytest.mark.parametrize("status", [EligibilityStatus.DIAGNOSTIC_ONLY, EligibilityStatus.BLOCKED])
def test_rejects_dataset_that_is_not_eligible(status: EligibilityStatus) -> None:
    assert_code(
        PlanValidationCode.DATASET_NOT_ELIGIBLE,
        lambda: validate_query_plan(
            sum_plan(), context=context(), schema=schema(eligibility=status)
        ),
    )


def test_rejects_schema_drift_even_when_dataset_id_matches() -> None:
    drifted = schema().model_copy(
        update={
            "columns": (
                *schema().columns[:1],
                schema().columns[1].model_copy(update={"field_name": "otro_valor"}),
            )
        }
    )
    assert_code(
        PlanValidationCode.DATASET_MISMATCH,
        lambda: validate_query_plan(sum_plan(), context=context(), schema=drifted),
    )


@pytest.mark.parametrize("operation", [QueryOperation.SUM, QueryOperation.AVG])
def test_sum_and_avg_reject_text_columns(operation: QueryOperation) -> None:
    assert_code(
        PlanValidationCode.TYPE_MISMATCH,
        lambda: validate_query_plan(
            sum_plan(
                operation=operation,
                metrics=(sum_plan().metrics[0].model_copy(update={"operation": operation}),),
            ),
            context=context(),
            schema=schema(value_type=ColumnDataType.TEXT),
        ),
    )


@pytest.mark.parametrize("risk", [PiiRiskLevel.HIGH, PiiRiskLevel.UNKNOWN])
def test_rejects_high_and_unknown_pii_before_rendering(risk: PiiRiskLevel) -> None:
    assert_code(
        PlanValidationCode.PII_BLOCKED,
        lambda: validate_query_plan(sum_plan(), context=context(), schema=schema(value_pii=risk)),
    )


def test_medium_pii_aggregate_requires_group_count() -> None:
    validated = validate_query_plan(
        sum_plan(), context=context(), schema=schema(value_pii=PiiRiskLevel.MEDIUM)
    )
    assert validated.include_group_count is True


def test_lookup_of_low_risk_column_is_not_blocked_by_unrelated_dataset_medium_risk() -> None:
    """T-617B-C13-D7 (pilot-025/pilot-026, golden-v2, datasets nudc-7mev/
    f5ai-gvqt): `schema.pii_risk_level` ya es el PEOR CASO de todas las
    columnas del dataset (`classify_dataset`), incluidas columnas que el
    plan nunca selecciona. Un LOOKUP que solo toca `municipio` (`low`) no
    debe bloquearse solo porque el dataset contenga OTRA columna (`valor`)
    clasificada `medium` que esta consulta no usa en absoluto."""

    lookup_plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=0), provenance=provenance()),
        ),
        filters=(
            FilterSelection(
                column=ColumnReference(column_index=0),
                operator=FilterOperator.EQ,
                values=(ScalarValue(type=ScalarType.TEXT, value="Pasto"),),
                provenance=provenance(),
            ),
        ),
        purpose="Consultar municipio",
    )

    validated = validate_query_plan(
        lookup_plan, context=context(), schema=schema(value_pii=PiiRiskLevel.MEDIUM)
    )

    assert validated.dimensions[0].field_name == "municipio"


def test_lookup_of_medium_risk_column_itself_still_requires_aggregation() -> None:
    """El acotamiento nunca deja pasar una columna MEDIUM que sí se
    selecciona -- solo deja de bloquear por columnas ajenas no consultadas."""

    lookup_plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(column=ColumnReference(column_index=1), provenance=provenance()),
        ),
        purpose="Consultar valor",
    )

    assert_code(
        PlanValidationCode.PII_REQUIRES_AGGREGATION,
        lambda: validate_query_plan(
            lookup_plan, context=context(), schema=schema(value_pii=PiiRiskLevel.MEDIUM)
        ),
    )


def test_validated_plan_is_a_distinct_frozen_type() -> None:
    validated = validate_query_plan(sum_plan(), context=context(), schema=schema())
    with pytest.raises(ValidationError):
        validated.limit = 2  # type: ignore[misc]


def test_rejects_invalid_typed_literal_before_renderer() -> None:
    date_context = context().model_copy(
        update={
            "candidates": (
                context()
                .candidates[0]
                .model_copy(
                    update={
                        "columns": (
                            context()
                            .candidates[0]
                            .columns[0]
                            .model_copy(update={"data_type": ColumnDataType.DATE}),
                            context().candidates[0].columns[1],
                        )
                    }
                ),
            )
        }
    )
    date_schema = schema().model_copy(
        update={
            "columns": (
                schema().columns[0].model_copy(update={"data_type": ColumnDataType.DATE}),
                schema().columns[1],
            )
        }
    )
    invalid_plan = sum_plan().model_copy(
        update={
            "filters": (
                sum_plan()
                .filters[0]
                .model_copy(update={"values": (ScalarValue(type=ScalarType.DATE, value="2025"),)}),
            )
        }
    )
    assert_code(
        PlanValidationCode.INVALID_LITERAL,
        lambda: validate_query_plan(
            invalid_plan,
            context=date_context,
            schema=date_schema,
        ),
    )
