"""Ejecución vertical determinista desde un plan validado hasta claims."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.persistence import persist_claims, persist_evidence_and_quality
from app.agent.plan_validator import ValidatedQueryPlan
from app.agent.query_plan import PiiRiskLevel, QueryOperation
from app.agent.soql_renderer import RenderedQuery, render_soql
from app.quality.claims import (
    ClaimsBuildResult,
    ClaimSpec,
    EvidenceContext,
    build_claims,
)
from app.quality.validator import (
    EvidenceDraft,
    QualityResult,
    SelectedColumn,
    validate_evidence,
)
from app.tools.ejecutar_soql import ejecutar_soql

QueryExecutor = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ExecutionMetadata:
    dataset_name: str
    publisher: str | None
    dataset_pii_risk_level: str
    dataset_eligibility_status: str
    dataset_eligibility_reasons: tuple[str, ...] = ()
    data_updated_at: datetime | None = None
    official_publisher_id: str | None = None


@dataclass(frozen=True)
class DeterministicExecutionResult:
    rendered_query: RenderedQuery
    tool_output: dict[str, Any]
    evidence_draft: EvidenceDraft
    quality: QualityResult
    claims: ClaimsBuildResult


@dataclass(frozen=True)
class PersistedDeterministicExecution:
    execution: DeterministicExecutionResult
    evidence: dict[str, Any]
    claims: tuple[dict[str, Any], ...]


class DeterministicExecutionError(RuntimeError):
    pass


def _selected_columns(rendered: RenderedQuery) -> tuple[SelectedColumn, ...]:
    selected = [
        SelectedColumn(field_name=alias, pii_risk_level=PiiRiskLevel.LOW.value)
        for alias in (*rendered.dimension_aliases, *rendered.metric_aliases)
    ]
    if rendered.group_count_alias:
        selected.append(
            SelectedColumn(
                field_name=rendered.group_count_alias,
                pii_risk_level=PiiRiskLevel.LOW.value,
            )
        )
    return tuple(selected)


def _claim_specs(
    plan: ValidatedQueryPlan, rendered: RenderedQuery, rows: tuple[dict, ...]
) -> tuple[ClaimSpec, ...]:
    specs: list[ClaimSpec] = []
    aliases = (
        rendered.dimension_aliases
        if plan.operation is QueryOperation.LOOKUP
        else rendered.metric_aliases
    )
    for row_index, row in enumerate(rows):
        for alias in aliases:
            if row.get(alias) is None:
                continue
            specs.append(
                ClaimSpec(
                    claim_type="direct",
                    description=f"{plan.purpose} ({alias}, fila {row_index})",
                    source_row_indexes=(row_index,),
                    columns=(alias,),
                )
            )
    return tuple(specs)


async def execute_validated_plan(
    plan: ValidatedQueryPlan,
    *,
    executor: QueryExecutor,
    metadata: ExecutionMetadata,
) -> DeterministicExecutionResult:
    """Ejecuta T5→T6→T7 sin participación de un LLM."""

    rendered = render_soql(plan)
    output = await executor(
        {
            "dataset_id": rendered.dataset_id,
            "soql": rendered.canonical_soql,
            "purpose": rendered.purpose,
        }
    )
    if output.get("ok") is not True:
        error = output.get("error", {})
        raise DeterministicExecutionError(
            f"{error.get('code', 'QUERY_FAILED')}: {error.get('message', 'falló T5')}"
        )
    rows = tuple(output.get("rows", ()))
    canonical_soql = output.get("canonical_soql", rendered.canonical_soql)
    evidence = EvidenceDraft(
        dataset_id=rendered.dataset_id,
        dataset_name=metadata.dataset_name,
        publisher=metadata.publisher,
        source_url=output.get("source_url"),
        dataset_pii_risk_level=metadata.dataset_pii_risk_level,
        dataset_eligibility_status=metadata.dataset_eligibility_status,
        dataset_eligibility_reasons=metadata.dataset_eligibility_reasons,
        canonical_soql=canonical_soql,
        selected_columns=_selected_columns(rendered),
        rows=rows,
        row_count=len(rows),
        data_updated_at=metadata.data_updated_at,
        evaluated_at=datetime.now(UTC),
    )
    quality = validate_evidence(evidence)
    if quality.eligibility_status != "eligible":
        raise DeterministicExecutionError(
            "EVIDENCE_NOT_ELIGIBLE: " + ",".join(quality.eligibility_reasons)
        )
    claims = build_claims(
        EvidenceContext(
            dataset_id=rendered.dataset_id,
            canonical_soql=canonical_soql,
            rows=rows,
        ),
        _claim_specs(plan, rendered, rows),
    )
    if claims.rejected or not claims.claims:
        reasons = "; ".join(item.reason for item in claims.rejected) or "sin claims"
        raise DeterministicExecutionError(f"CLAIMS_REJECTED: {reasons}")
    return DeterministicExecutionResult(
        rendered_query=rendered,
        tool_output=output,
        evidence_draft=evidence,
        quality=quality,
        claims=claims,
    )


def make_soql_executor(
    *,
    engine: AsyncEngine,
    http_client: httpx.AsyncClient,
    app_token: str | None = None,
) -> QueryExecutor:
    """Adapta T5 al contrato mínimo consumido por el pipeline."""

    async def _execute(payload: dict[str, Any]) -> dict[str, Any]:
        return await ejecutar_soql(
            payload,
            engine=engine,
            http_client=http_client,
            app_token=app_token,
        )

    return _execute


async def persist_deterministic_execution(
    execution: DeterministicExecutionResult,
    *,
    engine: AsyncEngine,
    run_id: uuid.UUID,
    official_publisher_id: str | None,
) -> PersistedDeterministicExecution:
    """Persiste T6 y T7 usando exclusivamente IDs creados por código."""

    evidence = await persist_evidence_and_quality(
        engine,
        run_id,
        execution.evidence_draft,
        execution.quality,
        official_publisher_id=official_publisher_id,
    )
    evidence_id = uuid.UUID(str(evidence["evidence_id"]))
    claim_records = await persist_claims(
        engine,
        run_id,
        evidence_id,
        execution.rendered_query.dataset_id,
        execution.claims.claims,
    )
    return PersistedDeterministicExecution(
        execution=execution,
        evidence=evidence,
        claims=tuple(claim_records),
    )


async def execute_and_persist_validated_plan(
    plan: ValidatedQueryPlan,
    *,
    engine: AsyncEngine,
    run_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    metadata: ExecutionMetadata,
    app_token: str | None = None,
) -> PersistedDeterministicExecution:
    execution = await execute_validated_plan(
        plan,
        executor=make_soql_executor(
            engine=engine,
            http_client=http_client,
            app_token=app_token,
        ),
        metadata=metadata,
    )
    return await persist_deterministic_execution(
        execution,
        engine=engine,
        run_id=run_id,
        official_publisher_id=metadata.official_publisher_id,
    )
