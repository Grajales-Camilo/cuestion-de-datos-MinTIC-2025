from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from app.agent.deterministic_graph import StopReason, SupervisorBudgets, SupervisorNode
from app.agent.deterministic_pipeline import (
    DeterministicExecutionError,
    DeterministicExecutionResult,
)
from app.agent.deterministic_runtime import (
    DeterministicRunCancelled,
    DeterministicRuntimeDependencies,
    ExploredColumnValues,
    ProfiledCandidate,
    run_deterministic_agent,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    FilterChoice,
    GroundedSynthesis,
    IntentExtraction,
    MetricChoice,
)
from app.agent.multiquery_retrieval import MultiQueryRetrievalResult, RetrievedCandidate
from app.agent.plan_validator import (
    ObservedColumn,
    ObservedDatasetSchema,
    PlanValidationCode,
    PlanValidationError,
)
from app.agent.query_plan import (
    ColumnDataType,
    ColumnOption,
    DatasetOption,
    EligibilityStatus,
    FilterOperator,
    PiiRiskLevel,
    QueryOperation,
    ScalarType,
)
from app.catalog.search import CatalogSearchItem
from app.llm.factory import LLMProviderError
from app.quality.claims import BuiltClaim, ClaimsBuildResult


def _intent() -> IntentExtraction:
    return IntentExtraction(topic="total de casos", operation=QueryOperation.SUM)


def _candidate(dataset_id: str = "abcd-1234") -> RetrievedCandidate:
    item = cast(
        CatalogSearchItem,
        SimpleNamespace(dataset_id=dataset_id),
    )
    return RetrievedCandidate(item=item, score=1.0, matched_queries=("casos",), best_rank=0)


def _profile(dataset_id: str = "abcd-1234") -> ProfiledCandidate:
    columns = (
        ColumnOption(
            index=0,
            field_name="valor",
            display_name="Valor",
            data_type=ColumnDataType.NUMBER,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
        ColumnOption(
            index=1,
            field_name="municipio",
            display_name="Municipio",
            data_type=ColumnDataType.TEXT,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
    )
    return ProfiledCandidate(
        option=DatasetOption(
            index=0,
            dataset_id=dataset_id,
            title="Casos",
            publisher="Entidad",
            columns=columns,
        ),
        schema=ObservedDatasetSchema(
            dataset_id=dataset_id,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            pii_risk_level=PiiRiskLevel.LOW,
            columns=(
                ObservedColumn(
                    field_name="valor",
                    data_type=ColumnDataType.NUMBER,
                    pii_risk_level=PiiRiskLevel.LOW,
                ),
                ObservedColumn(
                    field_name="municipio",
                    data_type=ColumnDataType.TEXT,
                    pii_risk_level=PiiRiskLevel.LOW,
                ),
            ),
        ),
    )


def _claim() -> BuiltClaim:
    return BuiltClaim(
        claim_type="direct",
        description="Total",
        raw_value=Decimal("42"),
        display_value="42",
        unit=None,
        rounding=0,
        formula=None,
        source_row_indexes=(0,),
        columns_used=("metric_0",),
        source_hash="sha256:test",
        public_columns=("total",),
        label="Total",
        label_status="verified",
    )


def _execution() -> DeterministicExecutionResult:
    return cast(
        DeterministicExecutionResult,
        SimpleNamespace(
            quality=SimpleNamespace(eligibility_status="eligible"),
            claims=ClaimsBuildResult(claims=(_claim(),), rejected=()),
        ),
    )


def _dependencies(
    *,
    candidates: int = 1,
    fail_first: bool = False,
    invalid_plan_first: bool = False,
    invalid_synthesis_first: bool = False,
    synthesis_provider_error: bool = False,
    text_filter: bool = False,
    fail_first_exploration: bool = False,
):
    executions = 0
    plans = 0
    syntheses = 0
    explorations = 0

    async def extract(question: str) -> IntentExtraction:
        assert question
        return _intent()

    async def retrieve(intent: IntentExtraction) -> MultiQueryRetrievalResult:
        assert intent.operation is QueryOperation.SUM
        assert intent.topic.startswith("¿Cuál es el total")
        return MultiQueryRetrievalResult(
            queries=("casos",),
            candidates=tuple(_candidate(f"abcd-123{index}") for index in range(candidates)),
        )

    async def profile(dataset_id: str) -> ProfiledCandidate:
        return _profile(dataset_id)

    async def plan(intent, context, explored, error):
        nonlocal plans
        del intent, context, error
        plans += 1
        filters = ()
        if text_filter:
            selected_value = "PASTO" if explored else "Pasto"
            filters = (
                FilterChoice(
                    column_index=1,
                    operator=FilterOperator.EQ,
                    value_type=ScalarType.TEXT,
                    values=(selected_value,),
                ),
            )
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            metrics=(
                MetricChoice(
                    operation=QueryOperation.SUM,
                    column_index=99 if invalid_plan_first and plans == 1 else 0,
                ),
            ),
            filters=filters,
            needs_value_exploration=text_filter,
        )

    async def execute(validated) -> DeterministicExecutionResult:
        nonlocal executions
        del validated
        executions += 1
        if fail_first and executions == 1:
            raise DeterministicExecutionError("dataset no consultable")
        return _execution()

    async def explore(profile, selection, explored) -> ExploredColumnValues:
        nonlocal explorations
        del profile, selection, explored
        explorations += 1
        if fail_first_exploration and explorations == 1:
            raise ValueError("la columna observada no admite LIKE")
        return ExploredColumnValues(column_index=1, search_term="Pasto", values=("PASTO",))

    async def synthesize(intent, claims) -> GroundedSynthesis:
        nonlocal syntheses
        del intent, claims
        syntheses += 1
        if synthesis_provider_error:
            raise LLMProviderError("504 timeout")
        answer = (
            "El total observado fue 999."
            if invalid_synthesis_first and syntheses == 1
            else "El total observado fue 42."
        )
        return GroundedSynthesis(answer=answer, cited_claim_indexes=(0,))

    return DeterministicRuntimeDependencies(
        extract,
        retrieve,
        profile,
        plan,
        explore,
        execute,
        synthesize,
    )


@pytest.mark.asyncio
async def test_runtime_rejects_candidate_when_value_exploration_is_incompatible() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total en Pasto?",
        dependencies=_dependencies(
            candidates=2,
            text_filter=True,
            fail_first_exploration=True,
        ),
    )

    assert result.status == "completed"
    assert result.trace[-1].candidate_index == 1


@pytest.mark.asyncio
async def test_runtime_rejects_irreparable_privacy_candidate(monkeypatch) -> None:
    from app.agent import deterministic_runtime

    real_validate = deterministic_runtime.validate_query_plan
    validations = 0

    def validate_with_first_privacy_failure(*args, **kwargs):
        nonlocal validations
        validations += 1
        if validations == 1:
            raise PlanValidationError(
                PlanValidationCode.PII_REQUIRES_AGGREGATION,
                "las columnas PII medium requieren agregación",
            )
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(
        deterministic_runtime,
        "validate_query_plan",
        validate_with_first_privacy_failure,
    )

    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(candidates=2),
    )

    assert result.status == "completed"
    assert result.trace[-1].candidate_index == 1
    assert result.usage.plan_repairs == 0


@pytest.mark.asyncio
async def test_runtime_completes_only_after_grounded_synthesis() -> None:
    result = await run_deterministic_agent("¿Cuál es el total?", dependencies=_dependencies())
    assert result.status == "completed"
    assert result.synthesis is not None
    assert result.execution is not None
    assert [entry.node for entry in result.trace] == [
        SupervisorNode.SELECT_CANDIDATE,
        SupervisorNode.PROFILE_DATASET,
        SupervisorNode.BUILD_PLAN,
        SupervisorNode.EXECUTE_QUERY,
        SupervisorNode.SYNTHESIZE,
        SupervisorNode.COMPLETE,
    ]


@pytest.mark.asyncio
async def test_runtime_rejects_failed_candidate_and_tries_next() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(candidates=2, fail_first=True),
    )
    assert result.status == "completed"
    assert sum(entry.node is SupervisorNode.SELECT_CANDIDATE for entry in result.trace) == 2
    assert result.usage.queries == 2


@pytest.mark.asyncio
async def test_runtime_abstains_when_retrieval_has_no_candidates() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(candidates=0),
    )
    assert result.status == "abstained"
    assert result.stop_reason is StopReason.NO_CANDIDATES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    (
        "¿Cuántos estudiantes abandonarán exactamente la escuela en 2027?",
        "¿Cuánta lluvia caerá exactamente mañana?",
        "¿Qué bus llegará primero en los próximos cinco minutos?",
        "¿Cuál es el nombre, edad y salario de cada servidor público?",
        "¿Qué tratamiento médico debe recibir una persona según su síntoma?",
    ),
)
async def test_runtime_abstains_early_for_unverifiable_or_sensitive_requests(
    question: str,
) -> None:
    result = await run_deterministic_agent(question, dependencies=_dependencies())

    assert result.status == "abstained"
    assert result.usage.llm_calls == 0
    assert result.retrieval.candidates == ()
    assert [entry.node for entry in result.trace] == [SupervisorNode.ABSTAIN]


@pytest.mark.asyncio
async def test_runtime_enforces_llm_budget_before_planning() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(),
        budgets=SupervisorBudgets(max_llm_calls=1),
    )
    assert result.status == "abstained"
    assert result.stop_reason is StopReason.LLM_BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_runtime_repairs_invented_indexes_within_bounded_budget() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(invalid_plan_first=True),
    )
    assert result.status == "completed"
    assert result.usage.plan_repairs == 1


@pytest.mark.asyncio
async def test_runtime_retries_synthesis_with_orphan_figures() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(invalid_synthesis_first=True),
    )
    assert result.status == "completed"
    assert result.usage.llm_calls == 3
    assert result.synthesis is not None
    assert (
        result.synthesis.answer == "Resultados calculados con la evidencia consultada: Total: 42."
    )


@pytest.mark.asyncio
async def test_runtime_falls_back_to_grounded_synthesis_on_provider_error() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(synthesis_provider_error=True),
    )
    assert result.status == "completed"
    assert result.usage.llm_calls == 3
    assert result.synthesis is not None
    assert (
        result.synthesis.answer == "Resultados calculados con la evidencia consultada: Total: 42."
    )


@pytest.mark.asyncio
async def test_runtime_forces_text_value_exploration_and_replanning() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total en Pasto?",
        dependencies=_dependencies(text_filter=True),
    )
    assert result.status == "completed"
    assert result.usage.explorations == 1
    assert SupervisorNode.EXPLORE_VALUE in [entry.node for entry in result.trace]


@pytest.mark.asyncio
async def test_runtime_canonicalizes_explored_values_without_diacritics() -> None:
    dependencies = _dependencies(text_filter=True)

    async def explore(profile, selection, explored) -> ExploredColumnValues:
        del profile, selection, explored
        return ExploredColumnValues(
            column_index=1,
            search_term="Villamaria",
            values=("VILLAMARIA",),
        )

    async def plan(intent, context, explored, error):
        del intent, context, error
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=0),),
            filters=(
                FilterChoice(
                    column_index=1,
                    operator=FilterOperator.EQ,
                    value_type=ScalarType.TEXT,
                    values=(("Villamaría" if not explored else "Villamaría"),),
                ),
            ),
            needs_value_exploration=True,
        )

    dependencies = DeterministicRuntimeDependencies(
        dependencies.extract_intent,
        dependencies.retrieve,
        dependencies.profile,
        plan,
        explore,
        dependencies.execute,
        dependencies.synthesize,
    )
    result = await run_deterministic_agent("¿Cuál es el total?", dependencies=dependencies)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_runtime_retains_observed_filter_when_replan_omits_it() -> None:
    dependencies = _dependencies(text_filter=True)
    captured = {}

    async def plan(intent, context, explored, error):
        del intent, context, error
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=0),),
            filters=(
                ()
                if explored
                else (
                    FilterChoice(
                        column_index=1,
                        operator=FilterOperator.EQ,
                        value_type=ScalarType.TEXT,
                        values=("Pasto",),
                    ),
                )
            ),
            needs_value_exploration=not explored,
        )

    async def execute(validated):
        captured["filters"] = validated.filters
        return _execution()

    dependencies = DeterministicRuntimeDependencies(
        dependencies.extract_intent,
        dependencies.retrieve,
        dependencies.profile,
        plan,
        dependencies.explore,
        execute,
        dependencies.synthesize,
    )
    result = await run_deterministic_agent("¿Cuál es el total en Pasto?", dependencies=dependencies)

    assert result.status == "completed"
    assert captured["filters"][0].values[0].value == "PASTO"


@pytest.mark.asyncio
async def test_runtime_observes_every_transition_for_durable_steps() -> None:
    observed = []

    async def observer(entry, usage) -> None:
        observed.append((entry, usage))

    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(),
        observe_transition=observer,
    )
    assert [entry for entry, _usage in observed] == list(result.trace)
    assert observed[-1][0].node is SupervisorNode.COMPLETE


@pytest.mark.asyncio
async def test_runtime_defers_synthesis_until_persistence_boundary() -> None:
    dependencies = _dependencies()
    synthesis_called = False

    async def forbidden_synthesis(*_args):
        nonlocal synthesis_called
        synthesis_called = True
        raise AssertionError("la síntesis no puede ejecutarse antes de persistir")

    dependencies = DeterministicRuntimeDependencies(
        dependencies.extract_intent,
        dependencies.retrieve,
        dependencies.profile,
        dependencies.plan,
        dependencies.explore,
        dependencies.execute,
        forbidden_synthesis,
    )

    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=dependencies,
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "ready_for_synthesis"
    assert result.synthesis is None
    assert result.trace[-1].node is SupervisorNode.PERSIST_FACTS
    assert synthesis_called is False


@pytest.mark.asyncio
async def test_runtime_honors_cooperative_cancellation_between_transitions() -> None:
    cancelled = False

    async def observer(entry, usage) -> None:
        nonlocal cancelled
        del entry, usage
        cancelled = True

    with pytest.raises(DeterministicRunCancelled):
        await run_deterministic_agent(
            "¿Cuál es el total?",
            dependencies=_dependencies(),
            observe_transition=observer,
            is_cancelled=lambda: cancelled,
        )


# --- RF-212: etiquetado y relevancia en el fallback determinista (T-617C) ----
#
# Fixture genérico (composición de personal por categoría, no pilot-005):
# ninguna prueba de esta sección condiciona por case_id, dataset_id ni los
# valores/entidad de pilot-005-empleo-publico.


def _labeled_claim(
    *,
    display_value: str,
    public_columns: tuple[str, ...],
    label: str | None,
    label_status: str,
) -> BuiltClaim:
    return BuiltClaim(
        claim_type="direct",
        description="Total",
        raw_value=Decimal(display_value.replace(".", "")),
        display_value=display_value,
        unit=None,
        rounding=0,
        formula=None,
        source_row_indexes=(0,),
        columns_used=("dim_1",),
        source_hash="sha256:test",
        public_columns=public_columns,
        label=label,
        label_status=label_status,
    )


def _mixed_claims() -> ClaimsBuildResult:
    return ClaimsBuildResult(
        claims=(
            _labeled_claim(
                display_value="30",
                public_columns=("categoria_a",),
                label="Categoria a",
                label_status="verified",
            ),
            _labeled_claim(
                display_value="12",
                public_columns=("categoria_b",),
                label="Categoria b",
                label_status="verified",
            ),
            _labeled_claim(
                display_value="2025",
                public_columns=("anio_reporte",),
                label="Anio reporte",
                label_status="verified",
            ),
            _labeled_claim(
                display_value="00042",
                public_columns=("codigo_interno",),
                label="Codigo interno",
                label_status="verified",
            ),
        ),
        rejected=(),
    )


def test_deterministic_fallback_labels_each_verified_claim() -> None:
    from app.agent.deterministic_runtime import _deterministic_synthesis

    intent = IntentExtraction(
        topic="composición del personal por categoría", operation=QueryOperation.SUM
    )
    synthesis = _deterministic_synthesis(_mixed_claims(), intent)

    assert "Categoria a: 30" in synthesis.answer
    assert "Categoria b: 12" in synthesis.answer


def test_deterministic_fallback_excludes_temporal_and_auxiliary_by_default() -> None:
    from app.agent.deterministic_runtime import _deterministic_synthesis

    intent = IntentExtraction(
        topic="composición del personal por categoría", operation=QueryOperation.SUM
    )
    synthesis = _deterministic_synthesis(_mixed_claims(), intent)

    assert "2025" not in synthesis.answer
    assert "00042" not in synthesis.answer
    assert 0 in synthesis.cited_claim_indexes
    assert 1 in synthesis.cited_claim_indexes
    assert 2 not in synthesis.cited_claim_indexes
    assert 3 not in synthesis.cited_claim_indexes


def test_deterministic_fallback_includes_temporal_when_explicitly_requested() -> None:
    from app.agent.deterministic_runtime import _deterministic_synthesis

    intent = IntentExtraction(
        topic="composición del personal por categoría",
        operation=QueryOperation.SUM,
        administrative_terms=("año",),
    )
    synthesis = _deterministic_synthesis(_mixed_claims(), intent)

    assert 2 in synthesis.cited_claim_indexes


def test_deterministic_fallback_marks_ambiguous_claim_without_inventing_label() -> None:
    from app.agent.deterministic_runtime import _deterministic_synthesis

    claims = ClaimsBuildResult(
        claims=(
            BuiltClaim(
                claim_type="derived",
                description="Tasa",
                raw_value=Decimal("8.4"),
                display_value="8,4 %",
                unit="%",
                rounding=1,
                formula={"op": "div", "args": [{"col": "a"}, {"col": "b"}]},
                source_row_indexes=(0,),
                columns_used=("dim_1", "dim_2"),
                source_hash="sha256:test",
                public_columns=("categoria_a", "categoria_b"),
                label=None,
                label_status="ambiguous",
            ),
        ),
        rejected=(),
    )
    intent = IntentExtraction(topic="tasa combinada", operation=QueryOperation.SUM)
    synthesis = _deterministic_synthesis(claims, intent)

    assert "8,4 %" in synthesis.answer
    assert "sin etiqueta verificable" in synthesis.answer
    # Nunca inventa una categoría combinando "categoria_a"/"categoria_b".
    assert "categoria_a" not in synthesis.answer
    assert "categoria_b" not in synthesis.answer
