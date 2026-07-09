"""Integracion T-202: upsert idempotente y busqueda trigram contra Postgres real.

Criterio de aceptacion (tasks.md T-202): buscar "carmen viboral" con
trigram debe devolver el codigo `05148`. El conteo real (>= 1.100
municipios) se verifica ejecutando `scripts/load_divipola.py` contra el
dataset real (ver quickstart.md §3); esta prueba usa filas sinteticas para
no depender de red.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import normalize_database_url_for_sqlalchemy
from app.db.divipola import rows_to_entries, upsert_divipola_entries

pytestmark = pytest.mark.integration

_SYNTHETIC_ROWS = [
    {
        "cod_dpto": "05",
        "dpto": "ANTIOQUIA",
        "cod_mpio": "05148",
        "nom_mpio": "EL CARMEN DE VIBORAL",
        "tipo_municipio": "Municipio",
    },
    {
        "cod_dpto": "05",
        "dpto": "ANTIOQUIA",
        "cod_mpio": "05001",
        "nom_mpio": "MEDELLÍN",
        "tipo_municipio": "Municipio",
    },
    {
        "cod_dpto": "11",
        "dpto": "BOGOTÁ, D.C.",
        "cod_mpio": "11001",
        "nom_mpio": "BOGOTÁ, D.C.",
        "tipo_municipio": "Municipio",
    },
]


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_divipola(engine):
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM divipola_entries"))


async def test_upsert_creates_departments_and_municipalities(engine, clean_divipola) -> None:
    entries = rows_to_entries(_SYNTHETIC_ROWS)

    summary = await upsert_divipola_entries(engine, entries)

    assert summary.entries_created == len(entries)
    assert summary.entries_updated == 0

    async with engine.connect() as connection:
        counts = (
            await connection.execute(
                text("SELECT level, count(*) FROM divipola_entries GROUP BY level")
            )
        ).all()
    counts_by_level = {row.level: row.count for row in counts}
    assert counts_by_level["municipality"] == 3
    assert counts_by_level["department"] == 2


async def test_upsert_is_idempotent(engine, clean_divipola) -> None:
    entries = rows_to_entries(_SYNTHETIC_ROWS)
    await upsert_divipola_entries(engine, entries)

    summary_again = await upsert_divipola_entries(engine, entries)

    assert summary_again.entries_created == 0
    assert summary_again.entries_updated == len(entries)

    async with engine.connect() as connection:
        total = (
            await connection.execute(text("SELECT count(*) FROM divipola_entries"))
        ).scalar_one()
    assert total == len(entries)


async def test_trigram_search_carmen_viboral_returns_05148(engine, clean_divipola) -> None:
    entries = rows_to_entries(_SYNTHETIC_ROWS)
    await upsert_divipola_entries(engine, entries)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT code FROM divipola_entries "
                    "WHERE level = 'municipality' AND name_normalized % :query "
                    "ORDER BY similarity(name_normalized, :query) DESC "
                    "LIMIT 1"
                ),
                {"query": "CARMEN VIBORAL"},
            )
        ).one()

    assert row.code == "05148"
