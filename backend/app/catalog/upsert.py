"""Upsert idempotente del catalogo (T-201, RF-304, data-model.md).

Dos reglas criticas derivadas del esquema ya migrado (no son decisiones
abiertas, son consecuencias obligatorias de los campos que ya existen):

1. Si un humano ya reviso manualmente el PII de un dataset
   (`pii_reviewed_at IS NOT NULL`), un re-run NO debe sobrescribir
   `pii_risk_level`/`eligibility_status`/`eligibility_reasons` con el valor
   recien calculado -- de lo contrario el mecanismo de revision manual
   quedaria anulado en cada corrida (T-206).
2. `api_active` solo se reconcilia (apagar los no vistos) en corridas
   COMPLETAS (`reset_api_active_flags`, llamada por el orquestador solo si
   no hay `--limit`); con `--limit` un dataset no visto simplemente
   conserva su estado anterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CatalogColumn, CatalogDataset


@dataclass
class ColumnUpsertData:
    field_name: str
    display_name: str | None
    data_type: str
    description: str | None
    pii_risk_level: str
    eligibility_status: str
    eligibility_reasons: list[str]


@dataclass
class DatasetUpsertData:
    id: str
    name: str
    description: str | None
    publisher_text: str | None
    official_publisher_id: str | None
    publisher_verification_status: str
    category: str | None
    data_updated_at: datetime | None
    metadata_synced_at: datetime
    embedding_text: str
    pii_risk_level: str
    eligibility_status: str
    eligibility_reasons: list[str]
    columns: list[ColumnUpsertData] = field(default_factory=list)


async def reset_api_active_flags(session: AsyncSession) -> None:
    """Apaga `api_active` de todo el catalogo antes de una corrida completa;
    cada dataset visto durante la corrida se reactiva explicitamente en
    `upsert_dataset` (data-model.md: "si desaparece del portal, api_active=false")."""

    await session.execute(update(CatalogDataset).values(api_active=False))


async def upsert_dataset(session: AsyncSession, data: DatasetUpsertData) -> str:
    """Upsert idempotente de un dataset + sus columnas. Devuelve "created" o
    "updated"."""

    existing = (
        await session.execute(
            select(
                CatalogDataset.pii_reviewed_at,
                CatalogDataset.pii_risk_level,
                CatalogDataset.eligibility_status,
                CatalogDataset.eligibility_reasons,
            ).where(CatalogDataset.id == data.id)
        )
    ).one_or_none()

    outcome = "updated" if existing is not None else "created"

    if existing is not None and existing.pii_reviewed_at is not None:
        pii_risk_level = existing.pii_risk_level
        eligibility_status = existing.eligibility_status
        eligibility_reasons = existing.eligibility_reasons
    else:
        pii_risk_level = data.pii_risk_level
        eligibility_status = data.eligibility_status
        eligibility_reasons = data.eligibility_reasons

    stmt = pg_insert(CatalogDataset).values(
        id=data.id,
        name=data.name,
        description=data.description,
        publisher=data.publisher_text,
        official_publisher_id=data.official_publisher_id,
        publisher_verification_status=data.publisher_verification_status,
        category=data.category,
        data_updated_at=data.data_updated_at,
        metadata_synced_at=data.metadata_synced_at,
        api_active=True,
        pii_risk_level=pii_risk_level,
        eligibility_status=eligibility_status,
        eligibility_reasons=eligibility_reasons,
        embedding_text=data.embedding_text,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[CatalogDataset.id],
        set_={
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
            "publisher": stmt.excluded.publisher,
            "official_publisher_id": stmt.excluded.official_publisher_id,
            "publisher_verification_status": stmt.excluded.publisher_verification_status,
            "category": stmt.excluded.category,
            "data_updated_at": stmt.excluded.data_updated_at,
            "metadata_synced_at": stmt.excluded.metadata_synced_at,
            "api_active": stmt.excluded.api_active,
            "pii_risk_level": stmt.excluded.pii_risk_level,
            "eligibility_status": stmt.excluded.eligibility_status,
            "eligibility_reasons": stmt.excluded.eligibility_reasons,
            "embedding_text": stmt.excluded.embedding_text,
        },
    )
    await session.execute(stmt)

    await session.execute(delete(CatalogColumn).where(CatalogColumn.dataset_id == data.id))
    for column in data.columns:
        session.add(
            CatalogColumn(
                dataset_id=data.id,
                field_name=column.field_name,
                display_name=column.display_name,
                data_type=column.data_type,
                description=column.description,
                pii_risk_level=column.pii_risk_level,
                eligibility_status=column.eligibility_status,
                eligibility_reasons=column.eligibility_reasons,
            )
        )

    return outcome
