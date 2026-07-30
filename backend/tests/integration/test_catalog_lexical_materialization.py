"""T-614R2: RF-301/RF-302/RF-304/RNF-010 lexical materialization."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.catalog.upsert import ColumnUpsertData, DatasetUpsertData, upsert_dataset
from app.config import normalize_database_url_for_sqlalchemy
from app.db.engine import create_app_async_engine

pytestmark = pytest.mark.integration

DATASET_ID = "r2lx-0001"


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM catalog_datasets WHERE id = :dataset_id"),
            {"dataset_id": DATASET_ID},
        )
    yield engine
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM catalog_datasets WHERE id = :dataset_id"),
            {"dataset_id": DATASET_ID},
        )
    await engine.dispose()


async def _insert_dataset(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO catalog_datasets (
                    id, name, description, publisher, category, metadata_synced_at,
                    embedding_text
                )
                VALUES (
                    :id, 'Nombre Alfa', 'Descripcion Beta', 'Publicador Gamma',
                    'Categoria Delta', now(), 'Embedding Epsilon'
                )
                """
            ),
            {"id": DATASET_ID},
        )
        await connection.execute(
            text(
                """
                INSERT INTO catalog_columns (
                    id, dataset_id, field_name, display_name, data_type, description
                )
                VALUES (
                    :id, :dataset_id, 'campo_zeta', 'Visible Eta', 'text',
                    'Descripcion Theta'
                )
                """
            ),
            {"id": str(uuid.uuid4()), "dataset_id": DATASET_ID},
        )


async def _matches(engine, tsquery: str) -> bool:
    async with engine.connect() as connection:
        return bool(
            (
                await connection.execute(
                    text(
                        """
                        SELECT lexical_search_vector @@ to_tsquery('spanish', :tsquery)
                        FROM catalog_datasets
                        WHERE id = :dataset_id
                        """
                    ),
                    {"dataset_id": DATASET_ID, "tsquery": tsquery},
                )
            ).scalar_one()
        )


async def test_vector_contains_all_dataset_and_column_fields(engine) -> None:
    await _insert_dataset(engine)

    assert await _matches(
        engine,
        "alfa & beta & gamma & delta & epsilon & zeta & eta & theta",
    )
    async with engine.connect() as connection:
        exact_rank = (
            await connection.execute(
                text(
                    """
                    SELECT lexical_rank_vector = to_tsvector(
                        'spanish',
                        concat_ws(
                            ' ',
                            name,
                            publisher,
                            category,
                            description,
                            'campo_zeta Visible Eta Descripcion Theta'
                        )
                    )
                    FROM catalog_datasets
                    WHERE id = :dataset_id
                    """
                ),
                {"dataset_id": DATASET_ID},
            )
        ).scalar_one()

    assert exact_rank is True


async def test_dataset_and_column_mutations_refresh_vector(engine) -> None:
    await _insert_dataset(engine)

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE catalog_datasets
                SET name = 'Nombre Iota',
                    description = 'Descripcion Kappa',
                    publisher = 'Publicador Lambda'
                WHERE id = :dataset_id
                """
            ),
            {"dataset_id": DATASET_ID},
        )
        await connection.execute(
            text(
                """
                UPDATE catalog_columns
                SET field_name = 'campo_mu',
                    display_name = 'Visible Nu',
                    description = 'Descripcion Xi'
                WHERE dataset_id = :dataset_id
                """
            ),
            {"dataset_id": DATASET_ID},
        )

    assert await _matches(engine, "iota & kappa & lambda & mu & nu & xi")

    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM catalog_columns WHERE dataset_id = :dataset_id"),
            {"dataset_id": DATASET_ID},
        )

    assert not await _matches(engine, "mu | nu | xi")


async def test_backfill_expression_is_idempotent(engine) -> None:
    await _insert_dataset(engine)
    backfill = text(
        """
        UPDATE catalog_datasets d
        SET lexical_search_vector = build_catalog_lexical_search_vector(
            d.name,
            d.description,
            d.publisher,
            d.category,
            d.embedding_text,
            COALESCE(
                (
                    SELECT string_agg(
                        concat_ws(' ', c.field_name, c.display_name, c.description),
                        ' ' ORDER BY c.field_name
                    )
                    FROM catalog_columns c
                    WHERE c.dataset_id = d.id
                ),
                ''
            )
        )
        WHERE d.id = :dataset_id
        RETURNING lexical_search_vector::text
        """
    )
    async with engine.begin() as connection:
        first = (
            await connection.execute(backfill, {"dataset_id": DATASET_ID})
        ).scalar_one()
        second = (
            await connection.execute(backfill, {"dataset_id": DATASET_ID})
        ).scalar_one()

    assert first == second


async def test_ingest_upsert_maintains_vector(engine) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    data = DatasetUpsertData(
        id=DATASET_ID,
        name="Ingesta Omicron",
        description="Descripcion Pi",
        publisher_text="Publicador Rho",
        official_publisher_id=None,
        publisher_verification_status="unknown",
        category="Categoria Sigma",
        data_updated_at=None,
        metadata_synced_at=datetime.now(UTC),
        embedding_text="Embedding Tau",
        pii_risk_level="low",
        eligibility_status="diagnostic_only",
        eligibility_reasons=["publisher_unknown"],
        columns=[
            ColumnUpsertData(
                field_name="campo_upsilon",
                display_name="Visible Phi",
                data_type="text",
                description="Descripcion Chi",
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        ],
    )

    async with session_factory.begin() as session:
        assert await upsert_dataset(session, data) == "created"
    async with session_factory.begin() as session:
        assert await upsert_dataset(session, data) == "updated"

    assert await _matches(
        engine,
        "omicron & pi & rho & sigma & tau & upsilon & phi & chi",
    )


async def test_gin_index_exists_and_is_usable(engine) -> None:
    async with engine.connect() as connection:
        index_definition = (
            await connection.execute(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'catalog_datasets'
                      AND indexname = 'ix_catalog_datasets_lexical_search_vector_gin'
                    """
                )
            )
        ).scalar_one()
        async with connection.begin_nested():
            await connection.execute(text("SET LOCAL enable_seqscan = off"))
            plan = (
                await connection.execute(
                    text(
                        """
                        EXPLAIN (FORMAT TEXT)
                        SELECT id
                        FROM catalog_datasets
                        WHERE lexical_search_vector @@
                              to_tsquery('spanish', 'acueducto:*')
                        """
                    )
                )
            ).scalars().all()

    assert "USING gin" in index_definition
    assert any("ix_catalog_datasets_lexical_search_vector_gin" in line for line in plan)
