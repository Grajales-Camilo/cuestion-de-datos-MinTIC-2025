from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError

from app.agent.deterministic_pipeline import (
    DeterministicExecutionError,
    DeterministicPersistenceCancelled,
    ExecutionMetadata,
    execute_validated_plan,
    persist_deterministic_execution,
)
from app.agent.deterministic_runtime import run_deterministic_agent
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    IntentExtraction,
    QuantitativePlanSelection,
    materialize_query_plan,
)
from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    PlanValidationCode,
    PlanValidationError,
    validate_query_plan,
)
from app.agent.query_plan import (
    ArgmaxLabelSelection,
    ArgminLabelSelection,
    CanonicalTextSetSelection,
    CategorySelection,
    ColumnDataType,
    ColumnOption,
    ColumnReference,
    DatasetOption,
    DimensionSelection,
    DirectTextSelection,
    EligibilityStatus,
    EnumeratedPlanningContext,
    FilterOperator,
    FilterSelection,
    PiiRiskLevel,
    QueryOperation,
    QueryPlan,
    ScalarType,
    ScalarValue,
    SortDirection,
    SortSelection,
    SortTargetKind,
    ValuePresenceSelection,
)
from app.quality.grounded_facts import (
    CategorySelectionRule,
    TextualFactOperation,
)
from app.quality.textual_fact_builder import TextualFactError
from tests.test_deterministic_pipeline import metadata
from tests.test_deterministic_runtime import _dependencies
from tests.test_plan_validator import schema
from tests.test_query_plan import context, provenance, sum_plan


def _lookup_plan(*requests, limit: int = 2, ordered: bool = False) -> QueryPlan:
    return QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=(
            DimensionSelection(
                column=ColumnReference(column_index=0),
                provenance=provenance(),
            ),
        ),
        order_by=(
            (
                SortSelection(
                    target_kind=SortTargetKind.DIMENSION,
                    target_index=0,
                    direction=SortDirection.ASC,
                ),
            )
            if ordered
            else ()
        ),
        textual_requests=requests,
        limit=limit,
        purpose="Consultar municipio",
    )


def _validated(plan: QueryPlan):
    return validate_query_plan(plan, context=context(), schema=schema())


def _selection_factories() -> tuple[Callable[[], object], ...]:
    return (
        lambda: DirectTextSelection(
            source_row_indexes=(0,),
            column=ColumnReference(column_index=0),
        ),
        lambda: ValuePresenceSelection(
            source_row_indexes=(0, 1),
            column=ColumnReference(column_index=0),
            target_raw="Medellín",
        ),
        lambda: CategorySelection(
            source_row_indexes=(0, 1),
            column=ColumnReference(column_index=0),
            rule=CategorySelectionRule.UNIQUE_NORMALIZED_VALUE,
        ),
        lambda: ArgmaxLabelSelection(
            source_row_indexes=(0, 1),
            label_column=ColumnReference(column_index=0),
            metric_column=ColumnReference(column_index=1),
        ),
        lambda: ArgminLabelSelection(
            source_row_indexes=(0, 1),
            label_column=ColumnReference(column_index=0),
            metric_column=ColumnReference(column_index=1),
        ),
        lambda: CanonicalTextSetSelection(
            source_row_indexes=(0, 1),
            column=ColumnReference(column_index=0),
        ),
    )


@pytest.mark.parametrize("factory", _selection_factories())
def test_closed_planning_contract_accepts_each_textual_operation(factory) -> None:
    request = factory()
    payload = {
        "dataset_index": 0,
        "operation": QueryOperation.SUM,
        "dimension_column_indexes": (0,),
        "metrics": ({"operation": "sum", "column_index": 1},),
        "textual_requests": (request,),
    }
    selection = EnumeratedPlanSelection.model_validate(payload)
    assert selection.textual_requests[0].operation in TextualFactOperation


def test_disabled_planning_schema_has_zero_textual_surface() -> None:
    with pytest.raises(ValidationError, match="textual_requests"):
        QuantitativePlanSelection.model_validate(
            {
                "dataset_index": 0,
                "operation": "lookup",
                "textual_requests": (
                    {
                        "operation": "direct_text",
                        "source_row_indexes": (0,),
                        "column": {"column_index": 0},
                    },
                ),
            }
        )


def test_llm_cannot_assert_eligibility_order_or_persistence() -> None:
    schema_json = str(EnumeratedPlanSelection.model_json_schema()).casefold()
    for forbidden in (
        "validated_order_is_total",
        "eligibility_status",
        "quality_classification",
        "evidence_id",
        "source_hash",
        "display_value",
        "persist",
    ):
        assert forbidden not in schema_json


def test_textual_contract_rejects_unknown_operation_extra_fields_and_duplicates() -> None:
    base = {
        "source_row_indexes": (0,),
        "column": {"column_index": 0},
    }
    with pytest.raises(ValidationError):
        EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.LOOKUP,
            textual_requests=({"operation": "invented", **base},),
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        DirectTextSelection(**base, validated_order_is_total=True)
    with pytest.raises(ValidationError, match="duplicados"):
        DirectTextSelection(
            source_row_indexes=(0, 0),
            column=ColumnReference(column_index=0),
        )


def test_historical_plan_hash_is_unchanged_when_textual_requests_are_absent() -> None:
    assert sum_plan().plan_hash() == (
        "58a9eb5935f92d3f63659351df6645c914b5c89387d335108e465f5df95dc7bd"
    )
    assert "textual_requests" not in sum_plan().canonical_json()


def test_materialization_and_validation_resolve_textual_indexes_but_not_results() -> None:
    request = ValuePresenceSelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=0),
        target_raw="  Medellín  ",
    )
    selection = EnumeratedPlanSelection(
        dataset_index=0,
        operation=QueryOperation.SUM,
        dimension_column_indexes=(0,),
        metrics=({"operation": "sum", "column_index": 1},),
        textual_requests=(request,),
    )
    plan = materialize_query_plan(
        selection,
        intent=IntentExtraction(topic="total", operation=QueryOperation.SUM),
        context=context(),
    )
    validated = _validated(plan)
    textual = validated.textual_requests[0]
    assert textual.columns[0].field_name == "municipio"
    assert textual.operation_params.target_raw == "  Medellín  "
    assert textual.operation_params.target_normalized == "medellín"


def test_validator_rejects_unselected_invalid_or_wrongly_typed_columns() -> None:
    request = DirectTextSelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=1),
    )
    with pytest.raises(PlanValidationError) as captured:
        _validated(_lookup_plan(request))
    assert captured.value.code is PlanValidationCode.TEXTUAL_REQUEST_INVALID

    numeric_dimension = _lookup_plan(
        DirectTextSelection(
            source_row_indexes=(0,),
            column=ColumnReference(column_index=1),
        )
    ).model_copy(
        update={
            "dimensions": (
                DimensionSelection(
                    column=ColumnReference(column_index=1),
                    provenance=provenance(),
                ),
            )
        }
    )
    with pytest.raises(PlanValidationError) as captured:
        _validated(numeric_dimension)
    assert captured.value.code is PlanValidationCode.TYPE_MISMATCH


@pytest.mark.asyncio
async def test_enabled_lookup_prepares_text_without_count_one_surrogate() -> None:
    plan = _lookup_plan(
        DirectTextSelection(
            source_row_indexes=(0,),
            column=ColumnReference(column_index=0),
        )
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "  Medellín  "}],
        }

    result = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    assert result.claims.claims == ()
    assert len(result.textual_facts) == 1
    assert result.textual_rejections == ()


@pytest.mark.asyncio
async def test_disabled_lookup_preserves_historical_count_one_rollback() -> None:
    plan = _lookup_plan()

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Medellín"}],
        }

    result = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=False,
    )
    assert result.claims.claims[0].raw_value == 1
    assert result.textual_facts == ()


@pytest.mark.asyncio
async def test_enabled_lookup_without_accepted_text_never_falls_back_to_count_one() -> None:
    plan = _lookup_plan()

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Medellín"}, {"dim_1": "Bogotá"}],
        }

    with pytest.raises(DeterministicExecutionError, match="CLAIMS_REJECTED"):
        await execute_validated_plan(
            _validated(plan),
            executor=executor,
            metadata=metadata(),
            textual_facts_enabled=True,
        )


def _single_project_lookup() -> tuple[QueryPlan, EnumeratedPlanningContext, ObservedDatasetSchema]:
    columns = (
        ColumnOption(
            index=0,
            field_name="codigo",
            display_name="Código",
            data_type=ColumnDataType.TEXT,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
        ColumnOption(
            index=1,
            field_name="nombre_proyecto",
            display_name="Nombre del proyecto",
            data_type=ColumnDataType.TEXT,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
        ColumnOption(
            index=2,
            field_name="tipo_app",
            display_name="Tipo APP",
            data_type=ColumnDataType.TEXT,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
        ColumnOption(
            index=3,
            field_name="entidad_encargada",
            display_name="Entidad encargada",
            data_type=ColumnDataType.TEXT,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
    )
    planning_context = EnumeratedPlanningContext(
        candidates=(
            DatasetOption(
                index=0,
                dataset_id="wxyz-9876",
                title="Proyectos de infraestructura",
                publisher="Entidad oficial",
                columns=columns,
            ),
        )
    )
    observed_schema = ObservedDatasetSchema(
        dataset_id="wxyz-9876",
        eligibility_status=EligibilityStatus.ELIGIBLE,
        pii_risk_level=PiiRiskLevel.LOW,
        columns=tuple(
            ObservedColumn(
                field_name=column.field_name,
                data_type=column.data_type,
                pii_risk_level=column.pii_risk_level,
            )
            for column in columns
        ),
    )
    plan = QueryPlan(
        dataset_index=0,
        operation=QueryOperation.LOOKUP,
        dimensions=tuple(
            DimensionSelection(
                column=ColumnReference(column_index=index),
                provenance=provenance(),
            )
            for index in range(len(columns))
        ),
        filters=(
            FilterSelection(
                column=ColumnReference(column_index=0),
                operator=FilterOperator.EQ,
                values=(ScalarValue(type=ScalarType.TEXT, value="ABC123"),),
                provenance=provenance(),
            ),
        ),
        limit=100,
        purpose="lookup: ¿Cuál es el tipo y nombre del proyecto APP ABC123?",
    )
    return plan, planning_context, observed_schema


@pytest.mark.asyncio
async def test_single_row_lookup_derives_only_requested_text_without_llm_request() -> None:
    plan, planning_context, observed_schema = _single_project_lookup()
    validated = validate_query_plan(
        plan,
        context=planning_context,
        schema=observed_schema,
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            # La herramienta real normaliza keywords y agrega OFFSET 0 a la
            # misma consulta renderizada antes de persistirla.
            "canonical_soql": (
                "SELECT codigo AS dim_1, nombre_proyecto AS dim_2, "
                "tipo_app AS dim_3, entidad_encargada AS dim_4 "
                "WHERE codigo = 'ABC123' LIMIT 100 OFFSET 0"
            ),
            "rows": [
                {
                    "dim_1": "ABC123",
                    "dim_2": "Corredor del Norte",
                    "dim_3": "Iniciativa privada",
                    "dim_4": "Agencia de Infraestructura",
                }
            ],
        }

    result = await execute_validated_plan(
        validated,
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )

    assert result.claims.claims == ()
    assert [fact.spec.operation for fact in result.textual_facts] == [
        TextualFactOperation.DIRECT_TEXT,
        TextualFactOperation.DIRECT_TEXT,
    ]
    assert [fact.spec.columns for fact in result.textual_facts] == [
        ("dim_2",),
        ("dim_3",),
    ]
    assert result.textual_rejections == ()


@pytest.mark.asyncio
async def test_single_row_lookup_does_not_promote_unrequested_text() -> None:
    plan, planning_context, observed_schema = _single_project_lookup()
    plan = plan.model_copy(update={"purpose": "lookup: Consultar el registro ABC123"})
    validated = validate_query_plan(
        plan,
        context=planning_context,
        schema=observed_schema,
    )

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {
                    "dim_1": "ABC123",
                    "dim_2": "Corredor del Norte",
                    "dim_3": "Iniciativa privada",
                    "dim_4": "Agencia de Infraestructura",
                }
            ],
        }

    with pytest.raises(DeterministicExecutionError, match="CLAIMS_REJECTED"):
        await execute_validated_plan(
            validated,
            executor=executor,
            metadata=metadata(),
            textual_facts_enabled=True,
        )


@pytest.mark.asyncio
async def test_first_by_order_certificate_is_derived_from_plan_and_rows() -> None:
    request = CategorySelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=0),
        rule=CategorySelectionRule.FIRST_BY_VALIDATED_ORDER,
    )
    plan = _lookup_plan(request, limit=2, ordered=True)

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Bogotá"}, {"dim_1": "Medellín"}],
        }

    result = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    assert result.textual_facts[0].validated_order_is_total is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limit", "ordered", "rows"),
    [
        (1, True, [{"dim_1": "Bogotá"}]),
        (2, False, [{"dim_1": "Bogotá"}, {"dim_1": "Medellín"}]),
        (2, True, [{"dim_1": "Bogotá"}, {"dim_1": "Bogotá"}]),
    ],
)
async def test_first_by_order_rejects_unprovable_order(
    limit: int,
    ordered: bool,
    rows: list[dict],
) -> None:
    request = CategorySelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=0),
        rule=CategorySelectionRule.FIRST_BY_VALIDATED_ORDER,
    )
    plan = _lookup_plan(request, limit=limit, ordered=ordered)

    async def executor(payload: dict) -> dict:
        return {"ok": True, "canonical_soql": payload["soql"], "rows": rows}

    result = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    assert result.textual_facts == ()
    assert result.textual_rejections[0].code == "textual_order_not_validated"
    assert result.claims.claims == ()


@pytest.mark.asyncio
async def test_argmax_tie_is_typed_and_never_becomes_quantitative_success() -> None:
    request = ArgmaxLabelSelection(
        source_row_indexes=(0, 1),
        label_column=ColumnReference(column_index=0),
        metric_column=ColumnReference(column_index=1),
    )
    plan = sum_plan(textual_requests=(request,))

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "Bogotá", "metric_sum_1": "10"},
                {"dim_1": "Medellín", "metric_sum_1": "10"},
            ],
        }

    result = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    assert result.textual_rejections[0].code == "textual_extremum_tie"
    assert result.claims.claims


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "textual_request",
    [
        ValuePresenceSelection(
            source_row_indexes=(0, 1),
            column=ColumnReference(column_index=0),
            target_raw="Bogotá",
        ),
        ArgminLabelSelection(
            source_row_indexes=(0, 1),
            label_column=ColumnReference(column_index=0),
            metric_column=ColumnReference(column_index=1),
        ),
        CanonicalTextSetSelection(
            source_row_indexes=(0, 1),
            column=ColumnReference(column_index=0),
        ),
    ],
)
async def test_pipeline_preflights_remaining_closed_operations(textual_request) -> None:
    plan = sum_plan(textual_requests=(textual_request,))

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "Bogotá", "metric_sum_1": "20"},
                {"dim_1": "Medellín", "metric_sum_1": "10"},
            ],
        }

    result = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    assert result.textual_facts[0].spec.operation is textual_request.operation
    assert result.textual_rejections == ()


@pytest.mark.asyncio
async def test_quality_and_cancellation_gate_text_before_construction() -> None:
    request = DirectTextSelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=0),
    )
    plan = _lookup_plan(request)

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Medellín"}],
        }

    blocked_metadata = ExecutionMetadata(
        dataset_name="Dataset",
        publisher="Entidad",
        dataset_pii_risk_level="low",
        dataset_eligibility_status="blocked",
    )
    with pytest.raises(DeterministicExecutionError, match="EVIDENCE_NOT_ELIGIBLE"):
        await execute_validated_plan(
            _validated(plan),
            executor=executor,
            metadata=blocked_metadata,
            textual_facts_enabled=True,
        )
    with pytest.raises(DeterministicPersistenceCancelled):
        await execute_validated_plan(
            _validated(plan),
            executor=executor,
            metadata=metadata(),
            textual_facts_enabled=True,
            is_cancelled=lambda: True,
        )


@pytest.mark.asyncio
async def test_text_only_internal_result_uses_existing_abstention_terminal() -> None:
    dependencies = _dependencies()

    async def execute(_validated):
        return SimpleNamespace(
            quality=SimpleNamespace(eligibility_status="eligible"),
            claims=SimpleNamespace(claims=(), rejected=()),
            textual_facts=(object(),),
            textual_rejections=(),
        )

    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=dataclasses.replace(dependencies, execute=execute),
    )
    assert result.status == "abstained"
    assert result.stop_reason is not None
    assert result.stop_reason.value == "CLAIMS_NOT_AVAILABLE"
    assert result.usage.llm_calls == 2


@pytest.mark.asyncio
async def test_textual_rejection_never_reaches_synthesis_or_legacy_fallback() -> None:
    dependencies = _dependencies()
    synthesis_calls = 0

    async def execute(_validated):
        return SimpleNamespace(
            quality=SimpleNamespace(eligibility_status="eligible"),
            claims=SimpleNamespace(claims=(object(),), rejected=()),
            textual_facts=(),
            textual_rejections=(SimpleNamespace(code="textual_extremum_tie"),),
        )

    async def synthesize(*_args):
        nonlocal synthesis_calls
        synthesis_calls += 1
        raise AssertionError("un rechazo textual no puede llegar a síntesis")

    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=dataclasses.replace(
            dependencies,
            execute=execute,
            synthesize=synthesize,
        ),
    )
    assert result.status == "abstained"
    assert synthesis_calls == 0
    assert result.trace[-1].diagnostic_code == "textual_extremum_tie"


@pytest.mark.asyncio
async def test_persistence_uses_code_created_evidence_id_for_textual_commands(
    monkeypatch,
) -> None:
    request = DirectTextSelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=0),
    )
    plan = _lookup_plan(request)

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Medellín"}],
        }

    execution = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    evidence_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def fake_evidence(*_args, **_kwargs):
        return {"evidence_id": str(evidence_id)}

    async def fake_claims(*_args, **_kwargs):
        return []

    async def fake_textual(_engine, run_id, commands):
        captured["run_id"] = run_id
        captured["commands"] = commands
        return ()

    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.persist_evidence_and_quality",
        fake_evidence,
    )
    monkeypatch.setattr("app.agent.deterministic_pipeline.persist_claims", fake_claims)
    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.build_verify_persist_textual_facts",
        fake_textual,
    )
    run_id = uuid.uuid4()
    await persist_deterministic_execution(
        execution,
        engine=cast(object, object()),
        run_id=run_id,
        official_publisher_id=None,
    )
    commands = cast(tuple, captured["commands"])
    assert captured["run_id"] == run_id
    assert commands[0].evidence_id == evidence_id
    assert commands[0].validated_order_is_total is False


@pytest.mark.asyncio
async def test_textual_transaction_failure_preserves_quantitative_boundary(
    monkeypatch,
) -> None:
    request = ArgmaxLabelSelection(
        source_row_indexes=(0, 1),
        label_column=ColumnReference(column_index=0),
        metric_column=ColumnReference(column_index=1),
    )
    plan = sum_plan(textual_requests=(request,))

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [
                {"dim_1": "Bogotá", "metric_sum_1": "20"},
                {"dim_1": "Medellín", "metric_sum_1": "10"},
            ],
        }

    execution = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )

    async def fake_evidence(*_args, **_kwargs):
        return {"evidence_id": str(uuid.uuid4())}

    async def fake_claims(*_args, **_kwargs):
        return [{"claim_id": "kept"}]

    async def fail_textual(*_args, **_kwargs):
        raise TextualFactError("textual_persistence_failed", "rollback")

    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.persist_evidence_and_quality",
        fake_evidence,
    )
    monkeypatch.setattr("app.agent.deterministic_pipeline.persist_claims", fake_claims)
    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.build_verify_persist_textual_facts",
        fail_textual,
    )
    persisted = await persist_deterministic_execution(
        execution,
        engine=cast(object, object()),
        run_id=uuid.uuid4(),
        official_publisher_id=None,
    )
    assert persisted.claims == ({"claim_id": "kept"},)
    assert persisted.textual_facts == ()
    assert persisted.textual_rejections[0].code == "textual_persistence_failed"


@pytest.mark.asyncio
async def test_cancellation_before_textual_persistence_stops_the_batch(
    monkeypatch,
) -> None:
    request = DirectTextSelection(
        source_row_indexes=(0,),
        column=ColumnReference(column_index=0),
    )
    plan = _lookup_plan(request)

    async def executor(payload: dict) -> dict:
        return {
            "ok": True,
            "canonical_soql": payload["soql"],
            "rows": [{"dim_1": "Medellín"}],
        }

    execution = await execute_validated_plan(
        _validated(plan),
        executor=executor,
        metadata=metadata(),
        textual_facts_enabled=True,
    )
    textual_calls = 0
    claim_calls = 0

    async def fake_evidence(*_args, **_kwargs):
        return {"evidence_id": str(uuid.uuid4())}

    async def fake_claims(*_args, **_kwargs):
        nonlocal claim_calls
        claim_calls += 1
        return []

    async def fake_textual(*_args, **_kwargs):
        nonlocal textual_calls
        textual_calls += 1
        return ()

    checks = iter((False, True))
    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.persist_evidence_and_quality",
        fake_evidence,
    )
    monkeypatch.setattr("app.agent.deterministic_pipeline.persist_claims", fake_claims)
    monkeypatch.setattr(
        "app.agent.deterministic_pipeline.build_verify_persist_textual_facts",
        fake_textual,
    )
    with pytest.raises(DeterministicPersistenceCancelled):
        await persist_deterministic_execution(
            execution,
            engine=cast(object, object()),
            run_id=uuid.uuid4(),
            official_publisher_id=None,
            is_cancelled=lambda: next(checks),
        )
    assert textual_calls == 0
    assert claim_calls == 0
