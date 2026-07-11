"""Integracion T-302/T-303: `explorar_valores` (T4) contra Socrata real.

Hallazgo T-303 (2026-07-10): `explorar_valores` construia `LIKE ... ESCAPE
'\\'`, sintaxis SQL estandar que SoQL NO soporta (`400
query.compiler.malformed`); las pruebas con mocks (respx) nunca lo
detectaron porque no validan la gramatica real de Socrata. pruebas.md §2.3
exige "explorar_valores reales" precisamente para detectar esta clase de
drift/incompatibilidad; este archivo cierra ese hueco de cobertura.

Hallazgo T-402 (2026-07-11): T4 ahora valida `catalog_columns.data_type`
antes de llamar a Socrata (solo texto); estas pruebas siembran una fila real
minima en Postgres para `ji8i-4anb`/`departamento` porque `explorar_valores`
ya no funciona sin `engine`.
"""

import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import normalize_database_url_for_sqlalchemy
from app.db.models import CatalogColumn, CatalogDataset
from app.tools.explorar_valores import explorar_valores
from app.tools.soda_client import SOCRATA_RESOURCE_BASE_URL

pytestmark = pytest.mark.integration

_DATASET_ID = "ji8i-4anb"


@pytest.fixture
async def engine():
    engine = create_async_engine(
        normalize_database_url_for_sqlalchemy(os.environ["DATABASE_URL"]), pool_pre_ping=True
    )
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def seed_departamento_column(engine):
    async def clean():
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM catalog_datasets WHERE id = :id"), {"id": _DATASET_ID}
            )

    await clean()
    now = datetime.now(UTC)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add(
            CatalogDataset(
                id=_DATASET_ID,
                name="Dataset de verificacion T4 en vivo",
                publisher="Agencia estatal",
                publisher_verification_status="verified",
                metadata_synced_at=now,
                data_updated_at=now,
                api_active=True,
                pii_risk_level="low",
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
        await session.flush()
        session.add(
            CatalogColumn(
                id=uuid.uuid4(),
                dataset_id=_DATASET_ID,
                field_name="departamento",
                data_type="Text",
                sample_values=[],
                pii_risk_level="low",
                contains_personal_data=False,
                eligibility_status="eligible",
                eligibility_reasons=[],
            )
        )
    yield
    await clean()


async def test_explorar_valores_finds_known_value_against_real_socrata(engine) -> None:
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as http_client:
        result = await explorar_valores(
            {"dataset_id": _DATASET_ID, "columna": "departamento", "termino_busqueda": "Antioquia"},
            engine=engine,
            http_client=http_client,
            app_token=app_token,
        )

    assert result["ok"] is True
    assert "Antioquia" in result["values"]


async def test_explorar_valores_no_match_returns_empty_not_error(engine) -> None:
    """El termino de busqueda no debe tratarse como patron LIKE: buscar algo
    que no exista no debe fallar por sintaxis (regresion del bug ESCAPE)."""
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    async with httpx.AsyncClient(base_url=SOCRATA_RESOURCE_BASE_URL) as http_client:
        result = await explorar_valores(
            {
                "dataset_id": _DATASET_ID,
                "columna": "departamento",
                "termino_busqueda": "ZonaQueNoExiste123",
            },
            engine=engine,
            http_client=http_client,
            app_token=app_token,
        )

    assert result == {"ok": True, "values": [], "truncated": False}
