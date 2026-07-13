import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agent.llm_contracts import (
    CandidateRanking,
    EnumeratedPlanSelection,
    FilterChoice,
    GroundedSynthesis,
    IntentExtraction,
    MetricChoice,
    materialize_query_plan,
    validate_candidate_ranking,
    validate_grounded_synthesis,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    DatasetOption,
    EnumeratedPlanningContext,
    FilterOperator,
    PiiRiskLevel,
    QueryOperation,
    ScalarType,
    SelectionOrigin,
)
from app.quality.claims import BuiltClaim


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


def intent(operation: QueryOperation = QueryOperation.SUM) -> IntentExtraction:
    return IntentExtraction(
        topic="homicidios por departamento",
        operation=operation,
        territory="Colombia",
        administrative_terms=("departamento", "seguridad ciudadana"),
    )


def test_llm_schemas_do_not_expose_free_identifiers_or_soql() -> None:
    schemas = (
        IntentExtraction.model_json_schema(),
        CandidateRanking.model_json_schema(),
        EnumeratedPlanSelection.model_json_schema(),
    )
    serialized = json.dumps(schemas).casefold()
    for forbidden in ("dataset_id", "field_name", "evidence_id", "soql", "where_clause"):
        assert forbidden not in serialized


def test_candidate_ranking_only_accepts_unique_existing_indexes() -> None:
    ranking = CandidateRanking(ranked_candidate_indexes=(0,))
    validate_candidate_ranking(ranking, context())
    with pytest.raises(ValidationError, match="duplicados"):
        CandidateRanking(ranked_candidate_indexes=(0, 0))
    with pytest.raises(ValueError, match="inexistentes"):
        validate_candidate_ranking(CandidateRanking(ranked_candidate_indexes=(1,)), context())


def test_materializes_query_plan_with_system_owned_provenance() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(0,),
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
        filters=(
            FilterChoice(
                column_index=0,
                operator=FilterOperator.EQ,
                value_type=ScalarType.TEXT,
                values=("Pasto",),
            ),
        ),
        limit=10,
    )
    plan = materialize_query_plan(selection, intent=intent(), context=context())
    assert plan.dataset_index == 0
    assert plan.dimensions[0].column.column_index == 0
    assert plan.metrics[0].column is not None
    assert plan.metrics[0].column.column_index == 1
    assert plan.metrics[0].provenance.origin is SelectionOrigin.INTENT


def test_materialization_rejects_invented_column_index() -> None:
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(99,),
        metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=1),),
    )
    with pytest.raises(ValueError, match="column_index inexistente"):
        materialize_query_plan(selection, intent=intent(), context=context())


def test_structured_outputs_forbid_extra_free_text_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        EnumeratedPlanSelection.model_validate(
            {
                "dataset_index": 0,
                "operation": "sum",
                "metrics": [{"operation": "sum", "column_index": 1}],
                "soql": "select sum(valor)",
            }
        )


def test_count_cannot_choose_a_column_and_lookup_is_not_a_metric() -> None:
    with pytest.raises(ValidationError, match=r"count\(\*\)"):
        MetricChoice(operation=QueryOperation.COUNT, column_index=1)
    with pytest.raises(ValidationError, match="lookup"):
        MetricChoice(operation=QueryOperation.LOOKUP, column_index=1)


def _claim(display_value: str = "66.723") -> BuiltClaim:
    return BuiltClaim(
        claim_type="direct",
        description="Total",
        raw_value=Decimal("66723"),
        display_value=display_value,
        unit=None,
        rounding=0,
        formula=None,
        source_row_indexes=(0,),
        columns_used=("metric_0",),
        source_hash="sha256:test",
    )


def test_grounded_synthesis_accepts_only_existing_claims_and_supported_figures() -> None:
    synthesis = GroundedSynthesis(
        answer="El total observado fue 66.723.",
        cited_claim_indexes=(0,),
    )
    validate_grounded_synthesis(synthesis, (_claim(),))

    with pytest.raises(ValueError, match="inexistentes"):
        validate_grounded_synthesis(
            GroundedSynthesis(answer="Resultado disponible.", cited_claim_indexes=(1,)),
            (_claim(),),
        )
    with pytest.raises(ValueError, match="huérfanas"):
        validate_grounded_synthesis(
            GroundedSynthesis(answer="El total fue 99.999.", cited_claim_indexes=(0,)),
            (_claim(),),
        )
