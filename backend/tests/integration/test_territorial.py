"""Integracion T-404 (T8 `comparabilidad_territorial`): consulta real de
`territorio_tipologia` contra Postgres (contracts/agent-tools.md §T8).
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import normalize_database_url_for_sqlalchemy
from app.db.divipola import rows_to_entries as divipola_rows_to_entries
from app.db.divipola import upsert_divipola_entries
from app.db.tipologias import TerritorioTipologiaData, upsert_territorio_tipologia
from app.quality.territorial import comparabilidad_territorial

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
        "cod_dpto": "11",
        "dpto": "BOGOTÁ, D.C.",
        "cod_mpio": "11001",
        "nom_mpio": "BOGOTÁ, D.C.",
        "tipo_municipio": "Municipio",
    },
]


def _tipologia(code: str, level: str, tipologia: str, categoria: str) -> TerritorioTipologiaData:
    return TerritorioTipologiaData(
        divipola_code=code,
        level=level,
        tipologia_dnp=tipologia,
        categoria_ley_617=categoria,
        poblacion=100,
        ingresos_totales_cop=1000.0,
        vigencia=2026,
        fuente_archivo="test.xlsx",
    )


@pytest.fixture
async def engine():
    database_url = normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"])
    engine = create_async_engine(database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def seeded(engine):
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM territorio_tipologia"))
        await connection.execute(text("DELETE FROM divipola_entries"))
    await upsert_divipola_entries(engine, divipola_rows_to_entries(_DIVIPOLA_ROWS))
    await upsert_territorio_tipologia(
        engine,
        [
            _tipologia("11001", "municipality", "Bogotá", "ESP"),
            _tipologia("05148", "municipality", "5", "6"),
        ],
    )
    yield
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM territorio_tipologia"))


async def test_flags_tipologia_gap_for_real_seeded_territories(engine, seeded) -> None:
    result = await comparabilidad_territorial(["11001", "05148"], engine=engine)

    assert result["ok"] is True
    assert result["comparable"] is False
    assert result["reasons"] == ["tipologia_gap"]
    codes = {t["divipola_code"] for t in result["territorios"]}
    assert codes == {"11001", "05148"}
    for territorio in result["territorios"]:
        assert "poblacion" not in territorio
        assert "ingresos_totales_cop" not in territorio


async def test_missing_territorio_tipologia_row_yields_null_comparable(engine, seeded) -> None:
    result = await comparabilidad_territorial(["11001", "99999"], engine=engine)

    assert result["comparable"] is None
    assert result["reasons"] == ["sin_tipologia"]
    missing = next(t for t in result["territorios"] if t["divipola_code"] == "99999")
    assert missing["tipologia_dnp"] is None
