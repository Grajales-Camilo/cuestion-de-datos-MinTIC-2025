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
    SOCRATA_TIMEOUT = "socrata_timeout"
    SOCRATA_ERROR = "socrata_error"
    RUN_TIMEOUT = "run_timeout"
    HEARTBEAT_EXPIRED = "heartbeat_expired"
    WORKER_LOST = "worker_lost"
    INTERNAL_ERROR = "internal_error"
    STRUCTURED_OUTPUT_INVALID = "structured_output_invalid"
    HARNESS_ERROR = "harness_error"
    RUN_INTERRUPTED = "run_interrupted"


# Códigos terminales tipados de `agent_runs.terminal_error_code`
# (`app.agent.graph._terminal_error`/`_llm_terminal_error`,
# `app.agent.heartbeat_sweep`, `app.agent.worker_lease`,
# `contracts/api-rest.md` §4) cuyas corridas NUNCA son evaluables como
# regresión semántica del agente: representan una falla real de
# infraestructura, proveedor o ejecución. Cada código mapea a un
# `FailureCode` propio (T-617B0-R3A: `INTERNAL` no puede leerse como
# "proveedor", ni `RUN_TIMEOUT`/`HEARTBEAT_EXPIRED`/`WORKER_LOST` deben
# perder su identidad bajo un rótulo genérico).
#
# `RUN_INTERRUPTED` (T-617B0-R3B, corrección de un comentario impreciso de
# R3A): NO es una cancelación del usuario. Según `plan.md` §11 y
# `contracts/api-rest.md` §4, es el arranque idempotente del backend
# marcando como `interrupted` las corridas `running` cuya lease de worker
# venció (reinicio/despliegue), y conserva evidencias/claims parciales ya
# validados hasta el corte. Es exactamente tan no evaluable como
# `HEARTBEAT_EXPIRED`/`WORKER_LOST`: la corrida se cortó por infraestructura
# del backend, no por una decisión semántica del agente.
#
# Excluye deliberadamente:
# - `STRUCTURED_OUTPUT_INVALID`: por contrato (`contracts/api-rest.md` §4)
#   distingue explícitamente una salida que sigue sin cumplir el esquema tras
#   agotar el repair loop de una falla real del proveedor; NO es
#   `retryable`, el problema es de esquema/prompt del agente, no de
#   infraestructura. Se clasifica aparte (ver `_STRUCTURED_OUTPUT_INVALID`
#   abajo) con `failure_owner="agent"` y SÍ puede contar como regresión
#   semántica bloqueante de un positivo sólido.
# `SOCRATA_TIMEOUT`/`SOCRATA_ERROR` pueden existir como errores aplicativos
# recuperables dentro de una corrida, pero desde T-617B-C10 también son
# terminales tipados cuando la exploración real no puede continuar. Solo
# entran a este mapeo cuando provienen de `agent_runs.terminal_error_code` con
# estado no evaluable; una observación intermedia nunca se promueve por sí sola.
# Distinto de `infrastructure_error` (nombre de excepción de Python
# capturada por el propio arnés de evaluación, ver `FailureCode.HARNESS_ERROR`
# abajo): un código de este mapeo viene de `agent_runs.terminal_error_code`
# con `agent_runs.status` en `{"failed", "interrupted"}` (T-617B0-R3A: antes
# solo se leía "failed", lo que hacía `HEARTBEAT_EXPIRED`/`WORKER_LOST`
# inalcanzables pese a estar documentados como soportados —ambos se
# persisten con `status="interrupted"`, `app.agent.heartbeat_sweep`).
_INFRASTRUCTURE_TERMINAL_ERROR_CODE_TO_FAILURE_CODE: dict[str, FailureCode] = {
    "LLM_PROVIDER_ERROR": FailureCode.PROVIDER_ERROR,
    "SOCRATA_TIMEOUT": FailureCode.SOCRATA_TIMEOUT,
    "SOCRATA_ERROR": FailureCode.SOCRATA_ERROR,
    "RUN_TIMEOUT": FailureCode.RUN_TIMEOUT,
    "HEARTBEAT_EXPIRED": FailureCode.HEARTBEAT_EXPIRED,
    "WORKER_LOST": FailureCode.WORKER_LOST,
    "INTERNAL": FailureCode.INTERNAL_ERROR,
    "RUN_INTERRUPTED": FailureCode.RUN_INTERRUPTED,
}
INFRASTRUCTURE_TERMINAL_ERROR_CODES: frozenset[str] = frozenset(
    _INFRASTRUCTURE_TERMINAL_ERROR_CODE_TO_FAILURE_CODE
)

# `STRUCTURED_OUTPUT_INVALID` NUNCA se clasifica como infraestructura o
# proveedor transitorio (contracts/api-rest.md §4): es un fallo del
# contrato de ejecución del agente tras agotar el repair loop.
_STRUCTURED_OUTPUT_INVALID_CODE = "STRUCTURED_OUTPUT_INVALID"

# `agent_runs.status` en los que un `terminal_error_code` es significativo
# para esta taxonomía (T-617B0-R3A). `RUN_TIMEOUT`/`LLM_PROVIDER_ERROR`/
# `STRUCTURED_OUTPUT_INVALID`/`INTERNAL` se persisten con "failed"
# (`app.agent.graph`); `HEARTBEAT_EXPIRED`/`WORKER_LOST`/`RUN_INTERRUPTED`
# se persisten con "interrupted" (`app.agent.heartbeat_sweep`,
# `app.agent.worker_lease`).
NON_EVALUABLE_RUN_STATUSES: frozenset[str] = frozenset({"failed", "interrupted"})


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

    Los fallos que hacen la corrida NO EVALUABLE tienen prioridad sobre
    ``golden_ambiguous`` y sobre cualquier clasificación semántica residual
    (T-617B0-R3A, requisito B): se resuelven primero, en este orden:

    1. ``provider_error_code`` reconocido en
       ``_INFRASTRUCTURE_TERMINAL_ERROR_CODE_TO_FAILURE_CODE`` (terminal
       tipado y persistido de ``agent_runs``): ``failure_owner="infrastructure"``
       con el ``FailureCode`` propio del código (nunca genérico "proveedor"
       para ``INTERNAL``/``RUN_TIMEOUT``/etc.).
    2. ``provider_error_code == "STRUCTURED_OUTPUT_INVALID"``: NO es
       infraestructura (contracts/api-rest.md §4); ``failure_owner="agent"``,
       ``failure_code="structured_output_invalid"``, cuenta como regresión
       semántica bloqueante si afecta un positivo sólido.
    3. ``infrastructure_error`` (nombre de excepción de Python capturada por
       el arnés de evaluación mismo — runner, engine, persistencia,
       dependencias): ``failure_owner="infrastructure"``,
       ``failure_code="harness_error"``. Nunca se convierte en regresión
       semántica del agente.

    Solo si ninguna de las tres aplica se evalúa ``golden_ambiguous`` y las
    clasificaciones semánticas (dataset esperado, plan, cifras, síntesis,
    etc.). Ninguna de las tres puede terminar como ``ambiguous_golden``,
    ``intent_mismatch`` ni ``plan_invalid``."""

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

    infra_failure_code = _INFRASTRUCTURE_TERMINAL_ERROR_CODE_TO_FAILURE_CODE.get(
        provider_error_code or ""
    )
    is_structured_output_invalid = provider_error_code == _STRUCTURED_OUTPUT_INVALID_CODE

    if not assessment.passed:
        owner = "agent"
        # T-617B0-R3A (requisito B): los fallos que hacen la corrida NO
        # EVALUABLE se resuelven ANTES de `golden_ambiguous` y de cualquier
        # clasificación semántica residual. Un `LLM_PROVIDER_ERROR` (o
        # cualquier otro terminal de infraestructura), una excepción del
        # arnés, o un `STRUCTURED_OUTPUT_INVALID`, nunca pueden terminar
        # como `ambiguous_golden`, `intent_mismatch` ni `plan_invalid`.
        if infra_failure_code is not None:
            # Falla terminal de infraestructura/proveedor/ejecución
            # (T-617B0-R3/R3A): nunca una regresión semántica. Conserva la
            # última etapa observada ANTES del fallo (p. ej. "planning" con
            # "profiling" como última etapa exitosa) y usa el código propio
            # del terminal persistido, nunca un código semántico.
            stage = stages[-1] if stages else EvalStage.INTENT
            code, owner = infra_failure_code, "infrastructure"
        elif is_structured_output_invalid:
            # NO es infraestructura (contracts/api-rest.md §4): fallo del
            # contrato de ejecución del agente tras agotar el repair loop.
            # Sigue contando como regresión semántica bloqueante.
            stage = stages[-1] if stages else EvalStage.SYNTHESIS
            code, owner = FailureCode.STRUCTURED_OUTPUT_INVALID, "agent"
        elif infrastructure_error:
            # Excepción propia del arnés de evaluación (runner, engine,
            # persistencia, dependencias) — NUNCA una regresión semántica
            # del agente (T-617B0-R3A, requisito C). `infrastructure_error`
            # conserva el nombre de la excepción para diagnóstico (persistido
            # aparte en `EvalCaseResult.error_code`, no en `failure_code`).
            stage = stages[-1] if stages else EvalStage.QUERY_EXECUTION
            code, owner = FailureCode.HARNESS_ERROR, "infrastructure"
        elif golden_ambiguous:
            stage, code, owner = EvalStage.ACCEPTANCE, FailureCode.AMBIGUOUS_GOLDEN, "golden"
        elif stop_reason and "BUDGET" in stop_reason:
            stage, code = (
                (stages[-1] if stages else EvalStage.ACCEPTANCE),
                FailureCode.BUDGET_EXCEEDED,
            )
        elif case.case_type == "positive" and expected and not expected.intersection(retrieved):
            stage, code = EvalStage.RETRIEVAL, FailureCode.EXPECTED_DATASET_NOT_RETRIEVED
        elif case.case_type == "positive" and expected and not expected.intersection(attempted):
            stage, code = EvalStage.CANDIDATE_SELECTION, FailureCode.EXPECTED_DATASET_NOT_ATTEMPTED
        elif plan_errors and not evidence:
            # `plan_errors` acumula errores de TODOS los candidatos
            # observados, incluidos los abandonados que el runtime superó
            # exitosamente al recuperar con otro candidato (T-617B-C6). Si
            # la corrida sí obtuvo evidencia (un candidato posterior validó
            # su plan y ejecutó T5), el motivo real del fallo está en las
            # ramas siguientes (dataset equivocado, cifra fuera de
            # tolerancia, etc.), no en un plan que ya fue reparado.
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
