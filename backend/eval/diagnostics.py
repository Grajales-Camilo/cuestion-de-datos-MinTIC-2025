"""Diagnósticos canónicos por etapa para la evaluación OE3 (T-613, RF-602/603)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from eval.loader import GoldenCase
from eval.metrics import CaseAssessment

DIAGNOSTICS_VERSION = "1.0"


class EvalStage(StrEnum):
    INTENT = "intent"
    RETRIEVAL = "retrieval"
    CANDIDATE_SELECTION = "candidate_selection"
    PROFILING = "profiling"
    PLANNING = "planning"
    PLAN_VALIDATION = "plan_validation"
    VALUE_EXPLORATION = "value_exploration"
    QUERY_EXECUTION = "query_execution"
    EVIDENCE_QUALITY = "evidence_quality"
    CLAIMS = "claims"
    SYNTHESIS = "synthesis"
    ACCEPTANCE = "acceptance"


class FailureCode(StrEnum):
    INTENT_MISMATCH = "intent_mismatch"
    EXPECTED_DATASET_NOT_RETRIEVED = "expected_dataset_not_retrieved"
    EXPECTED_DATASET_NOT_ATTEMPTED = "expected_dataset_not_attempted"
    PROFILE_FAILED = "profile_failed"
    PLAN_INVALID = "plan_invalid"
    PLAN_REPAIR_EXHAUSTED = "plan_repair_exhausted"
    VALUE_NOT_RESOLVED = "value_not_resolved"
    QUERY_FAILED = "query_failed"
    ZERO_ROWS = "zero_rows"
    EVIDENCE_NOT_ELIGIBLE = "evidence_not_eligible"
    CLAIMS_REJECTED = "claims_rejected"
    SYNTHESIS_REJECTED = "synthesis_rejected"
    EXPECTED_FACT_NOT_FOUND = "expected_fact_not_found"
    AMBIGUOUS_GOLDEN = "ambiguous_golden"
    BUDGET_EXCEEDED = "budget_exceeded"
    PROVIDER_ERROR = "provider_error"


# Códigos terminales tipados de `agent_runs.terminal_error_code`
# (`app.agent.graph._terminal_error`/`_llm_terminal_error`,
# `app.agent.heartbeat_sweep`) que representan una falla de infraestructura o
# proveedor, NUNCA una regresión semántica del agente. Excluye
# deliberadamente `RUN_INTERRUPTED` (cancelación, `status="interrupted"`, no
# "failed") y códigos aplicativos que no terminan la corrida (p. ej.
# `SOCRATA_TIMEOUT`/`SOCRATA_ERROR`, que ocurren dentro de una corrida que
# puede seguir y terminar `completed`/`no_evidence`). Distinto de
# `infrastructure_error` (nombre de excepción de Python capturada por el
# propio arnés de evaluación): un código de esta lista viene de
# `agent_runs.status="failed"` + `agent_runs.terminal_error_code`, es
# estructurado y siempre se diagnostica con `failure_owner="infrastructure"`.
INFRASTRUCTURE_TERMINAL_ERROR_CODES: frozenset[str] = frozenset(
    {
        "LLM_PROVIDER_ERROR",
        "STRUCTURED_OUTPUT_INVALID",
        "INTERNAL",
        "RUN_TIMEOUT",
        "HEARTBEAT_EXPIRED",
        "WORKER_LOST",
    }
)


_NODE_STAGE = {
    "router": EvalStage.INTENT,
    "retrieve_candidates": EvalStage.RETRIEVAL,
    "tool:buscar_catalogo": EvalStage.RETRIEVAL,
    "select_candidate": EvalStage.CANDIDATE_SELECTION,
    "next_candidate": EvalStage.CANDIDATE_SELECTION,
    "profile_dataset": EvalStage.PROFILING,
    "tool:perfilar_dataset": EvalStage.PROFILING,
    "build_plan": EvalStage.PLANNING,
    "claim_planner": EvalStage.PLANNING,
    "validate_plan": EvalStage.PLAN_VALIDATION,
    "explore_value": EvalStage.VALUE_EXPLORATION,
    "tool:explorar_valores": EvalStage.VALUE_EXPLORATION,
    "execute_query": EvalStage.QUERY_EXECUTION,
    "tool:ejecutar_soql": EvalStage.QUERY_EXECUTION,
    "validate_quality": EvalStage.EVIDENCE_QUALITY,
    "quality_validator": EvalStage.EVIDENCE_QUALITY,
    "derive_claims": EvalStage.CLAIMS,
    "claim_builder": EvalStage.CLAIMS,
    "synthesize": EvalStage.SYNTHESIS,
    "synthesizer": EvalStage.SYNTHESIS,
    "complete": EvalStage.ACCEPTANCE,
    "abstain": EvalStage.ACCEPTANCE,
}


@dataclass(frozen=True)
class StageObservation:
    node: str
    detail: Mapping[str, Any]
    output: Mapping[str, Any]
    message: str = ""


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _dataset_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return _unique(
        str(item.get("dataset_id")) if isinstance(item, dict) else str(item)
        for item in value
        if (isinstance(item, str) and item) or (isinstance(item, dict) and item.get("dataset_id"))
    )


def _usage(observations: tuple[StageObservation, ...], final: Mapping[str, Any]) -> dict[str, Any]:
    snapshots = [item.detail.get("usage") for item in observations]
    snapshots = [item for item in snapshots if isinstance(item, dict)]
    last = snapshots[-1] if snapshots else {}
    final_usage = final.get("usage") if isinstance(final.get("usage"), dict) else {}
    return {
        "query_count": int(last.get("queries", 0) or 0),
        "candidate_count": int(last.get("candidates", 0) or 0),
        "exploration_count": int(last.get("explorations", 0) or 0),
        "llm_call_count": int(last.get("llm_calls", 0) or 0),
        "latency_ms": final_usage.get("latency_ms", last.get("elapsed_ms")),
        "estimated_cost_usd": final_usage.get("estimated_cost_usd"),
    }


def build_stage_diagnostics(
    case: GoldenCase,
    final: Mapping[str, Any],
    assessment: CaseAssessment,
    observations: Iterable[StageObservation] = (),
    *,
    infrastructure_error: str | None = None,
    golden_ambiguous: bool | None = None,
    provider_error_code: str | None = None,
) -> dict[str, Any]:
    """Clasifica un resultado sin convertir texto humano en códigos de control.

    ``provider_error_code`` es el ``terminal_error_code`` tipado y persistido
    de ``agent_runs`` (T-617B0-R3): cuando pertenece a
    ``INFRASTRUCTURE_TERMINAL_ERROR_CODES`` la corrida terminó por una falla
    de infraestructura o proveedor, no por una regresión semántica del
    agente. Se clasifica SIEMPRE como ``FailureCode.PROVIDER_ERROR`` con
    ``failure_owner="infrastructure"``, preservando la última etapa
    observada antes del fallo, y nunca cae en ``intent_mismatch``,
    ``plan_invalid`` ni ningún otro código semántico. Distinto de
    ``infrastructure_error`` (nombre de excepción de Python capturada por el
    arnés de evaluación mismo), que conserva su clasificación previa por
    etapa."""

    observed = tuple(observations)
    if golden_ambiguous is None:
        golden_ambiguous = case.case_type == "positive" and any(
            not isinstance(fact.get("expected_value"), dict) or not fact.get("expected_value")
            for fact in case.expected_facts
        )
    stages = tuple(_NODE_STAGE[item.node] for item in observed if item.node in _NODE_STAGE)
    retrieved = _unique(
        dataset_id
        for item in observed
        for dataset_id in (
            *_dataset_ids(item.output.get("results")),
            *_dataset_ids(item.detail.get("retrieved_dataset_ids")),
        )
    )
    evidence = final.get("evidence") if isinstance(final.get("evidence"), list) else []
    evidence_ids = _unique(
        str(item.get("dataset_id"))
        for item in evidence
        if isinstance(item, dict) and item.get("dataset_id")
    )
    attempted = _unique(
        dataset_id
        for item in observed
        for dataset_id in (
            *_dataset_ids(item.detail.get("attempted_dataset_ids")),
            str(item.detail.get("dataset_id") or ""),
        )
    )
    attempted = _unique((*attempted, *evidence_ids))
    expected = set(case.expected_dataset_ids)
    expected_rank = next((i for i, value in enumerate(retrieved, 1) if value in expected), None)
    plan_errors = _unique(
        str(error)
        for item in observed
        for error in (
            item.detail.get("plan_validation_errors")
            if isinstance(item.detail.get("plan_validation_errors"), list)
            else []
        )
    )
    counts = _usage(observed, final)
    stop_reason = str((final.get("usage") or {}).get("termination_reason") or "") or None
    code: FailureCode | None = None
    stage: EvalStage | None = None
    owner: str | None = None

    is_provider_error = bool(
        provider_error_code and provider_error_code in INFRASTRUCTURE_TERMINAL_ERROR_CODES
    )

    if not assessment.passed:
        owner = "agent"
        if golden_ambiguous:
            stage, code, owner = EvalStage.ACCEPTANCE, FailureCode.AMBIGUOUS_GOLDEN, "golden"
        elif is_provider_error:
            # Falla terminal de proveedor/infraestructura (T-617B0-R3): nunca
            # una regresión semántica. Conserva la última etapa observada
            # ANTES del fallo (p. ej. "planning" con "profiling" como última
            # etapa exitosa), sin mapear a un código semántico como
            # `plan_invalid` o `intent_mismatch`.
            stage = stages[-1] if stages else EvalStage.INTENT
            code, owner = FailureCode.PROVIDER_ERROR, "infrastructure"
        elif infrastructure_error:
            stage = stages[-1] if stages else EvalStage.QUERY_EXECUTION
            code = {
                EvalStage.PROFILING: FailureCode.PROFILE_FAILED,
                EvalStage.PLANNING: FailureCode.PLAN_INVALID,
                EvalStage.PLAN_VALIDATION: FailureCode.PLAN_INVALID,
                EvalStage.VALUE_EXPLORATION: FailureCode.VALUE_NOT_RESOLVED,
            }.get(stage, FailureCode.QUERY_FAILED)
        elif stop_reason and "BUDGET" in stop_reason:
            stage, code = (
                (stages[-1] if stages else EvalStage.ACCEPTANCE),
                FailureCode.BUDGET_EXCEEDED,
            )
        elif case.case_type == "positive" and expected and not expected.intersection(retrieved):
            stage, code = EvalStage.RETRIEVAL, FailureCode.EXPECTED_DATASET_NOT_RETRIEVED
        elif case.case_type == "positive" and expected and not expected.intersection(attempted):
            stage, code = EvalStage.CANDIDATE_SELECTION, FailureCode.EXPECTED_DATASET_NOT_ATTEMPTED
        elif plan_errors:
            stage, code = EvalStage.PLAN_VALIDATION, FailureCode.PLAN_INVALID
        elif EvalStage.QUERY_EXECUTION in stages and not any(
            isinstance(item, dict) and item.get("rows") for item in evidence
        ):
            stage, code = EvalStage.QUERY_EXECUTION, FailureCode.ZERO_ROWS
        elif evidence and not assessment.expected_dataset_hit:
            stage, code = EvalStage.EVIDENCE_QUALITY, FailureCode.EVIDENCE_NOT_ELIGIBLE
        elif assessment.facts_verified is False and assessment.expected_dataset_hit:
            stage, code, owner = (
                EvalStage.ACCEPTANCE,
                FailureCode.EXPECTED_FACT_NOT_FOUND,
                "undetermined",
            )
        elif not final.get("claims") and evidence:
            stage, code = EvalStage.CLAIMS, FailureCode.CLAIMS_REJECTED
        elif final.get("status") != "completed" and final.get("claims"):
            stage, code = EvalStage.SYNTHESIS, FailureCode.SYNTHESIS_REJECTED
        else:
            stage, code = (
                (stages[-1] if stages else EvalStage.ACCEPTANCE),
                FailureCode.INTENT_MISMATCH,
            )

    if assessment.passed:
        last_successful = EvalStage.ACCEPTANCE
    elif stage in stages:
        failure_index = stages.index(stage)
        last_successful = stages[failure_index - 1] if failure_index else None
    else:
        last_successful = stages[-1] if stages else None
    return {
        "version": DIAGNOSTICS_VERSION,
        "last_successful_stage": last_successful.value if last_successful else None,
        "failure_stage": stage.value if stage else None,
        "failure_code": code.value if code else None,
        "failure_owner": owner,
        "terminal_error_code": provider_error_code,
        "stop_reason": stop_reason,
        "retrieved_dataset_ids": list(retrieved),
        "attempted_dataset_ids": list(attempted),
        "accepted_dataset_id": evidence_ids[0] if assessment.passed and evidence_ids else None,
        "expected_dataset_rank": expected_rank,
        "plan_validation_errors": list(plan_errors),
        **counts,
        "evidence_count": len(evidence),
        "claim_count": len(final.get("claims") or []),
        "facts_verified": assessment.facts_verified,
    }
