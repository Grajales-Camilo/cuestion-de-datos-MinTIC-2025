"""Persistencia transaccional del grafo real T-303 (RF-703, RF-209)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.durability import reserve_and_add_event
from app.db.models import (
    AgentRun,
    AgentStep,
    CatalogColumn,
    CatalogDataset,
    EvidenceResult,
    QualityReport,
    QuantitativeClaim,
)
from app.db.models import TextualFact as TextualFactRecord
from app.quality.claims import BuiltClaim, compute_source_hash, format_es_co
from app.quality.grounded_facts import (
    CategorySelectionParams,
    CategorySelectionRule,
    QuantitativeClaimResponse,
    TextualFact,
)
from app.quality.grounded_synthesis import (
    AllowedGroundedFacts,
    AllowedQuantitativeFact,
    AllowedTextualFact,
)
from app.quality.textual_fact_builder import (
    TextualEvidenceSnapshot,
    TextualFactBuildCommand,
    TextualFactError,
    build_textual_fact,
    verify_textual_fact,
)
from app.quality.textual_facts import TextualFactSpec
from app.quality.validator import EvidenceDraft, QualityResult
from app.tools.soql_parser import SoqlGuardError, parse_soql

TOOL_OUTPUT_SUMMARY_MAX_BYTES = 20 * 1024


@dataclass(frozen=True)
class DatasetEvidenceMetadata:
    dataset_id: str
    name: str
    publisher: str | None
    official_publisher_id: str | None
    pii_risk_level: str
    eligibility_status: str
    eligibility_reasons: tuple[str, ...]
    data_updated_at: datetime | None
    column_pii: dict[str, str]
    column_types: dict[str, str]


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, Decimal, uuid.UUID)):
        return str(value) if not isinstance(value, datetime) else value.isoformat()
    raise TypeError(f"No serializable: {type(value).__name__}")


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default, ensure_ascii=False))


def summarize_output(value: Any) -> Any:
    """Limita el resumen persistido sin truncar las filas de Evidencia."""

    safe = json_safe(value)
    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= TOOL_OUTPUT_SUMMARY_MAX_BYTES:
        return safe
    if isinstance(safe, dict) and isinstance(safe.get("rows"), list):
        compact = {**safe, "rows": safe["rows"][:50], "output_truncated": True}
        encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) <= TOOL_OUTPUT_SUMMARY_MAX_BYTES:
            return compact
    return {
        "output_truncated": True,
        "preview": encoded[: TOOL_OUTPUT_SUMMARY_MAX_BYTES - 100].decode("utf-8", errors="ignore"),
    }


async def load_dataset_evidence_metadata(
    engine: AsyncEngine, dataset_id: str
) -> DatasetEvidenceMetadata | None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        dataset = await session.get(CatalogDataset, dataset_id)
        if dataset is None:
            return None
        columns = (
            await session.execute(
                select(CatalogColumn).where(CatalogColumn.dataset_id == dataset_id)
            )
        ).scalars()
        return DatasetEvidenceMetadata(
            dataset_id=dataset.id,
            name=dataset.name,
            publisher=dataset.publisher,
            official_publisher_id=dataset.official_publisher_id,
            pii_risk_level=dataset.pii_risk_level,
            eligibility_status=dataset.eligibility_status,
            eligibility_reasons=tuple(dataset.eligibility_reasons or []),
            data_updated_at=dataset.data_updated_at,
            column_pii={column.field_name: column.pii_risk_level for column in columns},
            column_types={column.field_name: column.data_type for column in columns},
        )


async def record_step_and_event(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    *,
    step_number: int,
    node: str,
    display_message: str,
    detail: Any,
    tool_input: Any = None,
    tool_output: Any = None,
    latency_ms: int | None = None,
    error: str | None = None,
    run_values: dict[str, Any] | None = None,
) -> None:
    """Confirma `agent_steps` y su evento SSE en la misma transacción."""

    payload = {
        "step_number": step_number,
        "node": node,
        "display_message": display_message,
        "detail": json_safe(detail),
    }
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            AgentStep(
                run_id=run_id,
                step_number=step_number,
                node=node,
                tool_input=json_safe(tool_input),
                tool_output_summary=summarize_output(tool_output),
                display_message=display_message,
                latency_ms=latency_ms,
                error=error,
            )
        )
        values = {"steps_used": step_number, **(run_values or {})}
        await session.execute(update(AgentRun).where(AgentRun.id == run_id).values(**values))
        await reserve_and_add_event(session, run_id, "step", payload)


async def persist_evidence_and_quality(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    draft: EvidenceDraft,
    quality: QualityResult,
    *,
    official_publisher_id: str | None,
) -> dict[str, Any]:
    evidence_id = uuid.uuid4()
    cutoff = quality.data_cutoff
    citation = {
        "dataset_id": draft.dataset_id,
        "dataset_name": draft.dataset_name,
        "publisher": draft.publisher,
        "official_publisher_id": official_publisher_id,
        "soql_query": draft.canonical_soql,
        "executed_at": draft.evaluated_at.isoformat(),
        "source_url": draft.source_url,
        "data_updated_at": (draft.data_updated_at.isoformat() if draft.data_updated_at else None),
        "data_cutoff_at": (cutoff.data_cutoff_at.isoformat() if cutoff.data_cutoff_at else None),
    }
    dimensions = {name: asdict(value) for name, value in quality.dimensions.items()}
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            EvidenceResult(
                id=evidence_id,
                run_id=run_id,
                dataset_id=draft.dataset_id,
                soql_query=draft.canonical_soql,
                executed_at=draft.evaluated_at,
                source_url=draft.source_url or "",
                rows=list(draft.rows),
                row_count=draft.row_count,
                data_updated_at=draft.data_updated_at,
                data_cutoff_at=cutoff.data_cutoff_at,
                data_cutoff_method=cutoff.method,
                data_cutoff_column=cutoff.column,
                data_cutoff_confidence=cutoff.confidence,
                data_cutoff_basis=cutoff.basis,
                data_cutoff_inferred_at=cutoff.inferred_at,
                narrative=None,
                citation=citation,
            )
        )
        session.add(
            QualityReport(
                evidence_id=evidence_id,
                score_total=quality.score_total,
                classification=quality.classification,
                eligibility_status=quality.eligibility_status,
                eligibility_reasons=list(quality.eligibility_reasons),
                dim_schema=dimensions["schema"],
                dim_completeness=dimensions["completeness"],
                dim_timeliness=dimensions["timeliness"],
                dim_traceability=dimensions["traceability"],
                warnings_user=list(quality.warnings_user),
                validator_version=quality.validator_version,
            )
        )
    return {
        "evidence_id": str(evidence_id),
        "dataset_id": draft.dataset_id,
        "dataset_name": draft.dataset_name,
        "publisher": draft.publisher,
        "soql_query": draft.canonical_soql,
        "executed_at": draft.evaluated_at.isoformat(),
        "source_url": draft.source_url,
        "data_updated_at": citation["data_updated_at"],
        "data_cutoff_at": citation["data_cutoff_at"],
        "data_cutoff_method": cutoff.method,
        "data_cutoff_column": cutoff.column,
        "data_cutoff_confidence": cutoff.confidence,
        "data_cutoff_basis": cutoff.basis,
        "data_cutoff_inferred_at": cutoff.inferred_at.isoformat(),
        "columns": [column.field_name for column in draft.selected_columns],
        "rows": list(draft.rows),
        "row_count": draft.row_count,
        "narrative": None,
        "chart_suggestion": None,
        "quality": {
            "eligibility_status": quality.eligibility_status,
            "eligibility_reasons": list(quality.eligibility_reasons),
            "score_total": quality.score_total,
            "classification": quality.classification,
            "warnings_user": list(quality.warnings_user),
            "dimensions": json_safe(dimensions),
        },
        "citation": citation,
    }


async def persist_claims(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    evidence_id: uuid.UUID,
    dataset_id: str,
    claims: tuple[BuiltClaim, ...],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        for claim in claims:
            claim_id = uuid.uuid4()
            claim_text = f"{claim.description.rstrip(' .:')}: {claim.display_value}"
            session.add(
                QuantitativeClaim(
                    id=claim_id,
                    run_id=run_id,
                    evidence_id=evidence_id,
                    claim_text=claim_text,
                    claim_type=claim.claim_type,
                    source_row_indexes=list(claim.source_row_indexes),
                    columns_used=list(claim.columns_used),
                    formula=claim.formula,
                    raw_value=claim.raw_value,
                    display_value=claim.display_value,
                    unit=claim.unit,
                    rounding=claim.rounding,
                    source_hash=claim.source_hash,
                )
            )
            records.append(
                {
                    "claim_id": str(claim_id),
                    "claim": claim_text,
                    "claim_type": claim.claim_type,
                    "evidence_id": str(evidence_id),
                    "dataset_id": dataset_id,
                    "source_row_indexes": list(claim.source_row_indexes),
                    # RF-212 (T-617C-A §4c): nombre de columna fuente real,
                    # nunca el alias de ejecución `dim_N`/`metric_N` -- ese
                    # alias sigue viviendo en `columns_used`/DB para
                    # reproducir `source_hash`, pero nunca se expone aquí.
                    "columns": list(claim.public_columns),
                    "formula": claim.formula,
                    "raw_value": (
                        int(claim.raw_value)
                        if claim.raw_value == claim.raw_value.to_integral_value()
                        else float(claim.raw_value)
                    ),
                    "display_value": claim.display_value,
                    "unit": claim.unit,
                    "rounding": claim.rounding,
                    "source_hash": claim.source_hash,
                    "label": claim.label,
                    "label_status": claim.label_status,
                }
            )
    return records


async def persist_textual_facts(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    facts: tuple[TextualFact, ...],
) -> None:
    """Persiste hechos ya construidos sin integrarlos todavía al runtime (T-615C)."""

    if not facts:
        return
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await _persist_textual_facts_in_session(session, run_id, facts)


async def load_textual_facts(
    engine: AsyncEngine,
    run_id: uuid.UUID,
) -> tuple[TextualFact, ...]:
    """Reconstruye el contrato tipado desde la tabla aislada de T-615C."""

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        return await _load_textual_facts_in_session(session, run_id)


async def load_allowed_grounded_facts(
    engine: AsyncEngine,
    run_id: uuid.UUID,
) -> AllowedGroundedFacts:
    """Carga y reverifica únicamente hechos persistidos y elegibles de una corrida.

    Esta frontera no reconstruye propuestas preparadas ni consulta fuentes
    externas. Los registros alterados o incompatibles quedan fuera del
    conjunto autorizado; si no queda ninguno, el llamador debe abstenerse.
    """

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        quantitative_rows = (
            await session.execute(
                select(QuantitativeClaim, EvidenceResult, QualityReport)
                .join(EvidenceResult, EvidenceResult.id == QuantitativeClaim.evidence_id)
                .join(QualityReport, QualityReport.evidence_id == EvidenceResult.id)
                .where(
                    QuantitativeClaim.run_id == run_id,
                    EvidenceResult.run_id == run_id,
                    QualityReport.eligibility_status == "eligible",
                    QualityReport.classification.in_(("alta", "media", "baja")),
                )
                .order_by(QuantitativeClaim.id)
            )
        ).all()
        textual_rows = (
            await session.execute(
                select(TextualFactRecord, EvidenceResult, QualityReport)
                .join(EvidenceResult, EvidenceResult.id == TextualFactRecord.evidence_id)
                .join(QualityReport, QualityReport.evidence_id == EvidenceResult.id)
                .where(
                    TextualFactRecord.run_id == run_id,
                    EvidenceResult.run_id == run_id,
                    QualityReport.eligibility_status == "eligible",
                    QualityReport.classification.in_(("alta", "media", "baja")),
                )
                .order_by(TextualFactRecord.id)
            )
        ).all()

    facts: list[AllowedQuantitativeFact | AllowedTextualFact] = []
    for claim, evidence, quality in quantitative_rows:
        verified = _reverify_quantitative_synthesis_fact(
            run_id=run_id,
            claim=claim,
            evidence=evidence,
            quality=quality,
        )
        if verified is not None:
            facts.append(verified)
    for row, evidence, quality in textual_rows:
        verified = _reverify_textual_synthesis_fact(
            run_id=run_id,
            row=row,
            evidence=evidence,
            quality=quality,
        )
        if verified is not None:
            facts.append(verified)
    return AllowedGroundedFacts(run_id=run_id, facts=tuple(facts))


def _reverify_quantitative_synthesis_fact(
    *,
    run_id: uuid.UUID,
    claim: QuantitativeClaim,
    evidence: EvidenceResult,
    quality: QualityReport,
) -> AllowedQuantitativeFact | None:
    try:
        rounding = int(claim.rounding)
        public = QuantitativeClaimResponse.model_validate(
            {
                "claim_id": claim.id,
                "claim": claim.claim_text,
                "claim_type": claim.claim_type,
                "evidence_id": claim.evidence_id,
                "dataset_id": evidence.dataset_id,
                "source_row_indexes": claim.source_row_indexes,
                "columns": claim.columns_used,
                "formula": claim.formula,
                "raw_value": claim.raw_value,
                "display_value": claim.display_value,
                "unit": claim.unit,
                "rounding": rounding,
                "source_hash": claim.source_hash,
            }
        )
        expected_display = format_es_co(claim.raw_value, rounding, claim.unit)
        expected_hash = compute_source_hash(
            dataset_id=evidence.dataset_id,
            canonical_soql=evidence.soql_query,
            source_row_indexes=tuple(public.source_row_indexes),
            rows=tuple(evidence.rows),
            columns=tuple(public.columns),
            formula=public.formula,
            raw_value=claim.raw_value,
            unit=public.unit,
            rounding=rounding,
        )
        suffix = f": {public.display_value}"
        if (
            evidence.run_id != run_id
            or public.display_value != expected_display
            or public.source_hash != expected_hash
            or not public.claim.endswith(suffix)
        ):
            return None
        claim_label = public.claim[: -len(suffix)]
        if not claim_label:
            return None
        return AllowedQuantitativeFact(
            id=public.claim_id,
            run_id=run_id,
            evidence_id=public.evidence_id,
            dataset_id=public.dataset_id,
            source_row_indexes=public.source_row_indexes,
            columns=public.columns,
            source_hash=public.source_hash,
            claim=claim_label,
            display_value=public.display_value,
            quality_classification=quality.classification,
        )
    except (IndexError, TypeError, ValueError, ValidationError):
        return None


def _reverify_textual_synthesis_fact(
    *,
    run_id: uuid.UUID,
    row: TextualFactRecord,
    evidence: EvidenceResult,
    quality: QualityReport,
) -> AllowedTextualFact | None:
    try:
        fact = TextualFact.model_validate(
            {
                "fact_id": row.id,
                "fact_kind": "textual",
                "fact": row.fact_text,
                "operation": row.operation,
                "evidence_id": row.evidence_id,
                "dataset_id": evidence.dataset_id,
                "source_row_indexes": row.source_row_indexes,
                "columns": row.columns_used,
                "raw_values": row.raw_values,
                "normalized_values": row.normalized_values,
                "display_value": row.display_value,
                "normalization_profile": row.normalization_profile,
                "operation_params": row.operation_params,
                "algorithm_version": row.algorithm_version,
                "source_hash": row.source_hash,
            }
        )
        validated_order_is_total = (
            isinstance(fact.operation_params, CategorySelectionParams)
            and fact.operation_params.rule is CategorySelectionRule.FIRST_BY_VALIDATED_ORDER
            and _persisted_order_is_total(
                canonical_soql=evidence.soql_query,
                rows=tuple(evidence.rows),
                source_row_indexes=fact.source_row_indexes,
            )
        )
        snapshot = TextualEvidenceSnapshot(
            run_id=evidence.run_id,
            evidence_id=evidence.id,
            dataset_id=evidence.dataset_id,
            canonical_soql=evidence.soql_query,
            rows=tuple(evidence.rows),
            eligibility_status=quality.eligibility_status,
            quality_classification=quality.classification,
            validated_order_is_total=validated_order_is_total,
        )
        spec = TextualFactSpec(
            operation=fact.operation,
            source_row_indexes=fact.source_row_indexes,
            columns=fact.columns,
            operation_params=fact.operation_params,
        )
        verify_textual_fact(
            run_id=run_id,
            evidence_id=evidence.id,
            dataset_id=evidence.dataset_id,
            snapshot=snapshot,
            spec=spec,
            fact=fact,
        )
        return AllowedTextualFact(
            id=fact.fact_id,
            run_id=run_id,
            evidence_id=fact.evidence_id,
            dataset_id=fact.dataset_id,
            source_row_indexes=fact.source_row_indexes,
            columns=fact.columns,
            source_hash=fact.source_hash,
            fact=fact.fact,
            quality_classification=quality.classification,
        )
    except (TextualFactError, TypeError, ValueError, ValidationError):
        return None


def _persisted_order_is_total(
    *,
    canonical_soql: str,
    rows: tuple[dict, ...],
    source_row_indexes: tuple[int, ...],
) -> bool:
    """Reconstruye el certificado de orden desde la evidencia persistida.

    El certificado no puede deducirse de la operación solicitada: exige la
    forma canónica producida por el renderer determinista y una primera clave
    inequívoca dentro de la ventana observada.
    """

    if source_row_indexes != (0,) or not rows:
        return False
    try:
        parsed = parse_soql(canonical_soql)
    except (SoqlGuardError, ValueError):
        return False
    if not parsed.limit_was_explicit or parsed.limit < 2:
        return False

    selected_aliases: list[str] = []
    for item in parsed.select_items:
        alias = item.alias
        if alias == "group_count":
            continue
        if alias is None or not alias.startswith(("dim_", "metric_")):
            return False
        selected_aliases.append(alias)
    if not selected_aliases or len(selected_aliases) != len(set(selected_aliases)):
        return False

    ordered_aliases = tuple(item.ref for item in parsed.order_by)
    if len(ordered_aliases) != len(set(ordered_aliases)) or set(ordered_aliases) != set(
        selected_aliases
    ):
        return False
    if any(alias not in rows[0] for alias in ordered_aliases):
        return False
    if len(rows) == 1:
        return len(rows) < parsed.limit
    if any(alias not in rows[1] for alias in ordered_aliases):
        return False
    first_key = tuple(rows[0][alias] for alias in ordered_aliases)
    second_key = tuple(rows[1][alias] for alias in ordered_aliases)
    return first_key != second_key


async def build_verify_persist_textual_facts(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    commands: tuple[TextualFactBuildCommand, ...],
    *,
    fact_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
) -> tuple[TextualFact, ...]:
    """Construye, verifica, persiste, recarga y reverifica en una transacción.

    Es una conexión aislada para T-615E. Ningún runtime la invoca. Las
    decisiones de elegibilidad y clasificación se leen de ``quality_reports``;
    las filas y el SoQL se copian una vez a snapshots defensivos. Cualquier
    rechazo o fallo antes del commit revierte todos los hechos del lote.
    """

    if not commands:
        return ()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session, session.begin():
            snapshots = await _load_textual_evidence_snapshots(
                session,
                {command.evidence_id for command in commands},
            )
            built: list[TextualFact] = []
            command_snapshots: list[TextualEvidenceSnapshot] = []
            for command in commands:
                snapshot = snapshots.get(command.evidence_id)
                if snapshot is not None and command.validated_order_is_total:
                    snapshot = TextualEvidenceSnapshot(
                        run_id=snapshot.run_id,
                        evidence_id=snapshot.evidence_id,
                        dataset_id=snapshot.dataset_id,
                        canonical_soql=snapshot.canonical_soql,
                        rows=snapshot.rows,
                        eligibility_status=snapshot.eligibility_status,
                        quality_classification=snapshot.quality_classification,
                        validated_order_is_total=True,
                    )
                fact = build_textual_fact(
                    run_id=run_id,
                    evidence_id=command.evidence_id,
                    dataset_id=command.dataset_id,
                    snapshot=snapshot,
                    spec=command.spec,
                    fact_id_factory=fact_id_factory,
                )
                verify_textual_fact(
                    run_id=run_id,
                    evidence_id=command.evidence_id,
                    dataset_id=command.dataset_id,
                    snapshot=snapshot,
                    spec=command.spec,
                    fact=fact,
                )
                built.append(fact)
                assert snapshot is not None
                command_snapshots.append(snapshot)

            facts = tuple(built)
            await _persist_textual_facts_in_session(session, run_id, facts)
            await session.flush()
            loaded = await _load_textual_facts_in_session(
                session,
                run_id,
                fact_ids={fact.fact_id for fact in facts},
            )
            loaded_by_id = {fact.fact_id: fact for fact in loaded}
            if loaded_by_id.keys() != {fact.fact_id for fact in facts}:
                raise TextualFactError(
                    "textual_persistence_failed",
                    "la recarga transaccional no devolvió todos los hechos persistidos",
                )
            ordered_loaded = tuple(loaded_by_id[fact.fact_id] for fact in facts)
            for command, snapshot, fact in zip(
                commands,
                command_snapshots,
                ordered_loaded,
                strict=True,
            ):
                verify_textual_fact(
                    run_id=run_id,
                    evidence_id=command.evidence_id,
                    dataset_id=command.dataset_id,
                    snapshot=snapshot,
                    spec=command.spec,
                    fact=fact,
                )
            return ordered_loaded
    except TextualFactError:
        raise
    except (SQLAlchemyError, ValidationError, ValueError) as exc:
        raise TextualFactError(
            "textual_persistence_failed",
            "falló la transacción de hechos textuales",
        ) from exc


async def _persist_textual_facts_in_session(
    session: AsyncSession,
    run_id: uuid.UUID,
    facts: tuple[TextualFact, ...],
) -> None:
    evidence_ids = {fact.evidence_id for fact in facts}
    evidence_rows = (
        await session.execute(
            select(
                EvidenceResult.id,
                EvidenceResult.run_id,
                EvidenceResult.dataset_id,
            ).where(EvidenceResult.id.in_(evidence_ids))
        )
    ).all()
    evidence_by_id = {
        evidence_id: (evidence_run_id, dataset_id)
        for evidence_id, evidence_run_id, dataset_id in evidence_rows
    }
    missing = evidence_ids - evidence_by_id.keys()
    if missing:
        raise ValueError(f"evidence_id inexistente para hechos textuales: {sorted(missing)}")

    for fact in facts:
        evidence_run_id, dataset_id = evidence_by_id[fact.evidence_id]
        if evidence_run_id != run_id:
            raise ValueError("el hecho textual y su evidencia deben pertenecer a la misma corrida")
        if dataset_id != fact.dataset_id:
            raise ValueError("dataset_id del hecho textual no coincide con la evidencia persistida")
        session.add(
            TextualFactRecord(
                id=fact.fact_id,
                run_id=run_id,
                evidence_id=fact.evidence_id,
                fact_text=fact.fact,
                operation=fact.operation.value,
                source_row_indexes=list(fact.source_row_indexes),
                columns_used=list(fact.columns),
                raw_values=list(fact.raw_values),
                normalized_values=list(fact.normalized_values),
                display_value=fact.display_value,
                normalization_profile=fact.normalization_profile.value,
                operation_params=fact.operation_params.model_dump(mode="json"),
                algorithm_version=fact.algorithm_version.value,
                source_hash=fact.source_hash,
            )
        )


async def _load_textual_evidence_snapshots(
    session: AsyncSession,
    evidence_ids: set[uuid.UUID],
) -> dict[uuid.UUID, TextualEvidenceSnapshot]:
    rows = (
        await session.execute(
            select(EvidenceResult, QualityReport)
            .outerjoin(
                QualityReport,
                QualityReport.evidence_id == EvidenceResult.id,
            )
            .where(EvidenceResult.id.in_(evidence_ids))
        )
    ).all()
    snapshots: dict[uuid.UUID, TextualEvidenceSnapshot] = {}
    for evidence, quality in rows:
        if quality is None:
            raise TextualFactError(
                "textual_evidence_quality_missing",
                "la evidencia no tiene un reporte de calidad verificable",
            )
        snapshots[evidence.id] = TextualEvidenceSnapshot(
            run_id=evidence.run_id,
            evidence_id=evidence.id,
            dataset_id=evidence.dataset_id,
            canonical_soql=evidence.soql_query,
            rows=tuple(evidence.rows),
            eligibility_status=quality.eligibility_status,
            quality_classification=quality.classification,
        )
    return snapshots


async def _load_textual_facts_in_session(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    fact_ids: set[uuid.UUID] | None = None,
) -> tuple[TextualFact, ...]:
    statement = (
        select(TextualFactRecord, EvidenceResult.dataset_id)
        .join(
            EvidenceResult,
            EvidenceResult.id == TextualFactRecord.evidence_id,
        )
        .where(TextualFactRecord.run_id == run_id)
    )
    if fact_ids is not None:
        statement = statement.where(TextualFactRecord.id.in_(fact_ids))
    rows = (await session.execute(statement.order_by(TextualFactRecord.id))).all()
    return tuple(
        TextualFact.model_validate(
            {
                "fact_id": row.id,
                "fact_kind": "textual",
                "fact": row.fact_text,
                "operation": row.operation,
                "evidence_id": row.evidence_id,
                "dataset_id": dataset_id,
                "source_row_indexes": row.source_row_indexes,
                "columns": row.columns_used,
                "raw_values": row.raw_values,
                "normalized_values": row.normalized_values,
                "display_value": row.display_value,
                "normalization_profile": row.normalization_profile,
                "operation_params": row.operation_params,
                "algorithm_version": row.algorithm_version,
                "source_hash": row.source_hash,
            }
        )
        for row, dataset_id in rows
    )


async def update_evidence_narratives(engine: AsyncEngine, narratives: dict[str, str]) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        for evidence_id, narrative in narratives.items():
            await session.execute(
                update(EvidenceResult)
                .where(EvidenceResult.id == uuid.UUID(evidence_id))
                .values(narrative=narrative)
            )


async def persist_final_answer(
    engine: AsyncEngine,
    run_id: uuid.UUID,
    final_answer: dict[str, Any],
    *,
    latency_ms: int,
    llm_provider: str,
    llm_model: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        await session.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                final_answer=json_safe(final_answer),
                latency_ms=latency_ms,
                llm_provider=llm_provider,
                llm_model=llm_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost_usd,
            )
        )
