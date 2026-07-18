from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import normalize_database_url_for_sqlalchemy

_TEMP_DATABASE_PREFIX = "t615ir_"


def _url_with_database(database_url: str, database: str) -> str:
    return make_url(database_url).set(database=database).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
async def legacy_catalog_sentinel() -> AsyncIterator[tuple[str, str]]:
    """Fila ajena que debe sobrevivir todas las fixtures legacy aisladas."""

    shared_url = os.environ["DATABASE_URL"]
    sentinel_id = f"{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:4]}"
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(shared_url),
        pool_pre_ping=True,
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO catalog_datasets (
                    id, name, publisher, metadata_synced_at, api_active,
                    publisher_verification_status, pii_risk_level,
                    eligibility_status, eligibility_reasons
                )
                VALUES (
                    :id, 'Centinela ajeno T-615I-R', 'Fixture de aislamiento',
                    now(), false, 'unknown', 'unknown', 'blocked', '[]'::jsonb
                )
                """
            ),
            {"id": sentinel_id},
        )
    try:
        yield shared_url, sentinel_id
    finally:
        async with engine.begin() as connection:
            count = await connection.scalar(
                text("SELECT count(*) FROM catalog_datasets WHERE id = :id"),
                {"id": sentinel_id},
            )
            assert count == 1, "la fila centinela ajena no sobrevivió la suite"
            await connection.execute(
                text("DELETE FROM catalog_datasets WHERE id = :id"),
                {"id": sentinel_id},
            )
        await engine.dispose()


async def _assert_shared_sentinel(shared_url: str, sentinel_id: str) -> None:
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(shared_url),
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as connection:
            count = await connection.scalar(
                text("SELECT count(*) FROM catalog_datasets WHERE id = :id"),
                {"id": sentinel_id},
            )
        assert count == 1, "la fixture alteró datos ajenos de catalog_datasets"
    finally:
        await engine.dispose()


@pytest.fixture
async def isolated_database_url(
    monkeypatch: pytest.MonkeyPatch,
    legacy_catalog_sentinel: tuple[str, str],
) -> AsyncIterator[str]:
    """Base migrada y descartable para pruebas que controlan el catálogo."""

    shared_url, sentinel_id = legacy_catalog_sentinel
    await _assert_shared_sentinel(shared_url, sentinel_id)
    database_name = f"{_TEMP_DATABASE_PREFIX}{uuid.uuid4().hex}"
    admin_url = _url_with_database(shared_url, "postgres")
    admin_engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(admin_url),
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{database_name}" TEMPLATE template0'))

    test_url = _url_with_database(shared_url, database_name)
    try:
        test_engine = create_async_engine(
            normalize_database_url_for_sqlalchemy(test_url),
            isolation_level="AUTOCOMMIT",
        )
        async with test_engine.connect() as connection:
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await test_engine.dispose()

        migration_env = os.environ.copy()
        migration_env["DATABASE_URL"] = test_url
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            env=migration_env,
            check=True,
            capture_output=True,
            text=True,
        )
        monkeypatch.setenv("DATABASE_URL", test_url)
        yield test_url
    finally:
        async with admin_engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE "{database_name}"'))
        await admin_engine.dispose()
        await _assert_shared_sentinel(shared_url, sentinel_id)
