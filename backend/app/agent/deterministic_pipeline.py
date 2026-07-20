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
from app.agent.query_plan import ColumnDataType, PiiRiskLevel, QueryOperation, SortTargetKind
from app.agent.soql_renderer import RenderedQuery, render_soql
from app.quality.claim_labels import (
    COUNT_FIELD_SENTINEL,
    column_is_explicitly_requested,
    intent_relevance_tokens,
    is_identifier_field_name,
)
from app.quality.claims import (
    ClaimsBuildResult,
    ClaimSpec,
    EvidenceContext,
    build_claims,
)
from app.quality.grounded_facts import (
    CategorySelectionParams,
    CategorySelectionRule,
    EmptyTextualFactOperationParams,
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
    """Fallo posterior a invocar T5, conservando su salida observable."""

    def __init__(self, message: str, *, tool_output: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.tool_output = tool_output


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


def _column_field_names(plan: ValidatedQueryPlan, rendered: RenderedQuery) -> dict[str, str]:
    """Mapea cada alias de ejecución (`dim_N`/`metric_<op>_N`/`group_count`) al
    nombre de columna fuente real, o al centinela `COUNT_FIELD_SENTINEL`
    cuando el alias representa `count(*)` sin columna propia (RF-212)."""

    mapping: dict[str, str] = {}
    for dimension, alias in zip(plan.dimensions, rendered.dimension_aliases, strict=True):
        mapping[alias] = dimension.field_name
    for metric, alias in zip(plan.metrics, rendered.metric_aliases, strict=True):
        mapping[alias] = (
            metric.field_name if metric.field_name is not None else COUNT_FIELD_SENTINEL
        )
    if rendered.group_count_alias is not None:
        mapping[rendered.group_count_alias] = COUNT_FIELD_SENTINEL
    return mapping


def _claim_specs(
    plan: ValidatedQueryPlan, rendered: RenderedQuery, rows: tuple[dict, ...]
) -> tuple[ClaimSpec, ...]:
    specs: list[ClaimSpec] = []
    aliases = (
        rendered.dimension_aliases
        if plan.operation is QueryOperation.LOOKUP
        else rendered.metric_aliases
    )
    column_field_names = _column_field_names(plan, rendered)
    identifier_aliases = {
        alias
        for dimension, alias in zip(
            plan.dimensions,
            rendered.dimension_aliases,
            strict=True,
        )
        if is_identifier_field_name(dimension.field_name)
    }
    for row_index, row in enumerate(rows):
        for alias in aliases:
            if row.get(alias) is None or alias in identifier_aliases:
                continue
            specs.append(
                ClaimSpec(
                    claim_type="direct",
                    description=f"{plan.purpose} ({alias}, fila {row_index})",
                    source_row_indexes=(row_index,),
                    columns=(alias,),
                    column_field_names=column_field_names,
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
    column_field_names = _column_field_names(plan, rendered)
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
                column_field_names=column_field_names,
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


_IDENTIFIER_REQUEST_TOKENS = frozenset(
    {"codigo", "cod", "id", "identificador", "divipola", "postal", "nit", "sigep"}
)
_IDENTIFIER_QUALIFIER_GROUPS = (
    frozenset({"postal"}),
    frozenset({"nit"}),
    frozenset({"sigep"}),
    frozenset({"radicado"}),
    frozenset({"consecutivo"}),
    frozenset({"municipio", "mpio"}),
    frozenset({"departamento", "dpto"}),
)
_GEOGRAPHIC_IDENTIFIER_TOKENS = frozenset({"municipio", "mpio", "departamento", "dpto"})
_CODE_TOKENS = frozenset({"codigo", "cod", "id", "identificador"})


def _token_family_requested(
    family: frozenset[str],
    *,
    requested_tokens: frozenset[str],
) -> bool:
    return any(
        requested == token or requested in token or token in requested
        for requested in requested_tokens
        for token in family
    )


def _identifier_dimension_is_requested(
    field_name: str,
    *,
    requested_tokens: frozenset[str],
) -> bool:
    """Acota el identificador a su subtipo solicitado, si lo hay."""

    field_tokens = intent_relevance_tokens(field_name, ())
    requested_groups = tuple(
        group
        for group in _IDENTIFIER_QUALIFIER_GROUPS
        if _token_family_requested(group, requested_tokens=requested_tokens)
    )
    divipola_requested = _token_family_requested(
        frozenset({"divipola"}),
        requested_tokens=requested_tokens,
    )
    if requested_groups or divipola_requested:
        if any(field_tokens & group for group in requested_groups):
            return True
        return bool(
            divipola_requested
            and field_tokens & _CODE_TOKENS
            and field_tokens & _GEOGRAPHIC_IDENTIFIER_TOKENS
        )
    return column_is_explicitly_requested(
        field_name,
        requested_tokens=requested_tokens,
    ) or _token_family_requested(
        _IDENTIFIER_REQUEST_TOKENS,
        requested_tokens=requested_tokens,
    )


def _prepare_requested_identifier_facts(
    plan: ValidatedQueryPlan,
    rendered: RenderedQuery,
    *,
    canonical_soql: str,
    rows: tuple[dict, ...],
) -> tuple[tuple[PreparedTextualFact, ...], tuple[TextualRejection, ...]]:
    """Preserva códigos solicitados como texto exacto, nunca como magnitudes."""

    requested_tokens = intent_relevance_tokens(plan.purpose, ())
    evidence = TextualEvidence(
        dataset_id=rendered.dataset_id,
        canonical_soql=canonical_soql,
        rows=rows,
        validated_order_is_total=False,
    )
    prepared: list[PreparedTextualFact] = []
    rejected: list[TextualRejection] = []
    observed_values: set[tuple[str, str]] = set()
    for dimension, alias in zip(
        plan.dimensions,
        rendered.dimension_aliases,
        strict=True,
    ):
        if not is_identifier_field_name(
            dimension.field_name
        ) or not _identifier_dimension_is_requested(
            dimension.field_name,
            requested_tokens=requested_tokens,
        ):
            continue
        for row_index, row in enumerate(rows[:12]):
            raw_value = row.get(alias)
            if raw_value is None:
                continue
            value_key = (alias, str(raw_value))
            if value_key in observed_values:
                continue
            spec = TextualFactSpec(
                operation=TextualFactOperation.DIRECT_TEXT,
                source_row_indexes=(row_index,),
                columns=(alias,),
                operation_params=EmptyTextualFactOperationParams(),
            )
            try:
                evaluate_textual_operation(evidence=evidence, spec=spec)
            except TextualOperationError as exc:
                rejected.append(
                    TextualRejection(
                        operation=TextualFactOperation.DIRECT_TEXT,
                        code=exc.code,
                    )
                )
                continue
            prepared.append(
                PreparedTextualFact(
                    spec=spec,
                    validated_order_is_total=False,
                )
            )
            observed_values.add(value_key)
    return tuple(prepared), tuple(rejected)


def _merge_prepared_textual_facts(
    *groups: tuple[PreparedTextualFact, ...],
) -> tuple[PreparedTextualFact, ...]:
    merged: dict[
        tuple[TextualFactOperation, tuple[int, ...], tuple[str, ...]],
        PreparedTextualFact,
    ] = {}
    for group in groups:
        for item in group:
            key = (
                item.spec.operation,
                item.spec.source_row_indexes,
                item.spec.columns,
            )
            merged.setdefault(key, item)
    return tuple(merged.values())


def _prepare_single_row_textual_fallback(
    plan: ValidatedQueryPlan,
    rendered: RenderedQuery,
    *,
    canonical_soql: str,
    rows: tuple[dict, ...],
    quantitative_aliases: frozenset[str],
) -> tuple[tuple[PreparedTextualFact, ...], tuple[TextualRejection, ...]]:
    """Deriva ``direct_text`` solo para una fila única y campos solicitados.

    RF-211/RF-212 y pruebas.md §§4.5-4.6: una consulta que ya devolvió una
    única fila elegible no debe omitir una dimensión textual explícitamente
    solicitada solo porque el LLM no produjo ``textual_requests``. Esto cubre
    tanto LOOKUP como agregados agrupados top-1: el hecho afirma únicamente
    el valor textual observado en la fila, no que sea un ganador único.

    El fallback no elige entre filas ni columnas por sus valores: exige
    exactamente una fila, usa únicamente dimensiones TEXT seleccionadas cuyo
    nombre real coincide con la intención y excluye los aliases que ya
    produjeron un claim cuantitativo. Solicitudes textuales explícitas se
    procesan por la ruta normal y nunca llegan aquí.
    """

    if plan.textual_requests or len(rows) != 1:
        return (), ()

    # `ejecutar_soql` recibe exclusivamente `rendered.canonical_soql`, pero
    # devuelve la forma canónica persistible del parser (keywords en
    # mayúsculas y `OFFSET 0`). Comparar ambas cadenas literalmente descartaba
    # la misma consulta en producción aunque no cambiara su semántica. La
    # consulta ejecutada continúa siendo la única fuente del hash/evidencia.
    requested_tokens = intent_relevance_tokens(plan.purpose, ())
    prepared: list[PreparedTextualFact] = []
    rejected: list[TextualRejection] = []
    evidence = TextualEvidence(
        dataset_id=rendered.dataset_id,
        canonical_soql=canonical_soql,
        rows=rows,
        validated_order_is_total=False,
    )
    for dimension, alias in zip(
        plan.dimensions,
        rendered.dimension_aliases,
        strict=True,
    ):
        if (
            dimension.data_type is not ColumnDataType.TEXT
            or alias in quantitative_aliases
            or not column_is_explicitly_requested(
                dimension.field_name,
                requested_tokens=requested_tokens,
            )
        ):
            continue
        spec = TextualFactSpec(
            operation=TextualFactOperation.DIRECT_TEXT,
            source_row_indexes=(0,),
            columns=(alias,),
            operation_params=EmptyTextualFactOperationParams(),
        )
        try:
            evaluate_textual_operation(evidence=evidence, spec=spec)
        except TextualOperationError as exc:
            rejected.append(
                TextualRejection(
                    operation=TextualFactOperation.DIRECT_TEXT,
                    code=exc.code,
                )
            )
            continue
        prepared.append(
            PreparedTextualFact(
                spec=spec,
                validated_order_is_total=False,
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
            f"{error.get('code', 'QUERY_FAILED')}: {error.get('message', 'falló T5')}",
            tool_output=output,
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
            "EVIDENCE_NOT_ELIGIBLE: " + ",".join(quality.eligibility_reasons),
            tool_output=output,
        )
    if is_cancelled is not None and is_cancelled():
        raise DeterministicPersistenceCancelled("corrida cancelada antes de construir texto")
    claims = build_claims(
        EvidenceContext(
            dataset_id=rendered.dataset_id,
            canonical_soql=canonical_soql,
            rows=rows,
        ),
        _claim_specs(plan, rendered, rows),
    )
    textual_facts: tuple[PreparedTextualFact, ...] = ()
    textual_rejections: tuple[TextualRejection, ...] = ()
    if textual_facts_enabled:
        identifier_facts, identifier_rejections = _prepare_requested_identifier_facts(
            plan,
            rendered,
            canonical_soql=canonical_soql,
            rows=rows,
        )
        if plan.textual_requests:
            textual_facts, textual_rejections = _prepare_textual_facts(
                plan,
                rendered,
                canonical_soql=canonical_soql,
                rows=rows,
            )
        else:
            quantitative_aliases = frozenset(
                alias for claim in claims.claims for alias in claim.columns_used
            )
            textual_facts, textual_rejections = _prepare_single_row_textual_fallback(
                plan,
                rendered,
                canonical_soql=canonical_soql,
                rows=rows,
                quantitative_aliases=quantitative_aliases,
            )
        textual_facts = _merge_prepared_textual_facts(textual_facts, identifier_facts)
        textual_rejections = (*textual_rejections, *identifier_rejections)
    has_identifier_dimension = any(
        is_identifier_field_name(dimension.field_name) for dimension in plan.dimensions
    )
    if (
        not claims.claims
        and plan.operation is QueryOperation.LOOKUP
        and not textual_facts_enabled
        and not has_identifier_dimension
    ):
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
        raise DeterministicExecutionError(f"CLAIMS_REJECTED: {reasons}", tool_output=output)
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
