"""Runtime del agente v2 gobernado por el supervisor determinista.

El runtime coordina I/O mediante dependencias inyectadas; las decisiones de
transición siguen siendo exclusivas de ``decide_next_transition``.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.agent.deterministic_graph import (
    CandidateProgress,
    CandidateStatus,
    StopReason,
    SupervisorBudgets,
    SupervisorNode,
    SupervisorSnapshot,
    SupervisorUsage,
    decide_next_transition,
)
from app.agent.deterministic_pipeline import (
    DeterministicExecutionError,
    DeterministicExecutionResult,
)
from app.agent.llm_contracts import (
    EnumeratedPlanSelection,
    FilterChoice,
    GroundedSynthesis,
    IntentExtraction,
    ground_intent_topic_in_question,
    materialize_query_plan,
    normalize_aggregate_intent,
    normalize_budget_snapshot,
    normalize_explicit_date_filter,
    normalize_intent_for_observed_schema,
    normalize_lookup_filters,
    normalize_lookup_output_columns,
    normalize_lookup_total_column,
    normalize_ranked_aggregate,
    normalize_sort_references,
    normalize_system_owned_operation,
    normalize_temporal_year_filters,
    validate_grounded_synthesis,
)
from app.agent.multiquery_retrieval import MultiQueryRetrievalResult
from app.agent.plan_validator import (
    ObservedDatasetSchema,
    PlanValidationCode,
    PlanValidationError,
    ValidatedQueryPlan,
    validate_query_plan,
)
from app.agent.query_plan import (
    DatasetOption,
    EnumeratedPlanningContext,
    FilterOperator,
    QueryOperation,
    ScalarType,
)
from app.llm.factory import LLMProviderError
from app.quality.claims import ClaimsBuildResult


@dataclass(frozen=True)
class ProfiledCandidate:
    option: DatasetOption
    schema: ObservedDatasetSchema

    @property
    def context(self) -> EnumeratedPlanningContext:
        return EnumeratedPlanningContext(candidates=(self.option,))


@dataclass(frozen=True)
class ExploredColumnValues:
    column_index: int
    search_term: str
    values: tuple[str, ...]
    tool_calls: int = 1


@dataclass(frozen=True)
class RuntimeTraceEntry:
    node: SupervisorNode
    reason: str
    candidate_index: int | None


@dataclass(frozen=True)
class DeterministicRuntimeResult:
    status: str
    stop_reason: StopReason | None
    intent: IntentExtraction
    retrieval: MultiQueryRetrievalResult
    execution: DeterministicExecutionResult | None
    synthesis: GroundedSynthesis | None
    trace: tuple[RuntimeTraceEntry, ...]
    usage: SupervisorUsage


class DeterministicRunCancelled(RuntimeError):
    pass


IntentExtractor = Callable[[str], Awaitable[IntentExtraction]]
Retriever = Callable[[IntentExtraction], Awaitable[MultiQueryRetrievalResult]]
Profiler = Callable[[str], Awaitable[ProfiledCandidate]]
Planner = Callable[
    [
        IntentExtraction,
        EnumeratedPlanningContext,
        tuple[ExploredColumnValues, ...],
        PlanValidationError | None,
    ],
    Awaitable[EnumeratedPlanSelection],
]
Explorer = Callable[
    [ProfiledCandidate, EnumeratedPlanSelection, tuple[ExploredColumnValues, ...]],
    Awaitable[ExploredColumnValues],
]
Executor = Callable[[ValidatedQueryPlan], Awaitable[DeterministicExecutionResult]]
Synthesizer = Callable[[IntentExtraction, ClaimsBuildResult], Awaitable[GroundedSynthesis]]
TransitionObserver = Callable[[RuntimeTraceEntry, SupervisorUsage], Awaitable[None]]


@dataclass(frozen=True)
class DeterministicRuntimeDependencies:
    extract_intent: IntentExtractor
    retrieve: Retriever
    profile: Profiler
    plan: Planner
    explore: Explorer
    execute: Executor
    synthesize: Synthesizer


def _replace_status(
    candidates: list[CandidateProgress], index: int, status: CandidateStatus
) -> None:
    candidates[index] = CandidateProgress(dataset_index=index, status=status)


def _text_filter_indexes(selection: EnumeratedPlanSelection) -> tuple[int, ...]:
    return tuple(
        dict.fromkeys(
            item.column_index
            for item in selection.filters
            if item.value_type is ScalarType.TEXT
            and item.operator in {FilterOperator.EQ, FilterOperator.IN}
            and item.values
        )
    )


def _requires_exploration(
    selection: EnumeratedPlanSelection | None,
    explored: tuple[ExploredColumnValues, ...],
) -> bool:
    if selection is None:
        return False
    explored_indexes = {item.column_index for item in explored}
    return any(
        index not in explored_indexes for index in _text_filter_indexes(selection)
    )


def _validate_explored_filters(
    selection: EnumeratedPlanSelection,
    explored: tuple[ExploredColumnValues, ...],
) -> None:
    allowed = {
        item.column_index: {_fold_text(value) for value in item.values}
        for item in explored
    }
    for item in selection.filters:
        if item.value_type is not ScalarType.TEXT or not item.values:
            continue
        values = allowed.get(item.column_index)
        if values is None:
            raise ValueError(f"column_index {item.column_index} requiere exploración")
        invalid = [value for value in item.values if _fold_text(value) not in values]
        if invalid:
            raise ValueError(
                f"valores no observados para column_index {item.column_index}: {invalid}"
            )


def _normalize_explored_filter_values(
    selection: EnumeratedPlanSelection,
    explored: tuple[ExploredColumnValues, ...],
) -> EnumeratedPlanSelection:
    allowed = {item.column_index: item.values for item in explored}
    normalized = []
    for item in selection.filters:
        values = allowed.get(item.column_index)
        if item.value_type is not ScalarType.TEXT or not values:
            normalized.append(item)
            continue
        canonical = {
            _fold_text(value): next(
                observed for observed in values if _fold_text(observed) == _fold_text(value)
            )
            for value in item.values
            if any(_fold_text(observed) == _fold_text(value) for observed in values)
        }
        normalized.append(
            item.model_copy(
                update={
                    "values": tuple(
                        canonical.get(_fold_text(value), value) for value in item.values
                    )
                }
            )
        )
    normalized_indexes = {item.column_index for item in normalized}
    normalized.extend(
        FilterChoice(
            column_index=item.column_index,
            operator=FilterOperator.EQ,
            value_type=ScalarType.TEXT,
            values=(item.values[0],),
        )
        for item in explored
        if item.values and item.column_index not in normalized_indexes
    )
    return selection.model_copy(update={"filters": tuple(normalized)})


def _fold_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def _deterministic_synthesis(claims: ClaimsBuildResult) -> GroundedSynthesis:
    selected = claims.claims[:8]
    values = "; ".join(
        f"{claim.display_value}{f' {claim.unit}' if claim.unit else ''}"
        for claim in selected
    )
    suffix = (
        " Hay resultados adicionales en la evidencia adjunta."
        if len(claims.claims) > 8
        else ""
    )
    return GroundedSynthesis(
        answer=f"Resultados calculados con la evidencia consultada: {values}.{suffix}",
        cited_claim_indexes=tuple(range(len(selected))),
    )


def _unsupported_question(question: str) -> bool:
    normalized = _fold_text(question)
    exact_prediction = re.search(
        r"\b(exactamente|pronostico|predecir|futuro|abandonaran|caera)\b",
        normalized,
    )
    real_time = re.search(
        r"\b(proximos?\s+\w+\s+minutos?|tiempo real|llegara primero)\b",
        normalized,
    )
    personal_rows = (
        "cada servidor" in normalized
        and all(term in normalized for term in ("nombre", "edad", "salario"))
    )
    medical_advice = (
        "tratamiento medico" in normalized
        and ("debe recibir" in normalized or "diagnostico" in normalized)
    )
    return bool(exact_prediction or real_time or personal_rows or medical_advice)


async def run_deterministic_agent(
    question: str,
    *,
    dependencies: DeterministicRuntimeDependencies,
    budgets: SupervisorBudgets | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    observe_transition: TransitionObserver | None = None,
) -> DeterministicRuntimeResult:
    """Ejecuta el ciclo completo sin permitir que el LLM elija transiciones."""

    limits = budgets or SupervisorBudgets()
    started = time.monotonic()
    if _unsupported_question(question):
        intent = IntentExtraction(topic=question, operation=QueryOperation.LOOKUP)
        retrieval = MultiQueryRetrievalResult(queries=(), candidates=())
        trace_entry = RuntimeTraceEntry(
            SupervisorNode.ABSTAIN,
            "solicitud fuera del alcance verificable",
            None,
        )
        usage = SupervisorUsage()
        if observe_transition is not None:
            await observe_transition(trace_entry, usage)
        return DeterministicRuntimeResult(
            "abstained",
            StopReason.NO_CANDIDATES,
            intent,
            retrieval,
            None,
            None,
            (trace_entry,),
            usage,
        )
    intent = await dependencies.extract_intent(question)
    intent = ground_intent_topic_in_question(intent, question)
    intent = normalize_aggregate_intent(intent, question)
    llm_calls = 1
    retrieval = await dependencies.retrieve(intent)
    candidates = [
        CandidateProgress(dataset_index=index)
        for index, _candidate in enumerate(retrieval.candidates[: limits.max_candidates])
    ]
    current: int | None = None
    profile: ProfiledCandidate | None = None
    selection: EnumeratedPlanSelection | None = None
    validated: ValidatedQueryPlan | None = None
    execution: DeterministicExecutionResult | None = None
    synthesis: GroundedSynthesis | None = None
    validation_error: PlanValidationError | None = None
    explored: tuple[ExploredColumnValues, ...] = ()
    explorations = queries = repairs = 0
    trace: list[RuntimeTraceEntry] = []

    while True:
        if is_cancelled is not None and is_cancelled():
            raise DeterministicRunCancelled("corrida cancelada")
        elapsed_ms = round((time.monotonic() - started) * 1000)
        snapshot = SupervisorSnapshot(
            candidates=tuple(candidates),
            current_candidate_index=current,
            schema_available=profile is not None,
            plan_available=selection is not None,
            plan_valid=validated is not None,
            plan_error_correctable=validation_error is not None,
            exploration_required=_requires_exploration(selection, explored),
            query_executed=execution is not None,
            evidence_eligible=(
                execution is not None and execution.quality.eligibility_status == "eligible"
            ),
            claims_available=execution is not None and bool(execution.claims.claims),
            synthesis_valid=synthesis is not None,
            budgets=limits,
            usage=SupervisorUsage(
                candidates=sum(
                    item.status is not CandidateStatus.UNSEEN for item in candidates
                ),
                explorations=explorations,
                queries=queries,
                plan_repairs=repairs,
                llm_calls=llm_calls,
                elapsed_ms=elapsed_ms,
            ),
        )
        transition = decide_next_transition(snapshot)
        trace_reason = transition.reason
        if transition.node is SupervisorNode.BUILD_PLAN and validation_error is not None:
            trace_reason = f"{trace_reason}: {validation_error.code.value}: {validation_error}"
        trace_entry = RuntimeTraceEntry(transition.node, trace_reason, current)
        trace.append(trace_entry)
        if observe_transition is not None:
            await observe_transition(trace_entry, snapshot.usage)

        if transition.node is SupervisorNode.COMPLETE:
            return DeterministicRuntimeResult(
                "completed",
                None,
                intent,
                retrieval,
                execution,
                synthesis,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.ABSTAIN:
            return DeterministicRuntimeResult(
                "abstained",
                transition.stop_reason,
                intent,
                retrieval,
                execution,
                None,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.RETRIEVE_CANDIDATES:
            return DeterministicRuntimeResult(
                "abstained",
                StopReason.NO_CANDIDATES,
                intent,
                retrieval,
                None,
                None,
                tuple(trace),
                snapshot.usage,
            )
        if transition.node is SupervisorNode.SELECT_CANDIDATE:
            current = next(
                index
                for index, candidate in enumerate(candidates)
                if candidate.status is CandidateStatus.UNSEEN
            )
            _replace_status(candidates, current, CandidateStatus.SELECTED)
            repairs = 0
            continue
        if transition.node is SupervisorNode.PROFILE_DATASET:
            assert current is not None
            dataset_id = retrieval.candidates[current].item.dataset_id
            profile = await dependencies.profile(dataset_id)
            intent = normalize_intent_for_observed_schema(
                intent,
                question=question,
                context=profile.context,
            )
            _replace_status(candidates, current, CandidateStatus.PROFILED)
            continue
        if transition.node is SupervisorNode.BUILD_PLAN:
            assert profile is not None
            selection = await dependencies.plan(
                intent,
                profile.context,
                explored,
                validation_error,
            )
            llm_calls += 1
            selection = normalize_system_owned_operation(selection, intent)
            selection = normalize_budget_snapshot(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_lookup_total_column(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_lookup_filters(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_explicit_date_filter(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_lookup_output_columns(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_ranked_aggregate(
                selection,
                question=question,
                context=profile.context,
            )
            selection = normalize_sort_references(selection, profile.context)
            selection = normalize_temporal_year_filters(selection, profile.context)
            selection = _normalize_explored_filter_values(selection, explored)
            if _requires_exploration(selection, explored):
                validated = None
                validation_error = None
                continue
            try:
                _validate_explored_filters(selection, explored)
                plan = materialize_query_plan(selection, intent=intent, context=profile.context)
                validated = validate_query_plan(
                    plan,
                    context=profile.context,
                    schema=profile.schema,
                )
                validation_error = None
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.PLANNED)
            except PlanValidationError as exc:
                if exc.code in {
                    PlanValidationCode.DATASET_MISMATCH,
                    PlanValidationCode.DATASET_NOT_ELIGIBLE,
                    PlanValidationCode.PII_BLOCKED,
                }:
                    assert current is not None
                    _replace_status(candidates, current, CandidateStatus.REJECTED)
                    current = None
                    profile = selection = validated = execution = None
                    explored = ()
                    validation_error = None
                    repairs = 0
                    continue
                validation_error = exc
                validated = None
                repairs += 1
            except ValueError as exc:
                validation_error = PlanValidationError(
                    PlanValidationCode.UNKNOWN_REFERENCE,
                    str(exc),
                )
                validated = None
                repairs += 1
            continue
        if transition.node is SupervisorNode.EXPLORE_VALUE:
            assert profile is not None
            assert selection is not None
            try:
                item = await dependencies.explore(profile, selection, explored)
            except (LookupError, ValueError):
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.REJECTED)
                current = None
                profile = selection = validated = execution = None
                explored = ()
                validation_error = None
                repairs = 0
                continue
            explored = tuple(
                previous
                for previous in explored
                if previous.column_index != item.column_index
            ) + (item,)
            explorations += item.tool_calls
            if not item.values:
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.REJECTED)
                current = None
                profile = selection = validated = execution = None
                explored = ()
                validation_error = None
                continue
            selection = None
            validation_error = None
            continue
        if transition.node is SupervisorNode.EXECUTE_QUERY:
            assert validated is not None
            try:
                execution = await dependencies.execute(validated)
                queries += 1
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.QUERIED)
            except DeterministicExecutionError:
                queries += 1
                assert current is not None
                _replace_status(candidates, current, CandidateStatus.REJECTED)
                current = None
                profile = selection = validated = execution = None
                explored = ()
            continue
        if transition.node is SupervisorNode.DERIVE_CLAIMS:
            raise AssertionError("execute ya deriva claims de forma determinista")
        if transition.node is SupervisorNode.SYNTHESIZE:
            assert execution is not None
            try:
                synthesis = await dependencies.synthesize(intent, execution.claims)
                llm_calls += 1
            except LLMProviderError:
                llm_calls += 1
                synthesis = _deterministic_synthesis(execution.claims)
            try:
                validate_grounded_synthesis(synthesis, execution.claims.claims)
            except ValueError:
                synthesis = _deterministic_synthesis(execution.claims)
                validate_grounded_synthesis(synthesis, execution.claims.claims)
            assert current is not None
            _replace_status(candidates, current, CandidateStatus.ACCEPTED)
            continue
        if transition.node is SupervisorNode.NEXT_CANDIDATE:
            assert current is not None
            _replace_status(candidates, current, CandidateStatus.REJECTED)
            current = None
            profile = selection = validated = execution = None
            explored = ()
            validation_error = None
            continue
        raise AssertionError(f"transición sin implementación: {transition.node}")
