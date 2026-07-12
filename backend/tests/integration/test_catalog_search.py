import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.catalog.embeddings import EMBEDDING_DIMENSION, EXPECTED_EMBEDDING_MODEL
from app.catalog.search import search_catalog
from app.config import normalize_database_url_for_sqlalchemy
from app.db.engine import create_app_async_engine
from tests.integration._snapshot import backup_tables, restore_tables

pytestmark = pytest.mark.integration


class FakeQueryEmbeddingClient:
    async def aembed_query(
        self,
        text: str,
        *,
        task_type: str | None = None,
        title: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[float]:
        assert text == "desercion escolar"
        assert task_type == "RETRIEVAL_QUERY"
        assert output_dimensionality == EMBEDDING_DIMENSION
        return [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_app_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_catalog(engine):
    tables = ("catalog_datasets", "catalog_columns", "catalog_embeddings")
    async with engine.begin() as connection:
        await backup_tables(connection, *tables)
        await connection.execute(text("DELETE FROM catalog_embeddings"))
        await connection.execute(text("DELETE FROM catalog_columns"))
        await connection.execute(text("DELETE FROM catalog_datasets"))
    yield
    async with engine.begin() as connection:
        await restore_tables(connection, *tables)


async def _seed_dataset(
    connection,
    dataset_id: str,
    *,
    name: str,
    embedding: list[float],
    active: bool = True,
    metadata_synced_at: datetime | None = None,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO catalog_datasets (
                id, name, description, publisher, official_publisher_id,
                publisher_verification_status, category, row_count, data_updated_at,
                latest_observed_cutoff_at, metadata_synced_at, api_active,
                pii_risk_level, eligibility_status, eligibility_reasons
            )
            VALUES (
                :id, :name, 'Descripcion', 'Ministerio de Educacion Nacional', NULL,
                'verified', 'Educacion', 123, '2026-03-15T00:00:00+00:00',
                NULL, :metadata_synced_at, :api_active, 'low', 'eligible', '[]'::jsonb
            )
            """
        ),
        {
            "id": dataset_id,
            "name": name,
            "metadata_synced_at": metadata_synced_at or datetime.now(UTC),
            "api_active": active,
        },
    )
    for field_name in ["z_columna", "a_columna", "m_columna"]:
        await connection.execute(
            text(
                """
                INSERT INTO catalog_columns (
                    id, dataset_id, field_name, data_type, pii_risk_level,
                    eligibility_status, eligibility_reasons
                )
                VALUES (
                    :id, :dataset_id, :field_name, 'text', 'low', 'eligible', '[]'::jsonb
                )
                """
            ),
            {"id": str(uuid.uuid4()), "dataset_id": dataset_id, "field_name": field_name},
        )
    await connection.execute(
        text(
            """
            INSERT INTO catalog_embeddings (dataset_id, embedding, model)
            VALUES (:dataset_id, :embedding, :model)
            """
        ),
        {"dataset_id": dataset_id, "embedding": embedding, "model": EXPECTED_EMBEDDING_MODEL},
    )


async def test_search_catalog_orders_by_cosine_similarity_and_excludes_inactive(
    engine, clean_catalog
) -> None:
    async with engine.begin() as connection:
        await _seed_dataset(
            connection,
            "aaaa-0001",
            name="Desercion escolar municipal",
            embedding=[1.0] + [0.0] * (EMBEDDING_DIMENSION - 1),
        )
        await _seed_dataset(
            connection,
            "aaaa-0002",
            name="Salud publica",
            embedding=[0.8, 0.2] + [0.0] * (EMBEDDING_DIMENSION - 2),
        )
        await _seed_dataset(
            connection,
            "aaaa-0003",
            name="Inactivo cercano",
            embedding=[1.0] + [0.0] * (EMBEDDING_DIMENSION - 1),
            active=False,
        )

    summary = await search_catalog(
        engine,
        embedding_client=FakeQueryEmbeddingClient(),
        query="  desercion escolar  ",
        k=10,
        stale_after_days=8,
    )

    assert summary.query == "desercion escolar"
    assert [item.dataset_id for item in summary.results] == ["aaaa-0001", "aaaa-0002"]
    assert summary.results[0].similarity > summary.results[1].similarity
    assert summary.results[0].columns_preview == ["a_columna", "m_columna", "z_columna"]


async def test_search_catalog_marks_stale_index(engine, clean_catalog) -> None:
    async with engine.begin() as connection:
        await _seed_dataset(
            connection,
            "aaaa-0001",
            name="Indice obsoleto",
            embedding=[1.0] + [0.0] * (EMBEDDING_DIMENSION - 1),
            metadata_synced_at=datetime.now(UTC) - timedelta(days=9),
        )

    summary = await search_catalog(
        engine,
        embedding_client=FakeQueryEmbeddingClient(),
        query="desercion escolar",
        stale_after_days=8,
    )

    assert summary.results[0].index_stale is True
