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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.durability import get_run
from app.agent.runner import create_eval_run, execute_agent_run_async
from app.agent.worker_lease import mark_worker_shutdown, register_worker_instance
from app.config import get_settings
from app.db.engine import create_app_async_engine
from app.db.models import AgentStep, EvalCaseResult, EvalRun
from eval.loader import default_suite_path, load_golden_suite
from eval.metrics import CaseAssessment, assess_case, recall_hit_at_10
from eval.persistence import PersistedGoldenSuite, sync_golden_suite


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _config_snapshot(settings) -> dict[str, object]:
    return {
        "agent_max_steps": settings.agent_max_steps,
        "embedding_model": settings.embedding_model,
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
    if step is None or not isinstance(step.tool_output_summary, dict):
        return []
    results = step.tool_output_summary.get("results")
    if not isinstance(results, list):
        return []
    return [
        item["dataset_id"]
        for item in results
        if isinstance(item, dict) and item.get("dataset_id")
    ]


async def _persist_case_result(
    engine,
    *,
    eval_run_id: uuid.UUID,
    case_db_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    final: dict,
    assessment: CaseAssessment,
    error_code: str | None = None,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            EvalCaseResult(
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
                },
                quality_summary=[item.get("quality") for item in final.get("evidence", [])],
                evidence_dataset_ids=list(assessment.evidence_dataset_ids),
                claim_fingerprint_hashes=list(assessment.claim_hashes),
                error_code=error_code,
                failure_reason=assessment.failure_reason,
            )
        )


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
        config_snapshot=_config_snapshot(settings),
        started_at=datetime.now(UTC),
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(record)
    return record


async def _finalize_eval_record(
    engine, *, record_id: uuid.UUID, results: list[tuple[str, CaseAssessment]]
) -> None:
    """Cierra la corrida OE3 con los agregados disponibles del smoke/completo."""

    total = len(results)
    passed = sum(assessment.passed for _, assessment in results)
    positive = [item for item in results if item[1].recall_hit is not None]
    recall_hits = sum(bool(assessment.recall_hit) for _, assessment in positive)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        record = await session.get(EvalRun, record_id)
        assert record is not None
        record.finished_at = datetime.now(UTC)
        record.success_rate = Decimal(passed) / Decimal(total) if total else None
        record.recall_at_10 = Decimal(recall_hits) / Decimal(len(positive)) if positive else None
        record.fabrication_count = sum(assessment.fabrication for _, assessment in results)
        record.orphan_figures_count = sum(
            len(assessment.orphan_figures) for _, assessment in results
        )


def _write_report(
    path: Path, *, record: EvalRun, results: list[tuple[str, CaseAssessment]]
) -> None:
    passed = sum(item.passed for _, item in results)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Evaluación {record.id}",
        "",
        "- Suite: golden-v1",
        f"- Modelo: {record.llm_provider}/{record.llm_model}",
        f"- Casos ejecutados: {len(results)}",
        f"- Casos aprobados: {passed}",
        f"- Éxito: {passed / len(results):.1%}" if results else "- Éxito: no aplica",
        "",
        "| Caso | Aprobó | Motivo |",
        "|---|---:|---|",
    ]
    lines.extend(
        f"| {case_id} | {'sí' if item.passed else 'no'} | {item.failure_reason or ''} |"
        for case_id, item in results
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_suite(
    *,
    suite_name: str,
    provider: str | None,
    model: str | None,
    seed: int,
    limit: int | None,
) -> Path:
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
    selected_cases = suite.cases[:limit] if limit is not None else suite.cases
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    worker_id: str | None = None
    try:
        persisted = await sync_golden_suite(engine, suite)
        record = await _create_eval_record(engine, persisted, settings, seed)
        worker_id = await register_worker_instance(engine, settings.worker_lease_ttl_s)
        results: list[tuple[str, CaseAssessment]] = []
        for case in selected_cases:
            agent_run_id: uuid.UUID | None = None
            error_code: str | None = None
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
                assessment = assess_case(case, final)
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
            await _persist_case_result(
                engine,
                eval_run_id=record.id,
                case_db_id=persisted.case_ids[case.case_id],
                agent_run_id=agent_run_id,
                final=final,
                assessment=assessment,
                error_code=error_code,
            )
            results.append((case.case_id, assessment))
        await _finalize_eval_record(engine, record_id=record.id, results=results)
        report_path = Path("eval/reports") / f"{record.id}.md"
        _write_report(report_path, record=record, results=results)
        return report_path
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
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit debe ser mayor que cero")
    kwargs = vars(args)
    try:
        if sys.platform == "win32":
            report = asyncio.run(run_suite(**kwargs), loop_factory=asyncio.SelectorEventLoop)
        else:
            report = asyncio.run(run_suite(**kwargs))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"report": str(report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
