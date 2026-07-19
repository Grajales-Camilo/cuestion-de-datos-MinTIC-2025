"""Supervisor determinista del ciclo de investigación.

La función ``decide_next_transition`` es pura: no invoca LLM, herramientas,
red ni base de datos. Satisface RF-201/RF-205 y elimina ``action=finish`` como
autoridad sobre las transiciones críticas.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SupervisorNode(StrEnum):
    RETRIEVE_CANDIDATES = "retrieve_candidates"
    SELECT_CANDIDATE = "select_candidate"
    PROFILE_DATASET = "profile_dataset"
    BUILD_PLAN = "build_plan"
    EXPLORE_VALUE = "explore_value"
    VALIDATE_PLAN = "validate_plan"
    EXECUTE_QUERY = "execute_query"
    VALIDATE_QUALITY = "validate_quality"
    DERIVE_CLAIMS = "derive_claims"
    PERSIST_FACTS = "persist_facts"
    SYNTHESIZE = "synthesize"
    NEXT_CANDIDATE = "next_candidate"
    ABSTAIN = "abstain"
    COMPLETE = "complete"


class CandidateStatus(StrEnum):
    UNSEEN = "unseen"
    SELECTED = "selected"
    PROFILED = "profiled"
    PLANNED = "planned"
    QUERIED = "queried"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class StopReason(StrEnum):
    NO_CANDIDATES = "NO_CANDIDATES"
    CANDIDATE_BUDGET_EXCEEDED = "CANDIDATE_BUDGET_EXCEEDED"
    EXPLORATION_BUDGET_EXCEEDED = "EXPLORATION_BUDGET_EXCEEDED"
    QUERY_BUDGET_EXCEEDED = "QUERY_BUDGET_EXCEEDED"
    PLAN_REPAIR_BUDGET_EXCEEDED = "PLAN_REPAIR_BUDGET_EXCEEDED"
    LLM_BUDGET_EXCEEDED = "LLM_BUDGET_EXCEEDED"
    DURATION_BUDGET_EXCEEDED = "DURATION_BUDGET_EXCEEDED"
    ALL_CANDIDATES_REJECTED = "ALL_CANDIDATES_REJECTED"
    EVIDENCE_NOT_ELIGIBLE = "EVIDENCE_NOT_ELIGIBLE"
    CLAIMS_NOT_AVAILABLE = "CLAIMS_NOT_AVAILABLE"


class SupervisorBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_candidates: int = Field(default=5, ge=1, le=10)
    max_explorations: int = Field(default=4, ge=0, le=20)
    max_queries: int = Field(default=4, ge=1, le=10)
    max_plan_repairs: int = Field(default=2, ge=0, le=5)
    max_llm_calls: int = Field(default=6, ge=0, le=20)
    max_duration_ms: int = Field(default=75_000, ge=1_000, le=600_000)


class SupervisorUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: int = Field(default=0, ge=0)
    explorations: int = Field(default=0, ge=0)
    queries: int = Field(default=0, ge=0)
    plan_repairs: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)


class CandidateProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_index: int = Field(ge=0)
    status: CandidateStatus = CandidateStatus.UNSEEN


class SupervisorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[CandidateProgress, ...] = ()
    current_candidate_index: int | None = Field(default=None, ge=0)
    schema_available: bool = False
    plan_available: bool = False
    plan_valid: bool = False
    plan_error_correctable: bool = False
    exploration_required: bool = False
    query_executed: bool = False
    evidence_eligible: bool = False
    safe_aggregate_possible: bool = False
    claims_available: bool = False
    claims_materially_relevant: bool = True
    textual_result_available: bool = False
    textual_rejected: bool = False
    synthesis_deferred: bool = False
    synthesis_valid: bool = False
    budgets: SupervisorBudgets = SupervisorBudgets()
    usage: SupervisorUsage = SupervisorUsage()


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node: SupervisorNode
    reason: str
    stop_reason: StopReason | None = None


def _budget_stop(state: SupervisorSnapshot) -> Transition | None:
    usage, limits = state.usage, state.budgets
    checks = (
        (usage.elapsed_ms >= limits.max_duration_ms, StopReason.DURATION_BUDGET_EXCEEDED),
    )
    for exhausted, reason in checks:
        if exhausted:
            return Transition(node=SupervisorNode.ABSTAIN, reason=reason.value, stop_reason=reason)
    return None


def _has_unseen_candidate(state: SupervisorSnapshot) -> bool:
    return any(item.status is CandidateStatus.UNSEEN for item in state.candidates)


def decide_next_transition(state: SupervisorSnapshot) -> Transition:
    """Decide el siguiente nodo usando solo hechos verificables del estado."""

    if (
        state.synthesis_valid
        and state.claims_available
        and state.claims_materially_relevant
        and state.evidence_eligible
    ):
        return Transition(node=SupervisorNode.COMPLETE, reason="síntesis verificada desde claims")

    budget_stop = _budget_stop(state)
    if budget_stop is not None:
        return budget_stop

    if not state.candidates:
        return Transition(
            node=SupervisorNode.RETRIEVE_CANDIDATES,
            reason="todavía no se recuperaron candidatos",
        )
    if state.current_candidate_index is None:
        if state.usage.candidates >= state.budgets.max_candidates:
            return Transition(
                node=SupervisorNode.ABSTAIN,
                reason=StopReason.CANDIDATE_BUDGET_EXCEEDED.value,
                stop_reason=StopReason.CANDIDATE_BUDGET_EXCEEDED,
            )
        if _has_unseen_candidate(state):
            return Transition(
                node=SupervisorNode.SELECT_CANDIDATE,
                reason="hay candidato no intentado",
            )
        return Transition(
            node=SupervisorNode.ABSTAIN,
            reason="todos los candidatos fueron rechazados",
            stop_reason=StopReason.ALL_CANDIDATES_REJECTED,
        )
    if not state.schema_available:
        return Transition(node=SupervisorNode.PROFILE_DATASET, reason="falta esquema observado")
    if not state.plan_available:
        if state.usage.llm_calls >= state.budgets.max_llm_calls:
            return Transition(
                node=SupervisorNode.ABSTAIN,
                reason=StopReason.LLM_BUDGET_EXCEEDED.value,
                stop_reason=StopReason.LLM_BUDGET_EXCEEDED,
            )
        return Transition(node=SupervisorNode.BUILD_PLAN, reason="falta plan tipado")
    if state.exploration_required:
        if state.usage.explorations >= state.budgets.max_explorations:
            return Transition(
                node=SupervisorNode.NEXT_CANDIDATE,
                reason="se agotó exploración para este camino",
                stop_reason=StopReason.EXPLORATION_BUDGET_EXCEEDED,
            )
        return Transition(
            node=SupervisorNode.EXPLORE_VALUE,
            reason="falta resolver valor categórico",
        )
    if not state.plan_valid:
        if (
            state.plan_error_correctable
            and state.usage.plan_repairs < state.budgets.max_plan_repairs
        ):
            if state.usage.llm_calls >= state.budgets.max_llm_calls:
                return Transition(
                    node=SupervisorNode.ABSTAIN,
                    reason=StopReason.LLM_BUDGET_EXCEEDED.value,
                    stop_reason=StopReason.LLM_BUDGET_EXCEEDED,
                )
            return Transition(node=SupervisorNode.BUILD_PLAN, reason="reparar plan inválido")
        if state.plan_error_correctable and not _has_unseen_candidate(state):
            return Transition(
                node=SupervisorNode.ABSTAIN,
                reason=StopReason.PLAN_REPAIR_BUDGET_EXCEEDED.value,
                stop_reason=StopReason.PLAN_REPAIR_BUDGET_EXCEEDED,
            )
        return Transition(
            node=SupervisorNode.NEXT_CANDIDATE,
            reason="plan incompatible con esquema",
        )
    if not state.query_executed:
        if state.usage.queries >= state.budgets.max_queries:
            return Transition(
                node=SupervisorNode.ABSTAIN,
                reason=StopReason.QUERY_BUDGET_EXCEEDED.value,
                stop_reason=StopReason.QUERY_BUDGET_EXCEEDED,
            )
        return Transition(node=SupervisorNode.EXECUTE_QUERY, reason="plan validado listo para T5")
    if not state.evidence_eligible:
        if state.safe_aggregate_possible and state.usage.queries < state.budgets.max_queries:
            return Transition(node=SupervisorNode.BUILD_PLAN, reason="construir agregación segura")
        if _has_unseen_candidate(state):
            return Transition(node=SupervisorNode.NEXT_CANDIDATE, reason="evidencia no elegible")
        return Transition(
            node=SupervisorNode.ABSTAIN,
            reason="no se obtuvo evidencia elegible",
            stop_reason=StopReason.EVIDENCE_NOT_ELIGIBLE,
        )
    if state.synthesis_deferred and state.claims_available:
        # T-617B-C2 (corrección posterior): un claim cuantitativo irrelevante
        # no puede persistirse solo porque exista. Se exige o bien que algún
        # claim sea pertinente, o bien que haya un resultado textual
        # pertinente (T-615F/RF-212) que igual deba conservarse — nunca se
        # bloquea la persistencia de un hecho textual válido por culpa de
        # claims cuantitativos irrelevantes.
        if state.claims_materially_relevant or state.textual_result_available:
            return Transition(
                node=SupervisorNode.PERSIST_FACTS,
                reason="claims derivados listos para persistencia y reverificación",
            )
    if state.textual_rejected:
        return Transition(
            node=SupervisorNode.ABSTAIN,
            reason="la selección textual fue rechazada por código determinista",
            stop_reason=StopReason.CLAIMS_NOT_AVAILABLE,
        )
    if state.synthesis_deferred and state.textual_result_available:
        return Transition(
            node=SupervisorNode.PERSIST_FACTS,
            reason="hechos derivados listos para persistencia y reverificación",
        )
    if not state.claims_available:
        if state.textual_result_available:
            return Transition(
                node=SupervisorNode.ABSTAIN,
                reason="resultado textual interno no expuesto por T-615F",
                stop_reason=StopReason.CLAIMS_NOT_AVAILABLE,
            )
        return Transition(node=SupervisorNode.DERIVE_CLAIMS, reason="evidencia elegible sin claims")
    if not state.claims_materially_relevant:
        # T-617B-C2: evidencia técnicamente elegible cuyos claims no derivan
        # de ninguna columna pertinente a la intención (RF-205/RF-211) no
        # debe sintetizarse. Se agota primero el resto de candidatos, como ya
        # ocurre con `evidence_eligible`, antes de abstenerse.
        if _has_unseen_candidate(state):
            return Transition(
                node=SupervisorNode.NEXT_CANDIDATE,
                reason="ningún claim deriva de una columna pertinente a la intención",
            )
        return Transition(
            node=SupervisorNode.ABSTAIN,
            reason="ninguna evidencia recuperada es pertinente a la intención",
            stop_reason=StopReason.CLAIMS_NOT_AVAILABLE,
        )
    if not state.synthesis_valid:
        return Transition(node=SupervisorNode.SYNTHESIZE, reason="claims aceptados listos")
    raise AssertionError("estado exhaustivo no cubierto")
