"""Persistencia transaccional del grafo real T-303 (RF-703, RF-209)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

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
from app.quality.claims import BuiltClaim
from app.quality.validator import EvidenceDraft, QualityResult

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
        "preview": encoded[: TOOL_OUTPUT_SUMMARY_MAX_BYTES - 100].decode(
            "utf-8", errors="ignore"
        ),
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
        "data_updated_at": (
            draft.data_updated_at.isoformat() if draft.data_updated_at else None
        ),
        "data_cutoff_at": (
            cutoff.data_cutoff_at.isoformat() if cutoff.data_cutoff_at else None
        ),
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
                    "columns": list(claim.columns_used),
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
                }
            )
    return records


async def update_evidence_narratives(
    engine: AsyncEngine, narratives: dict[str, str]
) -> None:
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
