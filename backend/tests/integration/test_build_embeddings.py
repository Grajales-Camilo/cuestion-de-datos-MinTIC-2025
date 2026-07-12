import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.catalog.embeddings import (
    EMBEDDING_DIMENSION,
    EXPECTED_EMBEDDING_MODEL,
    build_catalog_embeddings,
)
from app.config import normalize_database_url_for_sqlalchemy
from app.db.engine import create_app_async_engine
from tests.integration._snapshot import backup_tables, restore_tables

pytestmark = pytest.mark.integration


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def aembed_documents(
        self,
        texts: list[str],
        *,
        batch_size: int = 100,
        task_type: str | None = None,
        output_dimensionality: int | None = None,
    ) -> list[list[float]]:
        assert task_type == "RETRIEVAL_DOCUMENT"
        assert output_dimensionality == EMBEDDING_DIMENSION
        assert batch_size <= 100
        self.calls.append(texts)
        return [[float(index + 1)] * EMBEDDING_DIMENSION for index, _ in enumerate(texts)]


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


async def _seed_dataset(connection, dataset_id: str, *, active: bool = True) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO catalog_datasets (
                id, name, description, publisher, category, metadata_synced_at,
                api_active, publisher_verification_status, pii_risk_level,
                eligibility_status, eligibility_reasons
            )
            VALUES (
                :id, :name, :description, :publisher, :category, :metadata_synced_at,
                :api_active, 'verified', 'low', 'eligible', '[]'::jsonb
            )
            """
        ),
        {
            "id": dataset_id,
            "name": f"Dataset {dataset_id}",
            "description": "Descripcion suficientemente larga para el texto de embeddings.",
            "publisher": "Entidad Oficial",
            "category": "Educacion",
            "metadata_synced_at": datetime.now(UTC),
            "api_active": active,
        },
    )
    for field_name in ["z_columna", "a_columna"]:
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


async def test_build_catalog_embeddings_upserts_active_datasets(
    engine, clean_catalog
) -> None:
    async with engine.begin() as connection:
        await _seed_dataset(connection, "aaaa-0001")
        await _seed_dataset(connection, "aaaa-0002")
        await _seed_dataset(connection, "aaaa-0003", active=False)

    client = FakeEmbeddingClient()
    summary = await build_catalog_embeddings(
        engine,
        embedding_client=client,
        model=EXPECTED_EMBEDDING_MODEL,
        batch_size=1,
    )

    assert summary.active_datasets == 2
    assert summary.selected_datasets == 2
    assert summary.embeddings_upserted == 2
    assert len(client.calls) == 2

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT d.id, d.embedding_text, e.model, vector_dims(e.embedding) AS dims
                    FROM catalog_datasets d
                    LEFT JOIN catalog_embeddings e ON e.dataset_id = d.id
                    ORDER BY d.id
                    """
                )
            )
        ).all()

    by_id = {row.id: row for row in rows}
    assert by_id["aaaa-0001"].model == EXPECTED_EMBEDDING_MODEL
    assert by_id["aaaa-0001"].dims == EMBEDDING_DIMENSION
    assert "Columnas: a_columna, z_columna" in by_id["aaaa-0001"].embedding_text
    assert by_id["aaaa-0003"].model is None


async def test_build_catalog_embeddings_is_idempotent(engine, clean_catalog) -> None:
    async with engine.begin() as connection:
        await _seed_dataset(connection, "aaaa-0001")

    first = await build_catalog_embeddings(
        engine,
        embedding_client=FakeEmbeddingClient(),
        model=EXPECTED_EMBEDDING_MODEL,
    )
    second = await build_catalog_embeddings(
        engine,
        embedding_client=FakeEmbeddingClient(),
        model=EXPECTED_EMBEDDING_MODEL,
    )

    assert first.embeddings_upserted == 1
    assert second.embeddings_upserted == 1
    async with engine.connect() as connection:
        count = (
            await connection.execute(text("SELECT count(*) FROM catalog_embeddings"))
        ).scalar_one()
    assert count == 1


async def test_build_catalog_embeddings_rejects_mixed_models(engine, clean_catalog) -> None:
    async with engine.begin() as connection:
        await _seed_dataset(connection, "aaaa-0001")
        await connection.execute(
            text(
                """
                INSERT INTO catalog_embeddings (dataset_id, embedding, model)
                VALUES ('aaaa-0001', :embedding, 'modelo-anterior')
                """
            ),
            {"embedding": [0.0] * EMBEDDING_DIMENSION},
        )

    with pytest.raises(ValueError, match="otro modelo"):
        await build_catalog_embeddings(
            engine,
            embedding_client=FakeEmbeddingClient(),
            model=EXPECTED_EMBEDDING_MODEL,
        )
