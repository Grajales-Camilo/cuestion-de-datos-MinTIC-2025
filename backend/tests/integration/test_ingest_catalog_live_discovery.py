"""Integracion T-201: una pagina real de la Discovery API produce registros validos.

pruebas.md §2.3, literal: "Discovery API: una pagina de ingesta real produce
registros validos." Deliberadamente pequeña (page_size=5) para no depender
de volumen ni tardar.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.catalog.ingest import run_ingest
from app.config import Settings, normalize_database_url_for_sqlalchemy

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_catalog(engine):
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM catalog_columns"))
        await connection.execute(text("DELETE FROM catalog_datasets"))
        await connection.execute(text("DELETE FROM ingest_runs"))


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DATABASE_URL=os.environ["DATABASE_URL"],
        SOCRATA_APP_TOKEN=os.environ.get("SOCRATA_APP_TOKEN"),
        RETENTION_HASH_SALT="test-salt-at-least-32-bytes-long!",
    )


async def test_one_real_discovery_page_produces_valid_rows(engine, clean_catalog, settings) -> None:
    summary = await run_ingest(engine, settings, trigger="manual", limit=5, page_size=5)

    assert summary.datasets_failed == 0
    assert (summary.datasets_new + summary.datasets_updated) > 0

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT id, name, metadata_synced_at, eligibility_status, pii_risk_level "
                    "FROM catalog_datasets LIMIT 1"
                )
            )
        ).one()

    assert row.id
    assert row.name
    assert row.metadata_synced_at is not None
    assert row.eligibility_status in ("eligible", "diagnostic_only", "blocked")
    assert row.pii_risk_level in ("low", "medium", "high", "unknown")
