"""Integracion T-302 (T3 `resolver_geografia`): consulta trigram + alt_names
real contra Postgres (contracts/agent-tools.md §T3, pruebas.md §2.1).
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import normalize_database_url_for_sqlalchemy
from app.db.divipola import rows_to_entries, upsert_divipola_entries
from app.tools.resolver_geografia import resolver_geografia

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
async def seeded_divipola(engine):
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM divipola_entries"))
    await upsert_divipola_entries(engine, rows_to_entries(_SYNTHETIC_ROWS))


@pytest.mark.parametrize("termino", ["Bogotá", "bogota", "Bogotá D.C.", "Santafé de Bogotá"])
async def test_bogota_variants_resolve_to_11001(engine, seeded_divipola, termino: str) -> None:
    result = await resolver_geografia({"termino": termino}, engine=engine)

    assert result["ok"] is True
    assert any(match["code"] == "11001" for match in result["matches"])


async def test_carmen_de_viboral_resolves_to_05148(engine, seeded_divipola) -> None:
    result = await resolver_geografia({"termino": "Carmen de Viboral"}, engine=engine)

    assert result["ok"] is True
    assert result["matches"][0]["code"] == "05148"
    assert result["matches"][0]["like_pattern"] == "%_L C_RM_N D_ V_B_R_L%"
