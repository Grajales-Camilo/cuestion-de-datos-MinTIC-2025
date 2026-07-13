"""Runtime del agente v2 gobernado por el supervisor determinista.

El runtime coordina I/O mediante dependencias inyectadas; las decisiones de
transición siguen siendo exclusivas de ``decide_next_transition``.
"""

from __future__ import annotations

import time
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
    GroundedSynthesis,
    IntentExtraction,
    materialize_query_plan,
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
from app.agent.query_plan import DatasetOption, EnumeratedPlanningContext
from app.quality.claims import ClaimsBuildResult


@dataclass(frozen=True)
class ProfiledCandidate:
    option: DatasetOption
    schema: ObservedDatasetSchema

    @property
    def context(self) -> EnumeratedPlanningContext:
        return EnumeratedPlanningContext(candidates=(self.option,))


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


IntentExtractor = Callable[[str], Awaitable[IntentExtraction]]
Retriever = Callable[[IntentExtraction], Awaitable[MultiQueryRetrievalResult]]
Profiler = Callable[[str], Awaitable[ProfiledCandidate]]
Planner = Callable[
    [IntentExtraction, EnumeratedPlanningContext, PlanValidationError | None],
    Awaitable[EnumeratedPlanSelection],
]
Executor = Callable[[ValidatedQueryPlan], Awaitable[DeterministicExecutionResult]]
Synthesizer = Callable[[IntentExtraction, ClaimsBuildResult], Awaitable[GroundedSynthesis]]


@dataclass(frozen=True)
class DeterministicRuntimeDependencies:
    extract_intent: IntentExtractor
    retrieve: Retriever
    profile: Profiler
    plan: Planner
    execute: Executor
    synthesize: Synthesizer


def _replace_status(
    candidates: list[CandidateProgress], index: int, status: CandidateStatus
) -> None:
    candidates[index] = CandidateProgress(dataset_index=index, status=status)


async def run_deterministic_agent(
    question: str,
    *,
    dependencies: DeterministicRuntimeDependencies,
    budgets: SupervisorBudgets | None = None,
) -> DeterministicRuntimeResult:
    """Ejecuta el ciclo completo sin permitir que el LLM elija transiciones."""

    limits = budgets or SupervisorBudgets()
    started = time.monotonic()
    intent = await dependencies.extract_intent(question)
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
    queries = repairs = 0
    trace: list[RuntimeTraceEntry] = []

    while True:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        snapshot = SupervisorSnapshot(
            candidates=tuple(candidates),
            current_candidate_index=current,
            schema_available=profile is not None,
            plan_available=selection is not None,
            plan_valid=validated is not None,
            plan_error_correctable=validation_error is not None,
            exploration_required=(
                selection.needs_value_exploration if selection is not None else False
            ),
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
                queries=queries,
                plan_repairs=repairs,
                llm_calls=llm_calls,
                elapsed_ms=elapsed_ms,
            ),
        )
        transition = decide_next_transition(snapshot)
        trace.append(RuntimeTraceEntry(transition.node, transition.reason, current))

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
            continue
        if transition.node is SupervisorNode.PROFILE_DATASET:
            assert current is not None
            dataset_id = retrieval.candidates[current].item.dataset_id
            profile = await dependencies.profile(dataset_id)
            _replace_status(candidates, current, CandidateStatus.PROFILED)
            continue
        if transition.node is SupervisorNode.BUILD_PLAN:
            assert profile is not None
            selection = await dependencies.plan(intent, profile.context, validation_error)
            llm_calls += 1
            try:
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
                validation_error = exc
                validated = None
                repairs += 1
            continue
        if transition.node is SupervisorNode.EXPLORE_VALUE:
            # La selección restringida debe pedir una nueva planificación tras
            # explorar; la integración concreta incorporará el valor al contexto.
            validation_error = PlanValidationError(
                PlanValidationCode.UNKNOWN_REFERENCE,
                "se requiere exploración categórica",
            )
            selection = None
            repairs += 1
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
            continue
        if transition.node is SupervisorNode.DERIVE_CLAIMS:
            raise AssertionError("execute ya deriva claims de forma determinista")
        if transition.node is SupervisorNode.SYNTHESIZE:
            assert execution is not None
            synthesis = await dependencies.synthesize(intent, execution.claims)
            llm_calls += 1
            validate_grounded_synthesis(synthesis, execution.claims.claims)
            assert current is not None
            _replace_status(candidates, current, CandidateStatus.ACCEPTED)
            continue
        if transition.node is SupervisorNode.NEXT_CANDIDATE:
            assert current is not None
            _replace_status(candidates, current, CandidateStatus.REJECTED)
            current = None
            profile = selection = validated = execution = None
            validation_error = None
            continue
        raise AssertionError(f"transición sin implementación: {transition.node}")
