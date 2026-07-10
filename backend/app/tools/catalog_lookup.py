"""Lecturas de catalogo compartidas por T2/T5 (`catalog_datasets`/`catalog_columns`).

Los campos de elegibilidad/PII ya estan precomputados en estas tablas por la
ingesta (T-201) y por `app/quality/eligibility.py`; estas herramientas solo
los leen, nunca los recalculan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.tools.soql_parser import ColumnInfo, DatasetCatalogInfo


@dataclass(frozen=True)
class ColumnCatalogRow:
    field_name: str
    data_type: str
    pii_risk_level: str
    eligibility_status: str


async def fetch_dataset_catalog_info(
    engine: AsyncEngine, dataset_id: str
) -> DatasetCatalogInfo | None:
    """`None` si el dataset no existe en `catalog_datasets` (mapea a DATASET_INACTIVE)."""

    async with engine.connect() as connection:
        dataset_row = (
            await connection.execute(
                text(
                    "SELECT api_active, eligibility_status FROM catalog_datasets WHERE id = :id"
                ),
                {"id": dataset_id},
            )
        ).first()
        if dataset_row is None:
            return None
        column_rows = (
            await connection.execute(
                text(
                    "SELECT field_name, data_type, pii_risk_level, eligibility_status "
                    "FROM catalog_columns WHERE dataset_id = :id"
                ),
                {"id": dataset_id},
            )
        ).all()

    return DatasetCatalogInfo(
        dataset_id=dataset_id,
        api_active=bool(dataset_row.api_active),
        eligibility_status=dataset_row.eligibility_status,
        columns=tuple(
            ColumnInfo(
                field_name=row.field_name,
                pii_risk_level=row.pii_risk_level,
                eligibility_status=row.eligibility_status,
            )
            for row in column_rows
        ),
    )


async def fetch_columns_catalog(
    engine: AsyncEngine, dataset_id: str
) -> list[ColumnCatalogRow]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT field_name, data_type, pii_risk_level, eligibility_status "
                    "FROM catalog_columns WHERE dataset_id = :id"
                ),
                {"id": dataset_id},
            )
        ).all()
    return [
        ColumnCatalogRow(
            field_name=row.field_name,
            data_type=row.data_type,
            pii_risk_level=row.pii_risk_level,
            eligibility_status=row.eligibility_status,
        )
        for row in rows
    ]


@dataclass(frozen=True)
class ColumnProfileUpdate:
    field_name: str
    null_ratio: float
    sample_values: list[object] | None


async def update_profile_cache(
    engine: AsyncEngine,
    dataset_id: str,
    column_updates: list[ColumnProfileUpdate],
    cutoff_at_iso: str | None,
) -> None:
    """Cachea `null_ratio`/`sample_values` (T2, agent-tools.md §T2).

    `sample_values` solo se sobreescribe cuando `update.sample_values` no es
    `None` (columnas `pii_risk_level=low`); para las demas se deja intacto lo
    que ya hubiera en `catalog_columns` (nunca se persisten valores de
    columnas medium/high/unknown, ver `perfilar_dataset.py`).
    """
    async with engine.begin() as connection:
        for update in column_updates:
            if update.sample_values is not None:
                await connection.execute(
                    text(
                        "UPDATE catalog_columns SET null_ratio = :null_ratio, "
                        "sample_values = CAST(:sample_values AS jsonb) "
                        "WHERE dataset_id = :dataset_id AND field_name = :field_name"
                    ),
                    {
                        "dataset_id": dataset_id,
                        "field_name": update.field_name,
                        "null_ratio": update.null_ratio,
                        "sample_values": json.dumps(update.sample_values),
                    },
                )
            else:
                await connection.execute(
                    text(
                        "UPDATE catalog_columns SET null_ratio = :null_ratio "
                        "WHERE dataset_id = :dataset_id AND field_name = :field_name"
                    ),
                    {
                        "dataset_id": dataset_id,
                        "field_name": update.field_name,
                        "null_ratio": update.null_ratio,
                    },
                )
        if cutoff_at_iso is not None:
            await connection.execute(
                text(
                    "UPDATE catalog_datasets SET latest_observed_cutoff_at = "
                    "CAST(:cutoff_at AS timestamptz) WHERE id = :dataset_id"
                ),
                {"cutoff_at": cutoff_at_iso, "dataset_id": dataset_id},
            )
