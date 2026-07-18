"""CLI de evaluación OE3 con LLM real (T-602)."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.durability import get_run
from app.agent.persistence import load_allowed_grounded_facts, load_textual_facts
from app.agent.runner import create_eval_run, execute_agent_run_async
from app.agent.worker_lease import mark_worker_shutdown, register_worker_instance
from app.config import get_settings
from app.db.engine import create_app_async_engine
from app.db.models import AgentRunEvent, AgentStep, EvalCaseResult, EvalRun
from eval.diagnostics import StageObservation, build_stage_diagnostics
from eval.gate import (
    AggregateMetrics,
    CaseOutcome,
    ClaimsIntegrityAssessment,
    GateVerdict,
    aggregate_metrics,
    classify_run_complexity,
    evaluate_claims_integrity,
    evaluate_full_gate,
    evaluate_smoke_gate,
    socrata_success_rate,
)
from eval.loader import default_suite_path, load_golden_suite
from eval.metrics import (
    CaseAssessment,
    assess_case,
    assess_textual_integrity,
    recall_hit_at_10,
)
from eval.persistence import PersistedGoldenSuite, sync_golden_suite

# Hallazgo (2026-07-12, diagnostico real): main() siempre devolvia 0 tras una
# corrida sin excepciones -- un 0/8 real (backend/eval/reports/994e0730-...)
# salia como "exito" para cualquier automatizacion que solo mirara el exit
# code. Corregido primero comparando success_rate contra RNF-002 y, desde
# T-617B0, con el VEREDICTO DE PUERTA completo (eval.gate): el exit code
# no-cero refleja el incumplimiento de CUALQUIER condicion normativa, no solo
# el umbral de positivos. Los umbrales viven en eval.gate (fuente unica); la
# decision de si el fallo bloquea un release o solo abre una alerta semanal
# (Art. IV.2) es del workflow de CI que invoca este script, no de este modulo.


def _select_cases(cases, *, limit: int | None, case_ids: list[str] | None):
    if not case_ids:
        return cases[:limit] if limit is not None else cases
    requested = set(case_ids)
    selected = [case for case in cases if case.case_id in requested]
    missing = requested.difference(case.case_id for case in selected)
    if missing:
        raise RuntimeError(f"case_id inexistente: {', '.join(sorted(missing))}")
    return selected


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _config_snapshot(settings, seed: int) -> dict[str, object]:
    commit = _git_commit()
    return {
        "runtime": settings.agent_runtime,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "agent_max_steps": settings.agent_max_steps,
        "embedding_model": settings.embedding_model,
        "eval_seed": seed,
        "git_commit": commit,
        "placeholder_min_ratio": settings.placeholder_min_ratio,
        "run_max_duration_s": settings.run_max_duration_s,
    }


async def _planner_search_dataset_ids(engine, agent_run_id: uuid.UUID) -> list[str]:
    """Dataset ids del PRIMER `buscar_catalogo` (la consulta del planificador,
    pruebas.md §4.2), leídos de `agent_steps.tool_output_summary` — no de la
    evidencia final, que depende de todo el resto de la corrida."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        step = await session.scalar(
            select(AgentStep)
            .where(AgentStep.run_id == agent_run_id, AgentStep.node == "tool:buscar_catalogo")
            .order_by(AgentStep.step_number)
            .limit(1)
        )
    if step is not None and isinstance(step.tool_output_summary, dict):
        results = step.tool_output_summary.get("results")
        if isinstance(results, list):
            return [
                item["dataset_id"]
                for item in results
                if isinstance(item, dict) and item.get("dataset_id")
            ]
    async with session_factory() as session:
        events = (
            await session.scalars(
                select(AgentRunEvent)
                .where(
                    AgentRunEvent.run_id == agent_run_id,
                    AgentRunEvent.event_type == "step",
                )
                .order_by(AgentRunEvent.seq)
            )
        ).all()
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
        retrieved = detail.get("retrieved_dataset_ids")
        if isinstance(retrieved, list) and retrieved:
            return [str(dataset_id) for dataset_id in retrieved if dataset_id]
    return []


async def _stage_observations(
    engine, agent_run_id: uuid.UUID | None
) -> tuple[StageObservation, ...]:
    if agent_run_id is None:
        return ()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        steps = (
            await session.scalars(
                select(AgentStep)
                .where(AgentStep.run_id == agent_run_id)
                .order_by(AgentStep.step_number)
            )
        ).all()
        step_events = (
            await session.scalars(
                select(AgentRunEvent)
                .where(
                    AgentRunEvent.run_id == agent_run_id,
                    AgentRunEvent.event_type == "step",
                )
                .order_by(AgentRunEvent.seq)
            )
        ).all()
    details_by_step = {
        event.payload.get("step_number"): event.payload.get("detail", {})
        for event in step_events
        if isinstance(event.payload, dict)
    }
    return tuple(
        StageObservation(
            node=step.node,
            detail=(
                details_by_step.get(step.step_number, {})
                if isinstance(details_by_step.get(step.step_number, {}), dict)
                else {}
            ),
            output=step.tool_output_summary if isinstance(step.tool_output_summary, dict) else {},
            message=step.display_message,
        )
        for step in steps
    )


async def _persist_case_result(
    engine,
    *,
    eval_run_id: uuid.UUID,
    case_db_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    final: dict,
    assessment: CaseAssessment,
    stage_diagnostics: dict[str, object],
    claims_integrity: ClaimsIntegrityAssessment | None = None,
    error_code: str | None = None,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            _case_result_model(
                eval_run_id=eval_run_id,
                case_db_id=case_db_id,
                agent_run_id=agent_run_id,
                final=final,
                assessment=assessment,
                stage_diagnostics=stage_diagnostics,
                claims_integrity=claims_integrity,
                error_code=error_code,
            )
        )


def _case_result_model(
    *,
    eval_run_id: uuid.UUID,
    case_db_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    final: dict,
    assessment: CaseAssessment,
    stage_diagnostics: dict[str, object],
    claims_integrity: ClaimsIntegrityAssessment | None = None,
    error_code: str | None = None,
) -> EvalCaseResult:
    """Construye la fila sin I/O para probar el contrato JSONB de T-613."""

    return EvalCaseResult(
        id=uuid.uuid4(),
        eval_run_id=eval_run_id,
        case_id=case_db_id,
        agent_run_id=agent_run_id,
        passed=assessment.passed,
        status_final=str(final.get("status", "failed")),
        expected_dataset_hit=assessment.expected_dataset_hit,
        metrics={
            "fabrication": assessment.fabrication,
            "facts_verified": assessment.facts_verified,
            "orphan_figures": list(assessment.orphan_figures),
            "recall_hit": assessment.recall_hit,
            "usage": final.get("usage", {}),
            "stage_diagnostics": stage_diagnostics,
            # Solo conteos/booleanos/códigos: sin valores mostrados ni narrativa.
            **(
                {"claims_integrity": claims_integrity.snapshot()}
                if claims_integrity is not None
                else {}
            ),
            **(
                {"textual_integrity": assessment.textual_integrity.snapshot()}
                if assessment.textual_integrity is not None
                else {}
            ),
        },
        quality_summary=_privacy_safe_quality_summary(final.get("evidence", [])),
        evidence_dataset_ids=list(assessment.evidence_dataset_ids),
        claim_fingerprint_hashes=list(assessment.claim_hashes),
        error_code=error_code,
        failure_reason=assessment.failure_reason,
    )


def _privacy_safe_quality_summary(evidence: object) -> dict[str, object]:
    """Reduce calidad a enums y conteos; excluye warnings y contenido."""

    classifications: dict[str, int] = {}
    eligibility: dict[str, int] = {}
    warning_count = 0
    for item in evidence if isinstance(evidence, list) else []:
        quality = item.get("quality") if isinstance(item, dict) else None
        if not isinstance(quality, dict):
            continue
        classification = quality.get("classification")
        if isinstance(classification, str):
            classifications[classification] = classifications.get(classification, 0) + 1
        status = quality.get("eligibility_status")
        if isinstance(status, str):
            eligibility[status] = eligibility.get(status, 0) + 1
        warnings = quality.get("warnings_user")
        if isinstance(warnings, list):
            warning_count += len(warnings)
    return {
        "classification_counts": classifications,
        "eligibility_status_counts": eligibility,
        "warning_count": warning_count,
    }


async def _create_eval_record(
    engine, persisted: PersistedGoldenSuite, settings, seed: int
) -> EvalRun:
    record = EvalRun(
        id=uuid.uuid4(),
        suite_id=persisted.suite_id,
        git_commit=_git_commit(),
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        embedding_model=settings.embedding_model,
        eval_seed=seed,
        config_snapshot=_config_snapshot(settings, seed),
        started_at=datetime.now(UTC),
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(record)
    return record


def _decimal_or_none(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _int_or_none(value: float | None) -> int | None:
    return int(round(value)) if value is not None else None


def apply_aggregate_metrics(record: Any, aggregate: AggregateMetrics) -> None:
    """Mapea los agregados de puerta a las columnas de ``EvalRun`` (puro,
    sin I/O, para probar la persistencia sin base de datos).

    ``success_rate`` se calcula exclusivamente sobre positivos (RNF-002); los
    negativos se agregan por separado. Completa además las columnas que antes
    quedaban en ``NULL``: socrata, cobertura/reproducibilidad de claims,
    latencias p50/p95 (global, simple y multipaso) y costo promedio.
    """

    record.success_rate = _decimal_or_none(aggregate.success_rate)
    record.recall_at_10 = _decimal_or_none(aggregate.recall_at_10)
    record.fabrication_count = aggregate.fabrication_count
    record.orphan_figures_count = aggregate.orphan_figures_count
    record.socrata_success_rate = _decimal_or_none(aggregate.socrata_success_rate)
    record.claims_coverage = _decimal_or_none(aggregate.claims_coverage)
    record.claims_reproducible = _decimal_or_none(aggregate.claims_reproducible)
    record.latency_p50_ms = _int_or_none(aggregate.latency_p50_ms)
    record.latency_p95_ms = _int_or_none(aggregate.latency_p95_ms)
    record.latency_simple_p95_ms = _int_or_none(aggregate.latency_simple_p95_ms)
    record.latency_multistep_p95_ms = _int_or_none(aggregate.latency_multistep_p95_ms)
    record.avg_cost_usd = aggregate.avg_cost_usd


async def _finalize_eval_record(
    engine, *, record_id: uuid.UUID, aggregate: AggregateMetrics
) -> None:
    """Cierra la corrida OE3 con TODOS los agregados de la puerta."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        record = await session.get(EvalRun, record_id)
        assert record is not None
        record.finished_at = datetime.now(UTC)
        apply_aggregate_metrics(record, aggregate)


def _md(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "no aplica"


def _gate_summary_lines(aggregate: AggregateMetrics, verdict: GateVerdict) -> list[str]:
    """Resumen mecánico de puerta: numerador/denominador, umbral, valor y
    PASS/FAIL con razones bloqueantes."""

    lines = [
        "",
        f"## Veredicto de puerta ({verdict.mode})",
        "",
        f"- Positivos aprobados: {aggregate.positive_passed}/{aggregate.positive_total} "
        f"({_pct(aggregate.success_rate)})",
        f"- Negativos aprobados: {aggregate.negative_passed}/{aggregate.negative_total} "
        f"({_pct(aggregate.negative_success_rate)})",
        f"- socrata_success_rate: {_pct(aggregate.socrata_success_rate)} "
        f"({aggregate.socrata_successes}/{aggregate.socrata_attempts} llamadas T5 observables)",
        f"- **Resultado: {'PASS' if verdict.passed else 'FAIL'}**",
        "",
        "| Métrica | Umbral | Observado | Estado | Razón bloqueante |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {_md(m.name)} | {_md(m.threshold)} | {_md(m.observed)} | "
        f"{'PASS' if m.passed else 'FAIL'} | {_md(m.reason)} |"
        for m in verdict.metrics
    )
    return lines


def _write_report(
    path: Path,
    *,
    record: EvalRun,
    results: list[tuple[str, CaseAssessment, dict[str, object]]],
    aggregate: AggregateMetrics,
    verdict: GateVerdict,
    suite_name: str = "golden-v1",
) -> None:
    passed = sum(item.passed for _, item, _ in results)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Evaluación {record.id}",
        "",
        f"- Suite: {_md(suite_name)}",
        f"- Runtime: {_md(record.config_snapshot.get('runtime'))}",
        f"- Modelo: {record.llm_provider}/{record.llm_model}",
        f"- Embeddings: {_md(record.embedding_model)}",
        f"- Semilla: {record.eval_seed}",
        f"- Commit: {_md(record.git_commit)}",
        f"- Casos ejecutados: {len(results)}",
        f"- Casos aprobados (todos): {passed}",
        f"- Éxito de positivos (RNF-002): {_pct(aggregate.success_rate)}",
    ]
    lines.extend(_gate_summary_lines(aggregate, verdict))
    lines.extend(
        [
            "",
            "## Métricas agregadas",
            "",
            "| Métrica | Valor |",
            "|---|---|",
            f"| latency_p50_ms | {_md(aggregate.latency_p50_ms)} |",
            f"| latency_p95_ms | {_md(aggregate.latency_p95_ms)} |",
            f"| latency_simple_p95_ms | {_md(aggregate.latency_simple_p95_ms)} |",
            f"| latency_multistep_p95_ms | {_md(aggregate.latency_multistep_p95_ms)} |",
            f"| avg_cost_usd | {_md(aggregate.avg_cost_usd)} |",
            f"| recall_at_10 | {_pct(aggregate.recall_at_10)} |",
            f"| claims_coverage | {_pct(aggregate.claims_coverage)} |",
            f"| claims_reproducible | {_pct(aggregate.claims_reproducible)} |",
            f"| orphan_figures_count | {aggregate.orphan_figures_count} |",
            f"| fabrication_count | {aggregate.fabrication_count} |",
        ]
    )
    lines.extend(
        [
            "",
            "## Resultado por caso",
            "",
            "| Caso | Agent run | Aprobó | Última etapa | Etapa de fallo | Código | "
            "Responsable | Motivo humano |",
            "|---|---|---:|---|---|---|---|---|",
        ]
    )
    lines.extend(
        f"| {_md(case_id)} | {_md(diag.get('agent_run_id'))} | {'sí' if item.passed else 'no'} | "
        f"{_md(diag['last_successful_stage'])} | {_md(diag['failure_stage'])} | "
        f"{_md(diag['failure_code'])} | "
        f"{_md(diag['failure_owner'])} | {_md(item.failure_reason)} |"
        for case_id, item, diag in results
    )
    stage_counts: dict[str, int] = {}
    code_counts: dict[str, int] = {}
    for _case_id, _item, diagnostics in results:
        if diagnostics["failure_stage"]:
            key = str(diagnostics["failure_stage"])
            stage_counts[key] = stage_counts.get(key, 0) + 1
        if diagnostics["failure_code"]:
            key = str(diagnostics["failure_code"])
            code_counts[key] = code_counts.get(key, 0) + 1
    lines.extend(["", "## Fallos por etapa", "", "| Etapa | Casos |", "|---|---:|"])
    lines.extend(f"| {_md(key)} | {count} |" for key, count in sorted(stage_counts.items()))
    lines.extend(["", "## Motivos de fallo", "", "| Código | Casos |", "|---|---:|"])
    lines.extend(f"| {_md(key)} | {count} |" for key, count in sorted(code_counts.items()))
    lines.extend(
        [
            "",
            "## Recuperación",
            "",
            "| Caso | Recuperados | Intentados | Aceptado | Rango esperado | "
            "Candidatos | Consultas | Exploraciones | Llamadas LLM |",
            "|---|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    lines.extend(
        f"| {_md(case_id)} | {_md(', '.join(diag['retrieved_dataset_ids']))} | "
        f"{_md(', '.join(diag['attempted_dataset_ids']))} | {_md(diag['accepted_dataset_id'])} | "
        f"{_md(diag['expected_dataset_rank'])} | {diag['candidate_count']} | "
        f"{diag['query_count']} | "
        f"{diag['exploration_count']} | {diag['llm_call_count']} |"
        for case_id, _item, diag in results
    )
    lines.extend(
        [
            "",
            "## Consumo y salida",
            "",
            "| Caso | Stop reason | Evidencias | Claims | Hechos verificados | "
            "Latencia ms | Costo USD |",
            "|---|---|---:|---:|---|---:|---:|",
        ]
    )
    lines.extend(
        f"| {_md(case_id)} | {_md(diag['stop_reason'])} | {diag['evidence_count']} | "
        f"{diag['claim_count']} | {_md(diag['facts_verified'])} | {_md(diag['latency_ms'])} | "
        f"{_md(diag['estimated_cost_usd'])} |"
        for case_id, _item, diag in results
    )
    lines.extend(
        [
            "",
            "## Integridad textual",
            "",
            "| Caso | Aplica | Cobertura refs | Reproducibles | Presentación | "
            "Segmentos huérfanos | Operaciones inválidas | Integridad total |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case_id, item, _diag in results:
        metric = item.textual_integrity
        lines.append(
            f"| {_md(case_id)} | "
            f"{'sí' if metric and metric.applicable else 'no'} | "
            f"{_md(metric.textual_fact_reference_coverage if metric else None)} | "
            f"{_md(metric.textual_facts_reproducible if metric else None)} | "
            f"{_md(metric.textual_fact_display_match if metric else None)} | "
            f"{metric.orphan_factual_segments_count if metric else 0} | "
            f"{metric.invalid_textual_operation_count if metric else 0} | "
            f"{'sí' if metric is None or metric.grounded_fact_integrity else 'no'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclasses.dataclass(frozen=True)
class RunSuiteResult:
    report_path: Path
    success_rate: float | None
    aggregate: AggregateMetrics | None = None
    verdict: GateVerdict | None = None


def _build_case_outcome(
    case,
    assessment: CaseAssessment,
    stage_diagnostics: dict[str, object],
    claims_integrity: ClaimsIntegrityAssessment,
    observations: tuple[StageObservation, ...],
) -> CaseOutcome:
    """Reúne las señales por caso para agregación y veredicto (sin I/O)."""

    latency_raw = stage_diagnostics.get("latency_ms")
    cost_raw = stage_diagnostics.get("estimated_cost_usd")
    socrata = socrata_success_rate(observations)
    return CaseOutcome(
        case_id=case.case_id,
        case_type=case.case_type,
        passed=assessment.passed,
        fabrication=assessment.fabrication,
        recall_hit=assessment.recall_hit,
        failure_stage=stage_diagnostics.get("failure_stage"),
        failure_code=stage_diagnostics.get("failure_code"),
        complexity=classify_run_complexity(stage_diagnostics),
        latency_ms=int(latency_raw) if isinstance(latency_raw, (int, float)) else None,
        cost_usd=Decimal(str(cost_raw)) if isinstance(cost_raw, (int, float)) else None,
        claims_integrity=claims_integrity,
        socrata_successes=socrata[0] if socrata else 0,
        socrata_attempts=socrata[1] if socrata else 0,
    )


async def run_suite(
    *,
    suite_name: str,
    provider: str | None,
    model: str | None,
    seed: int,
    limit: int | None,
    case_ids: list[str] | None = None,
    gate_mode: str = "full",
) -> RunSuiteResult:
    settings = get_settings()
    if not settings.eval_mode:
        raise RuntimeError("EVAL_MODE=true es obligatorio para ejecutar una evaluación.")
    settings = settings.model_copy(
        update={
            "llm_provider": provider or settings.llm_provider,
            "llm_model": model or settings.llm_model,
        }
    )
    suite = load_golden_suite(default_suite_path(suite_name))
    selected_cases = _select_cases(suite.cases, limit=limit, case_ids=case_ids)
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    worker_id: str | None = None
    try:
        persisted = await sync_golden_suite(engine, suite)
        record = await _create_eval_record(engine, persisted, settings, seed)
        worker_id = await register_worker_instance(engine, settings.worker_lease_ttl_s)
        results: list[tuple[str, CaseAssessment, dict[str, object]]] = []
        outcomes: list[CaseOutcome] = []
        for case in selected_cases:
            agent_run_id: uuid.UUID | None = None
            error_code: str | None = None
            observations: tuple[StageObservation, ...] = ()
            try:
                agent_run_id = await create_eval_run(
                    engine,
                    worker_instance_id=worker_id,
                    question=case.question,
                    retention_eval_months=settings.retention_eval_months,
                )
                await execute_agent_run_async(settings, agent_run_id)
                run = await get_run(engine, agent_run_id)
                final = run.final_answer if run and run.final_answer else {"status": "failed"}
                observations = await _stage_observations(engine, agent_run_id)
                synthesis_plan = next(
                    (
                        observation.detail.get("grounded_synthesis_plan")
                        for observation in observations
                        if observation.node == "synthesize"
                        and isinstance(observation.detail.get("grounded_synthesis_plan"), dict)
                    ),
                    None,
                )
                allowed_facts: list[dict[str, object]] = []
                verified_textual_facts: list[dict[str, object]] = []
                if final.get("textual_facts") or synthesis_plan is not None:
                    allowed = await load_allowed_grounded_facts(engine, agent_run_id)
                    allowed_facts = [fact.model_dump(mode="json") for fact in allowed.facts]
                    allowed_textual_ids = {
                        str(fact.id) for fact in allowed.facts if fact.fact_kind.value == "textual"
                    }
                    persisted_textual_facts = await load_textual_facts(engine, agent_run_id)
                    verified_textual_facts = [
                        fact.model_dump(mode="json")
                        for fact in persisted_textual_facts
                        if str(fact.fact_id) in allowed_textual_ids
                    ]
                textual_integrity = assess_textual_integrity(
                    final,
                    synthesis_plan,
                    allowed_facts,
                    verified_textual_facts,
                )
                assessment = assess_case(
                    case,
                    final,
                    textual_integrity=textual_integrity,
                )
                search_dataset_ids = await _planner_search_dataset_ids(engine, agent_run_id)
                assessment = dataclasses.replace(
                    assessment, recall_hit=recall_hit_at_10(case, search_dataset_ids)
                )
            except Exception as exc:  # noqa: BLE001 - un caso no puede tumbar los otros 49
                error_code = type(exc).__name__
                final = {"status": "eval_error"}
                assessment = CaseAssessment(
                    passed=False,
                    expected_dataset_hit=None,
                    fabrication=False,
                    evidence_dataset_ids=(),
                    claim_hashes=(),
                    failure_reason=f"Error de infraestructura al ejecutar el caso: {exc}",
                )
            if not observations:
                observations = await _stage_observations(engine, agent_run_id)
            stage_diagnostics = build_stage_diagnostics(
                case,
                final,
                assessment,
                observations,
                infrastructure_error=error_code,
            )
            stage_diagnostics["agent_run_id"] = (
                str(agent_run_id) if agent_run_id is not None else None
            )
            claims_integrity = evaluate_claims_integrity(final)
            try:
                await _persist_case_result(
                    engine,
                    eval_run_id=record.id,
                    case_db_id=persisted.case_ids[case.case_id],
                    agent_run_id=agent_run_id,
                    final=final,
                    assessment=assessment,
                    stage_diagnostics=stage_diagnostics,
                    claims_integrity=claims_integrity,
                    error_code=error_code,
                )
            except Exception as exc:  # noqa: BLE001
                # agent_run_id pudo dejar de existir entre la ejecucion y este
                # punto (p. ej. un barrido de retencion concurrente sobre la
                # misma base compartida viola la FK). Reintenta sin la
                # referencia rota; si sigue fallando, no tumba los otros 49.
                try:
                    await _persist_case_result(
                        engine,
                        eval_run_id=record.id,
                        case_db_id=persisted.case_ids[case.case_id],
                        agent_run_id=None,
                        final=final,
                        assessment=assessment,
                        stage_diagnostics=stage_diagnostics,
                        claims_integrity=claims_integrity,
                        error_code=type(exc).__name__,
                    )
                except Exception:  # noqa: BLE001
                    pass
            results.append((case.case_id, assessment, stage_diagnostics))
            outcomes.append(
                _build_case_outcome(
                    case, assessment, stage_diagnostics, claims_integrity, observations
                )
            )
        aggregate = aggregate_metrics(outcomes)
        verdict = (
            evaluate_smoke_gate(outcomes) if gate_mode == "smoke" else evaluate_full_gate(aggregate)
        )
        await _finalize_eval_record(engine, record_id=record.id, aggregate=aggregate)
        report_path = Path("eval/reports") / f"{record.id}.md"
        _write_report(
            report_path,
            record=record,
            suite_name=suite.name,
            results=results,
            aggregate=aggregate,
            verdict=verdict,
        )
        return RunSuiteResult(
            report_path=report_path,
            success_rate=aggregate.success_rate,
            aggregate=aggregate,
            verdict=verdict,
        )
    finally:
        if worker_id is not None:
            await mark_worker_shutdown(engine, worker_id)
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecuta una suite golden OE3 con LLM real")
    parser.add_argument("--suite", dest="suite_name", default="golden-v1")
    parser.add_argument("--provider", choices=["google", "anthropic"])
    parser.add_argument("--model")
    parser.add_argument("--seed", type=int, default=601000)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--case-id",
        dest="case_ids",
        action="append",
        help="Ejecuta sólo el case_id indicado; puede repetirse.",
    )
    parser.add_argument(
        "--gate",
        dest="gate_mode",
        choices=["full", "smoke"],
        default="full",
        help=(
            "Puerta a aplicar: 'full' es el umbral completo de golden (RNF-001…005/009); "
            "'smoke' es la puerta dirigida de pruebas.md §4.4 (negativos 100%, ningún "
            "positivo sólido retrocede, todo fallo con etapa+código)."
        ),
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit debe ser mayor que cero")
    if args.limit is not None and args.case_ids:
        parser.error("--limit y --case-id son mutuamente excluyentes")
    kwargs = vars(args)
    try:
        if sys.platform == "win32":
            result = asyncio.run(run_suite(**kwargs), loop_factory=asyncio.SelectorEventLoop)
        else:
            result = asyncio.run(run_suite(**kwargs))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    verdict = result.verdict
    print(
        json.dumps(
            {
                "report": str(result.report_path),
                "success_rate": result.success_rate,
                "gate_mode": verdict.mode if verdict else None,
                "gate_passed": verdict.passed if verdict else None,
                "blocking_reasons": list(verdict.blocking_reasons) if verdict else [],
            },
            ensure_ascii=False,
        )
    )
    # El exit code depende del VEREDICTO DE PUERTA completo, no solo de
    # success_rate: una corrida golden-v2 debe fallar si incumple cualquier
    # condición normativa (negativos 100%, fabricaciones 0, cifras huérfanas 0,
    # integridad de claims, recall, latencia y costo), no solo el umbral de
    # positivos (RNF-002). El smoke usa su propia puerta.
    if verdict is not None and not verdict.passed:
        for reason in verdict.blocking_reasons:
            print(f"PUERTA {verdict.mode} FAIL: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
