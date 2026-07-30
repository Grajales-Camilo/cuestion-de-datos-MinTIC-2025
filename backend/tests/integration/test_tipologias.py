"""Integracion T-207: upsert idempotente de `territorio_tipologia` contra
Postgres real, incluyendo el salto explicito de codigos DIVIPOLA
desconocidos (FK a `divipola_entries`, ver tasks.md T-207).
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import normalize_database_url_for_sqlalchemy
from app.db.divipola import rows_to_entries as divipola_rows_to_entries
from app.db.divipola import upsert_divipola_entries
from app.db.tipologias import (
    TerritorioTipologiaData,
    upsert_territorio_tipologia,
)

pytestmark = pytest.mark.integration

_DIVIPOLA_ROWS = [
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
]


def _entry(code: str, level: str, tipologia: str) -> TerritorioTipologiaData:
    return TerritorioTipologiaData(
        divipola_code=code,
        level=level,
        tipologia_dnp=tipologia,
        categoria_ley_617="ESP",
        poblacion=100,
        ingresos_totales_cop=1000.0,
        vigencia=2026,
        fuente_archivo="test.xlsx",
    )


@pytest.fixture
async def engine(isolated_database_url):
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def seeded_divipola(engine):
    await upsert_divipola_entries(engine, divipola_rows_to_entries(_DIVIPOLA_ROWS))
    yield


async def test_upsert_creates_rows_for_known_divipola_codes(engine, seeded_divipola) -> None:
    entries = [_entry("05148", "municipality", "5"), _entry("05", "department", "1")]

    summary = await upsert_territorio_tipologia(engine, entries)

    assert summary.entries_created == 2
    assert summary.entries_updated == 0
    assert summary.skipped_missing_divipola == []

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT divipola_code, tipologia_dnp FROM territorio_tipologia "
                    "ORDER BY divipola_code"
                )
            )
        ).all()
    assert [(row.divipola_code, row.tipologia_dnp) for row in rows] == [
        ("05", "1"),
        ("05148", "5"),
    ]


async def test_upsert_skips_and_reports_unknown_divipola_code(engine, seeded_divipola) -> None:
    entries = [_entry("05148", "municipality", "5"), _entry("99999", "municipality", "3")]

    summary = await upsert_territorio_tipologia(engine, entries)

    assert summary.entries_created == 1
    assert summary.skipped_missing_divipola == ["99999"]

    async with engine.connect() as connection:
        total = (
            await connection.execute(text("SELECT count(*) FROM territorio_tipologia"))
        ).scalar_one()
    assert total == 1


async def test_upsert_is_idempotent_and_updates_on_rerun(engine, seeded_divipola) -> None:
    first = [_entry("05148", "municipality", "5")]
    await upsert_territorio_tipologia(engine, first)

    second = [_entry("05148", "municipality", "4")]
    summary = await upsert_territorio_tipologia(engine, second)

    assert summary.entries_created == 0
    assert summary.entries_updated == 1

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT tipologia_dnp FROM territorio_tipologia WHERE divipola_code = '05148'")
            )
        ).one()
        total = (
            await connection.execute(text("SELECT count(*) FROM territorio_tipologia"))
        ).scalar_one()
    assert row.tipologia_dnp == "4"
    assert total == 1
