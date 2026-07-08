"""Integracion T-201: ingesta de catalogo contra Postgres real (Discovery API mockeada)."""

import os
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.catalog.ingest import run_ingest
from app.config import Settings, normalize_database_url_for_sqlalchemy

pytestmark = pytest.mark.integration

DISCOVERY_URL = "https://api.us.socrata.com/api/catalog/v1"


def _item(dataset_id: str, name: str, owner: str, field_names: list[str]) -> dict:
    return {
        "resource": {
            "id": dataset_id,
            "name": name,
            "description": "Descripcion de prueba de integracion suficientemente larga " * 3,
            "type": "dataset",
            "data_updated_at": "2026-01-15T00:00:00.000Z",
            "columns_name": field_names,
            "columns_field_name": field_names,
            "columns_datatype": ["Text"] * len(field_names),
            "columns_description": [""] * len(field_names),
        },
        "classification": {"domain_category": "Prueba"},
        "owner": {"display_name": owner},
    }


def _page(items: list[dict]) -> dict:
    return {"results": items, "resultSetSize": len(items)}


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
        SOCRATA_APP_TOKEN="token-test",
        RETENTION_HASH_SALT="test-salt-at-least-32-bytes-long!",
    )


def _mock_single_page(items: list[dict]) -> None:
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=_page(items)))


@respx.mock
async def test_run_ingest_creates_datasets(engine, clean_catalog, settings) -> None:
    _mock_single_page(
        [
            _item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno", "campo_dos"]),
            _item("aaaa-0002", "Dataset B", "Entidad B", ["campo_tres"]),
        ]
    )

    summary = await run_ingest(engine, settings, trigger="manual")

    assert summary.datasets_new == 2
    assert summary.datasets_updated == 0
    assert summary.datasets_failed == 0

    async with engine.connect() as connection:
        count = (
            await connection.execute(text("SELECT count(*) FROM catalog_datasets"))
        ).scalar_one()
        assert count == 2
        run_row = (
            await connection.execute(
                text(
                    "SELECT trigger, datasets_new, datasets_updated, finished_at "
                    "FROM ingest_runs WHERE id = :id"
                ),
                {"id": summary.ingest_run_id},
            )
        ).one()
        assert run_row.trigger == "manual"
        assert run_row.datasets_new == 2
        assert run_row.finished_at is not None


@respx.mock
async def test_run_ingest_is_idempotent(engine, clean_catalog, settings) -> None:
    items = [_item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno"])]
    _mock_single_page(items)

    first = await run_ingest(engine, settings, trigger="manual")
    respx.routes.clear()
    _mock_single_page(items)
    second = await run_ingest(engine, settings, trigger="manual")

    assert first.datasets_new == 1
    assert second.datasets_new == 0
    assert second.datasets_updated == 1

    async with engine.connect() as connection:
        count = (
            await connection.execute(text("SELECT count(*) FROM catalog_datasets"))
        ).scalar_one()
        assert count == 1


@respx.mock
async def test_api_active_reconciled_on_full_run(engine, clean_catalog, settings) -> None:
    _mock_single_page(
        [
            _item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno"]),
            _item("aaaa-0002", "Dataset B", "Entidad B", ["campo_uno"]),
        ]
    )
    await run_ingest(engine, settings, trigger="manual")

    respx.routes.clear()
    _mock_single_page([_item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno"])])
    await run_ingest(engine, settings, trigger="manual", limit=None)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(text("SELECT id, api_active FROM catalog_datasets"))
        ).all()
    active_by_id = {row.id: row.api_active for row in rows}
    assert active_by_id["aaaa-0001"] is True
    assert active_by_id["aaaa-0002"] is False


@respx.mock
async def test_api_active_not_reconciled_with_limit(engine, clean_catalog, settings) -> None:
    _mock_single_page(
        [
            _item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno"]),
            _item("aaaa-0002", "Dataset B", "Entidad B", ["campo_uno"]),
        ]
    )
    await run_ingest(engine, settings, trigger="manual")

    respx.routes.clear()
    _mock_single_page([_item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno"])])
    await run_ingest(engine, settings, trigger="manual", limit=1)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(text("SELECT id, api_active FROM catalog_datasets"))
        ).all()
    active_by_id = {row.id: row.api_active for row in rows}
    assert active_by_id["aaaa-0001"] is True
    assert active_by_id["aaaa-0002"] is True


@respx.mock
async def test_manual_pii_review_is_preserved_across_reingest(
    engine, clean_catalog, settings
) -> None:
    _mock_single_page([_item("aaaa-0001", "Nombre Original", "Entidad A", ["campo_uno"])])
    await run_ingest(engine, settings, trigger="manual")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE catalog_datasets SET pii_risk_level = 'low', "
                "eligibility_status = 'eligible', eligibility_reasons = '[]'::jsonb, "
                "pii_reviewed_by = 'analista_prueba', pii_reviewed_at = :now, "
                "pii_review_source = 'revision manual de prueba' "
                "WHERE id = 'aaaa-0001'"
            ),
            {"now": datetime.now(UTC)},
        )

    respx.routes.clear()
    _mock_single_page([_item("aaaa-0001", "Nombre Actualizado", "Entidad A", ["campo_uno"])])
    await run_ingest(engine, settings, trigger="manual")

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT name, pii_risk_level, eligibility_status, eligibility_reasons "
                    "FROM catalog_datasets WHERE id = 'aaaa-0001'"
                )
            )
        ).one()

    assert row.name == "Nombre Actualizado"
    assert row.pii_risk_level == "low"
    assert row.eligibility_status == "eligible"
    assert row.eligibility_reasons == []


@respx.mock
async def test_malformed_record_does_not_abort_the_run(engine, clean_catalog, settings) -> None:
    malformed = _item("aaaa-0003", "Dataset con columnas duplicadas", "Entidad C", ["dup", "dup"])

    _mock_single_page(
        [
            _item("aaaa-0001", "Dataset A", "Entidad A", ["campo_uno"]),
            malformed,
            _item("aaaa-0002", "Dataset B", "Entidad B", ["campo_uno"]),
        ]
    )

    summary = await run_ingest(engine, settings, trigger="manual")

    assert summary.datasets_new == 2
    assert summary.datasets_failed == 1
    assert len(summary.error_summary) == 1
    assert summary.error_summary[0]["dataset_id"] == "aaaa-0003"

    async with engine.connect() as connection:
        ids = (
            await connection.execute(text("SELECT id FROM catalog_datasets ORDER BY id"))
        ).scalars().all()
    assert ids == ["aaaa-0001", "aaaa-0002"]
