"""Ejecución vertical determinista desde un plan validado hasta claims."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.persistence import (
    build_verify_persist_textual_facts,
    persist_claims,
    persist_evidence_and_quality,
)
from app.agent.plan_validator import (
    ValidatedQueryPlan,
    ValidatedTextualColumn,
    ValidatedTextualRequest,
)
from app.agent.query_plan import PiiRiskLevel, QueryOperation, SortTargetKind
from app.agent.soql_renderer import RenderedQuery, render_soql
from app.quality.claims import (
    ClaimsBuildResult,
    ClaimSpec,
    EvidenceContext,
    build_claims,
)
from app.quality.grounded_facts import (
    CategorySelectionParams,
    CategorySelectionRule,
    ExtremumLabelParams,
    TextualFact,
    TextualFactOperation,
)
from app.quality.textual_fact_builder import (
    TextualFactBuildCommand,
    TextualFactError,
)
from app.quality.textual_facts import (
    TextualEvidence,
    TextualFactSpec,
    TextualOperationError,
    evaluate_textual_operation,
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
    textual_facts: tuple[PreparedTextualFact, ...] = ()
    textual_rejections: tuple[TextualRejection, ...] = ()


@dataclass(frozen=True)
class PersistedDeterministicExecution:
    execution: DeterministicExecutionResult
    evidence: dict[str, Any]
    claims: tuple[dict[str, Any], ...]
    textual_facts: tuple[TextualFact, ...] = ()
    textual_rejections: tuple[TextualRejection, ...] = ()


@dataclass(frozen=True)
class PreparedTextualFact:
    spec: TextualFactSpec
    validated_order_is_total: bool


@dataclass(frozen=True)
class TextualRejection:
    operation: TextualFactOperation
    code: str


class DeterministicExecutionError(RuntimeError):
    pass


class DeterministicPersistenceCancelled(RuntimeError):
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


def _lookup_presence_specs(
    plan: ValidatedQueryPlan,
    rendered: RenderedQuery,
    rows: tuple[dict, ...],
) -> tuple[ClaimSpec, ...]:
    """Representa filas textuales como presencia verificable, sin fingir magnitudes."""

    specs: list[ClaimSpec] = []
    field_aliases = tuple(
        zip(
            (dimension.field_name for dimension in plan.dimensions),
            rendered.dimension_aliases,
            strict=True,
        )
    )
    for row_index, row in enumerate(rows[:12]):
        observed = tuple(
            (field_name, alias, row.get(alias))
            for field_name, alias in field_aliases
            if row.get(alias) is not None
        )
        if not observed:
            continue
        description = "Registro observado: " + "; ".join(
            f"{field_name}={value}" for field_name, _alias, value in observed
        )
        count_alias = observed[0][1]
        specs.append(
            ClaimSpec(
                claim_type="derived",
                description=description,
                source_row_indexes=(row_index,),
                columns=(count_alias,),
                formula={"agg": "count", "col": count_alias},
            )
        )
    return tuple(specs)


def _alias(column: ValidatedTextualColumn, rendered: RenderedQuery) -> str:
    aliases = (
        rendered.dimension_aliases
        if column.target_kind is SortTargetKind.DIMENSION
        else rendered.metric_aliases
    )
    return aliases[column.target_index]


def _textual_spec(
    request: ValidatedTextualRequest,
    rendered: RenderedQuery,
) -> TextualFactSpec:
    columns = tuple(_alias(column, rendered) for column in request.columns)
    params = request.operation_params
    if isinstance(params, ExtremumLabelParams):
        params = ExtremumLabelParams(
            label_column=columns[0],
            metric_column=columns[1],
            tie_policy=params.tie_policy,
        )
    return TextualFactSpec(
        operation=request.operation,
        source_row_indexes=request.source_row_indexes,
        columns=columns,
        operation_params=params,
    )


def _validated_order_is_total(
    plan: ValidatedQueryPlan,
    rendered: RenderedQuery,
    rows: tuple[dict, ...],
    request: ValidatedTextualRequest,
) -> bool:
    params = request.operation_params
    if not (
        request.operation is TextualFactOperation.CATEGORY_SELECTION
        and isinstance(params, CategorySelectionParams)
        and params.rule is CategorySelectionRule.FIRST_BY_VALIDATED_ORDER
    ):
        return False
    if request.source_row_indexes != (0,) or plan.limit < 2 or not rows:
        return False

    expected = {
        *((SortTargetKind.DIMENSION, index) for index in range(len(plan.dimensions))),
        *((SortTargetKind.METRIC, index) for index in range(len(plan.metrics))),
    }
    observed = {(item.target_kind, item.target_index) for item in plan.order_by}
    if len(plan.order_by) != len(observed) or observed != expected:
        return False

    ordered_aliases = tuple(
        (
            rendered.dimension_aliases
            if item.target_kind is SortTargetKind.DIMENSION
            else rendered.metric_aliases
        )[item.target_index]
        for item in plan.order_by
    )
    if len(rows) == 1:
        return len(rows) < plan.limit
    first_key = tuple(rows[0].get(alias) for alias in ordered_aliases)
    second_key = tuple(rows[1].get(alias) for alias in ordered_aliases)
    return first_key != second_key


def _prepare_textual_facts(
    plan: ValidatedQueryPlan,
    rendered: RenderedQuery,
    *,
    canonical_soql: str,
    rows: tuple[dict, ...],
) -> tuple[tuple[PreparedTextualFact, ...], tuple[TextualRejection, ...]]:
    prepared: list[PreparedTextualFact] = []
    rejected: list[TextualRejection] = []
    for request in plan.textual_requests:
        if canonical_soql != rendered.canonical_soql:
            rejected.append(
                TextualRejection(
                    operation=request.operation,
                    code="textual_canonical_query_mismatch",
                )
            )
            continue
        spec = _textual_spec(request, rendered)
        order_is_total = _validated_order_is_total(plan, rendered, rows, request)
        try:
            evaluate_textual_operation(
                evidence=TextualEvidence(
                    dataset_id=rendered.dataset_id,
                    canonical_soql=canonical_soql,
                    rows=rows,
                    validated_order_is_total=order_is_total,
                ),
                spec=spec,
            )
        except TextualOperationError as exc:
            rejected.append(TextualRejection(operation=request.operation, code=exc.code))
            continue
        prepared.append(
            PreparedTextualFact(
                spec=spec,
                validated_order_is_total=order_is_total,
            )
        )
    return tuple(prepared), tuple(rejected)


async def execute_validated_plan(
    plan: ValidatedQueryPlan,
    *,
    executor: QueryExecutor,
    metadata: ExecutionMetadata,
    textual_facts_enabled: bool = False,
    is_cancelled: Callable[[], bool] | None = None,
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
    if is_cancelled is not None and is_cancelled():
        raise DeterministicPersistenceCancelled("corrida cancelada antes de construir texto")
    textual_facts: tuple[PreparedTextualFact, ...] = ()
    textual_rejections: tuple[TextualRejection, ...] = ()
    if textual_facts_enabled:
        textual_facts, textual_rejections = _prepare_textual_facts(
            plan,
            rendered,
            canonical_soql=canonical_soql,
            rows=rows,
        )
    claims = build_claims(
        EvidenceContext(
            dataset_id=rendered.dataset_id,
            canonical_soql=canonical_soql,
            rows=rows,
        ),
        _claim_specs(plan, rendered, rows),
    )
    if not claims.claims and plan.operation is QueryOperation.LOOKUP and not textual_facts_enabled:
        presence_claims = build_claims(
            EvidenceContext(
                dataset_id=rendered.dataset_id,
                canonical_soql=canonical_soql,
                rows=rows,
            ),
            _lookup_presence_specs(plan, rendered, rows),
        )
        claims = ClaimsBuildResult(
            claims=presence_claims.claims,
            rejected=claims.rejected + presence_claims.rejected,
        )
    if not claims.claims and not (textual_facts_enabled and (textual_facts or textual_rejections)):
        reasons = "; ".join(item.reason for item in claims.rejected) or "sin claims"
        raise DeterministicExecutionError(f"CLAIMS_REJECTED: {reasons}")
    return DeterministicExecutionResult(
        rendered_query=rendered,
        tool_output=output,
        evidence_draft=evidence,
        quality=quality,
        claims=claims,
        textual_facts=textual_facts,
        textual_rejections=textual_rejections,
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
    is_cancelled: Callable[[], bool] | None = None,
) -> PersistedDeterministicExecution:
    """Persiste T6/T7 y luego el lote textual en fronteras transaccionales separadas.

    Evidencia/calidad, claims cuantitativos y el lote textual tienen commits
    independientes. Un rechazo textual revierte todo su lote sin invalidar
    claims cuantitativos ya válidos (RF-208/RF-210).
    """

    if is_cancelled is not None and is_cancelled():
        raise DeterministicPersistenceCancelled("corrida cancelada antes de persistir")
    evidence = await persist_evidence_and_quality(
        engine,
        run_id,
        execution.evidence_draft,
        execution.quality,
        official_publisher_id=official_publisher_id,
    )
    evidence_id = uuid.UUID(str(evidence["evidence_id"]))
    if is_cancelled is not None and is_cancelled():
        raise DeterministicPersistenceCancelled(
            "corrida cancelada después de evidencia y antes de claims"
        )
    claim_records = await persist_claims(
        engine,
        run_id,
        evidence_id,
        execution.rendered_query.dataset_id,
        execution.claims.claims,
    )
    if is_cancelled is not None and is_cancelled():
        raise DeterministicPersistenceCancelled(
            "corrida cancelada antes de persistir hechos textuales"
        )
    textual_facts: tuple[TextualFact, ...] = ()
    textual_rejections = execution.textual_rejections
    if execution.textual_facts:
        commands = tuple(
            TextualFactBuildCommand(
                evidence_id=evidence_id,
                dataset_id=execution.rendered_query.dataset_id,
                spec=item.spec,
                validated_order_is_total=item.validated_order_is_total,
            )
            for item in execution.textual_facts
        )
        try:
            textual_facts = await build_verify_persist_textual_facts(
                engine,
                run_id,
                commands,
            )
        except TextualFactError as exc:
            textual_rejections = (
                *textual_rejections,
                *(
                    TextualRejection(operation=item.spec.operation, code=exc.code)
                    for item in execution.textual_facts
                ),
            )
    return PersistedDeterministicExecution(
        execution=execution,
        evidence=evidence,
        claims=tuple(claim_records),
        textual_facts=textual_facts,
        textual_rejections=textual_rejections,
    )


async def execute_and_persist_validated_plan(
    plan: ValidatedQueryPlan,
    *,
    engine: AsyncEngine,
    run_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    metadata: ExecutionMetadata,
    app_token: str | None = None,
    textual_facts_enabled: bool = False,
    is_cancelled: Callable[[], bool] | None = None,
) -> PersistedDeterministicExecution:
    execution = await execute_validated_plan(
        plan,
        executor=make_soql_executor(
            engine=engine,
            http_client=http_client,
            app_token=app_token,
        ),
        metadata=metadata,
        textual_facts_enabled=textual_facts_enabled,
        is_cancelled=is_cancelled,
    )
    return await persist_deterministic_execution(
        execution,
        engine=engine,
        run_id=run_id,
        official_publisher_id=metadata.official_publisher_id,
        is_cancelled=is_cancelled,
    )
