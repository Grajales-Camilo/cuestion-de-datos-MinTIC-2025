import pytest

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


def candidate(status: CandidateStatus = CandidateStatus.SELECTED) -> CandidateProgress:
    return CandidateProgress(dataset_index=0, status=status)


def state(**updates: object) -> SupervisorSnapshot:
    values: dict[str, object] = {
        "candidates": (candidate(),),
        "current_candidate_index": 0,
    }
    values.update(updates)
    return SupervisorSnapshot.model_validate(values)


def test_retrieves_then_selects_candidates_deterministically() -> None:
    assert decide_next_transition(SupervisorSnapshot()).node is SupervisorNode.RETRIEVE_CANDIDATES
    snapshot = SupervisorSnapshot(candidates=(candidate(CandidateStatus.UNSEEN),))
    assert decide_next_transition(snapshot).node is SupervisorNode.SELECT_CANDIDATE


def test_profiles_before_building_or_executing_plan() -> None:
    assert decide_next_transition(state()).node is SupervisorNode.PROFILE_DATASET
    assert decide_next_transition(state(schema_available=True)).node is SupervisorNode.BUILD_PLAN


def test_explores_required_value_before_validation_and_query() -> None:
    snapshot = state(schema_available=True, plan_available=True, exploration_required=True)
    assert decide_next_transition(snapshot).node is SupervisorNode.EXPLORE_VALUE


def test_valid_plan_executes_query_without_llm_finish_decision() -> None:
    snapshot = state(schema_available=True, plan_available=True, plan_valid=True)
    assert decide_next_transition(snapshot).node is SupervisorNode.EXECUTE_QUERY


def test_factual_path_cannot_complete_before_evidence_and_claims() -> None:
    no_evidence = state(
        schema_available=True,
        plan_available=True,
        plan_valid=True,
        query_executed=True,
    )
    assert decide_next_transition(no_evidence).node is not SupervisorNode.COMPLETE
    with_evidence = no_evidence.model_copy(update={"evidence_eligible": True})
    assert decide_next_transition(with_evidence).node is SupervisorNode.DERIVE_CLAIMS
    with_claims = with_evidence.model_copy(update={"claims_available": True})
    assert decide_next_transition(with_claims).node is SupervisorNode.SYNTHESIZE


def test_completes_only_verified_synthesis_with_claims_and_evidence() -> None:
    snapshot = state(
        evidence_eligible=True,
        claims_available=True,
        synthesis_valid=True,
    )
    assert decide_next_transition(snapshot).node is SupervisorNode.COMPLETE


def test_textual_rejection_abstains_even_when_quantitative_claims_exist() -> None:
    transition = decide_next_transition(
        state(
            schema_available=True,
            plan_available=True,
            plan_valid=True,
            query_executed=True,
            evidence_eligible=True,
            claims_available=True,
            textual_result_available=True,
            textual_rejected=True,
        )
    )
    assert transition.node is SupervisorNode.ABSTAIN
    assert transition.stop_reason is StopReason.CLAIMS_NOT_AVAILABLE


def test_deferred_synthesis_persists_quantitative_claims_before_textual_rejection() -> None:
    transition = decide_next_transition(
        state(
            schema_available=True,
            plan_available=True,
            plan_valid=True,
            query_executed=True,
            evidence_eligible=True,
            claims_available=True,
            textual_result_available=True,
            textual_rejected=True,
            synthesis_deferred=True,
        )
    )

    assert transition.node is SupervisorNode.PERSIST_FACTS


def test_deferred_textual_synthesis_requires_an_accepted_textual_result() -> None:
    accepted = state(
        schema_available=True,
        plan_available=True,
        plan_valid=True,
        query_executed=True,
        evidence_eligible=True,
        textual_result_available=True,
        synthesis_deferred=True,
    )
    rejected = accepted.model_copy(update={"textual_rejected": True})

    assert decide_next_transition(accepted).node is SupervisorNode.PERSIST_FACTS
    assert decide_next_transition(rejected).node is SupervisorNode.ABSTAIN


def test_blocked_evidence_builds_safe_aggregate_when_possible() -> None:
    snapshot = state(
        schema_available=True,
        plan_available=True,
        plan_valid=True,
        query_executed=True,
        safe_aggregate_possible=True,
    )
    transition = decide_next_transition(snapshot)
    assert transition.node is SupervisorNode.BUILD_PLAN
    assert "agregación segura" in transition.reason


@pytest.mark.parametrize(
    ("usage", "reason"),
    [
        (SupervisorUsage(elapsed_ms=75_000), StopReason.DURATION_BUDGET_EXCEEDED),
        (SupervisorUsage(candidates=5), StopReason.CANDIDATE_BUDGET_EXCEEDED),
        (SupervisorUsage(queries=4), StopReason.QUERY_BUDGET_EXCEEDED),
        (SupervisorUsage(plan_repairs=2), StopReason.PLAN_REPAIR_BUDGET_EXCEEDED),
        (SupervisorUsage(llm_calls=6), StopReason.LLM_BUDGET_EXCEEDED),
    ],
)
def test_independent_budgets_force_explicit_abstention(
    usage: SupervisorUsage, reason: StopReason
) -> None:
    transition = decide_next_transition(state(usage=usage))
    assert transition.node is SupervisorNode.ABSTAIN
    assert transition.stop_reason is reason


def test_exploration_budget_moves_to_next_candidate_not_global_finish() -> None:
    snapshot = state(
        candidates=(candidate(), CandidateProgress(dataset_index=1)),
        schema_available=True,
        plan_available=True,
        exploration_required=True,
        budgets=SupervisorBudgets(max_explorations=1),
        usage=SupervisorUsage(explorations=1),
    )
    transition = decide_next_transition(snapshot)
    assert transition.node is SupervisorNode.NEXT_CANDIDATE
    assert transition.stop_reason is StopReason.EXPLORATION_BUDGET_EXCEEDED
