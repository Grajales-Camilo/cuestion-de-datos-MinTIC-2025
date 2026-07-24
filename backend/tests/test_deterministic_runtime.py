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
    SynthesisIntegrityError,
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
    fail_first_profile: bool = False,
):
    executions = 0
    plans = 0
    syntheses = 0
    explorations = 0
    profiles = 0

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
        nonlocal profiles
        profiles += 1
        if fail_first_profile and profiles == 1:
            raise LookupError("dataset excede el máximo de columnas soportado")
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

    async def explore(profile, selection, explored, max_tool_calls) -> ExploredColumnValues:
        nonlocal explorations
        del profile, selection, explored, max_tool_calls
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
async def test_runtime_rejects_candidate_when_profiling_fails() -> None:
    """Un esquema no perfilable (p. ej. un dataset con más columnas que
    MAX_COLUMNS_PER_CANDIDATE) debe rechazar ÚNICAMENTE ese candidato y
    seguir con el siguiente, no propagar la excepción sin clasificar y
    tumbar la corrida entera (golden-v2 pilot-016-codigos-postales:
    `kg4b-vx7j` con 317 columnas producía un `ValidationError` no capturado
    que el arnés registraba como `terminal_error_code=INTERNAL`)."""

    result = await run_deterministic_agent(
        "¿Cuál es el total en Pasto?",
        dependencies=_dependencies(
            candidates=2,
            fail_first_profile=True,
        ),
    )

    assert result.status == "completed"
    select_candidate_entries = [
        entry for entry in result.trace if entry.node is SupervisorNode.SELECT_CANDIDATE
    ]
    assert len(select_candidate_entries) == 2
    assert select_candidate_entries[1].diagnostic_code == "PROFILING_ERROR"
    profile_dataset_entries = [
        entry for entry in result.trace if entry.node is SupervisorNode.PROFILE_DATASET
    ]
    assert [entry.candidate_index for entry in profile_dataset_entries] == [0, 1]


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
async def test_runtime_reads_published_quantity_instead_of_counting_matching_rows() -> None:
    columns = (
        ColumnOption(
            index=0,
            field_name="a_o",
            display_name="Año",
            data_type=ColumnDataType.INTEGER,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
        ColumnOption(
            index=1,
            field_name="cantidad",
            display_name="Cantidad",
            data_type=ColumnDataType.INTEGER,
            pii_risk_level=PiiRiskLevel.LOW,
        ),
    )
    profiled = ProfiledCandidate(
        option=DatasetOption(
            index=0,
            dataset_id="qty1-2345",
            title="Personas socializadas",
            publisher="Entidad oficial",
            columns=columns,
        ),
        schema=ObservedDatasetSchema(
            dataset_id="qty1-2345",
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
        ),
    )

    async def extract(_question: str) -> IntentExtraction:
        return IntentExtraction(topic="personas socializadas", operation=QueryOperation.COUNT)

    async def retrieve(_intent_arg: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(
            queries=("personas socializadas",),
            candidates=(_candidate("qty1-2345"),),
        )

    async def profile(_dataset_id: str) -> ProfiledCandidate:
        return profiled

    async def plan(intent_arg, _context, _explored, _error) -> EnumeratedPlanSelection:
        assert intent_arg.operation is QueryOperation.LOOKUP
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.COUNT,
            metrics=(MetricChoice(operation=QueryOperation.COUNT),),
            limit=1,
        )

    async def execute(validated) -> DeterministicExecutionResult:
        assert validated.operation is QueryOperation.LOOKUP
        assert validated.metrics == ()
        assert "cantidad" in [item.field_name for item in validated.dimensions]
        return _execution()

    async def explore(*_args, **_kwargs):
        raise AssertionError("la lectura directa no requiere exploración")

    async def synthesize(_intent_arg, _claims) -> GroundedSynthesis:
        return GroundedSynthesis(
            answer="La cantidad observada fue 42.",
            cited_claim_indexes=(0,),
        )

    result = await run_deterministic_agent(
        "¿Cuántas personas socializadas se reportaron?",
        dependencies=DeterministicRuntimeDependencies(
            extract,
            retrieve,
            profile,
            plan,
            explore,
            execute,
            synthesize,
        ),
    )

    assert result.status == "completed"


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
        # T-617B-C3 (1): atribución causal exclusiva explícita.
        "¿Qué política causó por sí sola la reducción de la pobreza en cada barrio de Colombia?",
        # T-617B-C3 (2): paráfrasis genérica de atribución causal fuerte,
        # sin repetir "causó ... por sí sola" ni el texto de ningún piloto.
        "¿Qué intervención fue la única causa del descenso en la tasa de mortalidad infantil?",
        # T-617B-C3 (3): polarización en redes sociales.
        "¿Cuál es la polarización de la ciudadanía en redes sociales frente a las políticas "
        "de educación en Antioquia?",
        # T-617B-C3 (4): sentimiento ciudadano en publicaciones/comentarios digitales.
        "¿Cuál es el sentimiento ciudadano expresado en los comentarios digitales sobre la "
        "reforma tributaria?",
        # T-617B-C13 (pilot-010-negativo-causalidad-barrial): atribución
        # causal simple (sin exclusividad explícita) a granularidad de
        # barrio, más fina que la que publica el catálogo.
        "¿En qué barrio la deserción escolar fue causada por el PAE durante junio de 2026?",
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


# --- T-617B-C3: guard determinista de capacidades analíticas no respaldadas --
# (causalidad exclusiva, análisis de sentimiento/polarización en redes
# sociales). Reglas por capacidad, nunca por `case_id`, dataset ni texto
# literal de un piloto concreto.


def _exploding_dependencies() -> DeterministicRuntimeDependencies:
    """Doble que falla ruidosamente si `extract_intent` o `retrieve` llegan
    a invocarse. Usado para demostrar que el guard de T-617B-C3 corta el
    flujo ANTES de esas dos dependencias — cero llamadas LLM, cero
    candidatos, cero evidencia, cero claims por construcción."""

    async def extract(_question: str) -> IntentExtraction:
        raise AssertionError("extract_intent no debe invocarse tras el guard de T-617B-C3")

    async def retrieve(_intent: IntentExtraction) -> MultiQueryRetrievalResult:
        raise AssertionError("retrieve no debe invocarse tras el guard de T-617B-C3")

    async def profile(_dataset_id: str) -> ProfiledCandidate:
        raise AssertionError("profile no debe invocarse tras el guard de T-617B-C3")

    async def plan(*_args, **_kwargs):
        raise AssertionError("plan no debe invocarse tras el guard de T-617B-C3")

    async def explore(*_args, **_kwargs):
        raise AssertionError("explore no debe invocarse tras el guard de T-617B-C3")

    async def execute(*_args, **_kwargs):
        raise AssertionError("execute no debe invocarse tras el guard de T-617B-C3")

    async def synthesize(*_args, **_kwargs):
        raise AssertionError("synthesize no debe invocarse tras el guard de T-617B-C3")

    return DeterministicRuntimeDependencies(
        extract, retrieve, profile, plan, explore, execute, synthesize
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    (
        "¿Qué política causó por sí sola la reducción de la pobreza en cada barrio de Colombia?",
        "¿Qué intervención fue la única causa del descenso en la tasa de mortalidad infantil?",
        "¿Cuál es la polarización de la ciudadanía en redes sociales frente a las políticas "
        "de educación en Antioquia?",
        "¿Cuál es el sentimiento ciudadano expresado en los comentarios digitales sobre la "
        "reforma tributaria?",
    ),
)
async def test_unsupported_capability_guard_never_invokes_dependencies(question: str) -> None:
    """T-617B-C3 (10): dobles explosivos prueban que ni `extract_intent` ni
    `retrieve` (ni ningún paso posterior) se invocan cuando el guard
    dispara — la abstención ocurre estrictamente antes de esas
    dependencias."""

    result = await run_deterministic_agent(question, dependencies=_exploding_dependencies())

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.NO_CANDIDATES
    assert result.usage.llm_calls == 0
    assert result.retrieval.candidates == ()
    assert result.execution is None
    assert result.synthesis is None
    assert [entry.node for entry in result.trace] == [SupervisorNode.ABSTAIN]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    (
        # T-617B-C3 (5): pregunta descriptiva sobre una política pública.
        "¿Qué política de vivienda aplica el municipio de Pasto?",
        # T-617B-C3 (6): tasa educativa en Antioquia (sin causalidad ni redes).
        "¿Cuál fue la tasa de deserción escolar en Antioquia en 2011?",
        # T-617B-C3 (7): "red vial" no es una red social.
        "¿Cuántos kilómetros de la red vial secundaria están pavimentados en el departamento?",
        # T-617B-C3 (8): asociación/comparación descriptiva sin atribución causal.
        "¿Cómo se relaciona la tasa de deserción escolar con el nivel de pobreza municipal?",
        # T-617B-C3 (9): "social" fuera del contexto de redes sociales.
        "¿Cuál es el gasto social ejecutado por el municipio en 2023?",
        # T-617B-C3 (corrección de sobrebloqueo): "principal causa" es
        # descriptivo (categoría más frecuente en una columna de causa), no
        # atribución exclusiva — "principal" no equivale a "única".
        "¿Cuál fue la principal causa de accidentes registrada por la entidad?",
        "¿Qué causa aparece con mayor frecuencia en el registro?",
        # T-617B-C5: controles literales pedidos por la auditoría consolidada.
        "¿Existe asociación entre cobertura educativa y deserción?",
        "¿Cuál es el estado de la red vial?",
        "¿Cuál fue el gasto social?",
        "¿Cuál es la opinión registrada por los usuarios de la biblioteca?",
        "¿Cuántas publicaciones existen en redes sociales por mes?",
    ),
)
async def test_unsupported_capability_guard_does_not_block_descriptive_questions(
    question: str,
) -> None:
    """Controles anti-sobrebloqueo: estas preguntas deben seguir su curso
    normal hasta `extract_intent`/`retrieve` (el guard no las intercepta),
    aunque contengan palabras sueltas como "política", "social", "red",
    "efecto" o "relación" que por sí solas no deben activar ninguna regla."""

    intent = IntentExtraction(topic=question, operation=QueryOperation.LOOKUP)
    result = await run_deterministic_agent(
        question,
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_relevant_claim("1"),), rejected=()),),
        ),
    )

    assert result.status == "completed"
    assert result.usage.llm_calls > 0
    assert result.retrieval.candidates != ()


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
async def test_runtime_finishes_deterministically_when_plan_uses_last_llm_call() -> None:
    result = await run_deterministic_agent(
        "¿Cuál es el total?",
        dependencies=_dependencies(),
        budgets=SupervisorBudgets(max_llm_calls=2),
    )

    assert result.status == "completed"
    assert result.usage.llm_calls == 2
    assert result.execution is not None
    assert result.synthesis is not None
    assert "Total: 42" in result.synthesis.answer


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
async def test_runtime_types_synthesis_that_remains_invalid_after_fallback(monkeypatch) -> None:
    from app.agent import deterministic_runtime

    monkeypatch.setattr(
        deterministic_runtime,
        "_deterministic_synthesis",
        lambda claims, intent: GroundedSynthesis(
            answer="El total observado fue 16.",
            cited_claim_indexes=(0,),
        ),
    )

    with pytest.raises(SynthesisIntegrityError, match="cifras huérfanas.*16"):
        await run_deterministic_agent(
            "¿Cuál es el total?",
            dependencies=_dependencies(invalid_synthesis_first=True),
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
async def test_runtime_passes_only_remaining_exploration_budget() -> None:
    dependencies = _dependencies(text_filter=True)
    observed_budgets: list[int] = []

    async def explore(profile, selection, explored, max_tool_calls) -> ExploredColumnValues:
        del profile, selection, explored
        observed_budgets.append(max_tool_calls)
        return ExploredColumnValues(
            column_index=1,
            search_term="Pasto",
            values=("PASTO",),
            tool_calls=max_tool_calls,
        )

    dependencies = DeterministicRuntimeDependencies(
        dependencies.extract_intent,
        dependencies.retrieve,
        dependencies.profile,
        dependencies.plan,
        explore,
        dependencies.execute,
        dependencies.synthesize,
    )
    result = await run_deterministic_agent(
        "¿Cuál es el total en Pasto?",
        dependencies=dependencies,
        budgets=SupervisorBudgets(max_explorations=2),
    )

    assert result.status == "completed"
    assert result.usage.explorations == 2
    assert observed_budgets == [2]


@pytest.mark.asyncio
async def test_runtime_does_not_require_categorical_exploration_for_text_ne_filter() -> None:
    dependencies = _dependencies()

    async def plan(intent, context, explored, error):
        del intent, context, explored, error
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=0),),
            filters=(
                FilterChoice(
                    column_index=1,
                    operator=FilterOperator.NE,
                    value_type=ScalarType.TEXT,
                    values=("Bogotá",),
                ),
            ),
        )

    dependencies = DeterministicRuntimeDependencies(
        dependencies.extract_intent,
        dependencies.retrieve,
        dependencies.profile,
        plan,
        dependencies.explore,
        dependencies.execute,
        dependencies.synthesize,
    )
    result = await run_deterministic_agent(
        "¿Cuál es el total fuera de Bogotá?",
        dependencies=dependencies,
    )

    assert result.status == "completed"
    assert result.usage.explorations == 0


@pytest.mark.asyncio
async def test_runtime_canonicalizes_explored_values_without_diacritics() -> None:
    dependencies = _dependencies(text_filter=True)

    async def explore(profile, selection, explored, max_tool_calls) -> ExploredColumnValues:
        del profile, selection, explored, max_tool_calls
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


# --- T-617B-C2: abstención determinista ante evidencia temáticamente ------
# irrelevante (RF-205/RF-211). Fixtures genéricas: ningún nombre de columna,
# `case_id` ni dataset concreto de la suite golden aparece aquí. La única
# señal es la clasificación léxica de columna ya aprobada en T-617C
# (`app.quality.claim_labels`) frente a los tokens de la intención.


def _irrelevant_claim(display_value: str = "15") -> BuiltClaim:
    """Claim cuya única columna fuente es un identificador auxiliar
    (categoría léxica `auxiliary`, nunca solicitado por las intenciones de
    prueba a continuación)."""

    return _labeled_claim(
        display_value=display_value,
        public_columns=("codigo_referencia",),
        label="Codigo referencia",
        label_status="verified",
    )


def _relevant_claim(display_value: str = "42") -> BuiltClaim:
    """Claim cuya columna fuente no es auxiliar ni temporal (categoría
    `primary`): siempre pertinente, sin importar la intención."""

    return _labeled_claim(
        display_value=display_value,
        public_columns=("total_observado",),
        label="Total observado",
        label_status="verified",
    )


def _relevance_dependencies(
    *,
    intent: IntentExtraction,
    claims_by_candidate: tuple[ClaimsBuildResult, ...],
    textual_facts_by_candidate: tuple[tuple[str, ...], ...] | None = None,
    textual_rejections_by_candidate: tuple[tuple[object, ...], ...] | None = None,
    dataset_names_by_candidate: tuple[str | None, ...] | None = None,
) -> DeterministicRuntimeDependencies:
    """Doble local sin red ni LLM real: cada candidato recuperado, en orden,
    devuelve el `ClaimsBuildResult` correspondiente en `claims_by_candidate`,
    los hechos textuales aceptados (T-615F) en `textual_facts_by_candidate` y
    los rechazos textuales en `textual_rejections_by_candidate` — señales
    independientes entre sí: una tupla no vacía en cada una simula, en la
    posición del candidato, un hecho aceptado y/o un rechazo simultáneos.
    Su contenido no se inspecciona, sólo su presencia/ausencia."""

    textual_facts_source = textual_facts_by_candidate or tuple(() for _ in claims_by_candidate)
    textual_rejections_source = textual_rejections_by_candidate or tuple(
        () for _ in claims_by_candidate
    )
    dataset_names_source = dataset_names_by_candidate or tuple(None for _ in claims_by_candidate)

    async def extract(question: str) -> IntentExtraction:
        assert question
        return intent

    async def retrieve(_intent: IntentExtraction) -> MultiQueryRetrievalResult:
        return MultiQueryRetrievalResult(
            queries=("q",),
            candidates=tuple(
                _candidate(f"rlv{index}-cand") for index in range(len(claims_by_candidate))
            ),
        )

    async def profile(dataset_id: str) -> ProfiledCandidate:
        return _profile(dataset_id)

    async def plan(intent, context, explored, error):
        del intent, context, explored, error
        return EnumeratedPlanSelection(
            dataset_index=0,
            operation=QueryOperation.SUM,
            metrics=(MetricChoice(operation=QueryOperation.SUM, column_index=0),),
            filters=(),
        )

    calls = 0

    async def execute(validated) -> DeterministicExecutionResult:
        nonlocal calls
        del validated
        claims = claims_by_candidate[calls]
        textual_facts = textual_facts_source[calls]
        textual_rejections = textual_rejections_source[calls]
        dataset_name = dataset_names_source[calls]
        calls += 1
        return cast(
            DeterministicExecutionResult,
            SimpleNamespace(
                quality=SimpleNamespace(eligibility_status="eligible"),
                claims=claims,
                textual_facts=textual_facts,
                textual_rejections=textual_rejections,
                evidence_draft=SimpleNamespace(dataset_name=dataset_name),
            ),
        )

    async def explore(profile, selection, explored, max_tool_calls) -> ExploredColumnValues:
        raise AssertionError("este doble no requiere exploración de valores")

    async def synthesize(intent, claims) -> GroundedSynthesis:
        del intent
        return GroundedSynthesis(
            answer="Resultado calculado con la evidencia consultada.",
            cited_claim_indexes=tuple(range(len(claims.claims))),
        )

    return DeterministicRuntimeDependencies(
        extract, retrieve, profile, plan, explore, execute, synthesize
    )


@pytest.mark.asyncio
async def test_runtime_abstains_when_only_evidence_is_eligible_but_irrelevant() -> None:
    """Evidencia técnicamente elegible (`eligibility_status="eligible"`) pero
    cuyos claims no derivan de ninguna columna pertinente a la intención debe
    terminar en abstención, no en `completed` con claims irrelevantes."""

    intent = IntentExtraction(
        topic="composición del personal por categoría", operation=QueryOperation.SUM
    )
    result = await run_deterministic_agent(
        "¿Cuál es la composición del personal por categoría?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),),
        ),
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE
    assert result.synthesis is None


@pytest.mark.asyncio
async def test_runtime_causal_question_without_causal_evidence_abstains_cleanly() -> None:
    """Pregunta de tono causal (sin exclusividad explícita, así que no la
    intercepta el guard previo de T-617B-C3) cuya única evidencia recuperada
    es ajena a la intención: debe producir abstención limpia vía la puerta
    de relevancia post-recuperación (T-617B-C2), sin narrativa cuantitativa
    inventada."""

    intent = IntentExtraction(
        topic="qué factores explican la reducción de un fenómeno social",
        operation=QueryOperation.LOOKUP,
    )
    result = await run_deterministic_agent(
        "¿Qué factores explican la reducción de un fenómeno social?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim("88"),), rejected=()),
            ),
        ),
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE


@pytest.mark.asyncio
async def test_runtime_network_analysis_question_without_network_evidence_abstains_cleanly() -> (
    None
):
    """Pregunta sobre redes sociales sin pedir polarización/sentimiento
    (así que no la intercepta el guard previo de T-617B-C3) cuya evidencia
    recuperada (identificadores administrativos) es ajena a la intención:
    debe abstenerse vía la puerta de relevancia post-recuperación
    (T-617B-C2), no replegarse a una narrativa irrelevante."""

    intent = IntentExtraction(
        topic="uso de redes sociales por parte de la ciudadanía frente a una política",
        operation=QueryOperation.LOOKUP,
    )
    result = await run_deterministic_agent(
        "¿Cómo usa la ciudadanía las redes sociales frente a esta política?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_irrelevant_claim("5"),), rejected=()),),
        ),
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE


@pytest.mark.asyncio
async def test_runtime_completes_and_preserves_claims_when_evidence_is_materially_relevant() -> (
    None
):
    """Control positivo: evidencia cuyas columnas sí son pertinentes a la
    intención debe completarse normalmente y conservar sus claims."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_relevant_claim(),), rejected=()),),
        ),
    )

    assert result.status == "completed"
    assert result.execution is not None
    assert [claim.display_value for claim in result.execution.claims.claims] == ["42"]


@pytest.mark.asyncio
async def test_runtime_completes_with_partially_relevant_evidence() -> None:
    """RF-211: una evidencia con claims mixtos (uno pertinente, uno auxiliar
    no solicitado) sigue produciendo una respuesta entregable — pertinencia
    parcial no es lo mismo que irrelevancia total."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    mixed = ClaimsBuildResult(claims=(_relevant_claim(), _irrelevant_claim()), rejected=())
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(intent=intent, claims_by_candidate=(mixed,)),
    )

    assert result.status == "completed"
    assert result.execution is not None
    assert len(result.execution.claims.claims) == 2


@pytest.mark.asyncio
async def test_runtime_tries_next_candidate_before_abstaining_on_irrelevant_claims() -> None:
    """El rechazo por pertinencia queda trazado: el primer candidato se
    marca rechazado y sólo se abstiene tras agotar los candidatos, igual que
    el patrón ya existente para `evidence_eligible`."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),
                ClaimsBuildResult(claims=(_relevant_claim(),), rejected=()),
            ),
        ),
    )

    assert result.status == "completed"
    next_candidate_reasons = [
        entry.reason for entry in result.trace if entry.node is SupervisorNode.NEXT_CANDIDATE
    ]
    assert any("pertinente" in reason for reason in next_candidate_reasons)
    assert sum(entry.node is SupervisorNode.SELECT_CANDIDATE for entry in result.trace) == 2


@pytest.mark.asyncio
async def test_rejected_candidate_reason_surfaces_on_next_select_candidate() -> None:
    """T-617B-C13-D6 (pilot-025/pilot-026, golden-v2): un candidato rechazado
    perdía su razón exacta en cuanto `current` volvía a `None` -- el evento
    `select_candidate` siguiente quedaba con `diagnostic_code=None`
    (`plan_validation_errors=[]` en el evento persistido, ver runner.py),
    haciendo irreconstruible por qué se abandonó el dataset correcto. Ahora
    la razón de `NEXT_CANDIDATE` se propaga una sola vez al siguiente
    `select_candidate`."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),
                ClaimsBuildResult(claims=(_relevant_claim(),), rejected=()),
            ),
        ),
    )

    assert result.status == "completed"
    next_candidate_index = next(
        index
        for index, entry in enumerate(result.trace)
        if entry.node is SupervisorNode.NEXT_CANDIDATE
    )
    following_select_candidate = result.trace[next_candidate_index + 1]
    assert following_select_candidate.node is SupervisorNode.SELECT_CANDIDATE
    assert following_select_candidate.diagnostic_code == (result.trace[next_candidate_index].reason)


@pytest.mark.asyncio
async def test_runtime_abstains_cleanly_when_all_candidates_are_irrelevant() -> None:
    """Trazabilidad de datasets revisados/rechazados: con dos candidatos
    ajenos a la intención, ambos quedan rechazados por pertinencia antes de
    la abstención final."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim("1"),), rejected=()),
                ClaimsBuildResult(claims=(_irrelevant_claim("2"),), rejected=()),
            ),
        ),
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE
    next_candidate_count = sum(
        entry.node is SupervisorNode.NEXT_CANDIDATE for entry in result.trace
    )
    assert next_candidate_count == 1
    assert result.execution is not None


@pytest.mark.asyncio
async def test_runtime_rejects_fallback_candidate_with_unrelated_dataset_name() -> None:
    """T-617B-C13 (RF-205/RF-211): reproduce golden-v1 pilot-026/027 -- un
    candidato de repliegue (`current > 0`, ya se rechazó el primero) cuyo
    claim es léxicamente "primary" (pasa `claim_is_relevant_to_narrative`,
    igual que antes de esta corrección) pero cuyo dataset publicado no tiene
    relación temática con la intención debe rechazarse también, no completar
    con una narrativa de tema ajeno."""

    intent = IntentExtraction(
        topic="paridad de género en cargos directivos", operation=QueryOperation.SUM
    )
    result = await run_deterministic_agent(
        "¿Cuál es la paridad de género en cargos directivos?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),
                ClaimsBuildResult(claims=(_relevant_claim(),), rejected=()),
            ),
            dataset_names_by_candidate=(None, "Deserción escolar por departamento"),
        ),
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE


@pytest.mark.asyncio
async def test_runtime_accepts_fallback_candidate_whose_dataset_name_matches_topic() -> None:
    """Control: el mismo candidato de repliegue completa normalmente cuando
    su dataset publicado sí comparte tema con la intención."""

    intent = IntentExtraction(
        topic="paridad de género en cargos directivos", operation=QueryOperation.SUM
    )
    result = await run_deterministic_agent(
        "¿Cuál es la paridad de género en cargos directivos?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),
                ClaimsBuildResult(claims=(_relevant_claim(),), rejected=()),
            ),
            dataset_names_by_candidate=(
                None,
                "Paridad de género en cargos directivos del sector público",
            ),
        ),
    )

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_runtime_rejects_fallback_candidate_textual_facts_from_unrelated_dataset() -> None:
    """T-617B-C13-D9 (golden-v2, pilot-018-transporte-ferreo): un candidato de
    repliegue (`current > 0`) cuyos claims cuantitativos ya se descartan por
    pertinencia (`claims_materially_relevant=False`) no debía poder colarse
    de todos modos vía `textual_result_available`, que antes se calculaba sin
    ningún chequeo de tema -- `decide_next_transition` avanza a
    PERSIST_FACTS con `claims_materially_relevant OR textual_result_available`,
    así que un hecho textual de un dataset sin relación temática bastaba para
    completar la síntesis con evidencia ajena a la pregunta. Ahora la misma
    señal de solapamiento de tema apaga ambas banderas a la vez."""

    intent = IntentExtraction(topic="concesiones y operadores", operation=QueryOperation.LOOKUP)
    result = await run_deterministic_agent(
        "¿Qué concesiones y operadores movilizaron carga férrea el 13 de octubre de 2023?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),
                ClaimsBuildResult(claims=(_irrelevant_claim("2"),), rejected=()),
            ),
            textual_facts_by_candidate=((), ("GRANEL LIQUIDO",)),
            dataset_names_by_candidate=(None, "Tráfico Portuario Marítimo en Colombia"),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE


@pytest.mark.asyncio
async def test_runtime_accepts_fallback_textual_facts_when_dataset_matches_topic() -> None:
    """Control: el mismo hecho textual de repliegue completa normalmente
    cuando su dataset publicado sí comparte tema con la intención."""

    intent = IntentExtraction(topic="concesiones y operadores", operation=QueryOperation.LOOKUP)
    result = await run_deterministic_agent(
        "¿Qué concesiones y operadores movilizaron carga férrea el 13 de octubre de 2023?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),
                ClaimsBuildResult(claims=(_irrelevant_claim("2"),), rejected=()),
            ),
            textual_facts_by_candidate=((), ("FENOCO",)),
            dataset_names_by_candidate=(None, "Concesiones y operadores de carga férrea"),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "ready_for_synthesis"


@pytest.mark.asyncio
async def test_runtime_does_not_apply_dataset_name_check_to_top_ranked_candidate() -> None:
    """El chequeo de nombre de dataset es exclusivo de candidatos de
    repliegue (`current > 0`); el candidato mejor rankeado (`current == 0`)
    conserva exactamente el comportamiento previo, sin este chequeo
    adicional -- evita romper casos ya aprobados cuyo dataset correcto no
    repite literalmente el tema de la pregunta en su nombre publicado."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_relevant_claim(),), rejected=()),),
            dataset_names_by_candidate=("Dataset totalmente ajeno al tema",),
        ),
    )

    assert result.status == "completed"


# --- T-617B-C2 (corrección): la ruta de síntesis diferida (T-615F,
# `defer_synthesis_until_persisted=True`) tiene su propia rama de transición
# a PERSIST_FACTS que, antes de esta corrección, no consultaba
# `claims_materially_relevant` y dejaba pasar claims irrelevantes a
# persistencia. Las pruebas siguientes fijan ese comportamiento en ambos
# modos (diferido e inmediato) sin bloquear un hecho textual pertinente.


@pytest.mark.asyncio
async def test_deferred_mode_with_only_irrelevant_claims_never_reaches_persist_facts() -> None:
    """Reproducción del hueco reportado: en modo diferido, un único candidato
    con claims irrelevantes y sin hecho textual debe terminar en NEXT_CANDIDATE
    seguido de ABSTAIN — nunca en PERSIST_FACTS/`ready_for_synthesis`."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "abstained"
    assert result.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE
    assert all(entry.node is not SupervisorNode.PERSIST_FACTS for entry in result.trace)


@pytest.mark.asyncio
async def test_deferred_mode_tries_next_candidate_and_persists_the_relevant_one() -> None:
    """Modo diferido + siguiente candidato relevante: el primer candidato
    (irrelevante) se rechaza y el segundo (relevante) sí llega a
    PERSIST_FACTS/`ready_for_synthesis`, con solo su propio claim expuesto."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(
                ClaimsBuildResult(claims=(_irrelevant_claim("1"),), rejected=()),
                ClaimsBuildResult(claims=(_relevant_claim("42"),), rejected=()),
            ),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "ready_for_synthesis"
    assert result.trace[-1].node is SupervisorNode.PERSIST_FACTS
    assert result.execution is not None
    # El claim del candidato rechazado ("1") no sobrevive: el estado de
    # ejecución se resetea en cada NEXT_CANDIDATE (ver `_replace_status` +
    # reseteo de `execution` en `run_deterministic_agent`), así que sólo
    # queda expuesto el claim del candidato aceptado.
    assert [claim.display_value for claim in result.execution.claims.claims] == ["42"]


@pytest.mark.asyncio
async def test_deferred_mode_preserves_pertinent_textual_fact_despite_irrelevant_claim() -> None:
    """Un claim cuantitativo irrelevante coexiste con un hecho textual
    (T-615F) pertinente en la misma evidencia: la persistencia no debe
    bloquearse — el hecho textual pertinente se conserva."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),),
            textual_facts_by_candidate=(("hecho textual pertinente",),),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "ready_for_synthesis"
    assert result.trace[-1].node is SupervisorNode.PERSIST_FACTS
    assert result.execution is not None
    assert tuple(result.execution.textual_facts) == ("hecho textual pertinente",)
    # El claim cuantitativo irrelevante viaja junto al hecho textual dentro
    # de `execution` (persistencia interna, T-615F reverifica antes de
    # exponer), pero la decisión de transición ya no lo trata como
    # justificación por sí solo: sólo pasó porque había hecho textual.
    assert [claim.display_value for claim in result.execution.claims.claims] == ["15"]


# --- T-617B-C2 (corrección R3): un rechazo textual puro no puede disfrazarse
# de "resultado textual pertinente". `textual_result_available` debe reflejar
# únicamente hechos textuales ACEPTADOS; `textual_rejected` es la señal
# independiente para rechazos. Antes de esta corrección,
# `textual_result_available = bool(textual_facts or textual_rejections)`
# permitía que un candidato con solo rechazos (sin ningún hecho aceptado)
# habilitara la persistencia de un claim cuantitativo irrelevante.


@pytest.mark.asyncio
async def test_deferred_mode_with_irrelevant_claim_and_only_textual_rejection_never_persists() -> (
    None
):
    """Reproducción del hueco reportado: claim irrelevante + único candidato
    con SOLO rechazo textual (sin hecho aceptado) + modo diferido. Debe
    terminar en NEXT_CANDIDATE/ABSTAIN — nunca en PERSIST_FACTS."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),),
            textual_rejections_by_candidate=((SimpleNamespace(code="rechazo_textual"),),),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "abstained"
    assert all(entry.node is not SupervisorNode.PERSIST_FACTS for entry in result.trace)


@pytest.mark.asyncio
async def test_deferred_mode_preserves_accepted_fact_despite_simultaneous_rejection() -> None:
    """Claim irrelevante + hecho textual ACEPTADO + rechazo textual
    simultáneo en la misma evidencia (pueden coexistir: T-615F puede aceptar
    unos hechos y rechazar otros dentro de la misma corrida). El hecho
    aceptado se preserva; la coexistencia con un rechazo no bloquea nada
    nuevo más allá de lo que ya bloqueaba `textual_rejected` por sí solo."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_irrelevant_claim(),), rejected=()),),
            textual_facts_by_candidate=(("hecho aceptado",),),
            textual_rejections_by_candidate=((SimpleNamespace(code="rechazo_simultaneo"),),),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "ready_for_synthesis"
    assert result.trace[-1].node is SupervisorNode.PERSIST_FACTS
    assert result.execution is not None
    assert tuple(result.execution.textual_facts) == ("hecho aceptado",)
    assert [r.code for r in result.execution.textual_rejections] == ["rechazo_simultaneo"]


@pytest.mark.asyncio
async def test_relevant_claim_with_textual_rejection_still_persists_the_claim() -> None:
    """Comportamiento existente preservado: un claim cuantitativo pertinente
    sigue persistiéndose aunque exista un rechazo textual simultáneo — el
    rechazo textual nunca bloqueó la vía cuantitativa válida, con o sin este
    incremento."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    result = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent,
            claims_by_candidate=(ClaimsBuildResult(claims=(_relevant_claim("42"),), rejected=()),),
            textual_rejections_by_candidate=((SimpleNamespace(code="rechazo_textual"),),),
        ),
        defer_synthesis_until_persisted=True,
    )

    assert result.status == "ready_for_synthesis"
    assert result.trace[-1].node is SupervisorNode.PERSIST_FACTS
    assert result.execution is not None
    assert [claim.display_value for claim in result.execution.claims.claims] == ["42"]


@pytest.mark.asyncio
async def test_rejected_candidate_claims_never_reach_the_accepted_execution() -> None:
    """Los claims del candidato rechazado por pertinencia no aparecen en la
    respuesta pública: `execution` sólo refleja el candidato finalmente
    aceptado, en modo inmediato (`completed`) y en modo diferido
    (`ready_for_synthesis`) por igual."""

    intent = IntentExtraction(topic="total observado en el catálogo", operation=QueryOperation.SUM)
    claims_by_candidate = (
        ClaimsBuildResult(claims=(_irrelevant_claim("999"),), rejected=()),
        ClaimsBuildResult(claims=(_relevant_claim("42"),), rejected=()),
    )

    immediate = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent, claims_by_candidate=claims_by_candidate
        ),
    )
    deferred = await run_deterministic_agent(
        "¿Cuál es el total observado en el catálogo?",
        dependencies=_relevance_dependencies(
            intent=intent, claims_by_candidate=claims_by_candidate
        ),
        defer_synthesis_until_persisted=True,
    )

    for result in (immediate, deferred):
        assert result.execution is not None
        display_values = [claim.display_value for claim in result.execution.claims.claims]
        assert "999" not in display_values
        assert display_values == ["42"]
