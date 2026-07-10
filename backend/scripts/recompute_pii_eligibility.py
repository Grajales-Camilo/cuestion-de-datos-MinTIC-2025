"""Recalcula pii_risk_level/eligibility_status sobre el catalogo YA ingerido
(hallazgo T-303, 2026-07-10, calibracion de app/quality/pii_patterns.yaml).

No vuelve a llamar a la Discovery API: field_name/display_name/description
de cada columna, y name/description/category/publisher_verification_status/
api_active de cada dataset, ya viven en Postgres desde la ingesta original.
Solo reaplica classify_column/classify_dataset/compute_dataset_eligibility/
compute_column_eligibility (mismas funciones que usa app/catalog/ingest.py)
con el fixture corregido. Idempotente: correrlo dos veces produce el mismo
resultado. NUNCA toca pii_reviewed_by/pii_reviewed_at/pii_review_source
(revision manual, mecanismo aparte de data-model.md).

Uso (desde backend/):
    python scripts/recompute_pii_eligibility.py [--dataset-id ID ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import get_settings
from app.db.engine import create_app_async_engine
from app.quality.eligibility import compute_column_eligibility, compute_dataset_eligibility
from app.quality.pii_classifier import (
    ColumnPiiClassification,
    classify_column,
    classify_dataset,
    load_pii_patterns,
)

_INHERITED_COLUMN_REASONS = {"api_inactive", "publisher_unknown", "publisher_private"}

_SELECT_DATASETS = text(
    "SELECT id, name, description, category, publisher_verification_status, api_active "
    "FROM catalog_datasets"
    + " WHERE id = ANY(:dataset_ids)"
)
_SELECT_ALL_DATASETS = text(
    "SELECT id, name, description, category, publisher_verification_status, api_active "
    "FROM catalog_datasets"
)
_SELECT_COLUMNS = text(
    "SELECT id, field_name, display_name, description FROM catalog_columns "
    "WHERE dataset_id = :dataset_id"
)
_UPDATE_DATASET = text(
    "UPDATE catalog_datasets "
    "SET pii_risk_level = :pii_risk_level, eligibility_status = :eligibility_status, "
    "eligibility_reasons = CAST(:eligibility_reasons AS jsonb) "
    "WHERE id = :id"
)
_UPDATE_COLUMN = text(
    "UPDATE catalog_columns "
    "SET pii_risk_level = :pii_risk_level, eligibility_status = :eligibility_status, "
    "eligibility_reasons = CAST(:eligibility_reasons AS jsonb) "
    "WHERE id = :id"
)


async def recompute(engine: AsyncEngine, dataset_ids: list[str] | None) -> dict[str, int]:
    fixture = load_pii_patterns()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    counts = {"datasets": 0, "columns": 0, "became_eligible": 0}

    async with session_factory() as session:
        if dataset_ids:
            rows = (
                await session.execute(_SELECT_DATASETS, {"dataset_ids": dataset_ids})
            ).mappings().all()
        else:
            rows = (await session.execute(_SELECT_ALL_DATASETS)).mappings().all()
        datasets = list(rows)

    for dataset in datasets:
        async with session_factory() as session, session.begin():
            column_rows = (
                await session.execute(_SELECT_COLUMNS, {"dataset_id": dataset["id"]})
            ).mappings().all()

            column_classifications: list[ColumnPiiClassification] = []
            per_column_updates = []
            for column in column_rows:
                classification = classify_column(
                    column["field_name"], column["display_name"], column["description"], fixture
                )
                column_classifications.append(classification)
                per_column_updates.append((column["id"], classification))

            dataset_pii = classify_dataset(
                column_classifications,
                dataset["name"],
                dataset["description"],
                dataset["category"],
                fixture,
            )
            dataset_eligibility = compute_dataset_eligibility(
                publisher_status=dataset["publisher_verification_status"],
                pii_risk_level=dataset_pii.risk_level,
                api_active=dataset["api_active"],
            )
            inherited_reasons = [
                reason
                for reason in dataset_eligibility.eligibility_reasons
                if reason in _INHERITED_COLUMN_REASONS
            ]

            previous_status_result = await session.execute(
                text("SELECT eligibility_status FROM catalog_datasets WHERE id = :id"),
                {"id": dataset["id"]},
            )
            previous_status = previous_status_result.scalar_one()

            await session.execute(
                _UPDATE_DATASET,
                {
                    "id": dataset["id"],
                    "pii_risk_level": dataset_pii.risk_level,
                    "eligibility_status": dataset_eligibility.eligibility_status,
                    "eligibility_reasons": _to_json(dataset_eligibility.eligibility_reasons),
                },
            )
            for column_id, classification in per_column_updates:
                column_eligibility = compute_column_eligibility(
                    inherited_reasons, classification.risk_level
                )
                await session.execute(
                    _UPDATE_COLUMN,
                    {
                        "id": column_id,
                        "pii_risk_level": classification.risk_level,
                        "eligibility_status": column_eligibility.eligibility_status,
                        "eligibility_reasons": _to_json(column_eligibility.eligibility_reasons),
                    },
                )

            counts["datasets"] += 1
            counts["columns"] += len(per_column_updates)
            became_eligible = (
                previous_status != "eligible"
                and dataset_eligibility.eligibility_status == "eligible"
            )
            if became_eligible:
                counts["became_eligible"] += 1

    return counts


def _to_json(reasons: list[str]) -> str:
    return json.dumps(reasons)


async def _main(dataset_ids: list[str] | None) -> None:
    settings = get_settings()
    engine = create_app_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
    try:
        counts = await recompute(engine, dataset_ids)
    finally:
        await engine.dispose()
    print(
        f"Datasets procesados: {counts['datasets']} | columnas: {counts['columns']} | "
        f"pasaron a eligible: {counts['became_eligible']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-id",
        dest="dataset_ids",
        action="append",
        default=None,
        help="Limita el recalculo a estos dataset_id (repetible); sin este flag procesa "
        "todo el catalogo.",
    )
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.run(_main(args.dataset_ids), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_main(args.dataset_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
